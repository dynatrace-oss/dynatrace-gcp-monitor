#!/bin/bash
set -eu

#build container
./build/version.sh
docker build -t dynatrace/dynatrace-gcp-function .

#tag contaiener
if [[ "${PUSH:-}" == "true" ]]; then
    mkdir -p ~/.docker && chmod 0700 ~/.docker
    touch ~/.docker/config.json && chmod 0600 ~/.docker/config.json
    base64 -d >~/.docker/config.json <<<"$OAO_DOCKER_AUTH"

    docker tag dynatrace/dynatrace-gcp-function:latest dynatrace/dynatrace-gcp-function:${TAG}
    docker push dynatrace/dynatrace-gcp-function:latest
    docker push dynatrace/dynatrace-gcp-function:${TAG}
elif [[ "${PUSH:-}" != "true" && "${E2E:-}" == "true" ]]; then
    docker tag dynatrace/dynatrace-gcp-function ${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}
    docker push ${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}
fi
