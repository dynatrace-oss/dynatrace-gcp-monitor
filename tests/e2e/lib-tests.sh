#!/usr/bin/env bash
#     Copyright 2020 Dynatrace LLC
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

install_yq() {
  curl -sSLo yq "https://github.com/mikefarah/yq/releases/download/v4.9.8/yq_linux_amd64" && chmod +x yq && sudo mv yq /usr/local/bin/yq
}

create_sample_app() {
  echo "Deploying sample app"
  gcloud functions deploy "${CLOUD_FUNCTION_NAME}" \
  --runtime python37 \
  --trigger-http \
  --source ./tests/e2e/sample_app/ > /dev/null 2>&1
}

generate_load_on_sample_app() {
  for i in {1..5}; do
    curl -s "https://us-central1-${GCP_PROJECT_ID}.cloudfunctions.net/${CLOUD_FUNCTION_NAME}?deployment_type=${DEPLOYMENT_TYPE}&build_id=${TRAVIS_BUILD_ID}" \
    -H "Authorization: bearer $(gcloud auth print-identity-token)"
    echo
  done
}