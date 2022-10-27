import jenkins

target_slave = "jython_slave"

j = jenkins.Jenkins('http://qa.sc.couchbase.com', username='ashwin.govindarajulu', password='couchbase123')

for n in j.get_nodes():
    if n["name"] == "master" or n["offline"]:
        continue
    n_info = j.get_node_info(n["name"], 2)
    for label in n_info["assignedLabels"]:
        if label["name"] == target_slave:
            print(n_info["description"])
            break
