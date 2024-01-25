#!/usr/bin/python3

import re
import sys
from argparse import ArgumentParser

import requests


deamon_killed = False
install_block = False
test_case_started = False
timestamp_pattern = re.compile("\d+-\d+-\d+ \d+:\d+:\d+,\d+")
test_complete_line_pattern = re.compile("Ran 1 test in (\d+\.\d+s)")
test_report_delimiter = '=' * 70
test_report_stage = 0


def process_install_steps(chunks):
    global install_block, timestamp_pattern

    install_logs = ""
    install_complete = False
    install_failed_pattern = re.compile("FAILED ON[\t :]+\d+\.\d+\.\d+\.\d+")
    time_elapsed = None
    l_idx = 0
    chunk = ['']
    for chunk in chunks:
        chunk = chunk.decode("utf-8").split("\n")
        for l_idx, line in enumerate(chunk):
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

            if install_block:
                install_logs += line + "\n"

        if install_complete:
            break
    ts_occurances = timestamp_pattern.findall(install_logs)
    install_failed_ips = install_failed_pattern.findall(install_logs)
    print("Install started.....%s" % ts_occurances[0])
    print("Install completed...%s" % ts_occurances[-1])
    print("Time elapsed........%s" % time_elapsed)
    if install_failed_ips:
        print(install_failed_ips)
    remaining_lines = chunk[l_idx:]
    return install_logs, '\n'.join(remaining_lines)


def process_test_line(line):
    global deamon_killed, test_case_started, test_report_stage

    if line.strip() == '':
        return

    if "- End of the daemon log -" in line:
        print("Test aborted due to end of daemon message")
        deamon_killed = True
        return

    if line.startswith("Test Input params:"):
        print("\nStarted parsing new test")
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
    global deamon_killed
    for line in remaining_lines.split("\n"):
        process_test_line(line)
        if deamon_killed:
            return

    for chunk in chunks:
        chunk = chunk.decode("utf-8").split("\n")
        chunk = [remaining_lines[-1] + chunk[0]] + chunk[1:]
        for l_idx, line in enumerate(chunk):
            process_test_line(line)
            if deamon_killed:
                return
        remaining_lines = [chunk[-1]]


def stream_and_process(url_str):
    local_filename = url_str.split('/')[-1]
    with requests.get(url_str, stream=True) as r:
        r.raise_for_status()
        chunks = r.iter_content(chunk_size=8192)
        _, remaining_lines = process_install_steps(chunks)
        process_test_cases(remaining_lines, chunks)
    return local_filename


def parse_cmd_arguments():
    parser = ArgumentParser(description="Paser for TAF logs")
    parser.add_argument("-v", "--version", dest="version", default=None,
                        help="Version on which the job has run")
    parser.add_argument("-b", "--build_num", dest="build_num", default=None,
                        help="Build number of jenkins run")

    parser.add_argument("--url", dest="url", default=None,
                        help="Use this URL to parse the logs directly")

    parser.add_argument("--repo", dest="repo", default='TAF',
                        help="Repo using which the logs are generated",
                        choices=["TAF"])
    return parser.parse_args(sys.argv[1:])


if __name__ == '__main__':
    arguments = parse_cmd_arguments()
    if arguments.url:
        url = arguments.url
    else:
        if arguments.version is None or arguments.build_num is None:
            print("Exiting: Pass both version and build_num")
            exit(1)

        job_name = None
        if arguments.repo == "TAF":
            job_name = "test_suite_executor-TAF"

        s3_url = "http://cb-logs-qe.s3-website-us-west-2.amazonaws.com"
        url = "%s/%s/jenkins_logs/%s/%s/consoleText.txt"\
              % (s3_url, arguments.version, job_name, arguments.build_num)
    stream_and_process(url)
