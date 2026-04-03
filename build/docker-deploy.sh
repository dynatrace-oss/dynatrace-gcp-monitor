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

# Set up Docker auth for both Docker Hub (push) and dhi.io (hardened base image pull)
mkdir -p ~/.docker && chmod 0700 ~/.docker
touch ~/.docker/config.json && chmod 0600 ~/.docker/config.json
base64 -d >~/.docker/config.json <<<"$OAO_DOCKER_AUTH"

#build container
./build/version.sh
docker build -t dynatrace/dynatrace-gcp-monitor:v1-latest --build-arg RELEASE_TAG_ARG="${TAG}" .

#tag container
if [[ "${PUSH:-}" == "true" ]]; then
    docker tag dynatrace/dynatrace-gcp-monitor:v1-latest "dynatrace/dynatrace-gcp-monitor:${TAG}"
    docker push dynatrace/dynatrace-gcp-monitor:v1-latest
    docker push "dynatrace/dynatrace-gcp-monitor:${TAG}"
elif [[ "${PUSH:-}" != "true" && "${E2E:-}" == "true" ]]; then
    docker tag dynatrace/dynatrace-gcp-monitor:v1-latest "${ARTIFACT_REGISTRY_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
    docker push "${ARTIFACT_REGISTRY_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
fi
