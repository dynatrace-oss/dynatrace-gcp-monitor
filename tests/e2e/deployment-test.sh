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
wget --no-verbose https://github.com/mikefarah/yq/releases/download/3.4.0/yq_linux_amd64 -O /usr/bin/yq && chmod +x /usr/bin/yq

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
gcloud config set project dynatrace-gcp-extension

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
EOF
yq m -i -x ${VALUES_FILE} values.e2e.yaml

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

if [[ ${METRICS_CONTAINER_STATE} == 0 ]] && [[ ${LOGS_CONTAINER_STATE} == 0 ]]; then
  echo "Deployment completed successfully"
  exit 0
else
  echo "Deployment failed"
  exit 1
fi
