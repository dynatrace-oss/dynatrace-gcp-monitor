#!/bin/bash
set -eu

#write version file on release
if [[ "${PUSH:-}" == "true" ]]; then
    chmod +x ./build/version.sh
    sh ./build/version.sh
fi

#build contaienr
docker build -f dockerfile -t dynatrace-gcp-function .        

#tag contaienr
if [[ "${PUSH:-}" == "true" ]]; then
    mkdir -p ~/.docker && chmod 0700 ~/.docker
    touch ~/.docker/config.json && chmod 0600 ~/.docker/config.json
    base64 -d >~/.docker/config.json <<<"$OAO_DOCKER_AUTH"
    docker tag dynatrace-gcp-function dynatrace/dynatrace-gcp-function:$TAG
    docker push dynatrace/dynatrace-gcp-function:$TAG
    docker tag dynatrace-gcp-function dynatrace/dynatrace-gcp-function:latest
    docker push dynatrace/dynatrace-gcp-function:latest
fi