#!/usr/bin/python3
import os
import re
import shutil
import sys
import tempfile
from argparse import ArgumentParser

import requests


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
    with requests.get(url_str, stream=True) as r:
        r.raise_for_status()
        chunks = r.iter_content(chunk_size=8192)
        _, remaining_lines = process_install_steps(chunks)
        process_test_cases(remaining_lines, chunks)


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

    parser.add_argument("--dont_save", dest="dont_save_content", default=False,
                        action="store_true",
                        help="Won't save the content locally after parsing")
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

    delete_tmp_file_flag = True if arguments.dont_save_content else False
    tmp_file = tempfile.NamedTemporaryFile(dir="/tmp",
                                           delete=delete_tmp_file_flag)
    print("Writing into file: %s" % tmp_file.name)
    stream_and_process(url)
    if not arguments.dont_save_content:
        user_input = input("Do you want to save this log ? [y/n]: ")
        tmp_file.close()
        if user_input.strip() in ["y", "Y"]:
            print("Saving content into ./%s" % final_out_file_name)
            shutil.move(tmp_file.name, "./%s" % final_out_file_name)
        else:
            os.remove(tmp_file.name)
