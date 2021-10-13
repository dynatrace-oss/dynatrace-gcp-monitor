#!/usr/bin/env bash
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

source ./lib.sh

trap onFailure ERR

generate_test_log() {
  DATE=$(date --iso-8601=seconds)
  cat <<EOF
{
"timestamp": "$DATE",
"cloud.provider": "gcp",
"content": "GCP Log Forwarder installation log",
"severity": "INFO"
}
EOF
}

check_dynatrace_log_ingest_url() {
  if RESPONSE=$(curl -k -s -X POST -d "$(generate_test_log)" "$DYNATRACE_LOG_INGEST_URL/api/v2/logs/ingest" -w "<<HTTP_CODE>>%{http_code}" -H "accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" --connect-timeout 20); then
    CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<<"$RESPONSE")
    RESPONSE=$(sed -r 's/(.*)<<HTTP_CODE>>.*$/\1/' <<<"$RESPONSE")
    if [ "$CODE" -ge 300 ]; then
      err "Failed to send a test log to Dynatrace - please verify provided log ingest url ($DYNATRACE_LOG_INGEST_URL) and API token. $RESPONSE"
      exit 1
    fi
  else
    warn "Failed to connect with provided log ingest url ($DYNATRACE_LOG_INGEST_URL) to send a test log. It can be ignored if ActiveGate does not allow public access."
  fi
}

check_dynatrace_docker_login() {
  check_if_parameter_is_empty "$DYNATRACE_PAAS_KEY" ".activeGate.dynatracePaasToken, Since the .activeGate.useExisting is false you have to generate and fill PaaS token in the Values file"

  DOCKER_LOGIN=$(helm template dynatrace-gcp-function --show-only templates/active-gate-statefulset.yaml | tr '\015' '\n' | grep "envid:" | awk '{print $2}')

  if RESPONSE=$(curl -ksS -w "%{http_code}" -o /dev/null -u "${DOCKER_LOGIN}:${DYNATRACE_PAAS_KEY}" "${DYNATRACE_URL}/v2/"); then
    if [[ $RESPONSE == "200" ]]; then
      echo "Successfully logged to Dynatrace cluster Docker registry"
      echo "The ActiveGate will be deployed in k8s cluster"
    else
      err "Couldn't log to Dynatrace cluster Docker registry. Is your PaaS token a valid one?"
      exit 1
    fi
  else
    warn "Failed to connect to Dynatrace endpoint ($DYNATRACE_URL) to check Docker registry login. It can be ignored if Dynatrace does not allow public access."
  fi
}

print_help() {
  printf "
usage: deploy-helm.sh [--service-account SA_NAME] [--role-name ROLE_NAME] [--create-autopilot-cluster] [--autopilot-cluster-name CLUSTER_NAME] [--upgrade-extensions] [--auto-yes] [--quiet]

arguments:
    --service-account SA_NAME
                            IAM service account name
                            By default 'dynatrace-gcp-function-sa' will be used.
    --role-name ROLE_NAME
                            IAM role name prefix
                            By default 'dynatrace_function' will be used as prefix (e.g. dynatrace_function.metrics).
    --create-autopilot-cluster
                            Create new GKE Autopilot cluster and deploy dynatrace-gcp-function into it.
    --autopilot-cluster-name CLUSTER_NAME
                            Name of new GKE Autopilot cluster to be created if '--create-autopilot-cluster option' was selected.
                            By default 'dynatrace-gcp-function' will be used.
    --upgrade-extensions
                            Upgrade all extensions into dynatrace cluster
    -y, --auto-yes
                            By default 'yes' will be answer for all user input prompts from GCP.
    -q, --quiet
                            Reduce output verbosity, progress messages and errors are still printed.
    -h, --help
                            Show this help message and exit
    "
}

# test pre-requirements
test_req_yq
test_req_gcloud
test_req_kubectl
test_req_helm

CMD_OUT_PIPE="/dev/stdout"
AUTOPILOT_CLUSTER_NAME="dynatrace-gcp-function"

while (( "$#" )); do
    case "$1" in
            "--service-account")
                SA_NAME=$2
                shift; shift
            ;;

            "--role-name")
                ROLE_NAME=$2
                shift; shift
            ;;

            "--create-autopilot-cluster")
                CREATE_AUTOPILOT_CLUSTER="Y"
                shift
            ;;

            "--autopilot-cluster-name")
                AUTOPILOT_CLUSTER_NAME=$2
                shift; shift
            ;;

            "--upgrade-extensions")
                UPGRADE_EXTENSIONS="Y"
                shift
            ;;

            "-y" | "--auto-yes")
                export CLOUDSDK_CORE_DISABLE_PROMPTS=1
                shift; shift
            ;;

            "-q" | "--quiet")
                CMD_OUT_PIPE="/dev/null"
                shift
            ;;

            "--s3-url")
                EXTENSION_S3_URL=$2
                shift; shift
            ;;

            "-h" | "--help")
                print_help
                exit 0
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

GCP_PROJECT=$(helm show values ./dynatrace-gcp-function --jsonpath "{.gcpProjectId}")
DEPLOYMENT_TYPE=$(helm show values ./dynatrace-gcp-function --jsonpath "{.deploymentType}")
readonly DYNATRACE_ACCESS_KEY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceAccessKey}")
readonly DYNATRACE_URL=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceUrl}" | sed 's:/*$::')
readonly DYNATRACE_LOG_INGEST_URL=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceLogIngestUrl}" | sed 's:/*$::')
readonly USE_EXISTING_ACTIVE_GATE=$(helm show values ./dynatrace-gcp-function --jsonpath "{.activeGate.useExisting}")
readonly DYNATRACE_PAAS_KEY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.activeGate.dynatracePaasToken}")
readonly LOGS_SUBSCRIPTION_ID=$(helm show values ./dynatrace-gcp-function --jsonpath "{.logsSubscriptionId}")
readonly USE_PROXY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.useProxy}")
readonly HTTP_PROXY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.httpProxy}")
readonly HTTPS_PROXY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.httpsProxy}")
SERVICES_FROM_ACTIVATION_CONFIG=$(yq e '.gcpServicesYaml' ./dynatrace-gcp-function/values.yaml | yq e -j '.services[]' - | jq -r '. | "\(.service)/\(.featureSets[])"')
API_TOKEN_SCOPES=('"metrics.ingest"' '"logs.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"')

if [ -z "$EXTENSION_S3_URL" ]; then
  EXTENSION_S3_URL="https://dynatrace-gcp-extensions.s3.amazonaws.com"
else
  warn "Development mode on: custom S3 url link."
fi

if [ -z "$GCP_PROJECT" ]; then
  GCP_PROJECT=$(gcloud config get-value project 2>/dev/null)
fi

gcloud config set project "$GCP_PROJECT"
echo "- Deploying dynatrace-gcp-function in [$GCP_PROJECT]"

if [ -z "$SA_NAME" ]; then
  SA_NAME="dynatrace-gcp-function-sa"
fi

if [ -z "$ROLE_NAME" ]; then
  ROLE_NAME="dynatrace_function"
fi

if [ -z "$DEPLOYMENT_TYPE" ]; then
  DEPLOYMENT_TYPE="all"
  echo "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == logs ]]; then
  echo "Deploying $DEPLOYMENT_TYPE ingest"
  API_TOKEN_SCOPES=('"logs.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"')
elif [[ $DEPLOYMENT_TYPE == metrics ]]; then
  echo "Deploying $DEPLOYMENT_TYPE ingest"
  API_TOKEN_SCOPES=('"metrics.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"')
else
  err "Invalid DEPLOYMENT_TYPE: $DEPLOYMENT_TYPE. use one of: 'all', 'metrics', 'logs'"
  exit 1
fi

if [ -n "$USE_PROXY" ]; then
  if [ -z "$HTTP_PROXY" ] || [ -z "$HTTPS_PROXY" ]; then
    err "The useProxy is set, please fill httpProxy or httpsProxy in your values file"
    exit 1
  fi
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]] || [[ ($DEPLOYMENT_TYPE == logs && $USE_EXISTING_ACTIVE_GATE == false) ]]; then
  check_if_parameter_is_empty "$DYNATRACE_URL" "DYNATRACE_URL"
  check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY" "DYNATRACE_ACCESS_KEY"
  check_url "$DYNATRACE_URL" "$DYNATRACE_URL_REGEX" "Not correct dynatraceUrl. Example of proper Dynatrace environment endpoint: https://<your_environment_ID>.live.dynatrace.com"
  check_api_token "$DYNATRACE_URL" 
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then

  if [[ $USE_EXISTING_ACTIVE_GATE == false ]]; then
    check_dynatrace_docker_login
  else
    echo "Using an existing Active Gate"
    check_if_parameter_is_empty "$DYNATRACE_LOG_INGEST_URL" "DYNATRACE_LOG_INGEST_URL"
    check_url "$DYNATRACE_LOG_INGEST_URL" "$ACTIVE_GATE_TARGET_URL_REGEX" "Not correct dynatraceLogIngestUrl. Example of proper ActiveGate endpoint used to ingest logs to Dynatrace: https://<your_activegate_IP_or_hostname>:9999/e/<your_environment_ID>"
    check_api_token "$DYNATRACE_LOG_INGEST_URL"
    check_dynatrace_log_ingest_url
  fi

  check_if_parameter_is_empty "$LOGS_SUBSCRIPTION_ID" "LOGS_SUBSCRIPTION_ID"

  readonly LOGS_SUBSCRIPTION_FULL_ID="projects/$GCP_PROJECT/subscriptions/$LOGS_SUBSCRIPTION_ID"

  if ! [[ $(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(name)") ]]; then
    err "Pub/Sub subscription '$LOGS_SUBSCRIPTION_FULL_ID' does not exist"
    exit 1
  fi

  INVALID_PUBSUB=false

  readonly ACK_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(ackDeadlineSeconds)")
  if [[ "$ACK_DEADLINE" != "120" ]]; then
    err "Invalid Pub/Sub subscription Acknowledgement Deadline - should be '120's (2 minutes), was '$ACK_DEADLINE's"
    INVALID_PUBSUB=true
  fi

  readonly MESSAGE_RETENTION_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(messageRetentionDuration)")
  if [[ "$MESSAGE_RETENTION_DEADLINE" != "86400s" ]]; then
    err "Invalid Pub/Sub subscription Acknowledge Deadline - should be '86400s' (24 hours), was '$MESSAGE_RETENTION_DEADLINE'"
    INVALID_PUBSUB=true
  fi

  if "$INVALID_PUBSUB"; then
    exit 1
  fi

  if [[ $USE_EXISTING_ACTIVE_GATE == true ]]; then
    ACTIVE_GATE_CONNECTIVITY=Y
    ACTIVE_GATE_STATE=$(curl -ksS "${DYNATRACE_LOG_INGEST_URL}/rest/health" --connect-timeout 20) || ACTIVE_GATE_CONNECTIVITY=N
    if [[ "$ACTIVE_GATE_CONNECTIVITY" != "Y" ]]; then
      warn "Unable to connect to ActiveGate endpoint $DYNATRACE_LOG_INGEST_URL to check if ActiveGate is running. It can be ignored if ActiveGate host network configuration does not allow access from outside of k8s cluster."
    fi
    if [[ "$ACTIVE_GATE_STATE" != "RUNNING" && "$ACTIVE_GATE_CONNECTIVITY" == "Y" ]]; then
      err "ActiveGate endpoint $DYNATRACE_LOG_INGEST_URL is not reporting RUNNING state. Please validate 'dynatraceLogIngestUrl' parameter value and ActiveGate host health."
      exit 1
    fi
  fi
fi

echo
echo "- downloading extensions"
get_extensions_zip_packages

echo
echo "- checking activated extensions in Dynatrace"
EXTENSIONS_FROM_CLUSTER=$(get_activated_extensions_on_cluster)

# If --upgrade option is not set, all gcp extensions are downloaded from the cluster to get configuration of gcp services for version that is currently active on the cluster.
if [[ "$UPGRADE_EXTENSIONS" != "Y" && -n "$EXTENSIONS_FROM_CLUSTER" ]]; then
  echo
  echo "- downloading active extensions from Dynatrace"
  get_extensions_from_dynatrace "$EXTENSIONS_FROM_CLUSTER"
fi

echo
echo "- read activation config"
SERVICES_FROM_ACTIVATION_CONFIG_STR=$(services_setup_in_config "$SERVICES_FROM_ACTIVATION_CONFIG")

echo
echo "- choosing and uploading extensions to Dynatrace"
upload_correct_extension_to_dynatrace "$SERVICES_FROM_ACTIVATION_CONFIG_STR"

if [[ $CREATE_AUTOPILOT_CLUSTER == "Y" ]]; then
  SELECTED_REGION=$(gcloud config get-value compute/region 2>/dev/null)
  if [ -z "$SELECTED_REGION" ]; then
    echo
    err "Default region not set. Set default region by running 'gcloud config set compute/region <REGION>'."
    exit 1
  fi
  echo
  echo "- Create and connect GKE Autopilot k8s cluster ${AUTOPILOT_CLUSTER_NAME}."
  gcloud container clusters create-auto "${AUTOPILOT_CLUSTER_NAME}" --project "${GCP_PROJECT}" >${CMD_OUT_PIPE}
  gcloud container clusters get-credentials "${AUTOPILOT_CLUSTER_NAME}" --project ${GCP_PROJECT} >${CMD_OUT_PIPE}
fi

echo
echo "- 1. Create dynatrace namespace in k8s cluster."
if [[ $(kubectl get namespace dynatrace --ignore-not-found) ]]; then
  echo "namespace dynatrace already exists"
else
  kubectl create namespace dynatrace >${CMD_OUT_PIPE}
fi

echo
echo "- 2. Create IAM service account."
if [[ $(gcloud iam service-accounts list --filter="name ~ serviceAccounts/$SA_NAME@" --project="$GCP_PROJECT" --format="value(name)") ]]; then
  echo "Service Account [$SA_NAME] already exists, skipping"
else
  gcloud iam service-accounts create "$SA_NAME" >${CMD_OUT_PIPE}
fi

echo
echo "- 3. Configure the IAM service account for Workload Identity."
gcloud iam service-accounts add-iam-policy-binding "$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role roles/iam.workloadIdentityUser --member "serviceAccount:$GCP_PROJECT.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]" >${CMD_OUT_PIPE}

echo
echo "- 4. Create dynatrace-gcp-function IAM role(s)."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.logs" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.logs"
    gcloud iam roles update $ROLE_NAME.logs --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml >${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.logs --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml >${CMD_OUT_PIPE}
  fi
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.metrics" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.metrics"
    gcloud iam roles update $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml >${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml >${CMD_OUT_PIPE}
  fi
fi

echo
echo "- 5. Grant the required IAM policies to the service account."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.logs" >${CMD_OUT_PIPE}
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.metrics" >${CMD_OUT_PIPE}
fi

echo
echo "- 6. Enable the APIs required for monitoring."
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com >${CMD_OUT_PIPE}

CLUSTER_NAME=""
if [[ $CREATE_AUTOPILOT_CLUSTER == "Y" ]]; then
  CLUSTER_NAME="$AUTOPILOT_CLUSTER_NAME"
else
  CLUSTER_NAME=$(kubectl config current-context 2>${CMD_OUT_PIPE})
fi

echo
echo "- 7. Install dynatrace-gcp-function with helm chart in $CLUSTER_NAME"
helm upgrade dynatrace-gcp-function ./dynatrace-gcp-function --install --namespace dynatrace --set clusterName="$CLUSTER_NAME" >${CMD_OUT_PIPE}

echo
echo -e "\e[92m- Deployment complete, check if containers are running:\e[37m" >${CMD_OUT_PIPE}
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs" >${CMD_OUT_PIPE}
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics" >${CMD_OUT_PIPE}
fi

if [[ $DEPLOYMENT_TYPE != "metrics" ]] && [[ $USE_EXISTING_ACTIVE_GATE != "true" ]]; then
  # We can build a Log viewer link only when a Dynatrace url is set (when the option with ActiveGate deployment is chosen)
  # When an existing ActiveGate is used we are not able to build the link - LOG_VIEWER is empty then.
  LOG_VIEWER="Log Viewer: ${DYNATRACE_URL}/ui/log-monitoring?query=cloud.provider%3D%22gcp%22"
fi

if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo
  echo -e "\e[92m- Check logs in Dynatrace in 5 min. ${LOG_VIEWER}\e[37m" >${CMD_OUT_PIPE}
  echo "You can verify if the installation was successful by following the steps from: https://www.dynatrace.com/support/help/shortlink/deploy-k8#anchor_verify"
  echo "Additionally you can enable self-monitoring for quick diagnosis: https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp#anchor_sfm"
fi
