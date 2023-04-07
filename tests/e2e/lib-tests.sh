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

# shellcheck disable=SC2034  # Unused variables left for readability
TEST_YQ=ext_tools/yq_linux_x64
TEST_JQ=ext_tools/jq_linux_x64

create_sample_app() {
  echo "Deploying sample app"
  gcloud functions deploy "${CLOUD_FUNCTION_NAME}" \
  --runtime python37 \
  --trigger-http \
  --source ./tests/e2e/sample_app/ > /dev/null 2>&1
}

check_container_state() {
  CONTAINER=$1
  CONTAINER_STATE=$(kubectl -n dynatrace get pods -o=jsonpath="{.items[*].status.containerStatuses[?(@.name==\"${CONTAINER}\")].state}")
  echo
  echo "$CONTAINER_STATE"
  if [[ "${CONTAINER_STATE}" != *"running"* ]]; then
    return 1
  fi
  return 0
}

check_deployment_status() {
  METRICS_CONTAINER_STATE=0
  LOGS_CONTAINER_STATE=0

  for _ in {1..60}
  do
    if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
      check_container_state "dynatrace-gcp-monitor-metrics"
      METRICS_CONTAINER_STATE=$?
    fi

    if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then
      check_container_state "dynatrace-gcp-monitor-logs"
      LOGS_CONTAINER_STATE=$?
    fi

    if [[ ${METRICS_CONTAINER_STATE} == 0 ]] && [[ ${LOGS_CONTAINER_STATE} == 0 ]]; then
      break
    fi

    sleep 10
    echo -n "."
  done

  if [[ ${METRICS_CONTAINER_STATE} == 0 ]] && [[ ${LOGS_CONTAINER_STATE} == 0 ]]; then
    echo "Deployment completed successfully"
  else
    echo "Deployment failed"
    return 1
  fi
}

generate_load_on_sample_app() {
  for _ in {1..5}; do
    curl -s "https://us-central1-${GCP_PROJECT_ID}.cloudfunctions.net/${CLOUD_FUNCTION_NAME}?deployment_type=${DEPLOYMENT_TYPE}&build_id=${TRAVIS_BUILD_ID}" \
    -H "Authorization: bearer $(gcloud auth print-identity-token)"
    echo
  done
}

create_values_e2e_file() {
  cat <<EOF > values.e2e.yaml
gcpProjectId: "${GCP_PROJECT_ID}"
deploymentType: "${DEPLOYMENT_TYPE}"
dynatraceAccessKey: "${DYNATRACE_ACCESS_KEY}"
dynatraceUrl: "${DYNATRACE_URL}"
logsSubscriptionId: "${PUBSUB_SUBSCRIPTION}"
requireValidCertificate: "false"
dockerImage: "${GCR_NAME}:e2e-travis-test-${TRAVIS_BUILD_ID}"
activeGate:
  useExisting: "true"
  dynatracePaasToken: "${DYNATRACE_PAAS_TOKEN}"
serviceAccount: "${IAM_SERVICE_ACCOUNT}"
scopingProjectSupportEnabled: "true"
gcpServicesYaml: |
  services:
    - service: api
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloudsql_database
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_function
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: datastore_request
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: filestore_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gce_instance
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: gcs_bucket
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: https_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_http_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_cluster
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_container
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_node
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_pod
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsublite_subscription_partition
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsublite_topic_partition
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_snapshot
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_subscription
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_topic
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_run_revision
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
EOF
}


create_activation_config_e2e_file() {
  cat <<EOF > activation.config.e2e.yaml
googleCloud:
  required:
    gcpProjectId: "${GCP_PROJECT_ID}"
    dynatraceTenantUrl: "${DYNATRACE_URL}"
    dynatraceApiToken: "${DYNATRACE_ACCESS_KEY}"
    cloudFunctionSize: s
    cloudFunctionRegion: us-central1
    preferredAppEngineRegion: us-central
  common:
    dynatraceUrlSecretName: "${DYNATRACE_URL_SECRET_NAME}"
    dynatraceAccessKeySecretName: "${DYNATRACE_ACCESS_KEY_SECRET_NAME}"
    serviceAccount: "${IAM_SERVICE_ACCOUNT}"
    iamRole: "${IAM_ROLE_METRCICS}"
    requireValidCertificate: false
    scopingProjectSupportEnabled: true
  metrics:
    pubSubTopic: "${PUBSUB_TOPIC}"
    function: "${METRIC_FORWARDING_FUNCTION}"
    scheduler: "${CLOUD_SCHEDULER}"
activation: |
  services:
    - service: api
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloudsql_database
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_function
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: datastore_request
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: filestore_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gce_instance
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: gcs_bucket
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: https_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_http_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_cluster
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_container
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_node
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_pod
      featureSets:
       - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsublite_subscription_partition
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsublite_topic_partition
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_snapshot
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_subscription
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_topic
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_run_revision
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
EOF
}

performance_test() {
    echo
    echo "#####PERFORMANCE TEST#####"

    echo "Setting variables to use GCP simulator"
    kubectl set env deployment dynatrace-gcp-monitor -c dynatrace-gcp-monitor-metrics -n dynatrace GCP_PROJECT_ID="fake-project-0" \
        GCP_METADATA_URL="http://${GCP_SIMULATOR_IP}/metadata.google.internal/computeMetadata/v1" \
        GCP_CLOUD_RESOURCE_MANAGER_URL="http://${GCP_SIMULATOR_IP}/cloudresourcemanager.googleapis.com/v1" \
        GCP_SERVICE_USAGE_URL="http://${GCP_SIMULATOR_IP}/serviceusage.googleapis.com/v1" \
        GCP_MONITORING_URL="http://${GCP_SIMULATOR_IP}/monitoring.googleapis.com/v3" \
        GCP_SECRET_ROOT="http://${GCP_SIMULATOR_IP}/secretmanager.googleapis.com/v1"

    echo "Wait until previous pod terminates"
    for _ in {1..60}
    do
      sleep 10

      PODS_COUNT=$(kubectl -n dynatrace get pods -o=json | $TEST_JQ -j '.items | length')
      if [[ $PODS_COUNT == 1 ]]; then
        break
      fi

      echo -n "."
    done

    echo
    kubectl -n dynatrace get pods

    check_deployment_status || exit 1
    begin_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")
    echo "Started at: $begin_timestamp"

    echo "Waiting 360s"
    sleep 360
    end_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")
    echo "Ended at: $end_timestamp"

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
      textPayload: (\"Polling finished after\" OR \"Metrics SFM\")
    "
    PERF_LOGS=$(gcloud beta logging read "$LOG_QUERY" --format=json)
    if [[ $PERF_LOGS == "[]" ]]; then
      echo "No logs"
      exit 1
    fi
    echo "$PERF_LOGS" | "$TEST_JQ" '.[-2,-1].textPayload'
    echo "#####PERFORMANCE TEST ENDED#####"
}
