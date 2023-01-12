#!/bin/bash

usage() {
    echo "Params:"
    echo " -b   build-num"
    echo " -n   nodes/ip list"
    echo " -f   <file_name>.deb"
    echo " --list       Lists the available builds"
    echo " --delete     Deletes the given build_num from '-b'"
    echo " --download   only download the build"
    echo " --elixir     Sets serverless profile during installation"
    echo " --help       Displays this help message"
    echo " --init <node_ip>             Initialize node <N>"
    echo " --init_services <s1,s2,..>   Services to use for init"
    echo ""
}

install_cb_build() {
    if [ "$vagrant_install" != "true" ]
    then
        echo "$1: Removing old build files"
        sshpass -p couchbase ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$1 -t "rm -f ~/couchbase-server*"
        echo "$1: Copying build"
        sshpass -p couchbase scp -r -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$build_dir/$file_name" root@$1:~/
    fi
    echo "$1: Starting installation"
    sshpass -p couchbase ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$node -t "$install_cmd" > /dev/null
    echo "$1: Installation complete"
}

initialize_node() {
    echo "Initilizing node $init_node with '$service_init'"
    echo "/opt/couchbase/bin/couchbase-cli cluster-init -c http://$init_node:8091 --cluster-username Administrator --cluster-password password --services $service_init --cluster-ramsize 512 --cluster-index-ramsize 256"
    sshpass -p couchbase ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$init_node -t "/opt/couchbase/bin/couchbase-cli cluster-init -c http://$init_node:8091 --cluster-username Administrator --cluster-password password --services $service_init --cluster-ramsize 512 --cluster-index-ramsize 256"
}

branch=NA
build=""
nodes=""
init_node=""
service_init="data"
file_name=""
serverless_cmd="#"
del_build=false
vagrant_install=true
vagrant_path="/Users/$USER/gitRepos/couchbaselabs/vagrants/7.1.0/ubuntu20"

download_only=true
build_dir=/Users/$USER/works/builds
mkdir -p $build_dir

while [ $# -ne 0 ]; do
    if [ "$1" == "-b" ]; then
        build=$2
        shift ; shift
    elif [ "$1" == "-n" ]; then
        nodes=$2
        download_only=false
        shift ; shift
    elif [ "$1" == "-f" ]; then
        file_name=$2
        shift ; shift
    elif [ "$1" == "--init" ]; then
        init_node=$2
        shift ; shift
    elif [ "$1" == "--init_services" ]; then
        service_init=$2
        shift ; shift
    elif [ "$1" == "--download" ]; then
        download_only=true
        shift
    elif [ "$1" == "--list" ]; then
        ls $build_dir/*ubuntu20* | cut -d'_' -f2 | cut -d'-' -f1 -f2
        exit $?
    elif [ "$1" == "--delete" ]; then
        del_build=true
        shift
    elif [ "$1" == "--elixir" ]; then
        serverless_cmd="mkdir -p /etc/couchbase.d ; echo serverless > /etc/couchbase.d/config_profile ; chmod ugo+r /etc/couchbase.d/"
        shift
    elif [ "$1" == "--help" ]; then
        usage
        exit 0
    else
        echo "Exiting: Invalid arg '$1'"
        usage
        exit 1
    fi
done

# Only INIT
if [ "$build" = "" ] && [ "$init_node" != "" ] && [ "$file_name" = "" ]; then
    initialize_node
    exit 0
fi

#time_sync="timedatectl set-timezone America/Los_Angeles"
time_sync="timedatectl set-timezone Asia/Kolkata"

if [  "$file_name" == "" ]; then
    branch=$(echo $build | cut -c1-3)
    build_num=$(echo $build | cut -d'-' -f 2)
    if [ $(echo "$branch >= 8.0" | bc) -eq 1 ]; then
        branch=morpheus
    elif [ $(echo "$branch >= 7.5" | bc) -eq 1 ]; then
        branch=elixir
    elif [ $(echo "$branch >= 7.1" | bc) -eq 1 ]; then
        branch=neo
    elif [ $(echo "$branch >= 7.0" | bc) -eq 1 ]; then
        branch=cheshire-cat
    elif [ $(echo "$branch >= 6.5" | bc) -eq 1 ]; then
        branch="mad-hatter"
    elif [ $(echo "$branch >= 6.0" | bc) -eq 1 ]; then
        branch="alice"
    else
        echo "Exiting: Unable to find branch name"
        exit 1
    fi

    # file_name=couchbase-server-enterprise-$build-centos7.x86_64.rpm
    file_name=couchbase-server-enterprise_$build-ubuntu20.04_amd64.deb
    build_link="http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-server/$branch/$build_num/$file_name"

    # cleanup_cmd="service couchbase-server stop ; rpm -qa | grep couchbase | xargs rpm -e ; rm -rf /opt/couchbase ; rm -f /etc/couchbase.d/config_profile"
    cleanup_cmd='service couchbase-server stop ; apt-get remove -y "couchbase*" ; rm -rf /opt/couchbase ; rm -f /etc/couchbase.d/config_profile'
    start_cmd="$serverless_cmd ; service couchbase-server start"
    if [ $vagrant_install = "true" ]
    then
        install_cmd="$time_sync && $cleanup_cmd ; mount -a ; dpkg -i /vagrant/$file_name ; $start_cmd"
    else
        install_cmd="$time_sync && $cleanup_cmd ; dpkg -i $file_name ; $start_cmd ; rm -f $file_name"
    fi

    if [ $del_build == true ]; then
        echo "Deleting :: $file_name"
        rm -f $build_dir/$file_name
        exit $?
    fi

    echo "################################################################################################################################################################################"
    echo " Branch......$branch"
    echo " Build.......$build"
    echo " File........$file_name"
    echo " Link........$build_link"
    echo "################################################################################################################################################################################"

    if [ ! -f "$build_dir/$file_name" ]; then
        echo "File not exists in build_dir. Downloading now..."
        # wget $build_link --directory-prefix=$build_dir
        /Applications/Free\ Download\ Manager.app/Contents/MacOS/fdm -fs $build_link
        downloading=true
    fi


    echo "File location :: $build_dir/$file_name"

    if [ $download_only == "true" ]; then
        exit 0
    fi

    if [ "$downloading" == "true" ]; then
        echo "Press any key after file download complete..."
        read dummy
    fi

    if [ $vagrant_install = "true" ]
    then
        echo "Removing old builds from $vagrant_path"
        rm -f $vagrant_path/couchbase-server*
        echo "Copying build to $vagrant_path/$file_name"
        cp $build_dir/$file_name $vagrant_path/
    fi
else
    install_cmd='$time_sync && service couchbase-server stop ; apt-get remove -y "couchbase*" ; rm -rf /opt/couchbase ; dpkg -i /vagrant/$file_name ; service couchbase-server start'
fi


if [ "$nodes" == "" ]; then
    echo "Exiting: No nodes to install. Provide using '--ips' option"
    exit 0
fi

for node in $nodes
do
    install_cb_build $node &
done

wait

if [ "$init_node" != "" ]; then
    echo "Sleep for 10 sec. before init cluster"
    sleep 10
    initialize_node
fi

echo Done
