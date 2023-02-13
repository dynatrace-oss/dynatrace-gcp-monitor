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

source ./tests/e2e/lib-tests.sh

check_function_state()
{
  FUNCTION=$1
  FUNCTION_DESCRIBE=$(gcloud functions describe "$FUNCTION"  --format="json")
  FUNCTION_STATE=$(echo "$FUNCTION_DESCRIBE" | "$TEST_JQ" -r '.status')
  if [[ "${FUNCTION_STATE}" != *"ACTIVE"* ]]; then
    return 1
  fi
  return 0
}

gcloud config set project "${GCP_PROJECT_ID}"
create_sample_app

# Run cloud function deployment.
rm -rf ./e2e_test
mkdir ./e2e_test
unzip -d ./e2e_test ./artefacts/function-deployment-package.zip
cp ./artefacts/dynatrace-gcp-monitor.zip ./e2e_test

ACTIVATION_CONFIG_FILE="./activation-config.yaml"

cd ./e2e_test || exit 1

# Create activation.config.e2e.yaml including lines to be replaced. Adding cloud run revision to list of default services
create_activation_config_e2e_file

"$TEST_YQ" eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' "$ACTIVATION_CONFIG_FILE" activation.config.e2e.yaml

echo "Deploying gcp cloud function"
./setup.sh --use-local-function-zip --auto-default

# Verify if function is running
echo
echo -n "Verifying deployment result"
CLOUD_FUNCTION_STATE=0

for _ in {1..60}
do
  check_function_state "$METRIC_FORWARDING_FUNCTION"
  CLOUD_FUNCTION_STATE=$?
  if [[ ${CLOUD_FUNCTION_STATE} == 0 ]]; then
    break
  fi
  sleep 10
  echo -n "."
done

generate_load_on_sample_app

if [[ ${CLOUD_FUNCTION_STATE} == 0 ]]; then
  echo "Deployment completed successfully"
  exit 0
else
  echo "Deployment failed"
  exit 1
fi
