#!/usr/bin/python3

from pprint import pprint

import argparse
import base64
import json
import requests
import subprocess
import urllib

parser = argparse.ArgumentParser()
parser.add_argument('--dataplanes', action='store_true', help='List all available data planes')
parser.add_argument('--delete_all_dbs', action='store_true', help='Removes all databases from the dataplane')
parser.add_argument('--delete_db', type=str, help='Removes all databases from the dataplane')
parser.add_argument('--info', type=str, help='Fetch dataplane info')
parser.add_argument('--jobs', type=str, help='Fetch jobs from the dataplane')
parser.add_argument('--delete', type=str, help='Delete the dataplane')
parser.add_argument('--bypass', type=str, help='Add your IP to allowed_id and creates a temp credentials')
parser.add_argument('--srv', type=str, help='SRV record to fetch the IPs')
parser.add_argument('--sandbox', type=str, help='Target sandbox env with given num "N"')
parser.add_argument('--get_jwt', action='store_true', help='Gets JWT token for external use')
parser.add_argument('--url', action='store_true', help='Prints the API endpoint for the given env')
args = parser.parse_args()

secret_token = ""
control_plane = 'https://api.dev.nonprod-project-avengers.com'
username = ""
password = ""

session = requests.Session()
jwt = None

if args.sandbox is not None:
    secret_token = ""
    control_plane = "https://api.%s.sandbox.nonprod-project-avengers.com" % args.sandbox
    username = ""
    password = ""
    
def get_jwt_header():
    global jwt, session
    if jwt is None:
        print("Fetching jwt token")
        basic = base64.b64encode(('%s:%s' % (username, password)).encode()).decode()
        header = {'Authorization': 'Basic %s' % basic}
        resp = session.post("%s/sessions" % control_plane, headers=header)
        jwt = json.loads(resp.content).get("jwt")
    return {"Content-Type": "application/json", "Authorization": "Bearer %s" % jwt}

if args.url:
    print(control_plane)
    exit(0)

elif args.dataplanes:
    api = '%s/internal/support/serverless-dataplanes' % control_plane
    headers = get_jwt_header()
    while True:
        response = requests.get(api, headers=headers).json()
        print("")
        if "message" in response and response["message"] == "Not Found.":
            print("No dataplanes found")
        else:
            line_len = 75
            print("-------------------------- List of dataplanes ----------------------------")
            for cluster in response:
                print(" * %s :: %s" % (cluster["id"], cluster["status"]["state"]))
                print("      Project id :: %s" % cluster["tenantId"])
                print("      Tenant id  :: %s" % cluster["projectId"])
                print("      CB cluster id  :: %s" % cluster["couchbaseCluster"]["id"])
                print("      Nebula :: %s" % cluster["config"]["nebula"]["image"])
                print("      DAPI   :: %s" % cluster["config"]["dataApi"]["image"])
                print("      Created  :: %s" % cluster["createdAt"])
                print("      Provider :: %s %s" % (cluster["config"]["provider"], cluster["config"]["region"]))
                print("-" * line_len)
        break

elif args.get_jwt:
    headers = get_jwt_header()
    output = "%s " % control_plane
    for k, v in headers.items():
        output += "-H \"%s: %s\" " % (k, v)
    print(output)
    exit(0)

#### Deletes all DBs ######
elif args.delete_all_dbs:
    api = "%s/internal/support/serverless-databases" % control_plane
    for db in requests.get(api, headers=get_jwt_header()).json():
        print(db["id"])
        requests.delete(api+"/%s" % db["id"], headers=get_jwt_header())

elif args.delete_db is not None:
    api = "%s/internal/support/serverless-databases/%s" % (control_plane, delete_db)
    requests.delete(api, headers=get_jwt_header())

#### Fetch /info details ##########
elif args.info is not None:
    headers = get_jwt_header()
    api = "%s/internal/support/serverless-dataplanes/%s/info" % (control_plane, args.info)
    response = requests.get("%s/internal/support/serverless-dataplanes/%s/info" % (control_plane, args.info), headers=headers)
    pprint(response.json())

#### Fetch /jobs details ##########
elif args.jobs is not None:
    headers = get_jwt_header()
    api = "%s/internal/support/serverless-dataplanes/%s/jobs" % (control_plane, args.jobs)
    response = requests.get("%s/internal/support/serverless-dataplanes/%s/jobs" % (control_plane, args.jobs), headers=headers)
    pprint(response.json())

#### Delete the dataplane ##########
elif args.delete is not None:
    headers = get_jwt_header()
    api = "%s/internal/support/serverless-dataplanes/%s" % (control_plane, args.delete)
    response = requests.delete("%s/internal/support/serverless-dataplanes/%s" % (control_plane, args.delete), headers=headers)
    pprint(response.json())

#### By pass support #################
elif args.bypass is not None:
    ip = requests.get('https://checkip.amazonaws.com').text.strip()
    api = "%s/internal/support/serverless-dataplanes/%s/bypass" % (control_plane, args.bypass)

    headers = get_jwt_header()
    output = ""
    for k, v in headers.items():
        output += " -H \"%s: %s\"" % (k, v)

    params = '\'{"allowCIDR": "%s/32"}\'' % ip
    cmd = ["curl", "-X", "POST", "-L", '"' + api + '"', 
           "-d", params, output]

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

session.close()
