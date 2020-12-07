#!/bin/bash

branch=NA
build=$1
nodes=$2
del_build=false

download_only=false
only_list_builds=false
build_dir=/Users/ashwin/works/builds

while [ $# -ne 0 ]; do
    if [ "$1" == "-b" ]; then
        build=$2
        shift ; shift
    elif [ "$1" == "-n" ]; then
        nodes=$2
        shift ; shift
    elif [ "$1" == "--download" ]; then
        download_only=true
        shift
    elif [ "$1" == "--list" ]; then
        only_list_builds=true
        shift
    elif [ "$1" == "--delete" ]; then
        del_build=true
        shift
    else
        echo "Exiting: Invalid arg '$1'"
        exit 1
    fi
done

if [ $only_list_builds == true ]; then
    ls $build_dir | cut -d'-' -f4 -f5
    exit $?
fi

branch=$(echo $build | cut -c1-3)
build_num=$(echo $build | cut -d'-' -f 2)
if [ $(echo "$branch >= 7.0" | bc) -eq 1 ]; then
    branch=cheshire-cat
elif [ $(echo "$branch >= 6.5" | bc) -eq 1 ]; then
    branch="mad-hatter"
else
    echo "Exiting: Unable to find branch name"
    exit 1
fi

file_name=couchbase-server-enterprise-$build-centos7.x86_64.rpm
build_link="http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-server/$branch/$build_num/$file_name"
time_sync="timedatectl set-timezone America/Los_Angeles"
install_cmd="$time_sync && service couchbase-server stop ; rpm -e couchbase-server ; rm -rf /opt/couchbase ; yum install -y $file_name ; service couchbase-server start ; rm -f $file_name"

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
    wget $build_link --directory-prefix=$build_dir
fi

echo "File location :: $build_dir/$file_name"

if [ $download_only == "true" ]; then
    exit 0
fi

if [ "$nodes" == "" ]; then
    echo "Exiting: No nodes to install. Provide using '--ips' option"
    exit 0
fi

install_cb_build() {
    echo "$1: Removing old rpms"
    sshpass -p couchbase ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$1 -t "rm -f ~/couchbase-server*"
    echo "$1: Copying build"
    sshpass -p couchbase scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$build_dir/$file_name" root@$1:~/
    echo "$1: Starting installation"
    sshpass -p couchbase ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$node -t "$install_cmd" > /dev/null
    echo "$1: Installation complete"
}

for node in $nodes
do
    install_cb_build $node &
done

wait

echo Done
