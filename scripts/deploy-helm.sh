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


WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./scripts/lib.sh
source "$WORKING_DIR/lib.sh"
init_ext_tools

trap ctrl_c INT
trap onFailure ERR
set -o pipefail

info "\033[1;34mDynatrace GCP integration on GKE"
info "\033[0;37m"

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
  if RESPONSE=$(curl -k -s -X POST -d "$(generate_test_log)" "$DYNATRACE_LOG_INGEST_URL/api/v2/logs/ingest" -w "<<HTTP_CODE>>%{http_code}" -H "accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" --connect-timeout 20 | tee -a "$FULL_LOG_FILE"); then
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

print_help() {
  printf "
usage: deploy-helm.sh [--role-name ROLE_NAME] [--create-autopilot-cluster] [--autopilot-cluster-name CLUSTER_NAME] [--without-extensions-upgrade] [--auto-default] [--quiet]

arguments:
    --role-name ROLE_NAME
                            IAM role name prefix
                            By default 'dynatrace_function' will be used as prefix (e.g. dynatrace_function.metrics).
    --create-autopilot-cluster
                            Create new GKE Autopilot cluster and deploy dynatrace-gcp-monitor into it.
    --autopilot-cluster-name CLUSTER_NAME
                            Name of new GKE Autopilot cluster to be created if '--create-autopilot-cluster option' was selected.
                            By default 'dynatrace-gcp-monitor' will be used.
    --without-extensions-upgrade
                            Keep existing versions of present extensions, and install latest versions for the rest of the selected extensions, if they are not present.
                            By default, this is not set, so extensions will be upgrade
    -n, --namespace
                            Kubernetes namespace, by default 'dynatrace'.
    -d, --auto-default
                            Disable all interactive prompts when running gcloud commands.
                            If input is required, defaults will be used, or an error will be raised.
                            It's equivalent to gcloud global parameter -q, --quiet
    -q, --quiet
                            Reduce output verbosity, progress messages and errors are still printed.
    -h, --help
                            Show this help message and exit
    "
}

# test pre-requirements
test_req_gcloud
test_req_unzip
test_req_kubectl
test_req_helm

CMD_OUT_PIPE="/dev/stdout"
AUTOPILOT_CLUSTER_NAME="dynatrace-gcp-monitor"

while (( "$#" )); do
    case "$1" in
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

            "--without-extensions-upgrade")
                UPGRADE_EXTENSIONS="N"
                shift
            ;;

            "-n" | "--namespace")
                KUBERNETES_NAMESPACE=$2
                shift; shift
            ;;

            "-d" | "--auto-default")
                export CLOUDSDK_CORE_DISABLE_PROMPTS=1
                shift
            ;;

            "-q" | "--quiet")
                CMD_OUT_PIPE="/dev/null"
                shift
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

GCP_PROJECT=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.gcpProjectId}")
DEPLOYMENT_TYPE=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.deploymentType}")
DYNATRACE_ACCESS_KEY=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.dynatraceAccessKey}" | sed 's/[\r\n\t ]//g')
readonly DYNATRACE_ACCESS_KEY
DYNATRACE_URL=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.dynatraceUrl}" | sed 's/[\r\n\t ]//g' | sed 's:/*$::')
readonly DYNATRACE_URL
DYNATRACE_LOG_INGEST_URL=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.dynatraceLogIngestUrl}" | sed 's/[\r\n\t ]//g' | sed 's:/*$::')
if [ -z "$DYNATRACE_LOG_INGEST_URL" ]; then
  DYNATRACE_LOG_INGEST_URL=$DYNATRACE_URL
fi
readonly DYNATRACE_LOG_INGEST_URL
LOGS_SUBSCRIPTION_ID=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.logsSubscriptionId}")
readonly LOGS_SUBSCRIPTION_ID
USE_PROXY=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.useProxy}")
readonly USE_PROXY
HTTP_PROXY=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.httpProxy}")
readonly HTTP_PROXY
HTTPS_PROXY=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.httpsProxy}")
readonly HTTPS_PROXY
readonly ACTIVE_GATE_TARGET_URL_REGEX="^https:\/\/[-a-zA-Z0-9@:%._+~=]{1,255}\/e\/[-a-z0-9]{1,36}[\/]{0,1}$"
SA_NAME=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.serviceAccount}")
readonly SA_NAME
VPC_NETWORK=$(helm show values ./dynatrace-gcp-monitor --jsonpath "{.vpcNetwork}")
if [ -z "$VPC_NETWORK" ]; then
  VPC_NETWORK="default"
fi
readonly VPC_NETWORK

API_TOKEN_SCOPES=('"logs.ingest"' '"metrics.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"' '"hub.read"' '"hub.write"' '"hub.install"')

debug "Setting GCP project"
check_if_parameter_is_empty "$GCP_PROJECT" "Set correct gcpProjectId in values.yaml"

gcloud config set project "$GCP_PROJECT" | tee -a "$FULL_LOG_FILE"
info "- Deploying dynatrace-gcp-monitor in [$GCP_PROJECT]"

if [ -z "$ROLE_NAME" ]; then
  ROLE_NAME="dynatrace_function"
fi

if [ -z "$UPGRADE_EXTENSIONS" ]; then
  UPGRADE_EXTENSIONS="Y"
fi

debug "Selecting deployment type"
if [ -z "$KUBERNETES_NAMESPACE" ]; then
  KUBERNETES_NAMESPACE="dynatrace"
fi

if [ -z "$DEPLOYMENT_TYPE" ]; then
  DEPLOYMENT_TYPE="all"
  info "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == all ]]; then
  info "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == logs ]]; then
  info "Deploying $DEPLOYMENT_TYPE ingest"
  API_TOKEN_SCOPES=('"logs.ingest"')
elif [[ $DEPLOYMENT_TYPE == metrics ]]; then
  info "Deploying $DEPLOYMENT_TYPE ingest"
  # shellcheck disable=SC2034  # Unused variables left for readability
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

debug "Check if any required parameter is empty"
check_if_parameter_is_empty "$DYNATRACE_URL" "DYNATRACE_URL"
check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY" "DYNATRACE_ACCESS_KEY"
check_url "$DYNATRACE_URL" "$DYNATRACE_URL_REGEX" "Not correct dynatraceUrl. Example of proper Dynatrace environment endpoint: https://<your_environment_ID>.live.dynatrace.com"
check_api_token "$DYNATRACE_URL"

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
  if EXTENSIONS_SCHEMA_RESPONSE=$(dt_api "/api/v2/extensions/schemas"); then
    GCP_EXTENSIONS_SCHEMA_PRESENT=$("$JQ" -r '.versions[] | select(.=="1.230.0")' <<<"${EXTENSIONS_SCHEMA_RESPONSE}")
    if [ -z "${GCP_EXTENSIONS_SCHEMA_PRESENT}" ]; then
      err "Dynatrace environment does not supports GCP extensions schema. Dynatrace needs to be running versions 1.230 or higher to complete installation."
      exit 1
    fi
  fi
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then

  if [[ -n $DYNATRACE_LOG_INGEST_URL ]]; then
    info "Sending logs through selected dynatraceLogIngestUrl"
    check_url "$DYNATRACE_LOG_INGEST_URL" "$DYNATRACE_URL_REGEX" "$ACTIVE_GATE_TARGET_URL_REGEX" \
      "Not correct dynatraceLogIngestUrl. Example of proper endpoint used to ingest logs to Dynatrace:\n
        - for direct ingest through the Cluster API: https://<your_environment_ID>.live.dynatrace.com\n
        - for Environment ActiveGate: https://<your_activegate_IP_or_hostname>:9999/e/<your_environment_ID>"
    check_api_token "$DYNATRACE_LOG_INGEST_URL"
    check_dynatrace_log_ingest_url
  fi

  check_if_parameter_is_empty "$LOGS_SUBSCRIPTION_ID" "LOGS_SUBSCRIPTION_ID"

  readonly LOGS_SUBSCRIPTION_FULL_ID="projects/$GCP_PROJECT/subscriptions/$LOGS_SUBSCRIPTION_ID"

  debug "Check PubSub subscription"
  if ! [[ $(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(name)") ]]; then
    err "Pub/Sub subscription '$LOGS_SUBSCRIPTION_FULL_ID' does not exist"
    exit 1
  fi

  INVALID_PUBSUB=false

  ACK_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(ackDeadlineSeconds)")
  readonly ACK_DEADLINE
  if [[ "$ACK_DEADLINE" != "120" ]]; then
    err "Invalid Pub/Sub subscription Acknowledgement Deadline - should be '120's (2 minutes), was '$ACK_DEADLINE's"
    INVALID_PUBSUB=true
  fi

  MESSAGE_RETENTION_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(messageRetentionDuration)")
  readonly MESSAGE_RETENTION_DEADLINE
  if [[ "$MESSAGE_RETENTION_DEADLINE" != "86400s" ]]; then
    err "Invalid Pub/Sub subscription Acknowledge Deadline - should be '86400s' (24 hours), was '$MESSAGE_RETENTION_DEADLINE'"
    INVALID_PUBSUB=true
  fi

  if "$INVALID_PUBSUB"; then
    exit 1
  fi

fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then

  debug "Checking installed extension version on Dynatrace environment"
  info ""
  info "- checking activated extensions in Dynatrace"
  EXTENSIONS_FROM_CLUSTER=$(get_activated_extensions_on_cluster)

  # If --without-extensions-upgrade is set, all gcp extensions are downloaded from the cluster to get configuration of gcp services for versions that are currently active on the cluster.
  if [[ "$UPGRADE_EXTENSIONS" == "N" && -n "$EXTENSIONS_FROM_CLUSTER" ]]; then
    info ""
    info "- Some google extensions have already been activated in Dynatrace."
    info "- No new extensions will be activated."
  else
    get_and_install_extensions
  fi

fi

# Check if gke auth necessary plugin is installed
# Until GKE 1.26 release, we also need to tell GKE to use the new auth plugin
if ! [[ $(gke-gcloud-auth-plugin --version) ]]; then
  err "gke-gcloud-auth-plugin not installed. Run the following commands to install it:"
  info "gcloud components install gke-gcloud-auth-plugin"
  info "export USE_GKE_GCLOUD_AUTH_PLUGIN=True"
  info "gcloud components update"
  info ""
  info "For more information, visit: https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke"
  exit 1
fi

if [[ $CREATE_AUTOPILOT_CLUSTER == "Y" ]]; then
  debug "Creating Autopilot GKE Cluster"
  SELECTED_REGION=$(gcloud config get-value compute/region 2>/dev/null | tee -a "$FULL_LOG_FILE")
  if [ -z "$SELECTED_REGION" ]; then
    info ""
    err "Default region not set. Set default region by running 'gcloud config set compute/region <REGION>'."
    exit 1
  fi
  KUBERNETES_ENGINE_API=$(gcloud services list --enabled --filter=container.googleapis.com --project="$GCP_PROJECT")
  if [[ -z "$KUBERNETES_ENGINE_API" ]]; then
    debug "Enabling Kubernetes Engine API"
    gcloud services enable container.googleapis.com | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  fi
  info ""
  info "- Create and connect GKE Autopilot k8s cluster ${AUTOPILOT_CLUSTER_NAME}."
  gcloud container clusters create-auto "${AUTOPILOT_CLUSTER_NAME}" --project "${GCP_PROJECT}" --zone "" --network "${VPC_NETWORK}" | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  gcloud container clusters get-credentials "${AUTOPILOT_CLUSTER_NAME}" --project "${GCP_PROJECT}" --zone "" | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
fi

debug "Creating dynatrace namespace into kubernetes cluster"
info ""
info "- 1. Create $KUBERNETES_NAMESPACE namespace in k8s cluster."
if [[ $(kubectl get namespace $KUBERNETES_NAMESPACE --ignore-not-found) ]]; then
  info "namespace $KUBERNETES_NAMESPACE already exists"
else
  kubectl create namespace $KUBERNETES_NAMESPACE | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
fi

debug "Creating GCP Service Account for kubernetes"
info ""
info "- 2. Create IAM service account."
if [[ $(gcloud iam service-accounts list --filter="name ~ serviceAccounts/$SA_NAME@" --project="$GCP_PROJECT" --format="value(name)") ]]; then
  info "Service Account [$SA_NAME] already exists, skipping"
else
  gcloud iam service-accounts create "$SA_NAME" | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
fi

debug "Binding correct policies to Service Account"
info ""
info "- 3. Configure the IAM service account for Workload Identity."
gcloud iam service-accounts add-iam-policy-binding "$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role roles/iam.workloadIdentityUser --member "serviceAccount:$GCP_PROJECT.svc.id.goog[$KUBERNETES_NAMESPACE/$SA_NAME]" | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}

info ""
info "- 4. Create dynatrace-gcp-monitor IAM role(s)."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  debug "Creating or updating GCP IAM role with gcp_iam_roles/dynatrace-gcp-monitor-logs-role.yaml"
  if [[ $(gcloud iam roles list --filter="name ~ $ROLE_NAME.logs" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    info "Updating existing IAM role $ROLE_NAME.logs. It was probably created for previous GCP integration deployment and you can safely replace it."
    gcloud iam roles update --quiet $ROLE_NAME.logs --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-monitor-logs-role.yaml | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.logs --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-monitor-logs-role.yaml | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  fi
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  debug "Creating or updating GCP IAM role with gcp_iam_roles/dynatrace-gcp-monitor-metrics-role.yaml"
  if [[ $(gcloud iam roles list --filter="name ~ $ROLE_NAME.metrics" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    info "Updating existing IAM role $ROLE_NAME.metrics. It was probably created for previous GCP integration deployment and you can safely replace it."
    gcloud iam roles update --quiet $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-monitor-metrics-role.yaml | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=gcp_iam_roles/dynatrace-gcp-monitor-metrics-role.yaml | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}
  fi
fi

info ""
# info "- 5. Grant the required IAM policies to the service account."
# if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
#   debug "Binding logs role to Service Account"
#   gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.logs" >/dev/null
# fi

info "- 5. Grant the required IAM policies to the service account."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  debug "Binding logs role to Service Account"
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/CustomDynatraceGCPLogsMonitor" >/dev/null
fi

# if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
#   debug "Binding metrics role to Service Account"
#   gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.metrics" >/dev/null
# fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  debug "Binding metrics role to Service Account"
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/CustomDynatraceGCPMetricsFunct" >/dev/null
fi


debug "Enablig required Google APIs"
info ""
info "- 6. Enable the APIs required for monitoring."
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE}

debug "Get kubernetes cluster name"
CLUSTER_NAME=""
if [[ $CREATE_AUTOPILOT_CLUSTER == "Y" ]]; then
  CLUSTER_NAME="$AUTOPILOT_CLUSTER_NAME"
else
  CLUSTER_NAME=$(kubectl config current-context 2>${CMD_OUT_PIPE})
fi

debug "Installing Dynatrace Integration Helm Chart on selected kubernetes cluster"
info ""
info "- 7. Install dynatrace-gcp-monitor with helm chart in $CLUSTER_NAME"
time (helm upgrade dynatrace-gcp-monitor ./dynatrace-gcp-monitor --install --debug --namespace "$KUBERNETES_NAMESPACE" --wait --timeout 20m --set clusterName="$CLUSTER_NAME" | tee -a "$FULL_LOG_FILE" >${CMD_OUT_PIPE})


echo "EVENTS: "
kubectl -n "$KUBERNETES_NAMESPACE" get events --sort-by='{.lastTimestamp}'

debug "Helm installation completed"
info ""
info "\e[92m- Deployment complete, check if containers are running:\e[37m"
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  info "kubectl -n $KUBERNETES_NAMESPACE logs -l app=dynatrace-gcp-monitor -c dynatrace-gcp-monitor-logs"
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  info "kubectl -n $KUBERNETES_NAMESPACE logs -l app=dynatrace-gcp-monitor -c dynatrace-gcp-monitor-metrics"
fi

if [[ $DEPLOYMENT_TYPE != "metrics" ]]; then
  LOG_VIEWER="Log Viewer: ${DYNATRACE_URL}/ui/log-monitoring?query=cloud.provider%3D%22gcp%22"
fi

info ""
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  info "\e[92m- Check logs in Dynatrace in 5 min. ${LOG_VIEWER}\e[37m"
  fi
if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  GCP_DASHBOARDS="GCP dashboards: ${DYNATRACE_URL}"
  info -e "\e[92m- Check metrics in Dynatrace in 5 min. ${GCP_DASHBOARDS}/ui/dashboards?filters=tag%3DGoogle%20Cloud\e[37m"
fi

debug "Cleaning all temporary files "
info ""
info "- cleaning up"
clean

info "You can verify if the installation was successful by following the steps from: https://www.dynatrace.com/support/help/shortlink/deploy-k8#anchor_verify"
info "Additionally you can enable self-monitoring for quick diagnosis: https://www.dynatrace.com/support/help/how-to-use-dynatrace/infrastructure-monitoring/cloud-platform-monitoring/google-cloud-platform-monitoring/set-up-gcp-integration-on-new-cluster#verify"
info ""
