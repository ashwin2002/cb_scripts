#!/bin/bash

while [ 1 ]; do
    clear
    date
    echo $@
    $@
    sleep 2
done
