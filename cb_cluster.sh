#!/bin/bash

help() {
    echo " Usage:"
    echo "    $0 [master_node] [task_name] [args..]"
    echo " Supported tasks:"
    echo "   add_nodes"
    echo "   del_all_buckets"
    echo "   reb_out_all_nodes"
    echo "   rebalance"
    exit 0
}
echo $#

if [ $# -lt 2 ]; then
    help
fi

master=$1
command=$2
username=Administrator
password=password

curl_cmd="curl -k -u $username:$password https://$master:18091"

case "$command" in
  add_nodes)
    nodes_to_add=$3
    service=$4
    if [ "$service" == "" ]; then
        service=kv
    fi
    for node in $nodes_to_add; do
        echo -n "Add '$node' .... "
        ${curl_cmd}/controller/addNode -X POST \
            -d "hostname=$node" \
            -d "user=$username" \
            -d "password=$password" \
            -d "services=$service"
        echo ""
    done
    ;;

  del_all_buckets)
    for bucket in `${curl_cmd}/pools/default/buckets -X GET | jq .[].name`
    do
        bucket=`echo $bucket | tr -d '"'`
        echo "Deleting bucket $bucket"
        ${curl_cmd}/pools/default/buckets/$bucket -X DELETE
    done
    ;;

  reb_out_all_nodes)
    knownNodes=""
    ejectNodes=""

    for otpNode in `${curl_cmd}/pools/nodes -X GET | jq .nodes[].otpNode`
    do
       otpNode=`echo $otpNode | tr -d '"'`
       ns=`echo $otpNode | cut -d'@' -f 1`
       node_ip=`echo $otpNode | cut -d'@' -f 2`
       knownNodes="$knownNodes%2C$ns%40$node_ip"
       if [ "$node_ip" != "$master" ]
       then
           ejectNodes="$ejectNodes%2C$ns%40$node_ip"
       fi
    done

    knownNodes=${knownNodes:3}
    ejectNodes=${ejectNodes:3}

    echo "Starting rebalance"
    ${curl_cmd}/controller/rebalance -X POST -d "knownNodes=$knownNodes" -d "ejectedNodes=$ejectNodes"
    ;;

  rebalance)
    nodes=$(for node in `$curl_cmd/pools/default | jq .nodes[].otpNode | xargs `; do python3 -c "import urllib.parse;print(urllib.parse.quote(input()))" <<< "$node"; done)
    nodes=$(echo $nodes | sed 's/ /,/g')
    ${curl_cmd}/controller/rebalance -X POST -d "knownNodes=$nodes"
    ;;
  *)
    echo "Invalid command $command"
    exit 1
esac
