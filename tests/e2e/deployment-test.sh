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

if [[ $(gcloud pubsub topics list --filter=name:"${PUBSUB_TOPIC}" --format="value(name)") ]]; then
    echo "Topic [${PUBSUB_TOPIC}] already exists, skipping"
else
    gcloud pubsub topics create "${PUBSUB_TOPIC}"
fi

if [[ $(gcloud pubsub subscriptions list --filter=name:"${PUBSUB_SUBSCRIPTION}" --format="value(name)") ]]; then
    echo "Subscription [${PUBSUB_SUBSCRIPTION}] already exists, skipping"
else
    gcloud pubsub subscriptions create "${PUBSUB_SUBSCRIPTION}" --topic="${PUBSUB_TOPIC}" --ack-deadline=120
fi

rm -rf ./e2e_test
mkdir ./e2e_test
cp ./scripts/deploy-helm.sh ./e2e_test/deploy-helm.sh
cp -r ./k8s/helm-chart/dynatrace-gcp-function/ ./e2e_test/dynatrace-gcp-function/

VALUES_FILE="./e2e_test/dynatrace-gcp-function/values.yaml"

sed -i '/^gcpProjectId:/c\gcpProjectId: "'${GCP_PROJECT_ID}'"' ${VALUES_FILE}
sed -i '/^deploymentType:/c\deploymentType: "logs"' ${VALUES_FILE}
sed -i '/^dynatraceAccessKey:/c\dynatraceAccessKey: "'${DYNATRACE_ACCESS_KEY}'"' ${VALUES_FILE}
sed -i '/^dynatraceLogIngestUrl:/c\dynatraceLogIngestUrl: "'${DYNATRACE_LOG_INGEST_URL}'"' ${VALUES_FILE}
sed -i '/^logsSubscriptionId:/c\logsSubscriptionId: "'${PUBSUB_SUBSCRIPTION}'"' ${VALUES_FILE}
sed -i '/^requireValidCertificate:/c\requireValidCertificate: "false"' ${VALUES_FILE}


chmod +x ./e2e_test/deploy-helm.sh
./e2e_test/deploy-helm.sh --service-account e2e-test-dynatrace-gcp-function-sa --role-name e2e_test_dynatrace_function
