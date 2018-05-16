#!/bin/bash

# ssh -L 3306:<db_hostname>:3306 <username>@<ssh_host>.com
# This app expects the preceeding line to be run on the docker host
# prior to operation if the mysql database is not running on the localhost
# or in another docker container visible to this one.

# exit if a simple command exits with a non-zero status
set -e

# if there's a prestart.sh script in the /app directory, run it before starting
PRE_START_PATH=/app/prestart.sh
echo "Checking for script in $PRE_START_PATH"
if [ -f $PRE_START_PATH ] ; then
    echo "Running script $PRE_START_PATH"
    source $PRE_START_PATH
else
    echo "There is no script $PRE_START_PATH"
fi

# Alert the app that it's running in a container
if [ -f /.dockerenv ]; then
    touch /app/isContainerized;
else
    rm -f /app/isContainerized;
fi

# start supervisor
/usr/bin/supervisord --nodaemon
