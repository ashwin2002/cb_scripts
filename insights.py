from argparse import ArgumentParser
from pprint import pprint
import sys
import hashlib

# import pandas as pd
import torch
from couchbase.exceptions import DocumentNotFoundException
from transformers import RobertaTokenizer, RobertaModel


from config.run_analyzer import run_analyzer_db_info as run_analyzer
from config.run_analyzer import error_db_info
from sdk_lib.sdk_conn import SDKClient


def parse_command_line_arguments(custom_args=None):
    parser = ArgumentParser(description="Paser for test logs")
    parser.add_argument("--component", dest="component",
                        help="Target component for which to parse the jobs")
    parser.add_argument("--subcomponent", dest="subcomponent",
                        help="If component not provided, then search for subcomponent regexp")
    parser.add_argument("--version", dest="version", required=True,
                        help="Version on which the job has run")
    parser.add_argument("--job_name", dest="job_name", default=None,
                        help="Target one job to analyze")
    parser.add_argument("--parse_last_run_only", dest="parse_last_run_only",
                        default=False, action="store_true",
                        help="Runs the script only on the last run of each subcomponent")
    return parser.parse_args(custom_args or sys.argv[1:])


def get_backtrace_embedding(backtrace):
    # Tokenize and encode the backtrace
    inputs = tokenizer(backtrace, return_tensors='pt', truncation=True,
                       padding=True, max_length=512)
    with torch.no_grad():
        # Pass through the CodeBERT model
        outputs = model(**inputs)

    # Use the [CLS] token's embedding as the representation of the backtrace
    embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
    return embedding


arguments = parse_command_line_arguments()

collection = f"`{run_analyzer['bucket_name']}`.`{run_analyzer['scope']}`.`{run_analyzer['collection']}`"
if arguments.component:
    query_str = f"SELECT * FROM {collection} " \
                f"WHERE cb_version='{arguments.version}'" \
                f" AND component='{arguments.component}'"
elif arguments.subcomponent:
    query_str = f"SELECT * FROM {collection} " \
                f"WHERE cb_version='{arguments.version}'" \
                f" AND subcomponent LIKE '%{arguments.subcomponent}%'"
else:
    parse_command_line_arguments(["--help"])

run_analyzer["sdk_client"] = SDKClient(
    run_analyzer["host"],
    run_analyzer["username"],
    run_analyzer["password"],
    run_analyzer["bucket_name"])
run_analyzer["sdk_client"].select_collection(
    run_analyzer["scope"], run_analyzer["collection"])

rows = run_analyzer["sdk_client"].cluster.query(query_str)

data = list()
for row in rows:
    if arguments.parse_last_run_only:
        run = row["run_analysis"]["runs"][0]
        if "commit_ref" not in run:
            continue
        if run["run_note"] != "PASS":
            data.append([
               row["run_analysis"]["component"],
               row["run_analysis"]["subcomponent"],
               run["branch"], run["commit_ref"],
               run["slave_label"], run["executor_name"],
               run["servers"], run["run_note"], run["job_id"], run["tests"]
            ])
    else:
        runs = row["run_analysis"]["runs"]
        subcomponent_jobs = list()
        test_passed = False
        for run in runs:
            if "commit_ref" not in run:
                continue
            data_entry = [
                row["run_analysis"]["component"],
                row["run_analysis"]["subcomponent"],
                run["branch"], run["commit_ref"],
                run["slave_label"], run["executor_name"],
                run["servers"], run["run_note"], run["job_id"], run["tests"]
            ]
            if run["run_note"] == "PASS":
                test_passed = True
                break
            subcomponent_jobs.append(data_entry)

        if not test_passed:
            data.extend(subcomponent_jobs)

run_analyzer["sdk_client"].close()

# data = pd.DataFrame(data,
#                     columns=["SubComponent", "Branch", "Commit",
#                              "Slave", "Executor", "Servers",
#                              "Comments", "JobId", "Tests"])

# Load CodeBERT model and tokenizer
tokenizer = RobertaTokenizer.from_pretrained('microsoft/codebert-base')
model = RobertaModel.from_pretrained('microsoft/codebert-base')

error_db_info["sdk_client"] = SDKClient(
    error_db_info["host"],
    error_db_info["username"],
    error_db_info["password"],
    error_db_info["bucket_name"])
error_db_info["sdk_client"].select_collection(
    error_db_info["scope"], error_db_info["collection"])

error_data = dict()
backtraces_hash_map = dict()

query_str = \
    f"SELECT * FROM " \
    f"`{error_db_info['bucket_name']}`.`{error_db_info['scope']}`.`{error_db_info['collection']}`" \
    f" WHERE vector_hash='%s'"
install_failed_jobs = list()
for run in data:
    for test_num, test in enumerate(run[9]):
        if run[8] == "installed_failed":
            install_failed_jobs.append(run[1])
            continue
        if 'backtrace' not in test:
            continue
        err_vector = get_backtrace_embedding(test["backtrace"])
        err_vector_pylist = err_vector.tolist()
        vector_hash = hashlib.sha256(err_vector.tobytes()).hexdigest()
        if vector_hash not in error_data:
            error_data[vector_hash] = list()
            backtraces_hash_map[vector_hash] = test["backtrace"]
        error_data[vector_hash].append({"component": run[0],
                                        "subcomponent": run[1],
                                        "job_id": run[8],
                                        "test_num": test_num+1})
        try:
            error_db_info["sdk_client"].collection.get(vector_hash)
        except DocumentNotFoundException:
            doc = {"vector": err_vector_pylist, "vector_hash": vector_hash,
                   "failure_history": list()}
            error_db_info["sdk_client"].collection.insert(vector_hash, doc)

        rows = error_db_info["sdk_client"].cluster.query(
            query_str % vector_hash)
        for row in rows:
            row = row[error_db_info['collection']]
            if row["vector"] != err_vector_pylist:
                continue
            for failed_hist in row["failure_history"]:
                if failed_hist["component"] == arguments.component \
                        and failed_hist["subcomponent"] == run[0] \
                        and failed_hist["cb_version"] == arguments.version \
                        and failed_hist["test_num"] == test_num+1:
                    break
            else:
                # Given error not present in the known error history
                failure_history = row["failure_history"]
                failure_history.append({"component": arguments.component,
                                        "subcomponent": run[0],
                                        "cb_version": arguments.version,
                                        "test_num": test_num+1,
                                        "job_id": run[8]})
                error_db_info["sdk_client"].upsert_sub_doc(
                    vector_hash, "failure_history", failure_history)

print("*" * 100)
print("Install failed jobs: ")
pprint(install_failed_jobs)
print("*" * 100)

print()

print("*" * 100)
print("Other error insights: ")
pprint(error_data)
for hash_val, failed_jobs in error_data.items():
    print("::::: Back Trace ::::::")
    print(backtraces_hash_map[hash_val].split("\n"))
    print("Jobs / Tests failing")
    print(failed_jobs)
    print("-" * 100)
    print()
print("*" * 100)
