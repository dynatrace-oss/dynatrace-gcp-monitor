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

check_container_state()
{
  CONTAINER=$1
  CONTAINER_STATE=$(kubectl -n dynatrace get pods -o=jsonpath="{.items[*].status.containerStatuses[?(@.name==\"${CONTAINER}\")].state}")
  if [[ "${CONTAINER_STATE}" != *"running"* ]]; then
    return 1
  fi
  return 0
}

while (( "$#" )); do
    case "$1" in
            "--logs")
                DEPLOYMENT_TYPE="logs"
                shift
            ;;

            "--metrics")
                DEPLOYMENT_TYPE="metrics"
                shift
            ;;

            "--all")
                DEPLOYMENT_TYPE="all"
                shift
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

# Install YQ
curl -sSLo yq "https://github.com/mikefarah/yq/releases/download/v4.9.8/yq_linux_amd64" && chmod +x yq && sudo mv yq /usr/local/bin/yq

# Install kubectl.
curl -sSLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && sudo mv kubectl /usr/local/bin/kubectl

# Install helm.
wget --no-verbose https://get.helm.sh/helm-v3.5.3-linux-amd64.tar.gz
FILE=./helm-v3.5.3-linux-amd64.tar.gz
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 1
fi
tar -zxvf helm-v3.5.3-linux-amd64.tar.gz
FILE=./linux-amd64/helm
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 1
fi

sudo mv linux-amd64/helm /usr/local/bin/helm

# Create Pub/Sub topic and subscription.
gcloud config set project "${GCP_PROJECT_ID}"

if [[ $(gcloud pubsub topics list --filter=name:"${PUBSUB_TOPIC}" --format="value(name)") ]]; then
    echo "Topic [${PUBSUB_TOPIC}] already exists, skipping"
else
    gcloud pubsub topics create "${PUBSUB_TOPIC}"
fi

if [[ $(gcloud pubsub subscriptions list --filter=name:"${PUBSUB_SUBSCRIPTION}" --format="value(name)") ]]; then
    echo "Subscription [${PUBSUB_SUBSCRIPTION}] already exists, skipping"
else
    gcloud pubsub subscriptions create "${PUBSUB_SUBSCRIPTION}" --topic="${PUBSUB_TOPIC}" --ack-deadline=120 --message-retention-duration=86400
fi

# Create Log Router Sink
if [[ $(gcloud logging sinks  list --filter=name:"${LOG_ROUTER}" --format="value(name)") ]]; then
    echo "Log Router [${LOG_ROUTER}] already exists, skipping"
else
  gcloud logging sinks create "${LOG_ROUTER}" "pubsub.googleapis.com/projects/${GCP_PROJECT_ID}/topics/${PUBSUB_TOPIC}" \
    --log-filter='resource.type="cloud_function" AND resource.labels.function_name="sample_app"' --description="Simple Sink for E2E tests" > /dev/null 2>&1
fi

writerIdentity=$(gcloud logging sinks describe "${LOG_ROUTER}" --format json | jq -r '.writerIdentity')
gcloud pubsub topics add-iam-policy-binding "${PUBSUB_TOPIC}" --member ${writerIdentity} --role roles/pubsub.publisher > /dev/null 2>&1

# Create E2E Sample App
gcloud functions deploy sample_app \
--runtime python37 \
--trigger-http \
--source ./tests/e2e/sample_app/ > /dev/null 2>&1

# Run helm deployment.
rm -rf ./e2e_test
mkdir ./e2e_test
cp ./scripts/deploy-helm.sh ./e2e_test/deploy-helm.sh
cp -r ./k8s/helm-chart/dynatrace-gcp-function/ ./e2e_test/dynatrace-gcp-function/

VALUES_FILE="./e2e_test/dynatrace-gcp-function/values.yaml"

cat <<EOF > values.e2e.yaml
gcpProjectId: "${GCP_PROJECT_ID}"
deploymentType: "${DEPLOYMENT_TYPE}"
dynatraceAccessKey: "${DYNATRACE_ACCESS_KEY}"
dynatraceLogIngestUrl: "${DYNATRACE_LOG_INGEST_URL}"
dynatraceUrl: "${DYNATRACE_URL}"
logsSubscriptionId: "${PUBSUB_SUBSCRIPTION}"
requireValidCertificate: "false"
dockerImage: "${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
activeGate:
  useExisting: "false"
  dynatracePaasToken: "${DYNATRACE_PAAS_TOKEN}"
EOF
yq eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' ${VALUES_FILE} values.e2e.yaml

gcloud container clusters get-credentials "${K8S_CLUSTER}" --region us-central1 --project ${GCP_PROJECT_ID}

cd ./e2e_test || exit 1
./deploy-helm.sh --service-account "${IAM_SERVICE_ACCOUNT}" --role-name "${IAM_ROLE_PREFIX}" --quiet || exit 1

# Verify containers running
echo
echo -n "Verifying deployment result"
METRICS_CONTAINER_STATE=0
LOGS_CONTAINER_STATE=0

for i in {1..60}
do
  if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
    check_container_state "dynatrace-gcp-function-metrics"
    METRICS_CONTAINER_STATE=$?
  fi

  if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then
    check_container_state "dynatrace-gcp-function-logs"
    LOGS_CONTAINER_STATE=$?
  fi

  if [[ ${METRICS_CONTAINER_STATE} == 0 ]] && [[ ${LOGS_CONTAINER_STATE} == 0 ]]; then
    break
  fi

  sleep 10
  echo -n "."
done

echo
kubectl -n dynatrace get pods

# Generate load on GC Function
for i in {1..5}; do
  curl "https://us-central1-${GCP_PROJECT_ID}.cloudfunctions.net/sample_app?deployment_type=${DEPLOYMENT_TYPE}&build_id=${TRAVIS_BUILD_ID}" \
  -H "Authorization: bearer $(gcloud auth print-identity-token)"
done

if [[ ${METRICS_CONTAINER_STATE} == 0 ]] && [[ ${LOGS_CONTAINER_STATE} == 0 ]]; then
  echo "Deployment completed successfully"
  exit 0
else
  echo "Deployment failed"
  exit 1
fi
