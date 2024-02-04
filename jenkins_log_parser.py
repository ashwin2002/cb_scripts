#!/usr/bin/python3
import os
import re
import shutil
import requests
import sys
import tempfile
from argparse import ArgumentParser
from datetime import timedelta

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions)
import couchbase.subdocument as SD


daemon_killed = False
install_block = False
test_case_started = False
timestamp_pattern = re.compile("\d+-\d+-\d+ \d+:\d+:\d+,\d+")
test_complete_line_pattern = re.compile("Ran 1 test in (\d+\.\d+s)")
test_num = 0
test_report_delimiter = '=' * 70
test_report_stage = 0
tmp_file = None
final_out_file_name = None
s3_url = "http://cb-logs-qe.s3-website-us-west-2.amazonaws.com"
section_delimitter = "=" * 80


def print_and_exit(msg, exit_code=1):
    print(msg)
    exit(exit_code)

def process_install_steps(chunks):
    global install_block, timestamp_pattern, tmp_file, final_out_file_name

    install_logs = ""
    install_complete = False
    install_failed_pattern = re.compile("FAILED ON[\t :]+\d+\.\d+\.\d+\.\d+")
    install_not_started_pattern = re.compile("NOT STARTED ON:[\t :]+\d+\.\d+\.\d+\.\d+")
    time_elapsed = None
    desc_set_log = re.compile("\[description-setter] Description set: (.*)")
    l_idx = 0
    chunk = ['']
    for chunk in chunks:
        tmp_file.write(chunk)
        chunk = chunk.decode("utf-8").split("\n")
        for l_idx, line in enumerate(chunk):
            desc_log = desc_set_log.match(line)
            if "python3 scripts/new_install.py" in line:
                install_block = True
            elif "TOTAL INSTALL TIME" in line:
                install_logs += line + "\n"
                install_block = False
                install_complete = True
                elapsed_pattern = re.compile(".*TOTAL INSTALL TIME = (\d+ seconds)")
                time_elapsed = elapsed_pattern.match(line)
                if time_elapsed:
                    time_elapsed = time_elapsed[1]
                break
            elif desc_log:
                print("Description: %s" % desc_log[1])
                desc_log = desc_log[1].split(" ")
                final_out_file_name = "%s.%s.%s" % (desc_log[0], desc_log[2],
                                                    desc_log[3])

            if install_block:
                install_logs += line + "\n"

        if install_complete:
            break
    ts_occurances = timestamp_pattern.findall(install_logs)
    install_failed_ips = install_failed_pattern.findall(install_logs)
    install_not_started_ips = install_not_started_pattern.findall(install_logs)
    print("-" * 70)
    print("Install summary:")
    print("-" * 70)
    if ts_occurances:
        print("   Started.....%s" % ts_occurances[0])
        print("   End time....%s" % ts_occurances[-1])
        print("   Elapsed.....%s" % time_elapsed)
    for ips in [install_failed_ips, install_not_started_ips]:
        if ips:
            print('   ' + '\n'.join(ips))
    print("-" * 70)
    remaining_lines = chunk[l_idx:]
    return install_logs, '\n'.join(remaining_lines)


def process_test_line(line):
    global daemon_killed, test_case_started, test_report_stage, test_num

    if line.strip() == '':
        return

    if "- End of the daemon log -" in line:
        print("Test aborted due to end of daemon message")
        daemon_killed = True
        return

    if line.startswith("Test Input params:"):
        test_num += 1
        print("\nParsing test: %s" % test_num)
        test_case_started = True
        return

    test_complete_line = test_complete_line_pattern.match(line)
    if test_complete_line:
        print("Test time elapsed....%s\n" % test_complete_line[1])
        test_case_started = False
        return

    if test_case_started:
        if test_report_stage == 0 and line == test_report_delimiter:
            test_report_stage = 1
            print("Test failure report:")
            return
        if test_report_stage > 0:
            print(line)
            if test_report_stage == 1 and line == '-' * 70:
                test_report_stage = 2
            elif test_report_stage == 2 and line == '-' * 70:
                test_report_stage = 0
                return


def process_test_cases(remaining_lines, chunks):
    global daemon_killed
    for line in remaining_lines.split("\n"):
        process_test_line(line)
        if daemon_killed:
            return

    for chunk in chunks:
        tmp_file.write(chunk)
        chunk = chunk.decode("utf-8").split("\n")
        chunk = [remaining_lines[-1] + chunk[0]] + chunk[1:]
        for l_idx, line in enumerate(chunk):
            process_test_line(line)
            if daemon_killed:
                return
        remaining_lines = [chunk[-1]]


def stream_and_process(url_str):
    try:
        with requests.get(url_str, stream=True) as r:
            r.raise_for_status()
            chunks = r.iter_content(chunk_size=8192)
            _, remaining_lines = process_install_steps(chunks)
            process_test_cases(remaining_lines, chunks)
    except (requests.exceptions.Timeout, requests.exceptions.HTTPError) as err:
        print(err)

def fetch_jobs_for_component(server_ip, username, password, bucket_name,
                             version, os_type, component):
    auth = PasswordAuthenticator(username, password)
    options = ClusterOptions(auth)
    cluster = Cluster(f'couchbase://{server_ip}', options)
    cluster.wait_until_ready(timedelta(seconds=5))
    collection = cluster.bucket(bucket_name).default_collection()
    run_data = collection.lookup_in(f"{version}_server",
                                    [SD.get(f"os.{os_type}.{component}")])
    cluster.close()
    return run_data.content_as[dict](0)


def parse_cmd_arguments():
    parser = ArgumentParser(description="Paser for test logs")
    parser.add_argument("--server_ip", dest="gb_ip", default="",
                        help="Server IP on which Couchbase db is hosted")
    parser.add_argument("--username", dest="username", default="Administrator",
                        help="Username to use login")
    parser.add_argument("--password", dest="password", default="password",
                        help="Password to use login")
    parser.add_argument("--bucket", dest="gb_bucket", default="",
                        help="Greenboard bucket name")
    parser.add_argument("--os", dest="os_type", default="debian",
                        help="Target OS for which to parse the jobs")
    parser.add_argument("--component", dest="component", default="",
                        help="Target component for which to parse the jobs")

    parser.add_argument("-v", "--version", dest="version", default=None,
                        help="Version on which the job has run")
    parser.add_argument("-b", "--build_num", dest="build_num", default=None,
                        help="Build number of jenkins run")

    parser.add_argument("--url", dest="url", default=None,
                        help="Use this URL to parse the logs directly")

    parser.add_argument("--repo", dest="repo", default='TAF',
                        help="Repo using which the logs are generated",
                        choices=["TAF"])

    parser.add_argument("--dont_save", dest="dont_save_content", default=False,
                        action="store_true",
                        help="Won't save the content locally after parsing")
    return parser.parse_args(sys.argv[1:])


if __name__ == '__main__':
    arguments = parse_cmd_arguments()
    if arguments.url:
        url = arguments.url
    else:
        if arguments.version is None:
            print_and_exit("Exiting: Pass --version [Eg: 7.6.0-1000]")

    if arguments.build_num:
        jobs = {"dummy": [{"displayName": "temp", "olderBuild": False,
                           "failCount": "NA", "totalCount": "NA",
                           "build_id": arguments.build_num}]}
    elif arguments.gb_ip and arguments.gb_bucket \
            and arguments.os_type and arguments.component:
        jobs = fetch_jobs_for_component(
            arguments.gb_ip, arguments.username, arguments.password,
            arguments.gb_bucket, arguments.version,
            arguments.os_type.upper(), arguments.component.upper())
        arguments.dont_save_content = True
    else:
        print_and_exit("Exiting: Pass --build_num")

    delete_tmp_file_flag = True if arguments.dont_save_content else False
    tmp_file = tempfile.NamedTemporaryFile(dir="/tmp",
                                           delete=delete_tmp_file_flag)
    result_tbl = dict()
    for job_name, runs in jobs.items():
        print(section_delimitter)
        print("Job::%s, Total runs: %s" % (job_name, len(runs)))
        print(section_delimitter)
        for run in runs:
            test_num = 0
            is_best_run = ""
            if arguments.url:
                url = arguments.url
            elif "url" in run:
                jenkins_job = (run["url"].strip("/")).split('/')[-1]
                if jenkins_job == "test_suite_executor-TAF":
                    url = "%s/%s/jenkins_logs/%s/%s/consoleText.txt" \
                          % (s3_url, arguments.version, jenkins_job,
                             run["build_id"])
                else:
                    continue
            else:
                if arguments.repo == "TAF":
                    jenkins_job = "test_suite_executor-TAF"
                url = "%s/%s/jenkins_logs/%s/%s/consoleText.txt" \
                      % (s3_url, arguments.version, jenkins_job,
                         run["build_id"])
            if not run["olderBuild"]:
                is_best_run = " (Best run)"
                result_tbl[run["displayName"]] = [run["failCount"],
                                                  run["totalCount"]]
            print("Parsing URL: %s %s" % (url, is_best_run))
            try:
                stream_and_process(url)
            except Exception as e:
                print(e)
            if not arguments.dont_save_content:
                user_input = input("Do you want to save this log ? [y/n]: ")
                tmp_file.close()
                if user_input.strip() in ["y", "Y"]:
                    print("Saving content into ./%s" % final_out_file_name)
                    shutil.move(tmp_file.name, "./%s" % final_out_file_name)
                else:
                    os.remove(tmp_file.name)
        print("End of job: %s" % job_name)
        print("")

    print("| %s|%s|%s|" % ("-" * 30, "-" * 3, "-" * 3))
    for job_name, result in result_tbl.items():
        print("| %s %s %s " % (job_name.ljust(30, "."),
                              result[0].rjust(3, " "),
                              str(result[1]).rjust(3, " ")))
    print("| %s|%s|%s|" % ("-" * 30, "-" * 3, "-" * 3))
