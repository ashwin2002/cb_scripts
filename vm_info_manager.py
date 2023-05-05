#!/usr/local/bin/python3.10

import argparse
from datetime import timedelta

# needed for any cluster connection
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions)
# from tabulate import tabulate
from prettytable import PrettyTable
table = PrettyTable()

parser = argparse.ArgumentParser()
parser.add_argument('--server', type=str, default="", help='Node to connect')
parser.add_argument('-u', '--username', type=str, default="Administrator", help='Username for auth')
parser.add_argument('-p', '--password', type=str, default="", help='Password for auth')
parser.add_argument('-b', '--bucket', type=str, default="", help='Target bucket')

parser.add_argument('--ipaddr', type=str, default="NA", help='IP address')
parser.add_argument('--os', type=str, default="", help='OS type')
parser.add_argument('--state', type=str, default=None, help='State to set')
parser.add_argument('cmd')
args = parser.parse_args()

# Connect options - authentication
auth = PasswordAuthenticator(args.username, args.password)

# get a reference to our cluster
options = ClusterOptions(auth)
cluster = Cluster(f'couchbase://{args.server}', options)

# Wait until the cluster is ready for use.
cluster.wait_until_ready(timedelta(seconds=5))

rows = list()
if args.cmd == "getState":
    req_fields = ["ipaddr", "origin", "os"]
    table.field_names = req_fields
    table.sortby = req_fields[0]

    q_str = f"SELECT * FROM `{args.bucket}` WHERE os='{args.os}' and state='{args.state}'"
    result = cluster.query(q_str)
    for row in result.rows():
        row = row[args.bucket]
        res = list()
        for field in req_fields:
            res.append(row[field])
        table.add_row(res)
elif args.cmd == "setState":
    q_str = f"UPDATE `{args.bucket}` SET state='{args.state}' WHERE ipaddr='{args.ipaddr}' AND os='{args.os}'"
    result = cluster.query(q_str)
    for row in result.rows():
        print(row)

for header in table.field_names:
    table.align[header] = 'l'
print(table)

cluster.close()
exit(0)
