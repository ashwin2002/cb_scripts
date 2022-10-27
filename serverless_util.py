#!/usr/local/bin/python3

from pprint import pprint

import argparse
import requests
import subprocess
import urllib


parser = argparse.ArgumentParser()
parser.add_argument('--dataplanes', action='store_true', help='List all available data planes')
parser.add_argument('--info', type=str, help='Fetch dataplane info')
parser.add_argument('--jobs', type=str, help='Fetch jobs from the dataplane')
parser.add_argument('--delete', type=str, help='Delete the dataplane')
parser.add_argument('--bypass', type=str, help='Add your IP to allowed_id and creates a temp credentials')
parser.add_argument('--srv', type=str, help='SRV record to fetch the IPs')
parser.add_argument('--sandbox', type=str, help='Target sandbox env with given num "N"')
args = parser.parse_args()

secret_token = ""
control_plane = 'https://api.dev.nonprod-project-avengers.com'

if args.sandbox is not None:
    secret_token = ""
    control_plane = "https://api.sbx-%s.sandbox.nonprod-project-avengers.com" % args.sandbox

headers = {"Content-Type": "application/json", "Authorization": "Bearer %s" % secret_token}

if args.dataplanes:
    response = requests.get('%s/internal/support/serverless-dataplanes' % control_plane, headers=headers)
    line_len = 75
    print("-" * line_len)
    for cluster in response.json():
        print(" * %s :: %s" % (cluster["id"], cluster["status"]["state"]))
        print("      Project id :: %s" % cluster["tenantId"])
        print("      Tenant id  :: %s" % cluster["projectId"])
        print("      CB cluster id  :: %s" % cluster["couchbaseCluster"]["id"])
        print("      Nebula :: %s" % cluster["config"]["nebula"]["image"])
        print("      DAPI   :: %s" % cluster["config"]["dataApi"]["image"])
        print("      Created  :: %s" % cluster["createdAt"])
        print("      Provider :: %s %s" % (cluster["config"]["provider"], cluster["config"]["region"]))
        print("-" * line_len)

#### Fetch /info details ##########
elif args.info is not None:
    api = "%s/internal/support/serverless-dataplanes/%s/info" % (control_plane, args.info)
    response = requests.get("%s/internal/support/serverless-dataplanes/%s/info" % (control_plane, args.info), headers=headers)
    pprint(response.json())

#### Fetch /jobs details ##########
elif args.jobs is not None:
    api = "%s/internal/support/serverless-dataplanes/%s/jobs" % (control_plane, args.jobs)
    response = requests.get("%s/internal/support/serverless-dataplanes/%s/jobs" % (control_plane, args.jobs), headers=headers)
    pprint(response.json())

#### Delete the dataplane ##########
elif args.delete is not None:
    api = "%s/internal/support/serverless-dataplanes/%s" % (control_plane, args.delete)
    response = requests.delete("%s/internal/support/serverless-dataplanes/%s" % (control_plane, args.delete), headers=headers)
    pprint(response.json())

#### By pass support #################
elif args.bypass is not None:
    ip = requests.get('https://checkip.amazonaws.com').text.strip()
    api = "%s/internal/support/serverless-dataplanes/%s/bypass" % (control_plane, args.bypass)

    params = '\'{"allowCIDR": "%s/32"}\'' % ip
    cmd = ["curl", "-X", "POST", "-L", '"' + api + '"', 
           "-H", '"Content-Type: application/json"',
           "-H", '"Authorization: Bearer %s"' % secret_token,
           "-d", params]

    print(' '.join(cmd)) 

#### SRV record support #############
elif args.srv is not None:
    cmd = ["dig", "_couchbases._tcp.%s" % args.srv, "SRV"]
    print(' '.join(cmd))
    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
    out, err = p.communicate()
    print(str(out).replace("\\n", "\n"))
    print(err)
