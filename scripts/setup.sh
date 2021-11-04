#!/usr/bin/env bash
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

warn() {
  MESSAGE=$1
  echo -e >&2
  echo -e "\e[93mWARNING: \e[37m$MESSAGE" >&2
  echo -e >&2
}

err() {
  MESSAGE=$1
  echo -e >&2
  echo -e "\e[91mERROR: \e[37m$MESSAGE" >&2
  echo -e >&2
}

clean() {
  echo "- removing archive [$FUNCTION_ZIP_PACKAGE]"
  rm $WORKING_DIR/$FUNCTION_ZIP_PACKAGE

  echo "- removing temporary directory [$GCP_FUNCTION_NAME]"
  rm -r $WORKING_DIR/$GCP_FUNCTION_NAME

  echo "- removing extensions files"
  rm -rf $EXTENSIONS_TMPDIR $EXTENSION_MANIFEST_FILE
}

onFailure() {
    clean
    err " - deployment failed, please examine error messages and run again"
    exit 2
}

ctrl_c() {
  clean
  err " - deployment failed, script was break by CTRL-C"
  exit 3
}

trap ctrl_c INT
trap onFailure ERR

versionNumber() {
   echo "$@" | awk -F. '{ printf("%d%03d%03d%03d\n", $1,$2,$3,$4); }';
}

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring"
echo -e "\033[0;37m"

print_help() {
  printf "
usage: setup.sh [--upgrade-extensions]

arguments:
    --upgrade-extensions
                            Upgrade all extensions into dynatrace cluster
    -d, --auto-default
                            Disable all interactive prompts when running gcloud commands.
                            If input is required, defaults will be used, or an error will be raised.
    -h, --help
                            Show this help message and exit
    "
}

if ! command -v yq &> /dev/null
then

    err 'yq and jq is required to install Dynatrace function. Please refer to following links for installation instructions:
    YQ: https://github.com/mikefarah/yq
    Example command to install yq:
    sudo wget https://github.com/mikefarah/yq/releases/download/v4.9.8/yq_linux_amd64 -O /usr/bin/yq && sudo chmod +x /usr/bin/yq'
    if ! command -v jq &> /dev/null
    then
        echo -e "JQ: https://stedolan.github.io/jq/download/"
    fi
    err 'You may also try installing YQ with PIP: pip install yq'
    exit 1
else
  VERSION_YQ=$(yq --version | cut -d' ' -f3 | tr -d '"')

  if [ "$VERSION_YQ" == "version" ]; then
    VERSION_YQ=$(yq --version | cut -d' ' -f4 | tr -d '"')
  fi

  echo "Using yq version $VERSION_YQ"

  if [ "$(versionNumber $VERSION_YQ)" -lt "$(versionNumber '4.0.0')" ]; then

      err 'yq in 4+ version is required to install Dynatrace function. Please refer to following links for installation instructions:
      YQ: https://github.com/mikefarah/yq'
      exit 1
  fi
fi


if ! command -v gcloud &> /dev/null
then

    err 'Google Cloud CLI is required to install Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:'
    err 'https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version'
    exit
fi

if ! command -v unzip &> /dev/null
then
    err 'unzip is required to install Dynatrace function'
    exit
fi

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

            "-d" | "--auto-default") #todo ms
                export CLOUDSDK_CORE_DISABLE_PROMPTS=1
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

readonly FUNCTION_REPOSITORY_RELEASE_URL=$(curl -s "https://api.github.com/repos/dynatrace-oss/dynatrace-gcp-function/releases" -H "Accept: application/vnd.github.v3+json" | jq 'map(select(.assets[].name == "dynatrace-gcp-function.zip" and .prerelease != true)) | sort_by(.created_at) | last | .assets[] | select( .name =="dynatrace-gcp-function.zip") | .browser_download_url' -r)
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml
readonly EXTENSION_MANIFEST_FILE=extensions-list.txt
EXTENSIONS_TMPDIR=$(mktemp -d)
CLUSTER_EXTENSIONS_TMPDIR=$(mktemp -d)
WORKING_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ -z "$EXTENSION_S3_URL" ]; then
  EXTENSION_S3_URL="https://dynatrace-gcp-extensions.s3.amazonaws.com"
else
  warn "Development mode on: custom S3 url link."
fi

if [[ "$USE_LOCAL_FUNCTION_ZIP" != "Y" ]]; then
  echo -e
  echo "- downloading functions source [$FUNCTION_REPOSITORY_RELEASE_URL]"
  wget -q $FUNCTION_REPOSITORY_RELEASE_URL -O $WORKING_DIR/$FUNCTION_ZIP_PACKAGE
fi

echo "- extracting archive [$FUNCTION_ZIP_PACKAGE]"
TMP_FUNCTION_DIR=$(mktemp -d)
unzip -o -q $WORKING_DIR/$FUNCTION_ZIP_PACKAGE -d $TMP_FUNCTION_DIR || exit

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
  echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, extracting default from release"
  mv $TMP_FUNCTION_DIR/$FUNCTION_ACTIVATION_CONFIG -O $FUNCTION_ACTIVATION_CONFIG
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
readonly FUNCTION_GCP_SERVICES=$(yq e -j '.activation.metrics.services' $FUNCTION_ACTIVATION_CONFIG | jq 'join(",")' 2>/dev/null)
readonly SERVICES_TO_ACTIVATE=$(yq e -j '.activation.metrics.services' $FUNCTION_ACTIVATION_CONFIG | jq -r .[]? | sed 's/\/.*$//')
SERVICES_FROM_ACTIVATION_CONFIG=($(yq e -j '.activation.metrics.services' $FUNCTION_ACTIVATION_CONFIG | jq -r .[]? ))
readonly PRINT_METRIC_INGEST_INPUT=$(yq e '.debug.printMetricIngestInput' $FUNCTION_ACTIVATION_CONFIG)
readonly DEFAULT_GCP_FUNCTION_SIZE=$(yq e '.googleCloud.common.cloudFunctionSize' $FUNCTION_ACTIVATION_CONFIG)
readonly SERVICE_USAGE_BOOKING=$(yq e '.googleCloud.common.serviceUsageBooking' $FUNCTION_ACTIVATION_CONFIG)
readonly USE_PROXY=$(yq e '.googleCloud.common.useProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTP_PROXY=$(yq e '.googleCloud.common.httpProxy' $FUNCTION_ACTIVATION_CONFIG)
readonly HTTPS_PROXY=$(yq e '.googleCloud.common.httpsProxy' $FUNCTION_ACTIVATION_CONFIG)
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
EXTENSIONS_FROM_CLUSTER=""

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
      warn "Received ${CODE} response from ${DYNATRACE_URL}${URL}"
      return 1
    fi
  else
    warn "Unable to connect to ${DYNATRACE_URL}"
    return 2
  fi
}

get_ext_files() {
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

get_extensions_zip_packages() {
  curl -s -O $EXTENSION_S3_URL/$EXTENSION_MANIFEST_FILE
  EXTENSIONS_LIST=$(grep "^google.*\.zip" < "$EXTENSION_MANIFEST_FILE" 2>/dev/null)
  if [ -z "$EXTENSIONS_LIST" ]; then
    err "Empty extensions manifest file downloaded"
    exit 1
  fi

  echo "${EXTENSIONS_LIST}" | while IFS= read -r EXTENSION_FILE_NAME
  do
    echo -n "."
    (cd ${EXTENSIONS_TMPDIR} && curl -s -O "${EXTENSION_S3_URL}/${EXTENSION_FILE_NAME}")
  done
}

check_gcp_config_in_extension() {
    EXTENSION_ZIP=$1

    echo ${EXTENSION_ZIP}
    unzip ${EXTENSION_ZIP} -d "$EXTENSION_ZIP-tmp" &> /dev/null
    if [[ $(unzip -c "$EXTENSION_ZIP-tmp/extension.zip" "extension.yaml" | tail -n +3 | yq e 'has("gcp")' -) == "false" ]] ; then
        warn "- Extension $EXTENSION_ZIP definition is incorrect. The definition must contain 'gcp' section. The extension won't be uploaded."
        rm ${EXTENSION_ZIP}
    fi
    rm -r "$EXTENSION_ZIP-tmp"
}

check_gcp_config_in_extensions() {
    EXTENSION_DIR=$1

    pushd ${EXTENSION_DIR} &> /dev/null  || exit
    for EXTENSION_ZIP in *.zip; do
        check_gcp_config_in_extension ${EXTENSION_ZIP}
    done
    popd &> /dev/null
}

upload_extension_to_cluster() {
  DYNATRACE_URL=$1
  DYNATRACE_ACCESS_KEY=$2
  EXTENSION_ZIP=$3
  EXTENSION_VERSION=$4

  UPLOAD_RESPONSE=$(curl -s -k -X POST "${DYNATRACE_URL}api/v2/extensions" -w "<<HTTP_CODE>>%{http_code}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" -H "Content-Type: multipart/form-data" -F "file=@$EXTENSION_ZIP;type=application/zip")
  CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<<"$UPLOAD_RESPONSE")

  if [[ "$CODE" -ge "400" ]]; then
    warn "- Extension $EXTENSION_ZIP upload failed with error code: $CODE"
  else
    UPLOADED_EXTENSION=$(echo "$UPLOAD_RESPONSE" | sed -r 's/<<HTTP_CODE>>.*$//' | jq -r '.extensionName')

    if ! RESPONSE=$(dt_api "api/v2/extensions/${UPLOADED_EXTENSION}/environmentConfiguration" "PUT" "{\"version\": \"${EXTENSION_VERSION}\"}"); then
      warn "- Activation $EXTENSION_ZIP failed."
    else
      echo
      echo "- Extension $UPLOADED_EXTENSION:$EXTENSION_VERSION activated."
    fi
  fi
}

get_activated_extensions_on_cluster() {
  DYNATRACE_URL=$1
  DYNATRACE_ACCESS_KEY=$2

  if RESPONSE=$(dt_api "api/v2/extensions"); then
    EXTENSIONS_FROM_CLUSTER=$(echo "$RESPONSE" | sed -r 's/<<HTTP_CODE>>.*$//' | jq -r '.extensions[] | select(.extensionName) | "\(.extensionName):\(.version)"')
  else
    err "- Dynatrace Cluster failed on ${DYNATRACE_URL}api/v2/extensions endpoint."
    exit
  fi
}

activate_extension_on_cluster() {
  DYNATRACE_URL=$1
  DYNATRACE_ACCESS_KEY=$2
  EXTENSIONS_FROM_CLUSTER=$3
  EXTENSION_ZIP=$4

  EXTENSION_NAME=${EXTENSION_ZIP:0:${#EXTENSION_ZIP}-10}
  EXTENSION_VERSION=${EXTENSION_ZIP: -9:5}
  EXTENSION_IN_DT=$(echo "${EXTENSIONS_FROM_CLUSTER[*]}" | grep "${EXTENSION_NAME}:")

  if [ -z "$EXTENSION_IN_DT" ]; then
    # missing extension in cluster installing it
    upload_extension_to_cluster "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY" "$EXTENSION_ZIP" "$EXTENSION_VERSION"
  elif [ "$(versionNumber ${EXTENSION_VERSION})" -gt "$(versionNumber ${EXTENSION_IN_DT: -5})" ]; then
    # cluster has never version warning and install if flag was set
    if [ -n "$UPGRADE_EXTENSIONS" ]; then
      upload_extension_to_cluster "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY" "$EXTENSION_ZIP" "$EXTENSION_VERSION"
    else
      warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT: -5} installed on the cluster, use '--upgrade-extensions' to uprgate to: ${EXTENSION_NAME}:${EXTENSION_VERSION}"
    fi
  elif [ "$(versionNumber ${EXTENSION_VERSION})" -lt "$(versionNumber ${EXTENSION_IN_DT: -5})" ]; then
    warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT: -5} installed on the cluster is newer than ${EXTENSION_NAME}:${EXTENSION_VERSION}"
  fi
}

check_if_parameter_is_empty()
{
  PARAMETER=$1
  PARAMETER_NAME=$2
  if [ "$PARAMETER" == "null" ] || [ -z "$PARAMETER" ]; then
    warn "Missing required parameter: $PARAMETER_NAME. Please set proper value in ./activation-config.yaml or delete it to fetch latest version automatically"
    exit
  fi
}

check_api_token() {
  DYNATRACE_URL=$1
  DYNATRACE_ACCESS_KEY=$2
  V1_API_REQUIREMENTS=("ReadConfig" "WriteConfig")
  V2_API_REQUIREMENTS=("extensions.read" "extensions.write" "extensionConfigurations.read" "extensionConfigurations.write" "extensionEnvironment.read" "extensionEnvironment.write")

  if RESPONSE=$(dt_api "api/v2/apiTokens/lookup" "POST" "{\"token\":\"$DYNATRACE_ACCESS_KEY\"}"); then
    for REQUIRED in "${V1_API_REQUIREMENTS[@]}"; do
      if ! grep -q "$REQUIRED" <<<"$RESPONSE"; then
        err "Missing $REQUIRED permission (v1) for the API token"
        exit 1
      fi
    done

    for REQUIRED in "${V2_API_REQUIREMENTS[@]}"; do
      if ! grep -q "$REQUIRED" <<<"$RESPONSE"; then
        err "Missing $REQUIRED permission (v2) for the API token"
        exit 1
      fi
    done
  else
    warn "Failed to connect to endpoint $DYNATRACE_URL to check API token permissions. It can be ignored if Dynatrace does not allow public access."
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
check_if_parameter_is_empty "$FUNCTION_GCP_SERVICES" "'googleCloud.activation.metrics.services'"

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

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

UPDATE=$(gcloud functions list --filter=$GCP_FUNCTION_NAME --project="$GCP_PROJECT" --format="value(name)")
INSTALL=true

if [ -n  "$UPDATE" ]; then
echo -e "- function \e[1;32m $GCP_FUNCTION_NAME \e[0m already exists in $GCP_PROJECT and it will be updated"
INSTALL=false
fi

if [ "$INSTALL" == true ]; then
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
      echo "unexpected function size"
      exit 1
      ;;
  esac
fi

echo "Please provide the URL used to access Dynatrace, for example: https://mytenant.live.dynatrace.com/"
while ! [[ "${DYNATRACE_URL}" =~ ^(https?:\/\/[-a-zA-Z0-9@:%._+~=]{1,256}\/)(e\/[a-z0-9-]{36}\/)?$ ]]; do
  read -p "Enter Dynatrace tenant URI: " DYNATRACE_URL
done
echo ""

echo "Please log in to Dynatrace, and generate API token (Settings->Integration->Dynatrace API)."
echo "The token requires grant of 'Ingest metrics (API v2)', 'Read extensions (API v2)', 'Write extensions (API v2)', 'Read configuration (API v1)',  and 'Write configuration (API v1)' scope"
while ! [[ "${DYNATRACE_ACCESS_KEY}" != "" ]]; do
  read -s -p "Enter Dynatrace API token: " DYNATRACE_ACCESS_KEY #todo ms -s?
done
echo ""

if [ "$INSTALL" == true ]; then
  if EXTENSIONS_SCHEMA_RESPONSE=$(dt_api "api/v2/extensions/schemas"); then
    GCP_EXTENSIONS_SCHEMA_PRESENT=$(jq -r '.versions[] | select(.=="1.229.0")' <<<"${EXTENSIONS_SCHEMA_RESPONSE}")
    if [ -z "${GCP_EXTENSIONS_SCHEMA_PRESENT}" ]; then
      err "Dynatrace environment does not supports GCP extensions schema. Dynatrace needs to be running versions 1.229 or higher to complete installation."
      exit 1
    fi
  fi

  echo -e
  echo "- enable googleapis [secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudmonitoring.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com]"
  gcloud services enable secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com

  echo -e #todo ms update?
  echo "- create the pubsub topic [$GCP_PUBSUB_TOPIC]"
  if [[ $(gcloud pubsub topics list --filter=name:$GCP_PUBSUB_TOPIC --format="value(name)") ]]; then
      echo "Topic [$GCP_PUBSUB_TOPIC] already exists, skipping"
  else
      gcloud pubsub topics create "$GCP_PUBSUB_TOPIC"
  fi

  echo -e #todo ms update?
  echo "- create secrets [$DYNATRACE_URL_SECRET_NAME, $DYNATRACE_ACCESS_KEY_SECRET_NAME]"
  if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_URL_SECRET_NAME$" --format="value(name)" ) ]]; then
      echo "Secret [$DYNATRACE_URL_SECRET_NAME] already exists, skipping"
  else
      printf "$DYNATRACE_URL" | gcloud secrets create $DYNATRACE_URL_SECRET_NAME --data-file=- --replication-policy=automatic
  fi

  if [[ $(gcloud secrets list --filter="name ~ $DYNATRACE_ACCESS_KEY_SECRET_NAME$" --format="value(name)" ) ]]; then
      echo "Secret [$DYNATRACE_ACCESS_KEY_SECRET_NAME] already exists, skipping"
  else
      gcloud secrets create $DYNATRACE_ACCESS_KEY_SECRET_NAME --data-file=- --replication-policy=automatic <<<"$DYNATRACE_ACCESS_KEY"
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
      gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT" >/dev/null
      gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$GCP_IAM_ROLE" >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_URL_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
      gcloud secrets add-iam-policy-binding $DYNATRACE_ACCESS_KEY_SECRET_NAME --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer >/dev/null
  fi
fi

check_api_token "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY"

echo -e
echo "- downloading extensions"
get_extensions_zip_packages

echo -e
echo "- checking extensions"
check_gcp_config_in_extensions $EXTENSIONS_TMPDIR

echo -e
echo "- checking activated extensions in Dynatrace"
get_activated_extensions_on_cluster "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY"

mv $TMP_FUNCTION_DIR $WORKING_DIR/$GCP_FUNCTION_NAME
pushd $WORKING_DIR/$GCP_FUNCTION_NAME || exit

if [ "$QUERY_INTERVAL_MIN" -lt 1 ] || [ "$QUERY_INTERVAL_MIN" -gt 6 ]; then
  echo "Invalid value of 'googleCloud.metrics.queryInterval', defaulting to 3"
  GCP_FUNCTION_TIMEOUT=180
  GCP_SCHEDULER_CRON="*/3 * * * *"
else
  GCP_FUNCTION_TIMEOUT=$(( QUERY_INTERVAL_MIN*60 ))
  GCP_SCHEDULER_CRON="*/${QUERY_INTERVAL_MIN} * * * *"
fi

# If --upgrade option is not set, all gcp extensions are downloaded from the cluster to get configuration of gcp services for version that is currently active on the cluster.
if [[ "$UPGRADE_EXTENSIONS" != "Y" && -n "$EXTENSIONS_FROM_CLUSTER" ]]; then
  echo -e
  echo "- downloading active extensions from Dynatrace"

  cd ${CLUSTER_EXTENSIONS_TMPDIR} || exit

  EXTENSIONS_TO_DOWNLOAD="com.dynatrace.extension.google"
  readarray -t EXTENSIONS_FROM_CLUSTER_ARRAY <<<"$( echo "${EXTENSIONS_FROM_CLUSTER}" | sed 's/ /\n/' | grep "$EXTENSIONS_TO_DOWNLOAD" )"
  for i in "${!EXTENSIONS_FROM_CLUSTER_ARRAY[@]}"; do
    EXTENSION_NAME="$(cut -d':' -f1 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"
    EXTENSION_VERSION="$(cut -d':' -f2 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"
    curl -k -s -X GET "${DYNATRACE_URL}api/v2/extensions/${EXTENSION_NAME}/${EXTENSION_VERSION}" -H "Accept: application/octet-stream" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" -o "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip"
    if [ -f "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ] && [[ "$EXTENSION_NAME" =~ ^com.dynatrace.extension.(google.*)$ ]]; then
      check_gcp_config_in_extension "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip"
      if [ -f "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ]; then
        find ${EXTENSIONS_TMPDIR} -regex ".*${BASH_REMATCH[1]}.*" -exec rm -rf {} \;
        mv "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ${EXTENSIONS_TMPDIR}
      fi
    fi
  done
fi

echo
echo "- read activation config"
# Add '/default' to service name when featureSet is missing
for i in "${!SERVICES_FROM_ACTIVATION_CONFIG[@]}"; do
  if ! [[ "${SERVICES_FROM_ACTIVATION_CONFIG[$i]}" == *"/"* ]];then
    SERVICES_FROM_ACTIVATION_CONFIG[$i]="${SERVICES_FROM_ACTIVATION_CONFIG[$i]}/default"
  fi
done
SERVICES_FROM_ACTIVATION_CONFIG_STR="${SERVICES_FROM_ACTIVATION_CONFIG[*]}"
echo "${SERVICES_FROM_ACTIVATION_CONFIG_STR}"

mkdir -p $WORKING_DIR/$GCP_FUNCTION_NAME/config/
cd ${EXTENSIONS_TMPDIR} || exit
echo
echo "- choosing and uploading extensions to Dynatrace"
for EXTENSION_ZIP in *.zip; do
  EXTENSION_FILE_NAME="$(basename "$EXTENSION_ZIP" .zip)"
  unzip -j -q "$EXTENSION_ZIP" "extension.zip"
  unzip -p -q "extension.zip" "extension.yaml" >"$EXTENSION_FILE_NAME".yaml
  EXTENSION_GCP_CONFIG=$(yq e '.gcp' "$EXTENSION_FILE_NAME".yaml)
  #Get all service/featureSet pairs defined in extensions
  SERVICES_FROM_EXTENSIONS=$(echo "$EXTENSION_GCP_CONFIG" | yq e -j | jq -r 'to_entries[] | "\(.value.service)/\(.value.featureSet)"')
  for SERVICE_FROM_EXTENSION in $SERVICES_FROM_EXTENSIONS; do
    SERVICE_FROM_EXTENSION="${SERVICE_FROM_EXTENSION/null/default}"
    #Check if service should be monitored
    if [[ "$SERVICES_FROM_ACTIVATION_CONFIG_STR" == *"$SERVICE_FROM_EXTENSION"* ]]; then
      CONFIG_NAME=$(yq e '.name' "$EXTENSION_FILE_NAME".yaml)
      if [[ "$CONFIG_NAME" =~ ^.*\.(.*)$ ]]; then
        echo "gcp:" >$WORKING_DIR/$GCP_FUNCTION_NAME/config/"${BASH_REMATCH[1]}".yaml
        echo "$EXTENSION_GCP_CONFIG" >>$WORKING_DIR/$GCP_FUNCTION_NAME/config/"${BASH_REMATCH[1]}".yaml
      fi
      activate_extension_on_cluster "$DYNATRACE_URL" "$DYNATRACE_ACCESS_KEY" "$EXTENSIONS_FROM_CLUSTER" "$EXTENSION_ZIP"
      break
    fi
    echo -n "."
  done
  rm extension.zip
  rm "$EXTENSION_FILE_NAME".yaml
  rm "$EXTENSION_ZIP"
done
cd $WORKING_DIR/$GCP_FUNCTION_NAME || exit
rm -rf ${CLUSTER_EXTENSIONS_TMPDIR}

if [ "$INSTALL" == true ]; then
  echo -e
  echo -e "- deploying the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m"
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --memory="$GCP_FUNCTION_MEMORY"  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --set-env-vars ^:^GCP_SERVICES=$FUNCTION_GCP_SERVICES:PRINT_METRIC_INGEST_INPUT=$PRINT_METRIC_INGEST_INPUT:DYNATRACE_ACCESS_KEY_SECRET_NAME=$DYNATRACE_ACCESS_KEY_SECRET_NAME:DYNATRACE_URL_SECRET_NAME=$DYNATRACE_URL_SECRET_NAME:REQUIRE_VALID_CERTIFICATE=$REQUIRE_VALID_CERTIFICATE:SERVICE_USAGE_BOOKING=$SERVICE_USAGE_BOOKING:USE_PROXY=$USE_PROXY:HTTP_PROXY=$HTTP_PROXY:HTTPS_PROXY=$HTTPS_PROXY:SELF_MONITORING_ENABLED=$SELF_MONITORING_ENABLED:QUERY_INTERVAL_MIN=$QUERY_INTERVAL_MIN
else

  while true; do
    echo -e
    read -p "- your Cloud Function will be updated - any manual changes made to Cloud Function environment variables will be replaced with values from 'activation-config.yaml' file, do you want to continue? [y/n]" yn
    case $yn in
        [Yy]* ) echo -e "- updating the function \e[1;92m[$GCP_FUNCTION_NAME]\e[0m";  break;;
        [Nn]* ) echo -e "Update aborted" ; exit;;
        * ) echo "- please answer yes or no.";;
    esac
  done
  gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --timeout="$GCP_FUNCTION_TIMEOUT" --set-env-vars ^:^GCP_SERVICES=$FUNCTION_GCP_SERVICES:PRINT_METRIC_INGEST_INPUT=$PRINT_METRIC_INGEST_INPUT:DYNATRACE_ACCESS_KEY_SECRET_NAME=$DYNATRACE_ACCESS_KEY_SECRET_NAME:DYNATRACE_URL_SECRET_NAME=$DYNATRACE_URL_SECRET_NAME:REQUIRE_VALID_CERTIFICATE=$REQUIRE_VALID_CERTIFICATE:SERVICE_USAGE_BOOKING=$SERVICE_USAGE_BOOKING:USE_PROXY=$USE_PROXY:HTTP_PROXY=$HTTP_PROXY:HTTPS_PROXY=$HTTPS_PROXY:SELF_MONITORING_ENABLED=$SELF_MONITORING_ENABLED:QUERY_INTERVAL_MIN=$QUERY_INTERVAL_MIN
fi

echo -e
echo "- schedule the runs"
if [[ $(gcloud scheduler jobs list --filter=name:$GCP_SCHEDULER_NAME --format="value(name)") ]]; then
    echo "Recreating Cloud Scheduler [$GCP_SCHEDULER_NAME]"
    gcloud -q scheduler jobs delete "$GCP_SCHEDULER_NAME"
fi
gcloud scheduler jobs create pubsub "$GCP_SCHEDULER_NAME" --topic="$GCP_PUBSUB_TOPIC" --schedule="$GCP_SCHEDULER_CRON" --message-body="x"

echo -e
echo "- create self monitoring dashboard"
SELF_MONITORING_DASHBOARD_NAME=$(cat dashboards/dynatrace-gcp-function_self_monitoring.json | jq .displayName)
if [[ $(gcloud monitoring dashboards  list --filter=displayName:"$SELF_MONITORING_DASHBOARD_NAME" --format="value(displayName)") ]]; then
  echo "Dashboard already exists, skipping"
else
  gcloud monitoring dashboards create --config-from-file=dashboards/dynatrace-gcp-function_self_monitoring.json
fi

echo -e
echo "- cleaning up"

popd || exit 1
clean
