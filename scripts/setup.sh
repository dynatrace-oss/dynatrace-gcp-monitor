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
source $WORKING_DIR/lib.sh
init_ext_tools

trap ctrl_c INT
trap onFailure ERR

info "\033[1;34mDynatrace GCP metric integration in GCP Cloud Function ${GCP_FUNCTION_RELEASE_VERSION}"
info "\033[0;37m"

print_help() {
  printf "
usage: setup.sh [--upgrade-extensions] [--auto-default]

arguments:
    --upgrade-extensions
                            Upgrade all extensions into dynatrace cluster
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
            "--upgrade-extensions")
                UPGRADE_EXTENSIONS="Y"
                shift
            ;;

            "--s3-url")
                EXTENSION_S3_URL=$2
                shift; shift
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
  FUNCTION_REPOSITORY_RELEASE_URL="https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/latest/download/dynatrace-gcp-function.zip"
else
  FUNCTION_REPOSITORY_RELEASE_URL="https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/download/${GCP_FUNCTION_RELEASE_VERSION}/dynatrace-gcp-function.zip"
fi
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml
API_TOKEN_SCOPES=('"metrics.ingest"' '"ReadConfig"' '"WriteConfig"' '"extensions.read"' '"extensions.write"' '"extensionConfigurations.read"' '"extensionConfigurations.write"' '"extensionEnvironment.read"' '"extensionEnvironment.write"')

check_s3_url

debug "Downloading function sources from GitHub release"
if [[ "$USE_LOCAL_FUNCTION_ZIP" != "Y" ]]; then
  info ""
  info "- downloading functions source [$FUNCTION_REPOSITORY_RELEASE_URL]"
  wget -q $FUNCTION_REPOSITORY_RELEASE_URL -O $WORKING_DIR/$FUNCTION_ZIP_PACKAGE | tee -a "$FULL_LOG_FILE"
else
  warn "Development mode on: using local function zip"
fi

debug "Unpacking downloaded release"
info "- extracting archive [$FUNCTION_ZIP_PACKAGE]"
TMP_FUNCTION_DIR=$(mktemp -d)
unzip -o -q $WORKING_DIR/$FUNCTION_ZIP_PACKAGE -d $TMP_FUNCTION_DIR || exit

debug "Check if $FUNCTION_ACTIVATION_CONFIG exist in working directory"
if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
  err "Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing! Download correct function-deployment-package.zip again."
  exit 1
fi

debug "Parsing $FUNCTION_ACTIVATION_CONFIG to set correct parameteras for current installation"
readonly GCP_SERVICE_ACCOUNT=$("$YQ" e '.googleCloud.common.serviceAccount' $FUNCTION_ACTIVATION_CONFIG)
readonly REQUIRE_VALID_CERTIFICATE=$("$YQ" e '.googleCloud.common.requireValidCertificate' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_PUBSUB_TOPIC=$("$YQ" e '.googleCloud.metrics.pubSubTopic' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_NAME=$("$YQ" e '.googleCloud.metrics.function' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SCHEDULER_NAME=$("$YQ" e '.googleCloud.metrics.scheduler' $FUNCTION_ACTIVATION_CONFIG)
readonly QUERY_INTERVAL_MIN=$("$YQ" e '.googleCloud.metrics.queryInterval' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_URL_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceUrlSecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceAccessKeySecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly ACTIVATION_JSON=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -P -j | tee -a "$FULL_LOG_FILE")
readonly SERVICES_TO_ACTIVATE=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -j '.services[]' - | "$JQ" -r '.service' | tee -a "$FULL_LOG_FILE")
SERVICES_WITH_FEATURE_SET=$("$YQ" e '.activation' $FUNCTION_ACTIVATION_CONFIG | "$YQ" e -j '.services[]' - | "$JQ" -r '. | "\(.service)/\(.featureSets[])"' 2>/dev/null | tee -a "$FULL_LOG_FILE")
readonly PRINT_METRIC_INGEST_INPUT=$("$YQ" e '.debug.printMetricIngestInput' $FUNCTION_ACTIVATION_CONFIG)
readonly DEFAULT_GCP_FUNCTION_SIZE=$("$YQ" e '.googleCloud.common.cloudFunctionSize' $FUNCTION_ACTIVATION_CONFIG)
readonly SERVICE_USAGE_BOOKING=$("$YQ" e '.googleCloud.common.serviceUsageBooking' $FUNCTION_ACTIVATION_CONFIG)
readonly USE_PROXY=$("$YQ" e '.googleCloud.common.useProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTP_PROXY=$("$YQ" e '.googleCloud.common.httpProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTPS_PROXY=$("$YQ" e '.googleCloud.common.httpsProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_IAM_ROLE=$("$YQ" e '.googleCloud.common.iamRole' $FUNCTION_ACTIVATION_CONFIG)
# Should be equal to ones in `gcp_iam_roles\dynatrace-gcp-function-metrics-role.yaml`
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
readonly SELF_MONITORING_ENABLED=$("$YQ" e '.googleCloud.common.selfMonitoringEnabled' $FUNCTION_ACTIVATION_CONFIG)
EXTENSIONS_FROM_CLUSTER=""

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
info "You are now logged in as [$GCP_ACCOUNT]"
info ""
DEFAULT_PROJECT=$(gcloud config get-value project)
GCP_REGION=$(gcloud config get-value functions/region)
echo -e "Using region [$GCP_REGION]"
echo

info "Please provide the GCP project ID where Dynatrace function should be deployed to. Default value: [$DEFAULT_PROJECT] (current project)"
info ""
info "Available projects:"
gcloud projects list --format="value(project_id)"
info ""
while ! [[ "${GCP_PROJECT}" =~ ^[a-z]{1}[a-z0-9-]{5,29}$ ]]; do
    read -p "Enter GCP project ID: " -i $DEFAULT_PROJECT -e GCP_PROJECT
done
info ""

info "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

UPDATE=$(gcloud functions list --filter=$GCP_FUNCTION_NAME --project="$GCP_PROJECT" --format="value(name)")
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
  info "To continue deployment your GCP project must contain an App Engine app - it's required for Cloud Scheduler"
  while true; do
    read -p "Do you want to create App Engine app? [y/n]" yn
    case $yn in
    [Yy]*)
      info ""
      info "Please provide the region for App Engine app."
      info ""
      info "Available regions:"
      APP_ENGINE_LOCATIONS=$(gcloud app regions list --format="json" | "$JQ" -r '.[] | .region')
      info "$APP_ENGINE_LOCATIONS"
      readarray -t LOCATIONS_ARR <<<"$(echo "${APP_ENGINE_LOCATIONS}")"
      info ""
      while ! [[ " ${LOCATIONS_ARR[*]} " == *" $APP_ENGINE_LOCATION "* ]]; do
        read -p "Enter location for App Engine app: " -e APP_ENGINE_LOCATION
      done
      info ""
      info "- creating the App Engine app"
      gcloud app create -q --region="$APP_ENGINE_LOCATION" | tee -a "$FULL_LOG_FILE"
      break
      ;;
    [Nn]*)
      info ""
      info "\e[91mERROR: \e[37mCannot continue without App Engine. Deployment aborted."
      exit
      ;;
    *) echo "- please answer y or n" ;;
    esac
  done
elif [[ "$SERVING_APP_ENGINE" != "SERVING"  ]]; then
  info ""
  info "\e[91mERROR: \e[37mTo continue deployment your GCP project must contain an App Engine app - it's required for Cloud Scheduler"
  info ""
  info 'Enable App Engine on: https://console.cloud.google.com/appengine/settings'
  info ""
  exit
fi

debug "Select size of GCP Function"
if [ "$INSTALL" == true ]; then
  info "Please provide the size of Your GCP environment to adjust memory allocated to monitoring function"
  info "[s] - small, up to 500 instances, 256 MB memory allocated to function"
  info "[m] - medium, up to 1000 instances, 512 MB memory allocated to function"
  info "[l] - large, up to 5000 instances, 2048 MB memory allocated to function"
  info "Default value: [$DEFAULT_GCP_FUNCTION_SIZE]"
   while ! [[ "${GCP_FUNCTION_SIZE}" =~ ^(s|m|l)$ ]]; do
      read -p "Enter function size: " -i $DEFAULT_GCP_FUNCTION_SIZE -e GCP_FUNCTION_SIZE
  done
  info ""

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
      info "unexpected function size"
      exit 1
      ;;
  esac
fi

debug "Set Dynatrace tenant url"
info "Please provide the URL used to access Dynatrace, for example: https://mytenant.live.dynatrace.com/"
while ! [[ "${DYNATRACE_URL}" =~ $DYNATRACE_URL_REGEX ]]; do
  read -p "Enter Dynatrace tenant URI: " DYNATRACE_URL
done
info ""

#remove last '/' from URL
DYNATRACE_URL=$(echo "${DYNATRACE_URL}" | sed 's:/*$::')

debug "Set Dynatrace API token"
info "Please log in to Dynatrace, and generate API token (Settings->Integration->Dynatrace API)."
info "The token requires grant of 'Read configuration (API v1)', 'Write configuration (API v1)', 'Ingest metrics (API v2)', 'Read extensions (API v2)', 'Write extensions (API v2)', 'Read extension monitoring configurations (API v2)', 'Write extension monitoring configurations (API v2)', 'Read extension environment configurations (API v2)' and 'Write extension environment configurations (API v2)' scope"
while ! [[ "${DYNATRACE_ACCESS_KEY}" != "" ]]; do
  read -p "Enter Dynatrace API token: " DYNATRACE_ACCESS_KEY
done
info ""

debug "Creating GCP Secret with Dynatrace URL and Dynatrace API token"
info ""
info "- create secrets [$DYNATRACE_URL_SECRET_NAME, $DYNATRACE_ACCESS_KEY_SECRET_NAME]"
if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_URL_SECRET_NAME$" --format="value(name)" | tee -a "$FULL_LOG_FILE") ]]; then
  printf "$DYNATRACE_URL" | gcloud secrets versions add $DYNATRACE_URL_SECRET_NAME --data-file=-
  info "Secret [$DYNATRACE_URL_SECRET_NAME] already exists, added new active version. You can delete previous versions manually if they are not needed."
else
  printf "$DYNATRACE_URL" | gcloud secrets create $DYNATRACE_URL_SECRET_NAME --data-file=- --replication-policy=automatic
fi

if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_ACCESS_KEY_SECRET_NAME$" --format="value(name)" | tee -a "$FULL_LOG_FILE") ]]; then
  printf "$DYNATRACE_ACCESS_KEY" | gcloud secrets versions add $DYNATRACE_ACCESS_KEY_SECRET_NAME --data-file=-
  info "Secret [$DYNATRACE_ACCESS_KEY_SECRET_NAME] already exists, added new active version. You can delete previous versions manually if they are not needed."
else
  printf "$DYNATRACE_ACCESS_KEY" | gcloud secrets create $DYNATRACE_ACCESS_KEY_SECRET_NAME --data-file=- --replication-policy=automatic
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
  if [[ $(gcloud pubsub topics list --filter=name:$GCP_PUBSUB_TOPIC --format="value(name)") ]]; then
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
      readonly GCP_IAM_ROLE_DESCRIPTION="Role for Dynatrace GCP function operating in metrics mode"
      readonly GCP_IAM_ROLE_PERMISSIONS_STRING=$(IFS=, ; echo "${GCP_IAM_ROLE_PERMISSIONS[*]}")
      gcloud iam roles create $GCP_IAM_ROLE --project="$GCP_PROJECT" --title="$GCP_IAM_ROLE_TITLE" --description="$GCP_IAM_ROLE_DESCRIPTION" --stage="GA" --permissions="$GCP_IAM_ROLE_PERMISSIONS_STRING" | tee -a "$FULL_LOG_FILE"
  fi

  debug "Creating GCP Service Account for Dynatrace integration"
  info ""
  info "- create service account [$GCP_SERVICE_ACCOUNT] with created role [roles/$GCP_IAM_ROLE]"
  if [[ $(gcloud iam service-accounts list --filter=name:$GCP_SERVICE_ACCOUNT --format="value(name)") ]]; then
      info "Service account [$GCP_SERVICE_ACCOUNT] already exists, skipping"
  else
      gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT" >/dev/null
      gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$GCP_IAM_ROLE" >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
  fi
fi

debug "Dynatrace API token validation"
check_api_token "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY"

debug "Downloading Dynatrace GCP Extensions from S3"
info ""
info "- downloading extensions"
get_extensions_zip_packages

debug "Checking installed extension version on Dynatrace environemnt"
info ""
info "- checking activated extensions in Dynatrace"
EXTENSIONS_FROM_CLUSTER=$(get_activated_extensions_on_cluster)

mv $TMP_FUNCTION_DIR $WORKING_DIR/$GCP_FUNCTION_NAME
pushd $WORKING_DIR/$GCP_FUNCTION_NAME || exit

debug "Verification GCP Function Interval"
if [ "$QUERY_INTERVAL_MIN" -lt 1 ] || [ "$QUERY_INTERVAL_MIN" -gt 6 ]; then
  info "Invalid value of 'googleCloud.metrics.queryInterval', defaulting to 3"
  GCP_FUNCTION_TIMEOUT=180
  GCP_SCHEDULER_CRON="*/3 * * * *"
else
  GCP_FUNCTION_TIMEOUT=$(( QUERY_INTERVAL_MIN*60 ))
  GCP_SCHEDULER_CRON="*/${QUERY_INTERVAL_MIN} * * * *"
fi

# If --upgrade option is not set, all gcp extensions are downloaded from the cluster to get configuration of gcp services for version that is currently active on the cluster.
if [[ "$UPGRADE_EXTENSIONS" != "Y" && -n "$EXTENSIONS_FROM_CLUSTER" ]]; then
  debug "Downloading activated extensions from Dynatrace environment"
  info ""
  info "- downloading active extensions from Dynatrace"
  get_extensions_from_dynatrace "$EXTENSIONS_FROM_CLUSTER"
fi

debug "Validation all downloaded extensions"
info ""
info "- validating extensions"
validate_gcp_config_in_extensions

debug "Select correct extensions depend on activation config"
info ""
info "- read activation config"
SERVICES_WITH_FEATURE_SET_STR=$(services_setup_in_config "$SERVICES_WITH_FEATURE_SET")
info "$SERVICES_WITH_FEATURE_SET_STR"

debug "Upload selected extensions to Dynatrace environemnt"
mkdir -p $WORKING_DIR/$GCP_FUNCTION_NAME/config/ | tee -a "$FULL_LOG_FILE"
info ""
info "- choosing and uploading extensions to Dynatrace"
upload_correct_extension_to_dynatrace "$SERVICES_WITH_FEATURE_SET_STR"

debug "Prepare environemnt veriables for GCP Function"
cd $WORKING_DIR/$GCP_FUNCTION_NAME || exit
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
QUERY_INTERVAL_MIN: '$QUERY_INTERVAL_MIN'
GCP_PROJECT: '$GCP_PROJECT'
FUNCTION_REGION: '$GCP_REGION'
EOF

if [ "$INSTALL" == true ]; then
  debug "Installing Dynatrace integration on GCP Function"
  info ""
  info "- deploying the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m"
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python38 --memory="$GCP_FUNCTION_MEMORY"  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --env-vars-file function_env_vars.yaml | tee -a "$FULL_LOG_FILE"
else

  while true; do
    info ""
    read -p "- your Cloud Function will be updated - any manual changes made to Cloud Function environment variables will be replaced with values from 'activation-config.yaml' file, do you want to continue? [y/n]" yn
    case $yn in
        [Yy]* ) info "- updating the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m";  break;;
        [Nn]* ) info "Update aborted"; exit;;
        * ) info "- please answer yes or no.";;
    esac
  done
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python38  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --env-vars-file function_env_vars.yaml | tee -a "$FULL_LOG_FILE"
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
SELF_MONITORING_DASHBOARD_NAME=$(cat dashboards/dynatrace-gcp-function_self_monitoring.json | "$JQ" .displayName)
if [[ $(gcloud monitoring dashboards  list --filter=displayName:"$SELF_MONITORING_DASHBOARD_NAME" --format="value(displayName)") ]]; then
  info "Dashboard already exists, skipping"
else
  gcloud monitoring dashboards create --config-from-file=dashboards/dynatrace-gcp-function_self_monitoring.json | tee -a "$FULL_LOG_FILE"
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
