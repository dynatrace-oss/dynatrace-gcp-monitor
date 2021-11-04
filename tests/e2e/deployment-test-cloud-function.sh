#!/bin/bash
#     Copyright 2021 Dynatrace LLC
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

check_function_state()
{
  FUNCTION=$1
  FUNCTION_DESCRIBE=$(gcloud functions describe "$FUNCTION"  --format="json")
  FUNCTION_STATE=$(echo "$FUNCTION_DESCRIBE" | jq -r '.status')
  if [[ "${FUNCTION_STATE}" != *"ACTIVE"* ]]; then
    return 1
  fi
  return 0
}

#todo ms common methods?
# Install YQ
curl -sSLo yq "https://github.com/mikefarah/yq/releases/download/v4.9.8/yq_linux_amd64" && chmod +x yq && sudo mv yq /usr/local/bin/yq

gcloud config set project "${GCP_PROJECT_ID}"

# Create E2E Sample App
echo "Deploying sample app"
gcloud functions deploy "${CLOUD_FUNCTION_NAME}" \
--runtime python37 \
--trigger-http \
--source ./tests/e2e/sample_app/ > /dev/null 2>&1

# Run cloud function deployment.
rm -rf ./e2e_test
mkdir -p ./e2e_test/gcp_iam_roles
cp ./scripts/setup.sh ./e2e_test/setup.sh
cp dynatrace-gcp-function.zip ./e2e_test/dynatrace-gcp-function.zip
cp ./gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml ./e2e_test/gcp_iam_roles/

cat <<EOF > activation.config.e2e.yaml
googleCloud:
  common:
    dynatraceUrlSecretName: "${DYNATRACE_URL_SECRET_NAME}"
    dynatraceAccessKeySecretName: "${DYNATRACE_ACCESS_KEY_SECRET_NAME}"
    serviceAccount: "${IAM_SERVICE_ACCOUNT}"
    iamRole: "${IAM_ROLE_METRCICS}"
    requireValidCertificate: false
  metrics:
    pubSubTopic: "${PUBSUB_TOPIC}"
    function: "${METRIC_FORWARDING_FUNCTION}"
    scheduler: "${CLOUD_SCHEDULER}"
EOF
yq eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' activation-config.yaml activation.config.e2e.yaml
ACTIVATION_CONFIG_FILE="./e2e_test/activation-config.yaml"
cp activation-config.yaml "$ACTIVATION_CONFIG_FILE"

cd ./e2e_test || exit 1
echo "Deploying gcp cloud function"
echo -e "$GCP_PROJECT_ID\ns\n$DYNATRACE_URL\n$DYNATRACE_ACCESS_KEY" | ./setup.sh --use-local-function-zip --auto-default

# Verify if function is running
echo
echo -n "Verifying deployment result"
CLOUD_FUNCTION_STATE=0

for i in {1..60}
do
  check_function_state "$METRIC_FORWARDING_FUNCTION"
  CLOUD_FUNCTION_STATE=$?
  if [[ ${CLOUD_FUNCTION_STATE} == 0 ]]; then
    break
  fi
  sleep 10
  echo -n "."
done

# Generate load on GC Function
DEPLOYMENT_TYPE="metrics"
for i in {1..5}; do
  curl -s "https://us-central1-${GCP_PROJECT_ID}.cloudfunctions.net/${CLOUD_FUNCTION_NAME}?deployment_type=${DEPLOYMENT_TYPE}&build_id=${TRAVIS_BUILD_ID}" \
  -H "Authorization: bearer $(gcloud auth print-identity-token)"
  echo
done

echo
if [[ ${CLOUD_FUNCTION_STATE} == 0 ]]; then
  echo "Deployment completed successfully"
  exit 0
else
  echo "Deployment failed"
  exit 1
fi
