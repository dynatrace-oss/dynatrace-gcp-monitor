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

# Create Log Router Sink.
if [[ $(gcloud logging sinks  list --filter=name:"${LOG_ROUTER}" --format="value(name)") ]]; then
    echo "Log Router [${LOG_ROUTER}] already exists, skipping"
else
  gcloud logging sinks create "${LOG_ROUTER}" "pubsub.googleapis.com/projects/${GCP_PROJECT_ID}/topics/${PUBSUB_TOPIC}" \
    --log-filter="resource.type=\"cloud_function\" AND resource.labels.function_name=\"${CLOUD_FUNCTION_NAME}\"" --description="Simple Sink for E2E tests" > /dev/null 2>&1
fi

writerIdentity=$(gcloud logging sinks describe "${LOG_ROUTER}" --format json | "$TEST_JQ" -r '.writerIdentity')
gcloud pubsub topics add-iam-policy-binding "${PUBSUB_TOPIC}" --member "${writerIdentity}" --role roles/pubsub.publisher > /dev/null 2>&1

create_sample_app

# Run helm deployment.
rm -rf ./e2e_test
mkdir ./e2e_test
tar -C ./e2e_test -xf ./artefacts/helm-deployment-package.tar

VALUES_FILE="./dynatrace-gcp-monitor/values.yaml"

cd ./e2e_test/helm-deployment-package || exit 1

if [[ $TRAVIS_BRANCH == 'PCLOUDS-1718-add-perf-test' ]]; then
  echo "Add permission to read logs for perf test"
  echo "  - logging.views.access" >> ./gcp_iam_roles/dynatrace-gcp-monitor-metrics-role.yaml
fi

# Create values.e2e.yaml including lines to be replaced. Adding cloud run revision to list of default services
create_values_e2e_file

"$TEST_YQ" eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' ${VALUES_FILE} values.e2e.yaml

gcloud container clusters get-credentials "${K8S_CLUSTER}" --region us-central1 --project "${GCP_PROJECT_ID}"

./deploy-helm.sh --role-name "${IAM_ROLE_PREFIX}" --quiet || exit 1

# Verify containers running
echo
echo -n "Verifying deployment result"
check_deployment_status || exit 1

echo
kubectl -n dynatrace get pods

generate_load_on_sample_app


if [[ $TRAVIS_BRANCH == 'PCLOUDS-1718-add-perf-test' ]]; then
  echo "#####PERFOMANCE TEST#####"
  begin_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")

  echo "Setting variables to use GCP simulator"
  kubectl set env deployment dynatrace-gcp-monitor -c dynatrace-gcp-monitor-metrics -n dynatrace GCP_PROJECT_ID="fake-project-0" \
      GCP_METADATA_URL="http://${GCP_SIMULATOR_IP}/metadata.google.internal/computeMetadata/v1" \
      GCP_CLOUD_RESOURCE_MANAGER_URL="http://${GCP_SIMULATOR_IP}/cloudresourcemanager.googleapis.com/v1" \
      GCP_SERVICE_USAGE_URL="http://${GCP_SIMULATOR_IP}/serviceusage.googleapis.com/v1" \
      GCP_MONITORING_URL="http://${GCP_SIMULATOR_IP}/monitoring.googleapis.com/v3" \
      GCP_SECRET_ROOT="http://${GCP_SIMULATOR_IP}/secretmanager.googleapis.com/v1"

  check_deployment_status || exit 1

  echo "Waiting 360s"
  sleep 360
  end_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")

  echo "Wait until logs will be vissible in GCP: 30s"
  sleep 30
  LOG_QUERY="
    timestamp>=\"$begin_timestamp\" AND
    timestamp<=\"$end_timestamp\" AND
    resource.type=k8s_container AND
    resource.labels.project_id=$GCP_PROJECT_ID AND
    resource.labels.location=us-central1 AND
    resource.labels.cluster_name=$K8S_CLUSTER AND
    resource.labels.namespace_name=dynatrace AND
    labels.k8s-pod/app=dynatrace-gcp-monitor AND
    severity>=DEFAULT AND
    textPayload:Polling finished after
  "
  PERF_LOGS=$(gcloud beta logging read "$LOG_QUERY" --format=json)
  echo "$PERF_LOGS" | "$TEST_JQ" '.[].textPayload'
fi
