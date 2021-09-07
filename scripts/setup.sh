#!/bin/bash 
#     Copyright 2020 Dynatrace LLC
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

onFailure() {
    echo -e "\e[91mERROR: - deployment failed, please examine error messages and run again"
    exit 2
}

trap onFailure ERR


versionNumber() {
   echo "$@" | awk -F. '{ printf("%d%03d%03d%03d\n", $1,$2,$3,$4); }';
}

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring"
echo -e "\033[0;37m"

if ! command -v yq &> /dev/null
then

    echo -e "\e[91mERROR: \e[37m yq and jq is required to install Dynatrace function. Please refer to following links for installation instructions:"
    echo -e
    echo -e "YQ: https://github.com/mikefarah/yq"
    if ! command -v jq &> /dev/null
    then
        echo -e "JQ: https://stedolan.github.io/jq/download/"
    fi
    echo -e
    echo -e "You may also try installing YQ with PIP: pip install yq"
    echo -e ""
    echo
    exit 1
else
  VERSION_YQ=$(yq --version | cut -d' ' -f3 | tr -d '"')
  echo "Using yq version $VERSION_YQ"


  if [ $(versionNumber $VERSION_YQ) -lt $(versionNumber '4.0.0') ]; then
      echo -e
      echo -e "\e[91mERROR: \e[37m yq in 4+ version is required to install Dynatrace function. Please refer to following links for installation instructions:"
      echo -e "YQ: https://github.com/mikefarah/yq"
      echo -e
      exit 1
  fi
fi


if ! command -v gcloud &> /dev/null
then

    echo -e "\e[91mERROR: \e[37mGoogle Cloud CLI is required to install Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:"
    echo -e
    echo -e "https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version"
    echo -e
    echo
    exit
fi

if ! command -v unzip &> /dev/null
then
    echo -e "\e[91mERROR: \e[37munzip is required to install Dynatrace function"
    echo
    exit
fi

readonly FUNCTION_REPOSITORY_RELEASE_URL=$(curl -s "https://api.github.com/repos/dynatrace-oss/dynatrace-gcp-function/releases" -H "Accept: application/vnd.github.v3+json" | jq 'map(select(.assets[].name == "dynatrace-gcp-function.zip" and .prerelease != true)) | sort_by(.created_at) | last | .assets[] | select( .name =="dynatrace-gcp-function.zip") | .browser_download_url' -r)
readonly FUNCTION_RAW_REPOSITORY_URL=https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
    echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, downloading default"
    wget -q $FUNCTION_RAW_REPOSITORY_URL/$FUNCTION_ACTIVATION_CONFIG -O $FUNCTION_ACTIVATION_CONFIG
    echo
fi

readonly GCP_SERVICE_ACCOUNT=$(yq e '.googleCloud.common.serviceAccount' $FUNCTION_ACTIVATION_CONFIG)
readonly REQUIRE_VALID_CERTIFICATE=$(yq e '.googleCloud.common.requireValidCertificate' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_PUBSUB_TOPIC=$(yq e '.googleCloud.metrics.pubSubTopic' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_NAME=$(yq e '.googleCloud.metrics.function' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SCHEDULER_NAME=$(yq e '.googleCloud.metrics.scheduler' $FUNCTION_ACTIVATION_CONFIG)
readonly QUERY_INTERVAL_MIN=$(yq e '.googleCloud.metrics.queryInterval' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_URL_SECRET_NAME=$(yq e '.googleCloud.common.dynatraceUrlSecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME=$(yq e '.googleCloud.common.dynatraceAccessKeySecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly FUNCTION_GCP_SERVICES=$(yq e -j '.activation.metrics.services' $FUNCTION_ACTIVATION_CONFIG | jq 'join(",")')
readonly SERVICES_TO_ACTIVATE=$(yq e -j '.activation.metrics.services' $FUNCTION_ACTIVATION_CONFIG | jq -r .[] | sed 's/\/.*$//')
readonly PRINT_METRIC_INGEST_INPUT=$(yq e '.debug.printMetricIngestInput' $FUNCTION_ACTIVATION_CONFIG)
readonly DEFAULT_GCP_FUNCTION_SIZE=$(yq e '.googleCloud.common.cloudFunctionSize' $FUNCTION_ACTIVATION_CONFIG)
readonly SERVICE_USAGE_BOOKING=$(yq e '.googleCloud.common.serviceUsageBooking' $FUNCTION_ACTIVATION_CONFIG)
readonly USE_PROXY=$(yq e '.googleCloud.common.useProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTP_PROXY=$(yq e '.googleCloud.common.httpProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTPS_PROXY=$(yq e '.googleCloud.common.httpsProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly IMPORT_DASHBOARDS=$(yq e '.googleCloud.common.importDashboards' $FUNCTION_ACTIVATION_CONFIG)
readonly IMPORT_ALERTS=$(yq e '.googleCloud.common.importAlerts' $FUNCTION_ACTIVATION_CONFIG)
readonly COMPATIBILITY_MODE=$(yq e $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.compatibilityMode')
readonly GCP_IAM_ROLE=$(yq e '.googleCloud.common.iamRole' $FUNCTION_ACTIVATION_CONFIG)
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
readonly SELF_MONITORING_ENABLED=$(yq e '.googleCloud.common.selfMonitoringEnabled' $FUNCTION_ACTIVATION_CONFIG)


shopt -s nullglob


dt_api()
{
  URL=$1
  if [ $# -eq 3 ]; then
    METHOD="$2"
    DATA=("-d" "$3")
  else
    METHOD="GET"
  fi
  if RESPONSE=$(curl -k -s -X $METHOD "${DYNATRACE_URL}${URL}" -w "<<HTTP_CODE>>%{http_code}" -H "Accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" "${DATA[@]}"); then
    CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<< "$RESPONSE")
    sed -r 's/(.*)<<HTTP_CODE>>.*$/\1/' <<< "$RESPONSE"
    if [ "$CODE" -ge 400 ]; then
      return 255
    fi
  fi

}

warn()
{
  MESSAGE=$1
  echo -e >&2
  echo -e "\e[93mWARNING: \e[37m$MESSAGE" >&2
  echo -e >&2
}

get_ext_files()
{
  YAML_PATH=$1
  for FILEPATH in ./config/*.yaml ./config/*.yml
  do
    SERVICE=$(basename -s .yml "$(basename -s .yaml "$FILEPATH")" )
    if ! (grep -q "$SERVICE" <<< "$SERVICES_TO_ACTIVATE") ; then
      continue
    fi
    for EXT_FILE in $(yq e -j ".$YAML_PATH"  "$FILEPATH"| tr -d '"')
    do
      if [ ! -f "./$EXT_FILE" ] ; then
        warn "Missing file $EXT_FILE"
        continue
      else
        echo "$EXT_FILE"
      fi
    done
  done
}

check_if_parameter_is_empty()
{
  PARAMETER=$1
  PARAMETER_NAME=$2
  if [ -z "$PARAMETER" ]
  then
    echo "Missing required parameter: $PARAMETER_NAME. Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
    exit
  fi
}



check_if_parameter_is_empty "$GCP_PUBSUB_TOPIC" "'googleCloud.metrics.pubSubTopic'"
check_if_parameter_is_empty "$GCP_SCHEDULER_NAME" "'googleCloud.metrics.scheduler'"
check_if_parameter_is_empty "$DYNATRACE_URL_SECRET_NAME" "'googleCloud.common.dynatraceUrlSecretName'"
check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY_SECRET_NAME" "'googleCloud.common.dynatraceAccessKeySecretName'"
check_if_parameter_is_empty "$GCP_FUNCTION_NAME" 'googleCloud.metrics.function'
check_if_parameter_is_empty "$GCP_IAM_ROLE" "'googleCloud.common.iamRole'"
check_if_parameter_is_empty "$GCP_SERVICE_ACCOUNT" "'googleCloud.common.serviceAccount'"
check_if_parameter_is_empty "$QUERY_INTERVAL_MIN" "'googleCloud.metrics.queryInterval'"

echo  "- Logging to your account..."
GCP_ACCOUNT=$(gcloud config get-value account)
echo -e "You are now logged in as [$GCP_ACCOUNT]"
echo
DEFAULT_PROJECT=$(gcloud config get-value project)

echo "Please provide the GCP project ID where Dynatrace function should be deployed to. Default value: [$DEFAULT_PROJECT] (current project)"
echo
echo "Available projects:"
gcloud projects list --format="value(project_id)"
echo
while ! [[ "${GCP_PROJECT}" =~ ^[a-z]{1}[a-z0-9-]{5,29}$ ]]; do
    read -p "Enter GCP project ID: " -i $DEFAULT_PROJECT -e GCP_PROJECT
done
echo ""

echo "Please provide the size of Your GCP environment to adjust memory allocated to monitoring function"
echo "[s] - small, up to 500 instances, 256 MB memory allocated to function"
echo "[m] - medium, up to 1000 instances, 512 MB memory allocated to function"
echo "[l] - large, up to 5000 instances, 2048 MB memory allocated to function"
echo "Default value: [$DEFAULT_GCP_FUNCTION_SIZE]"
 while ! [[ "${GCP_FUNCTION_SIZE}" =~ ^(s|m|l)$ ]]; do
    read -p "Enter function size: " -i $DEFAULT_GCP_FUNCTION_SIZE -e GCP_FUNCTION_SIZE
done
echo ""

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
    echo "unexepected function size"
    exit 1
    ;;
esac

echo "Please provide the URL used to access Dynatrace, for example: https://mytenant.live.dynatrace.com/"
while ! [[ "${DYNATRACE_URL}" =~ ^(https?:\/\/[-a-zA-Z0-9@:%._+~=]{1,256}\/)(e\/[a-z0-9-]{36}\/)?$ ]]; do
    read -p "Enter Dynatrace tenant URI: " DYNATRACE_URL
done
echo ""

echo "Please log in to Dynatrace, and generate API token (Settings->Integration->Dynatrace API). The token requires grant of 'API v2 Ingest metrics', 'API v1 Read configuration' and 'WriteConfig' scope"
while ! [[ "${DYNATRACE_ACCESS_KEY}" != "" ]]; do
    read -p "Enter Dynatrace API token: " DYNATRACE_ACCESS_KEY
done
echo ""

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

echo -e
echo "- enable googleapis [secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudmonitoring.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com]"
gcloud services enable secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com

echo -e
echo "- create the pubsub topic [$GCP_PUBSUB_TOPIC]"
if [[ $(gcloud pubsub topics list --filter=name:$GCP_PUBSUB_TOPIC --format="value(name)") ]]; then
    echo "Topic [$GCP_PUBSUB_TOPIC] already exists, skipping"
else
    gcloud pubsub topics create "$GCP_PUBSUB_TOPIC"
fi

echo -e
echo "- create secrets [$DYNATRACE_URL_SECRET_NAME, $DYNATRACE_ACCESS_KEY_SECRET_NAME]"
if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_URL_SECRET_NAME$" --format="value(name)" ) ]]; then
    echo "Secret [$DYNATRACE_URL_SECRET_NAME] already exists, skipping"
else
    printf "$DYNATRACE_URL" | gcloud secrets create $DYNATRACE_URL_SECRET_NAME --data-file=- --replication-policy=automatic
fi

if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_ACCESS_KEY_SECRET_NAME$" --format="value(name)" ) ]]; then
    echo "Secret [$DYNATRACE_ACCESS_KEY_SECRET_NAME] already exists, skipping"
else
    stty -echo
    printf "$DYNATRACE_ACCESS_KEY" | gcloud secrets create $DYNATRACE_ACCESS_KEY_SECRET_NAME --data-file=- --replication-policy=automatic
    stty echo
fi

echo -e
echo "- create GCP IAM Role"
if [[ $(gcloud iam roles list --filter="name ~ $GCP_IAM_ROLE$" --format="value(name)" --project="$GCP_PROJECT") ]]; then
    echo "Role [$GCP_IAM_ROLE] already exists, skipping"
else
    readonly GCP_IAM_ROLE_TITLE="Dynatrace GCP Metrics Function"
    readonly GCP_IAM_ROLE_DESCRIPTION="Role for Dynatrace GCP function operating in metrics mode"
    readonly GCP_IAM_ROLE_PERMISSIONS_STRING=$(IFS=, ; echo "${GCP_IAM_ROLE_PERMISSIONS[*]}")
    gcloud iam roles create $GCP_IAM_ROLE --project="$GCP_PROJECT" --title="$GCP_IAM_ROLE_TITLE" --description="$GCP_IAM_ROLE_DESCRIPTION" --stage="GA" --permissions="$GCP_IAM_ROLE_PERMISSIONS_STRING"
fi

echo -e
echo "- create service account [$GCP_SERVICE_ACCOUNT with created role [roles/$GCP_IAM_ROLE]"
if [[ $(gcloud iam service-accounts list --filter=name:$GCP_SERVICE_ACCOUNT --format="value(name)") ]]; then
    echo "Service account [$GCP_SERVICE_ACCOUNT] already exists, skipping"
else
    gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT"
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$GCP_IAM_ROLE"
    gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
    gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer
    gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
    gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer
fi

echo -e
echo "- downloading functions source [$FUNCTION_REPOSITORY_RELEASE_URL]"
wget -q $FUNCTION_REPOSITORY_RELEASE_URL -O $FUNCTION_ZIP_PACKAGE


echo "- extracting archive [$FUNCTION_ZIP_PACKAGE]"
mkdir -p $GCP_FUNCTION_NAME
unzip -o -q ./$FUNCTION_ZIP_PACKAGE -d ./$GCP_FUNCTION_NAME || exit
echo "- deploy the function [$GCP_FUNCTION_NAME]"
pushd ./$GCP_FUNCTION_NAME || exit
GCP_FUNCTION_TIMEOUT=$(( QUERY_INTERVAL_MIN*60 ))
gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --memory="$GCP_FUNCTION_MEMORY"  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --set-env-vars ^:^GCP_SERVICES=$FUNCTION_GCP_SERVICES:PRINT_METRIC_INGEST_INPUT=$PRINT_METRIC_INGEST_INPUT:COMPATIBILITY_MODE=$COMPATIBILITY_MODE:DYNATRACE_ACCESS_KEY_SECRET_NAME=$DYNATRACE_ACCESS_KEY_SECRET_NAME:DYNATRACE_URL_SECRET_NAME=$DYNATRACE_URL_SECRET_NAME:REQUIRE_VALID_CERTIFICATE=$REQUIRE_VALID_CERTIFICATE:SERVICE_USAGE_BOOKING=$SERVICE_USAGE_BOOKING:USE_PROXY=$USE_PROXY:HTTP_PROXY=$HTTP_PROXY:HTTPS_PROXY=$HTTPS_PROXY:SELF_MONITORING_ENABLED=$SELF_MONITORING_ENABLED:QUERY_INTERVAL_MIN=$QUERY_INTERVAL_MIN

echo -e
echo "- schedule the runs"
if [[ $(gcloud scheduler jobs list --filter=name:$GCP_SCHEDULER_NAME --format="value(name)") ]]; then
    echo "Scheduler [$GCP_SCHEDULER_NAME] already exists, skipping"
else
    GCP_SCHEDULER_CRON="*/${QUERY_INTERVAL_MIN} * * * *"
    gcloud scheduler jobs create pubsub "$GCP_SCHEDULER_NAME" --topic="$GCP_PUBSUB_TOPIC" --schedule="$GCP_SCHEDULER_CRON" --message-body="x"
fi

echo -e
echo "- create self monitoring dashboard"
SELF_MONITORING_DASHBOARD_NAME=$(cat dashboards/dynatrace-gcp-function_self_monitoring.json | jq .displayName)
if [[ $(gcloud monitoring dashboards  list --filter=displayName:"$SELF_MONITORING_DASHBOARD_NAME" --format="value(displayName)") ]]; then
    echo "Dashboard already exists, skipping"
else
    gcloud monitoring dashboards create --config-from-file=dashboards/dynatrace-gcp-function_self_monitoring.json
fi

IMPORTED_DASHBOARD_IDS=()
if [[ "${IMPORT_DASHBOARDS,,}" =~ ^(yes|true)$ ]] ; then
  EXISTING_DASHBOARDS=$(dt_api "api/config/v1/dashboards" | jq -r '.dashboards[].name | select (. |contains("Google"))')
  if [ -n "${EXISTING_DASHBOARDS}" ]; then
      warn "Found existing Google dashboards in [${DYNATRACE_URL}] tenant:\n$EXISTING_DASHBOARDS"
  fi

  for DASHBOARD_PATH in $(get_ext_files 'dashboards[].dashboard')
  do
    DASHBOARD_JSON=$(cat "./$DASHBOARD_PATH")
    DASHBOARD_NAME=$(jq -r .dashboardMetadata.name < "./$DASHBOARD_PATH")
    if ! grep -q "$DASHBOARD_NAME" <<< "$EXISTING_DASHBOARDS"; then
      echo "- Create [$DASHBOARD_NAME] dashboard from file [$DASHBOARD_PATH]"
          if ! DASHBOARD_RESPONSE=$(dt_api "api/config/v1/dashboards" POST "$DASHBOARD_JSON"); then
            warn "Unable to create dashboard($?)\n$DASHBOARD_RESPONSE"
            continue
          fi
          IMPORTED_DASHBOARD_IDS+=("$(jq -r .id <<< "$DASHBOARD_RESPONSE")")
    else
      echo "- Dashboard [$DASHBOARD_NAME] already exists on cluster, skipping"
    fi
  done

  for DASHBOARD_ID in "${IMPORTED_DASHBOARD_IDS[@]}"
  do
    DASHBOARD_SHARE_RESPONSE=$(dt_api "api/config/v1/dashboards/${DASHBOARD_ID}/shareSettings" \
        PUT "{ \"id\": \"${DASHBOARD_ID}\",\"published\": \"true\", \"preset\": \"true\", \"enabled\" : \"true\", \"publicAccess\" : { \"managementZoneIds\": [], \"urls\": {}}, \"permissions\": [ { \"type\": \"ALL\", \"permission\": \"VIEW\"} ] }"\
        ) || warn "Unable to set dashboard permissions($?)\n$DASHBOARD_SHARE_RESPONSE"
  done

else
  echo "Dashboards import disabled"
fi

if [[ "${IMPORT_ALERTS,,}" =~ ^(yes|true)$ ]]; then
  echo "- Importing alerts"
  EXISTING_ALERTS=$(dt_api "api/config/v1/anomalyDetection/metricEvents"| jq -r '.values[] | select (.id |startswith("cloud.gcp.")) | (.id + "\t" + .name )')
  if [ -n "${EXISTING_ALERTS}" ]; then
      warn "Found existing Google alerts in [${DYNATRACE_URL}] tenant:\n$EXISTING_ALERTS"
  fi

  for ALERT_PATH in $(get_ext_files 'alerts[].path')
  do
    ALERT_JSON=$(cat "./$ALERT_PATH")
    ALERT_ID=$(jq -r .id < "./$ALERT_PATH")
    ALERT_NAME=$(jq -r  .name < "./$ALERT_PATH" )

    if ! grep -q "$ALERT_ID" <<< "$EXISTING_ALERTS"; then
      echo "- Create [$ALERT_NAME] alert from file [$ALERT_PATH]"
      RESPONSE=$(dt_api "api/config/v1/anomalyDetection/metricEvents/$ALERT_ID" PUT "$ALERT_JSON") || warn "Unable to create alert($?):\n$RESPONSE"
    else
      echo "- Alert [$ALERT_NAME] already exists on cluster, skipping"
    fi
  done
else
  echo "Alerts import disabled"
fi
echo "- cleaning up"

popd || exit 1
echo "- removing archive [$FUNCTION_ZIP_PACKAGE]"
rm ./$FUNCTION_ZIP_PACKAGE

echo "- removing temporary directory [$FUNCTION_ZIP_PACKAGE]"
rm -r ./$GCP_FUNCTION_NAME
