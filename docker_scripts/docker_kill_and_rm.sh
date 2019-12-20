#!/bin/bash

ID=$(sudo docker ps -a -f ancestor=litter_robot_intercept -q)

if [[ -z "$ID" ]]; then
    echo "No litter robot monitor process running"
    exit 0
fi

sudo docker ps -f id=$ID

sudo docker kill $ID

sudo docker rm $ID
