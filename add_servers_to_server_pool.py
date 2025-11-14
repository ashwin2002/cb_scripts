import argparse
from datetime import timedelta

import paramiko
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions)


def classify_linux_os(os_rel_file_content):
    """Classify Linux OS based on /etc/os-release file"""
    try:
        os_info = dict()
        for t_line in os_rel_file_content:
            t_line = t_line.strip()
            if '=' in t_line:
                key, value = t_line.split('=', 1)
                # Remove quotes from value
                os_info[key] = value.strip('"')

        # Get the main identifiers
        name = os_info.get('NAME', '').lower()
        version = os_info.get('VERSION_ID', '')
        id_like = os_info.get('ID_LIKE', '').lower()
        id_name = os_info.get('ID', '').lower()

        # Classification logic
        if 'debian' in name or 'debian' in id_like or id_name == 'debian':
            if version.startswith('12'):
                return 'debian12'
            elif version.startswith('11'):
                return 'debian11'
            elif version.startswith('10'):
                return 'debian10'
            elif version.startswith('9'):
                return 'debian9'
            else:
                return f'debian{version}'

        elif 'ubuntu' in name or id_name == 'ubuntu':
            if version.startswith('22.04'):
                return 'ubuntu22.04'
            elif version.startswith('20.04'):
                return 'ubuntu20.04'
            elif version.startswith('18.04'):
                return 'ubuntu18.04'
            else:
                return f'ubuntu{version}'

        elif 'centos' in name or id_name == 'centos':
            if version.startswith('8'):
                return 'centos8'
            elif version.startswith('7'):
                return 'centos7'
            elif version.startswith('6'):
                return 'centos6'
            else:
                return f'centos{version}'

        elif 'rhel' in name or id_name == 'rhel' or 'red hat' in name:
            if version.startswith('8'):
                return 'rhel8'
            elif version.startswith('7'):
                return 'rhel7'
            elif version.startswith('6'):
                return 'rhel6'
            else:
                return f'rhel{version}'

        elif 'rocky' in name or id_name == 'rocky':
            if version.startswith('8'):
                return 'rocky8'
            elif version.startswith('9'):
                return 'rocky9'
            else:
                return f'rocky{version}'

        elif 'alma' in name or id_name == 'almalinux':
            if version.startswith('8'):
                return 'alma8'
            elif version.startswith('9'):
                return 'alma9'
            else:
                return f'alma{version}'

        elif 'fedora' in name or id_name == 'fedora':
            return f'fedora{version}'

        elif 'suse' in name or 'sles' in name or id_name in ['sles',
                                                             'opensuse']:
            if 'sles' in name.lower():
                return f'sles{version}'
            else:
                return f'opensuse{version}'

        else:
            # Fallback: return generic classification
            return f'{id_name}{version}' if version else id_name

    except FileNotFoundError:
        return 'unknown'
    except Exception as e:
        print(f"Error reading /etc/os-release: {e}")
        return 'unknown'


if __name__ == "__main__":
    """
    Usage: 
        python add_servers_to_server_pool.py
            --host 172.23.100.2
            --username Admin
            --password passwrd
            --server_pool_bucket 'server-pool'
            --server_pool_scope _default
            --server_pool_collection custom_collection
            --server_info_csv_file /tmp/server_pool_vms.csv
            --it_ticket_number zendesk_12345
    """
    parser = argparse.ArgumentParser(description="Script to update servers into server pool")
    parser.add_argument("--host", type=str, required=True,
                        help="Couchbase server host IP")
    parser.add_argument("--username", type=str, required=True,
                        help="Couchbase username")
    parser.add_argument("--password", type=str, required=True,
                        help="Couchbase password")
    parser.add_argument("--server_pool_bucket", type=str, required=True,
                        help="Couchbase bucket name for server pool")
    parser.add_argument("--server_pool_scope", type=str, required=True,
                        help="Couchbase scope name for server pool")
    parser.add_argument("--server_pool_collection", type=str, required=True,
                        help="Couchbase collection name for server pool")
    parser.add_argument("--server_info_csv_file", type=str, required=True,
                        help="Path to CSV file containing server info to add")
    parser.add_argument("--it_ticket_number", type=str, default=None,
                        help="IT ticket number associated with the servers being added")
    args = parser.parse_args()

    timeout_opts = ClusterTimeoutOptions(
        connect_timeout=timedelta(seconds=60),
        kv_timeout=timedelta(seconds=10),
        analytics_timeout=timedelta(seconds=1200),
        dns_srv_timeout=timedelta(seconds=10))
    cluster_opts = {
        "authenticator": PasswordAuthenticator(args.username, args.password),
        "enable_tls": False,
        "timeout_options": timeout_opts,
        # "tls_verify": TLSVerifyMode.NO_VERIFY
    }

    cluster_opts = ClusterOptions(**cluster_opts)
    connection_string = f"couchbase://{args.host}"

    cluster = Cluster.connect(connection_string,cluster_opts)
    bucket = cluster.bucket(args.server_pool_bucket)
    collection = bucket.scope(args.server_pool_scope)\
        .collection(args.server_pool_collection)

    with open(args.server_info_csv_file, 'r') as fp:
        while True:
            line = fp.readline()
            # Each line in the CSV is expected to be in the format:
            # origin,vm_name,ipaddr,poolId
            if not line:
                break
            line = line.strip()
            origin, vm_name, ipaddr, pool_id, it_ticket_number = line.split(",")
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())

            ssh_client.connect(
                hostname=ipaddr, username="root", password="couchbase",
                look_for_keys=False)

            _, stdout, _ = ssh_client.exec_command(
                "free  | grep Mem: | awk '{print $2}'")
            memory = int(stdout.readline().strip())

            _, stdout, _ = ssh_client.exec_command("hostname")
            hostname = stdout.readline().strip()

            _, stdout, _ = ssh_client.exec_command(
                "lscpu | grep '^CPU(' | awk '{print $2}'")
            num_cores = int(stdout.readline().strip())

            _, stdout, _ = ssh_client.exec_command("cat /etc/os-release")
            os_release_content = stdout.readlines()
            vm_os = classify_linux_os(os_release_content)

            _, stdout, _ = ssh_client.exec_command(
                "df -h  | grep '/data' | awk '{print $2}'")
            data_partition_size = stdout.readline().strip() or "NA"

            ssh_client.close()

            server_doc ={
                "ipaddr": ipaddr,
                "origin": origin,
                "hostname": hostname,
                "os": vm_os,
                "core": num_cores,
                "memory": memory,
                "data_partition": data_partition_size,
                "poolId": [
                    pool_id,
                ],
                "it_ticket_reference": args.it_ticket_number or it_ticket_number,
                "username": "NA",
                "prevUser": "NA",
                "state": "available"
            }

            result = collection.insert(vm_name, server_doc)
            print(f"Added server document {vm_name} with CAS {result.cas}")

    cluster.close()
