#!/usr/bin/env bash
#     Copyright 2022 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
set -eu

#build container
./build/version.sh
docker build -t dynatrace/dynatrace-gcp-function:v1-latest --build-arg TRAVIS_TAG_ARG="${TAG}" .

#tag container
if [[ "${PUSH:-}" == "true" ]]; then
    mkdir -p ~/.docker && chmod 0700 ~/.docker
    touch ~/.docker/config.json && chmod 0600 ~/.docker/config.json
    base64 -d >~/.docker/config.json <<<"$OAO_DOCKER_AUTH"

    docker tag dynatrace/dynatrace-gcp-function:v1-latest "dynatrace/dynatrace-gcp-function:${TAG}"
    docker push dynatrace/dynatrace-gcp-function:v1-latest
    docker push "dynatrace/dynatrace-gcp-function:${TAG}"
elif [[ "${PUSH:-}" != "true" && "${E2E:-}" == "true" ]]; then
    docker tag dynatrace/dynatrace-gcp-function:v1-latest "${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
    docker push "${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
fi
