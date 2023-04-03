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

GCP_FUNCTION_RELEASE_VERSION=''

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./scripts/lib.sh
source "$WORKING_DIR"/lib.sh
init_ext_tools

trap ctrl_c INT
trap onFailure ERR

info "\033[1;34mDynatrace GCP metric integration in GCP Cloud Function ${GCP_FUNCTION_RELEASE_VERSION}"
info "\033[0;37m"

print_help() {
  printf "
usage: setup.sh [--without-extensions-upgrade] [--auto-default]

arguments:
    --without-extensions-upgrade
                            Keep existing versions of present extensions, and install latest versions for the rest of the selected extensions, if they are not present.
    -d, --auto-default
                            Disable all interactive prompts when running gcloud commands.
                            If input is required, defaults will be used, or an error will be raised.
                            It's equivalent to gcloud global parameter -q, --quiet
    -h, --help
                            Show this help message and exit
    "
}

test_req_gcloud
test_req_unzip

while (( "$#" )); do
    case "$1" in
            "--without-extensions-upgrade")
                UPGRADE_EXTENSIONS="N"
                shift
            ;;

            "--use-local-function-zip")
                USE_LOCAL_FUNCTION_ZIP="Y"
                shift
            ;;

            "-d" | "--auto-default")
                export CLOUDSDK_CORE_DISABLE_PROMPTS=1
                shift
            ;;

            "-h" | "--help")
                print_help
                exit 0
            ;;

            *)
            info "Unknown param $1"
            print_help
            exit 1
    esac
done

if [[ -z "$GCP_FUNCTION_RELEASE_VERSION" ]]; then
  FUNCTION_REPOSITORY_RELEASE_URL="https://github.com/dynatrace-oss/dynatrace-gcp-monitor/releases/latest/download/dynatrace-gcp-monitor.zip"
else
  FUNCTION_REPOSITORY_RELEASE_URL="https://github.com/dynatrace-oss/dynatrace-gcp-monitor/releases/download/${GCP_FUNCTION_RELEASE_VERSION}/dynatrace-gcp-monitor.zip"
fi
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-monitor.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml
# shellcheck disable=SC2034  # Unused variables left for readability
API_TOKEN_SCOPES=('"metrics.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"' '"hub.read"' '"hub.write"' '"hub.install"')

debug "Downloading function sources from GitHub release"
if [[ "$USE_LOCAL_FUNCTION_ZIP" != "Y" ]]; then
  info ""
  info "- downloading functions source [$FUNCTION_REPOSITORY_RELEASE_URL]"
  wget -q $FUNCTION_REPOSITORY_RELEASE_URL -O "$WORKING_DIR"/$FUNCTION_ZIP_PACKAGE | tee -a "$FULL_LOG_FILE"
else
  warn "Development mode on: using local function zip"
fi

debug "Unpacking downloaded release"
info "- extracting archive [$FUNCTION_ZIP_PACKAGE]"
TMP_FUNCTION_DIR=$(mktemp -d)
unzip -o -q "$WORKING_DIR"/$FUNCTION_ZIP_PACKAGE -d "$TMP_FUNCTION_DIR" || exit

debug "Check if $FUNCTION_ACTIVATION_CONFIG exist in working directory"
if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
  err "Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing! Download correct function-deployment-package.zip again."
  exit 1
fi

debug "Parsing $FUNCTION_ACTIVATION_CONFIG to set correct parameteras for current installation"
GCP_PROJECT=$("$YQ" e '.googleCloud.required.gcpProjectId' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_PROJECT
DYNATRACE_URL=$("$YQ" e '.googleCloud.required.dynatraceTenantUrl' $FUNCTION_ACTIVATION_CONFIG)
DYNATRACE_ACCESS_KEY=$("$YQ" e '.googleCloud.required.dynatraceApiToken' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_ACCESS_KEY
GCP_FUNCTION_SIZE=$("$YQ" e '.googleCloud.required.cloudFunctionSize' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_SIZE
GCP_FUNCTION_REGION=$("$YQ" e '.googleCloud.required.cloudFunctionRegion' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_REGION
PREFERRED_APP_ENGINE_REGION=$("$YQ" e '.googleCloud.required.preferredAppEngineRegion' $FUNCTION_ACTIVATION_CONFIG)
readonly PREFERRED_APP_ENGINE_REGION
GCP_SERVICE_ACCOUNT=$("$YQ" e '.googleCloud.common.serviceAccount' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SERVICE_ACCOUNT
REQUIRE_VALID_CERTIFICATE=$("$YQ" e '.googleCloud.common.requireValidCertificate' $FUNCTION_ACTIVATION_CONFIG)
readonly REQUIRE_VALID_CERTIFICATE
GCP_PUBSUB_TOPIC=$("$YQ" e '.googleCloud.metrics.pubSubTopic' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_PUBSUB_TOPIC
GCP_FUNCTION_NAME=$("$YQ" e '.googleCloud.metrics.function' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_NAME
GCP_SCHEDULER_NAME=$("$YQ" e '.googleCloud.metrics.scheduler' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SCHEDULER_NAME
QUERY_INTERVAL_MIN=$("$YQ" e '.googleCloud.metrics.queryInterval' $FUNCTION_ACTIVATION_CONFIG)
readonly QUERY_INTERVAL_MIN
DYNATRACE_URL_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceUrlSecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_URL_SECRET_NAME
DYNATRACE_ACCESS_KEY_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceAccessKeySecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME
ACTIVATION_JSON=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -P -j | tee -a "$FULL_LOG_FILE")
readonly ACTIVATION_JSON
SERVICES_TO_ACTIVATE=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -j '.services[]' - | "$JQ" -r '.service' | tee -a "$FULL_LOG_FILE")
readonly SERVICES_TO_ACTIVATE
SERVICES_WITH_FEATURE_SET=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -j '.services[]' - | "$JQ" -r '. | "\(.service)/\(.featureSets[])"' 2>/dev/null | tee -a "$FULL_LOG_FILE")
PRINT_METRIC_INGEST_INPUT=$("$YQ" e '.debug.printMetricIngestInput' $FUNCTION_ACTIVATION_CONFIG)
readonly PRINT_METRIC_INGEST_INPUT
SERVICE_USAGE_BOOKING=$("$YQ" e '.googleCloud.common.serviceUsageBooking' $FUNCTION_ACTIVATION_CONFIG)
readonly SERVICE_USAGE_BOOKING
USE_PROXY=$("$YQ" e '.googleCloud.common.useProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly USE_PROXY
HTTP_PROXY=$("$YQ" e '.googleCloud.common.httpProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTP_PROXY
HTTPS_PROXY=$("$YQ" e '.googleCloud.common.httpsProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTPS_PROXY
GCP_IAM_ROLE=$("$YQ" e '.googleCloud.common.iamRole' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_IAM_ROLE
# Should be equal to ones in `gcp_iam_roles\dynatrace-gcp-monitor-metrics-role.yaml`
readonly GCP_IAM_ROLE_PERMISSIONS=(
  resourcemanager.projects.get
  serviceusage.services.list
  cloudfunctions.functions.list
  cloudsql.instances.list
  compute.instances.list
  compute.zones.list
  file.instances.list
  pubsub.subscriptions.list
  monitoring.timeSeries.list
  monitoring.metricDescriptors.create
  monitoring.metricDescriptors.delete
  monitoring.metricDescriptors.list
  monitoring.timeSeries.create
  monitoring.dashboards.list
  monitoring.dashboards.create
)
SELF_MONITORING_ENABLED=$("$YQ" e '.googleCloud.common.selfMonitoringEnabled' $FUNCTION_ACTIVATION_CONFIG)
readonly SELF_MONITORING_ENABLED
SCOPING_PROJECT_SUPPORT_ENABLED=$("$YQ" e '.googleCloud.common.scopingProjectSupportEnabled' $FUNCTION_ACTIVATION_CONFIG)
readonly SCOPING_PROJECT_SUPPORT_ENABLED
EXTENSIONS_FROM_CLUSTER=""

if [ -z "$UPGRADE_EXTENSIONS" ]; then
  UPGRADE_EXTENSIONS="Y"
fi

shopt -s nullglob

get_ext_files() {
  YAML_PATH=$1
  for FILEPATH in ./config/*.yaml ./config/*.yml
  do
    SERVICE=$(basename -s .yml "$(basename -s .yaml "$FILEPATH")" )
    if ! (grep -q "$SERVICE" <<< "$SERVICES_TO_ACTIVATE") ; then
      continue
    fi
    for EXT_FILE in $("$YQ" e -j ".$YAML_PATH"  "$FILEPATH"| tr -d '"')
    do
      if [ ! -f "./$EXT_FILE" ] ; then
        warn "Missing file $EXT_FILE"
        continue
      else
        info "$EXT_FILE"
      fi
    done
  done
}

debug "Check if any required parameter is empty"
check_if_parameter_is_empty "$GCP_PROJECT" "'.googleCloud.required.gcpProjectId'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$DYNATRACE_URL" "'.googleCloud.required.dynatraceTenantUrl'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY" "'.googleCloud.required.dynatraceApiToken'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_FUNCTION_SIZE" "'.googleCloud.required.cloudFunctionSize'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_FUNCTION_REGION" "'.googleCloud.required.cloudFunctionSize'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$PREFERRED_APP_ENGINE_REGION" "'.googleCloud.required.preferredAppEngineRegion'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_PUBSUB_TOPIC" "'googleCloud.metrics.pubSubTopic'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_SCHEDULER_NAME" "'googleCloud.metrics.scheduler'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$DYNATRACE_URL_SECRET_NAME" "'googleCloud.common.dynatraceUrlSecretName'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY_SECRET_NAME" "'googleCloud.common.dynatraceAccessKeySecretName'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_FUNCTION_NAME" 'googleCloud.metrics.function' "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_IAM_ROLE" "'googleCloud.common.iamRole'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$GCP_SERVICE_ACCOUNT" "'googleCloud.common.serviceAccount'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$QUERY_INTERVAL_MIN" "'googleCloud.metrics.queryInterval'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
check_if_parameter_is_empty "$SERVICES_WITH_FEATURE_SET" "'activation.services'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"

debug "Logging to GCP project"
info  "- Logging to your account..."
GCP_ACCOUNT=$(gcloud config get-value account)
info -e "You are now logged in as [$GCP_ACCOUNT]"

info "- set current project to [$GCP_PROJECT]"
gcloud config set project "$GCP_PROJECT"

UPDATE=$(gcloud functions list --filter="$GCP_FUNCTION_NAME" --project="$GCP_PROJECT" --format="value(name)")
INSTALL=true

debug "Check if function already exist"
if [ -n  "$UPDATE" ]; then
info "- function \e[1;32m $GCP_FUNCTION_NAME \e[0m already exists in $GCP_PROJECT and it will be updated"
INSTALL=false
fi

# Create App Engine app if not exists
debug "Check if App Engine exist and configured"
info ""
info "- checking App Engine app, required for Cloud Scheduler"
APP_ENGINE=$(gcloud app describe --format="json" 2>/dev/null || true)
SERVING_APP_ENGINE=$(echo "$APP_ENGINE" | "$JQ" -r '.servingStatus')

if [[ -z "$APP_ENGINE" ]]; then
  info ""
  info "AppEngine not found. It will be created in your preferredAppEngineRegion $PREFERRED_APP_ENGINE_REGION"
  info "- creating the App Engine app"
  gcloud app create -q --region="$PREFERRED_APP_ENGINE_REGION"
elif [[ "$SERVING_APP_ENGINE" != "SERVING"  ]]; then
  info ""
  info "\e[91mERROR: \e[37mTo continue deployment your GCP project must contain an App Engine"
  info ""
  info 'Please check status of App Engine and enable it on: https://console.cloud.google.com/appengine/settings'
  exit
fi

debug "Select size of Cloud Function"
if [ "$INSTALL" == true ]; then
  check_if_parameter_is_empty "$GCP_FUNCTION_SIZE" "'.googleCloud.required.cloudFunctionSize'" "Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"

  case $GCP_FUNCTION_SIZE in
  l)
      GCP_FUNCTION_MEMORY=2048
      ;;
  m)
      GCP_FUNCTION_MEMORY=512
      ;;
  s)
      GCP_FUNCTION_MEMORY=256
      ;;
  *)
      info "unexpected function size, should be one of: s/m/l"
      exit 1
      ;;
  esac
fi

debug "Check Dynatrace tenant url against regexp"
if ! [[ "${DYNATRACE_URL}" =~ $DYNATRACE_URL_REGEX ]]; then
  info "Dynatrace Tenant URL does not match expected pattern"
  exit 1
fi

# shellcheck disable=SC2001 # remove last '/' from URL
DYNATRACE_URL=$(echo "${DYNATRACE_URL}" | sed 's:/*$::')

debug "Creating GCP Secret with Dynatrace URL and Dynatrace API token"
info ""
info "- create secrets [$DYNATRACE_URL_SECRET_NAME, $DYNATRACE_ACCESS_KEY_SECRET_NAME]"
if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_URL_SECRET_NAME$" --format="value(name)" | tee -a "$FULL_LOG_FILE") ]]; then
  printf '%s' "$DYNATRACE_URL" | gcloud secrets versions add "$DYNATRACE_URL_SECRET_NAME" --data-file=-
  info "Secret [$DYNATRACE_URL_SECRET_NAME] already exists, added new active version. You can delete previous versions manually if they are not needed."
else
  printf '%s' "$DYNATRACE_URL" | gcloud secrets create "$DYNATRACE_URL_SECRET_NAME" --data-file=- --replication-policy=automatic
fi

debug "Creating GCP Secret with Dynatrace URL and Dynatrace API token"
if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_ACCESS_KEY_SECRET_NAME$" --format="value(name)" | tee -a "$FULL_LOG_FILE") ]]; then
  printf '%s' "$DYNATRACE_ACCESS_KEY" | gcloud secrets versions add "$DYNATRACE_ACCESS_KEY_SECRET_NAME" --data-file=-
  info "Secret [$DYNATRACE_ACCESS_KEY_SECRET_NAME] already exists, added new active version. You can delete previous versions manually if they are not needed."
else
  printf '%s' "$DYNATRACE_ACCESS_KEY" | gcloud secrets create "$DYNATRACE_ACCESS_KEY_SECRET_NAME" --data-file=- --replication-policy=automatic
fi

debug "Check if Dynatrace Environment support API at least in version 1.230.0"
if [ "$INSTALL" == true ]; then
  if EXTENSIONS_SCHEMA_RESPONSE=$(dt_api "/api/v2/extensions/schemas"); then
    GCP_EXTENSIONS_SCHEMA_PRESENT=$("$JQ" -r '.versions[] | select(.=="1.230.0")' <<<"${EXTENSIONS_SCHEMA_RESPONSE}")
    if [ -z "${GCP_EXTENSIONS_SCHEMA_PRESENT}" ]; then
      err "Dynatrace environment does not supports GCP extensions schema. Dynatrace needs to be running versions 1.230 or higher to complete installation."
      exit 1
    fi
  fi

  debug "Enablig required Google APIs"
  info ""
  info "- enable googleapis [secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudmonitoring.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com]"
  gcloud services enable secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com | tee -a "$FULL_LOG_FILE"

  debug "Creating PubSub topic"
  info ""
  info "- create the pubsub topic [$GCP_PUBSUB_TOPIC]"
  if [[ $(gcloud pubsub topics list --filter=name:"$GCP_PUBSUB_TOPIC" --format="value(name)") ]]; then
      info "Topic [$GCP_PUBSUB_TOPIC] already exists, skipping"
  else
      gcloud pubsub topics create "$GCP_PUBSUB_TOPIC" | tee -a "$FULL_LOG_FILE"
  fi

  debug "Creating GCP IAM Role for Dynatrace integration"
  info ""
  info "- create GCP IAM Role"
  if [[ $(gcloud iam roles list --filter="name ~ $GCP_IAM_ROLE$" --format="value(name)" --project="$GCP_PROJECT") ]]; then
      info "Role [$GCP_IAM_ROLE] already exists, skipping"
  else
      readonly GCP_IAM_ROLE_TITLE="Dynatrace GCP Metrics Function"
      readonly GCP_IAM_ROLE_DESCRIPTION="Role for Dynatrace GCP Monitor operating in metrics mode"
      GCP_IAM_ROLE_PERMISSIONS_STRING=$(IFS=, ; echo "${GCP_IAM_ROLE_PERMISSIONS[*]}")
      readonly GCP_IAM_ROLE_PERMISSIONS_STRING
      gcloud iam roles create "$GCP_IAM_ROLE" --project="$GCP_PROJECT" --title="$GCP_IAM_ROLE_TITLE" --description="$GCP_IAM_ROLE_DESCRIPTION" --stage="GA" --permissions="$GCP_IAM_ROLE_PERMISSIONS_STRING" | tee -a "$FULL_LOG_FILE"
  fi

  debug "Creating GCP Service Account for Dynatrace integration"
  info ""
  info "- create service account [$GCP_SERVICE_ACCOUNT] with created role [roles/$GCP_IAM_ROLE]"
  if [[ $(gcloud iam service-accounts list --filter=name:"$GCP_SERVICE_ACCOUNT" --format="value(name)") ]]; then
      info "Service account [$GCP_SERVICE_ACCOUNT] already exists, skipping"
  else
      gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT" >/dev/null
      gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$GCP_IAM_ROLE" >/dev/null
      gcloud secrets add-iam-policy-binding "$DYNATRACE_URL_SECRET_NAME" --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding "$DYNATRACE_URL_SECRET_NAME" --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
      gcloud secrets add-iam-policy-binding "$DYNATRACE_ACCESS_KEY_SECRET_NAME" --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding "$DYNATRACE_ACCESS_KEY_SECRET_NAME" --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
  fi
fi

debug "Dynatrace API token validation"
check_api_token "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY"

debug "Checking installed extension version on Dynatrace environemnt"
info ""
info "- checking activated extensions in Dynatrace"
EXTENSIONS_FROM_CLUSTER=$(get_activated_extensions_on_cluster)

mv "$TMP_FUNCTION_DIR" "$WORKING_DIR/$GCP_FUNCTION_NAME"
pushd "$WORKING_DIR/$GCP_FUNCTION_NAME" || exit

debug "Verification Cloud Function Interval"
if [ "$QUERY_INTERVAL_MIN" -lt 1 ] || [ "$QUERY_INTERVAL_MIN" -gt 6 ]; then
  info "Invalid value of 'googleCloud.metrics.queryInterval', defaulting to 3"
  GCP_FUNCTION_TIMEOUT=180
  GCP_SCHEDULER_CRON="*/3 * * * *"
else
  GCP_FUNCTION_TIMEOUT=$(( QUERY_INTERVAL_MIN*60 ))
  GCP_SCHEDULER_CRON="*/${QUERY_INTERVAL_MIN} * * * *"
fi

# If --without-extensions-upgrade is set, all gcp extensions are downloaded from the cluster to get configuration of gcp services for version that is currently active on the cluster.
if [[ "$UPGRADE_EXTENSIONS" == "N" && -n "$EXTENSIONS_FROM_CLUSTER" ]]; then
  debug "Downloading activated extensions from Dynatrace environment"
  info ""
  info "- downloading active extensions from Dynatrace"
  get_extensions_from_dynatrace "$EXTENSIONS_FROM_CLUSTER"
fi

get_and_install_extensions

debug "Prepare environemnt veriables for Cloud Function"
cd "$WORKING_DIR/$GCP_FUNCTION_NAME" || exit
cat <<EOF > function_env_vars.yaml
ACTIVATION_CONFIG: '$ACTIVATION_JSON'
PRINT_METRIC_INGEST_INPUT: '$PRINT_METRIC_INGEST_INPUT'
DYNATRACE_ACCESS_KEY_SECRET_NAME: '$DYNATRACE_ACCESS_KEY_SECRET_NAME'
DYNATRACE_URL_SECRET_NAME: '$DYNATRACE_URL_SECRET_NAME'
REQUIRE_VALID_CERTIFICATE: '$REQUIRE_VALID_CERTIFICATE'
SERVICE_USAGE_BOOKING: '$SERVICE_USAGE_BOOKING'
USE_PROXY: '$USE_PROXY'
HTTP_PROXY: '$HTTP_PROXY'
HTTPS_PROXY: '$HTTPS_PROXY'
SELF_MONITORING_ENABLED: '$SELF_MONITORING_ENABLED'
SCOPING_PROJECT_SUPPORT_ENABLED: '$SCOPING_PROJECT_SUPPORT_ENABLED'
QUERY_INTERVAL_MIN: '$QUERY_INTERVAL_MIN'
GCP_PROJECT: '$GCP_PROJECT'
FUNCTION_REGION: '$GCP_FUNCTION_REGION'
EOF

if [ "$INSTALL" == true ]; then
  debug "Installing Dynatrace integration on Cloud Function"
  info ""
  info "- deploying the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m"
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --region "$GCP_FUNCTION_REGION" --entry-point=dynatrace_gcp_extension --runtime=python38 --memory="$GCP_FUNCTION_MEMORY"  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --env-vars-file function_env_vars.yaml | tee -a "$FULL_LOG_FILE"
else
  info "- your Cloud Function will be updated - any manual changes made to Cloud Function environment variables will be replaced with values from 'activation-config.yaml' file"
  info "- updating the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m"
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --region "$GCP_FUNCTION_REGION" --entry-point=dynatrace_gcp_extension --runtime=python38  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --env-vars-file function_env_vars.yaml | tee -a "$FULL_LOG_FILE"
fi

debug "Set GCP cheduler to run function periodically"
info ""
info "- schedule the runs"
if [[ $(gcloud scheduler jobs list --filter="name ~ $GCP_SCHEDULER_NAME$" --format="value(name)") ]]; then
    info "Recreating Cloud Scheduler [$GCP_SCHEDULER_NAME]"
    gcloud -q scheduler jobs delete "$GCP_SCHEDULER_NAME" | tee -a "$FULL_LOG_FILE"
fi
gcloud scheduler jobs create pubsub "$GCP_SCHEDULER_NAME" --topic="$GCP_PUBSUB_TOPIC" --schedule="$GCP_SCHEDULER_CRON" --message-body="x" | tee -a "$FULL_LOG_FILE"

debug "Uploading Dynatrace integration dashboard to GCP"
info ""
info "- create self monitoring dashboard"
SELF_MONITORING_DASHBOARD_NAME=$("$JQ" .displayName < dashboards/dynatrace-gcp-monitor_self_monitoring.json)
if [[ $(gcloud monitoring dashboards  list --filter=displayName:"$SELF_MONITORING_DASHBOARD_NAME" --format="value(displayName)") ]]; then
  info "Dashboard already exists, skipping"
else
  gcloud monitoring dashboards create --config-from-file=dashboards/dynatrace-gcp-monitor_self_monitoring.json | tee -a "$FULL_LOG_FILE"
fi

debug "Cleaning all temporary files "
info ""
info "- cleaning up"

popd | tee -a "$FULL_LOG_FILE" || exit 1
clean

GCP_DASHBOARDS="GCP dashboards: ${DYNATRACE_URL}"
info ""
info "\e[92m- Deployment complete\e[37m"
info "\e[92m- Check metrics in Dynatrace in 5 min. ${GCP_DASHBOARDS}/ui/dashboards?filters=tag%3DGoogle%20Cloud\e[37m"
info "Check the 'Verify installation' section in the docs for further steps."
info ""
