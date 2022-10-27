#!/usr/local/bin/python

import jenkins
import sys

from couchbase.cluster import Cluster
from couchbase.cluster import PasswordAuthenticator
from couchbase.n1ql import N1QLQuery

class TableView:
    def __init__(self):
        self.h_sep = "-"
        self.v_sep = None
        self.join_sep = None
        self.r_align = False
        self.headers = list()
        self.rows = list()
        self.set_show_vertical_lines(True)

    def set_show_vertical_lines(self, show_vertical_lines):
        self.v_sep = "|" if show_vertical_lines else ""
        self.join_sep = "+" if show_vertical_lines else " "

    def set_headers(self, headers):
        self.headers = headers

    def add_row(self, row_data):
        self.rows.append(row_data)

    def get_line(self, max_widths):
        row_buffer = ""
        for index, width in enumerate(max_widths):
            line = self.h_sep * (width + len(self.v_sep) + 1)
            last_char = self.join_sep if index == len(max_widths) - 1 else ""
            row_buffer += self.join_sep + line + last_char
        return row_buffer + "\n"

    def get_row(self, row, max_widths):
        row_buffer = ""
        for index, data in enumerate(row):
            v_str = self.v_sep if index == len(row) - 1 else ""
            if self.r_align:
                pass
            else:
                line = "{} {:" + str(max_widths[index]) + "s} {}"
                row_buffer += line.format(self.v_sep, data, v_str)
        return row_buffer + "\n"

    def display(self, message):
        # Nothing to display if there are no data rows
        if len(self.rows) == 0:
            return

        # Set max_width of each cell using headers
        max_widths = [len(header) for header in self.headers]

        # Update max_widths if header is not defined
        if not max_widths:
            max_widths = [len(item) for item in self.rows[0]]

        # Align cell length with row_data
        for row_data in self.rows:
            for index, item in enumerate(row_data):
                max_widths[index] = max(max_widths[index], len(str(item)))

        # Start printing to console
        table_data_buffer = message + "\n"
        if self.headers:
            table_data_buffer += self.get_line(max_widths)
            table_data_buffer += self.get_row(self.headers, max_widths)

        table_data_buffer += self.get_line(max_widths)
        for row in self.rows:
            table_data_buffer += self.get_row(row, max_widths)
        table_data_buffer += self.get_line(max_widths)
        print(table_data_buffer)

 
def get_time_from_ms(ms):
    seconds=(ms/1000)%60
    seconds = int(seconds)
    minutes=(ms/(1000*60))%60
    minutes = int(minutes)
    hours=(ms/(1000*60*60))%24
    return ("%d:%d:%d" % (hours, minutes, seconds))


def print_build_durations():
    table_view = TableView()
    table_view.set_headers(["Job", build, compare_duration_with])
    total_duration_1 = 0
    total_duration_2 = 0
    print("Running N1ql queries")
    itr_rows = cb.n1ql_query(N1QLQuery(
        'SELECT name,duration FROM `%s` data \
        WHERE component="%s" and \
              os="%s" and \
              `build`="%s" and result="SUCCESS"'
        % (bucket_name, component, os, build)))

    for row in itr_rows:
        name = row["name"]
        duration_1 = row["duration"]
        total_duration_1 += duration_1

        compare_row = cb.n1ql_query(N1QLQuery(
            'SELECT duration FROM `%s` data \
            WHERE component="%s" and \
                  os="%s" and \
                  `build`="%s" and \
                  name="%s"'
            % (bucket_name, component, os, compare_duration_with, name)))
        for row in compare_row:
            duration_2 = row["duration"]
            total_duration_2 += duration_2
            table_view.add_row([name, 
                                get_time_from_ms(duration_1),
                                get_time_from_ms(duration_2)])
            break

    table_view.add_row(["Total", 
                        get_time_from_ms(total_duration_1),
                        get_time_from_ms(total_duration_2)])
    table_view.display("Time Comparison")


def print_failed_jobs(component, os, build):
    print("Running N1ql query")
    row_iter = cb.n1ql_query(N1QLQuery(
        'SELECT * FROM `%s` data \
        WHERE component="%s" and \
              os="%s" and \
              `build`="%s"'
        % (bucket_name, component, os, build)))

    total_tc = 0
    failed_tc = 0

    for row in row_iter:
        row = row["data"]

        total_tc += row["totalCount"]
        failed_tc += row["failCount"]

        if row["result"] == "SUCCESS":
            continue

        job_id = row["build_id"]
        job_name = row["url"].split("/")[-2]
        job_details[job_id] = dict()
        job_details[job_id]["job_name"] = job_name
        job_details[job_id]["status"] = row["result"]

    print("Closing the bucket connection")
    cb._close()

    jenkins_server = jenkins.Jenkins('http://qa.sc.couchbase.com')

    for job_id, data in job_details.items():
        job_data = jenkins_server.get_build_info(data["job_name"], job_id)
        for job_param in job_data['actions'][0]['parameters']:
            if job_param["name"] == "subcomponent":
                job_details[job_id]["sub_component"] = job_param["value"]
            if job_param["name"] == "component":
                job_details[job_id]["component"] = job_param["value"]

    for job_id, data in job_details.items():
        job_status = job_details[job_id]["status"]

        if job_details[job_id]["component"] not in failed_jobs:
            failed_jobs[job_details[job_id]["component"]] = dict()
        if job_status not in failed_jobs[job_details[job_id]["component"]]:
            failed_jobs[job_details[job_id]["component"]][job_status] = list()
        failed_jobs[job_details[job_id]["component"]][job_status].append(job_details[job_id]["sub_component"])

    for component, result_dict in failed_jobs.items():
        for job_status, sub_comps in result_dict.items():
            print("***** %s %s (%s) *****\n%s" 
                  % (component, job_status,
                     len(sub_comps), ",".join(sub_comps)))

    passed_tc = total_tc - failed_tc
    pass_percent = (100 * passed_tc) / total_tc
    print("Total: %s, Passed: %s Failed: %s. Pass percent: %s%%" % (total_tc, passed_tc, failed_tc, pass_percent))

SERVER_IP = "172.23.98.63"
username = "Administrator"
password = "password"
bucket_name = "server"

os = "CENTOS"
component = "DURABILITY"
build = ""
compare_duration_with=None

job_details = dict()
failed_jobs = dict()

supported_options = ["--component", "--build", "--os", "--compare_duration_with"]

index = 1
arg_len = len(sys.argv)
while index < arg_len:
  if sys.argv[index] == "--component":
    component = sys.argv[index+1]
  elif sys.argv[index] == "--build":
    build = sys.argv[index+1]
  elif sys.argv[index] == "--os":
    os = sys.argv[index+1]
  elif sys.argv[index] == "--compare_duration_with":
    compare_duration_with = sys.argv[index+1]
  else:
    print("Supported options: %s" % supported_options)
    exit(0)

  index += 2

print("Connecting to cluster")
cluster = Cluster('couchbase://%s' % SERVER_IP)
authenticator = PasswordAuthenticator(username, password)
cluster.authenticate(authenticator)

print("Opening bucket")
cb = cluster.open_bucket(bucket_name)

if compare_duration_with is not None:
    print_build_durations()
else:
    print_failed_jobs(component, os, build)
