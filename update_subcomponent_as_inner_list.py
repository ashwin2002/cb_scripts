from copy import deepcopy
from datetime import timedelta
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.durability import ServerDurability, DurabilityLevel
from couchbase.options import ClusterOptions, ClusterTimeoutOptions, \
    UpsertOptions

host_ip = "172.23.104.162"
username = "Administrator"
password = "couchbase"[::-1]
target_component = "columnar"
bucket_name = "QE-Test-Suites"

auth = PasswordAuthenticator(username, password)
timeout_opts = ClusterTimeoutOptions(kv_timeout=timedelta(seconds=10),
                                     dns_srv_timeout=timedelta(seconds=10))
cluster_opts = {
    "authenticator": auth,
    "enable_tls": False,
    "timeout_options": timeout_opts,
}

cluster_opts = ClusterOptions(**cluster_opts)
cluster = Cluster.connect(f"couchbase://{host_ip}", cluster_opts)
bucket = cluster.bucket(bucket_name)
collection = bucket.default_collection()

q_result = cluster.query(f"SELECT meta().id,* FROM `{bucket_name}` "
                         f"WHERE component='{target_component}'")
common_param_fields = ["component", "confFile", "config", "framework",
                       "jenkins_server_url", "mailing_list", "mode", "partOf",
                       "slave", "support_py3", "timeOut"]

upsert_options = UpsertOptions(
    timeout=timedelta(seconds=5),
    durability=ServerDurability(level=DurabilityLevel.MAJORITY))
for row in q_result.rows():
    doc_id, doc = row["id"], row[bucket_name]
    new_doc = dict()
    for field_to_remove in common_param_fields:
        if field_to_remove not in doc:
            continue
        new_doc[field_to_remove] = doc.pop(field_to_remove)
    if str(doc["subcomponent"]).startswith("columnar"):
        doc["subcomponent"] = doc["subcomponent"][9:]

    gcp_subcomp_doc = deepcopy(doc)
    gcp_subcomp_doc['subcomponent'] = f"gcp_{doc['subcomponent']}"
    doc["subcomponent"] = f"aws_{doc['subcomponent']}"

    gcp_subcomp_doc["implementedIn"] = '1.1'
    gcp_subcomp_doc['subcomponent'] = f"gcp_{gcp_subcomp_doc['subcomponent'][4:]}"
    new_doc["subcomponents"] = [doc, gcp_subcomp_doc]

    result = collection.upsert(doc_id, new_doc, upsert_options)
    print(f"{doc_id}: {result.cas}")

cluster.close()
