#!/usr/bin/env bash

# This script is used to launch the application.

if [ -z "${MINIO_ACCESS_KEY}" ]; then
    echo "MINIO_ACCESS_KEY is not set"
    exit 1
fi

if [ -z "${MINIO_SECRET_KEY}" ]; then
    echo "MINIO_SECRET_KEY is not set"
    exit 1
fi

if [ -z "${LABEL_STUDIO_TOKEN}" ]; then
    echo "LABEL_STUDIO_TOKEN is not set"
    exit 1
fi

LABEL_STUDIO_SERVER=${LABEL_STUDIO_SERVER:-"app:8080"}
MINIO_SERVER=${MINIO_SERVER:-"minio:9000"}
DINGTALK_ACCESS_KEY=${DINGTALK_ACCESS_KEY:-""}

# Remove http:// or https:// from LABEL_STUDIO_SERVER
LABEL_STUDIO_SERVER=${LABEL_STUDIO_SERVER#*://}
MINIO_SERVER=${MINIO_SERVER#*://}

MINUTES_BETWEEN_RUNS=${MINUTES_BETWEEN_RUNS:-"1"}

# Start the processes
echo "Starting pfetcher-monitor"
pfetcher-monitor minio -u ${MINIO_ACCESS_KEY} -p ${MINIO_SECRET_KEY} -d /data/paper-downloader/ -t ${DINGTALK_ACCESS_KEY} -s ${MINIO_SERVER} &

echo "Starting pfetcher-syncer"
pfetcher-syncer --minutes ${MINUTES_BETWEEN_RUNS} --ls-server http://${LABEL_STUDIO_SERVER} --token ${LABEL_STUDIO_TOKEN} --minio-server http://${MINIO_SERVER} --access-key ${MINIO_ACCESS_KEY} --secret-key ${MINIO_SECRET_KEY} &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?