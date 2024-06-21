import hashlib
import json
import re
import requests
import sys
import xml.etree.ElementTree as EleTree
from argparse import ArgumentParser
from collections import OrderedDict
from os import getenv

from couchbase.exceptions import DocumentNotFoundException, \
    PathNotFoundException

from sdk_lib.sdk_conn import SDKClient


def parse_cmd_arguments():
    parser = ArgumentParser(description="Get test cases")
    parser.add_argument("--server_ip", dest="gb_ip", required=True,
                        help="Server IP on which Couchbase db is hosted")
    parser.add_argument("--username", dest="username", default="Administrator",
                        help="Username to use login")
    parser.add_argument("--password", dest="password", default="password",
                        help="Password to use login")
    parser.add_argument("--bucket", dest="gb_bucket", default="greenboard",
                        help="Greenboard bucket name")
    parser.add_argument("--os", dest="os_type", default="DEBIAN",
                        help="Target OS for which to parse the jobs")
    parser.add_argument("--component", dest="component",
                        help="Target component for which to parse the jobs")

    parser.add_argument("-v", "--version", dest="version", required=True,
                        help="Couchbase version on which the job has run")

    parser.add_argument("--job_url", dest="job_url", default=None,
                        help="Job URL excluding the build_num")
    parser.add_argument("--job_num", dest="job_num", default=None,
                        help="Job's build_num")
    parser.add_argument("--job_name", dest="job_name", default=None,
                        help="Job_name used in creating the greenboard entry")

    return parser.parse_args(sys.argv[1:])


def parse_case(case_xml):
    data = dict()
    for block in case_xml:
        data[block.tag] = block.text
    return data


def parse_tcs(sdk_conn, cb_version, job_run_id, jenkins_build_num, xml_text):
    root = EleTree.fromstring(xml_text)
    for suite in root.findall("suite"):
        for case in suite.findall("case"):
            parsed_case = parse_case(case)
            case_str = parsed_case["name"]
            case_str = case_str.split(",")
            tc = case_str[0]
            params = dict()
            print(case_str)
            for param in case_str[1:]:
                key, value = param.split('=')
                if key in ['GROUP', 'ini', 'total_testcases',
                           'case_number', 'conf_file', 'rerun',
                           'logs_folder', 'last_case_fail',
                           'cluster_name', 'upgrade_version',
                           'num_nodes', 'get-cbcollect-info', 'sirius_url']:
                    continue
                params[key] = value
            params = OrderedDict(sorted(params.items()))
            param_str = tc + json.dumps(params, separators=(',', ':'),
                                        ensure_ascii=False)
            param_str_bytes = param_str.encode('utf-8')
            sha256 = hashlib.sha256()
            sha256.update(param_str_bytes)
            tc_hash = sha256.hexdigest()
            try:
                _ = sdk_conn.get_doc(tc_hash)
            except DocumentNotFoundException:
                print(f"Creating new test for: {tc}")
                sdk_conn.collection.insert(tc_hash,
                                           {"function": tc,
                                            "params": dict(params),
                                            "job_name": job_run_id,
                                            "runs": {}})
            cb_release, cb_build_num = cb_version.split("-")
            sub_path = f"runs.`{cb_release}`.`{cb_build_num}`"
            # Create version field (if_req)
            try:
                _ = sdk_conn.get_sub_doc_as_list(tc_hash, sub_path)
            except PathNotFoundException:
                # Create place-holder for this version
                print(f"New run on build: {cb_release}")
                sdk_conn.insert_sub_doc(tc_hash, sub_path, [],
                                        create_parents=True)

            doc = sdk_conn.get_sub_doc_as_dict(tc_hash, f"runs.`{cb_release}`")
            jenkins_build_num = str(jenkins_build_num)
            for t_run in doc[cb_build_num]:
                if list(t_run.keys())[0] == jenkins_build_num:
                    break
            else:
                doc[cb_build_num].append(
                    {jenkins_build_num: parsed_case["status"]})
                sdk_conn.upsert_sub_doc(tc_hash, f"runs.`{cb_release}`", doc)


if __name__ == "__main__":
    arguments = parse_cmd_arguments()
    s3_url_prefix = "http://cb-logs-qe.s3-website-us-west-2.amazonaws.com/" \
                    f"{arguments.version}/jenkins_logs"

    tc_db_ip = getenv("tc_db_ip")
    tc_db_username = getenv("tc_db_username")
    tc_db_password = getenv("tc_db_password")
    tc_db_bucket = getenv("tc_db_bucket")
    print("Connecting SDK to cluster")
    tc_tracker_sdk = SDKClient(tc_db_ip, tc_db_username, tc_db_password,
                               tc_db_bucket)

    if arguments.job_url is not None \
            and arguments.job_num is not None\
            and arguments.job_name is not None:
        job_url = str(arguments.job_url).rstrip("/")
        exec_job_type = job_url.split("/")[-1]
        job_name = arguments.job_name

        s3_job_url = f"{s3_url_prefix}/{exec_job_type}/{arguments.job_num}/"
        test_result_url = s3_job_url + "testresult.xml"
        xml_text_data = requests.get(test_result_url).text
        print(f"Trying to get: {test_result_url}")
        if "404 Not Found" in xml_text_data:
            jenkins_link = f"{job_url}/{arguments.job_num}/artifact/job_logs/"
            print(f"Fetching from Jenkins: {jenkins_link}")
            r = requests.get(jenkins_link)
            file_name_pattern = re.compile(
                r"<a href=\"([a-zA-Z0-9\-_]+testresult\.xml)\"")
            matches = file_name_pattern.findall(r.text)
            if matches:
                xml_file_name = matches[0]
                test_result_url = f"{job_url}/{arguments.job_num}/artifact/" \
                                  f"job_logs/{xml_file_name}"
                print(test_result_url)
                xml_text_data = requests.get(test_result_url).text
                data_found = True
            else:
                print("No link for testresult.xml found")
        else:
            print("Parsing tests:")
            parse_tcs(tc_tracker_sdk, arguments.version,
                      job_name, arguments.job_num, xml_text_data)
    else:
        test_run_info_sdk = SDKClient(arguments.gb_ip, arguments.username,
                                      arguments.password, arguments.gb_bucket)
        run_doc = test_run_info_sdk.get_sub_doc_as_dict(
            f"{arguments.version}_server",
            f"os.{arguments.os_type.upper()}.{arguments.component.upper()}")
        test_run_info_sdk.close()

        for job_name, run_list in run_doc.items():
            # # Create doc per job (if_required)
            # try:
            #     _ = tc_tracker_sdk.get_doc(job_name)
            # except DocumentNotFoundException:
            #     print(f"New job: {job_name}")
            #     tc_tracker_sdk.collection.insert(job_name, {})

            for run in run_list:
                exec_job_type = run["url"].split("/")[-2]
                s3_job_url = \
                    f"{s3_url_prefix}/{exec_job_type}/{run['build_id']}/"
                test_result_url = s3_job_url + "testresult.xml"
                print(test_result_url)
                xml_text_data = requests.get(test_result_url).text
                if "404 Not Found" in xml_text_data:
                    print(f"Job: {job_name}, testresult.xml not found")
                    continue
                parse_tcs(tc_tracker_sdk, arguments.version,
                          job_name, run['build_id'], xml_text_data)

                # if str(run["url"]).endswith("/test_suite_executor-TAF/"):

    tc_tracker_sdk.close()
