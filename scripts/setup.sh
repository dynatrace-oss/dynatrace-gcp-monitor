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

readonly FUNCTION_REPOSITORY_RELEASE_URL=$(curl -s "https://api.github.com/repos/dynatrace-oss/dynatrace-gcp-function/releases" -H "Accept: application/vnd.github.v3+json" | jq 'map(select(.assets[].name == "dynatrace-gcp-function.zip" and .prerelease != true)) | sort_by(.created_at) | last | .assets[] | select( .name =="dynatrace-gcp-function.zip") | .browser_download_url' -r)
readonly FUNCTION_RAW_REPOSITORY_URL=https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring"
echo -e "\033[0;37m"

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
    echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, downloading default"
    wget -q $FUNCTION_RAW_REPOSITORY_URL/$FUNCTION_ACTIVATION_CONFIG -O $FUNCTION_ACTIVATION_CONFIG
    echo
fi

readonly GCP_SERVICE_ACCOUNT=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.serviceAccount')
readonly REQUIRE_VALID_CERTIFICATE=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.requireValidCertificate')
readonly GCP_PUBSUB_TOPIC=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.pubSubTopic')
readonly GCP_FUNCTION_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.function')
readonly GCP_SCHEDULER_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.scheduler')
readonly GCP_SCHEDULER_CRON=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.schedulerSchedule')
readonly DYNATRACE_URL_SECRET_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.dynatraceUrlSecretName')
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.dynatraceAccessKeySecretName')
readonly FUNCTION_GCP_SERVICES=$(yq r -j -P $FUNCTION_ACTIVATION_CONFIG 'activation.metrics.services' | jq 'join(",")')
readonly DASHBOARDS_TO_ACTIVATE=$(yq r -j -P $FUNCTION_ACTIVATION_CONFIG 'activation.metrics.services' | jq -r .[]) 
readonly PRINT_METRIC_INGEST_INPUT=$(yq r $FUNCTION_ACTIVATION_CONFIG 'debug.printMetricIngestInput')
readonly DEFAULT_GCP_FUNCTION_SIZE=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.cloudFunctionSize')
readonly SERVICE_USAGE_BOOKING=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.serviceUsageBooking')


if ! command -v gcloud &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37mGoogle Cloud CLI is required to install Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:"
    echo -e
    echo -e "https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version"
    echo -e
    echo 
    exit
fi


if ! command -v yq &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37m yq and jq is required to install Dynatrace function. Please refer to following links for installation instructions"
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
    exit
fi


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
if [[ $(gcloud pubsub topics list --filter=name:dynatrace-gcp-service-invocation --format="value(name)") ]]; then 
    echo "Topic [$GCP_PUBSUB_TOPIC] already exists, skipping"
else
    gcloud pubsub topics create "$GCP_PUBSUB_TOPIC"
fi

echo -e
echo "- create secrets [$DYNATRACE_URL_SECRET_NAME, $DYNATRACE_ACCESS_KEY_SECRET_NAME]"
if [[ $(gcloud secrets list --filter=name:$DYNATRACE_URL_SECRET_NAME --format="value(name)" ) ]]; then
    echo "Secret [$DYNATRACE_URL_SECRET_NAME] already exists, skipping"
else
    printf "$DYNATRACE_URL" | gcloud secrets create $DYNATRACE_URL_SECRET_NAME --data-file=- --replication-policy=automatic
fi
if [[ $(gcloud secrets list --filter=name:$DYNATRACE_ACCESS_KEY_SECRET_NAME --format="value(name)" ) ]]; then
    echo "Secret [$DYNATRACE_ACCESS_KEY_SECRET_NAME] already exists, skipping"
else
    stty -echo
    printf "$DYNATRACE_ACCESS_KEY" | gcloud secrets create $DYNATRACE_ACCESS_KEY_SECRET_NAME --data-file=- --replication-policy=automatic
    stty echo
fi 

echo -e
echo "- create service account [$GCP_SERVICE_ACCOUNT with permissions [roles/monitoring.editor, roles/monitoring.viewer, roles/secretmanager.secretAccessor, roles/secretmanager.viewer, roles/cloudfunctions.viewer, roles/cloudsql.viewer, roles/compute.viewer, roles/file.viewer, roles/pubsub.viewer"
if [[ $(gcloud iam service-accounts list --filter=name:$GCP_SERVICE_ACCOUNT --format="value(name)") ]]; then
    echo "Service account [$GCP_SERVICE_ACCOUNT] already exists, skipping"
else
    gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT"
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/monitoring.editor
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/monitoring.viewer
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/compute.viewer
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/cloudsql.viewer
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/cloudfunctions.viewer
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/file.viewer
    gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/pubsub.viewer 
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
unzip -o -q ./$FUNCTION_ZIP_PACKAGE -d ./$GCP_FUNCTION_NAME
echo "- deploy the function [$GCP_FUNCTION_NAME]"
cd ./$GCP_FUNCTION_NAME
gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --memory="$GCP_FUNCTION_MEMORY"  --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only --set-env-vars ^:^GCP_SERVICES=$FUNCTION_GCP_SERVICES:PRINT_METRIC_INGEST_INPUT=$PRINT_METRIC_INGEST_INPUT:DYNATRACE_ACCESS_KEY_SECRET_NAME=$DYNATRACE_ACCESS_KEY_SECRET_NAME:DYNATRACE_URL_SECRET_NAME=$DYNATRACE_URL_SECRET_NAME:REQUIRE_VALID_CERTIFICATE=$REQUIRE_VALID_CERTIFICATE:SERVICE_USAGE_BOOKING=$SERVICE_USAGE_BOOKING

echo -e
echo "- schedule the runs"
if [[ $(gcloud scheduler jobs list --filter=name:$GCP_SCHEDULER_NAME --format="value(name)") ]]; then 
    echo "Scheduler [$GCP_SCHEDULER_NAME] already exists, skipping"
else
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

if [ $? -ne 0 ]; then
    echo -e "\e[93mWARNING: \e[37mSelf monitoring dashboard could not be created."
    echo -e
    echo -e "Please verify if project [$GCP_PROJECT] is assigned to Google Monitoring Workspace, in the console https://console.cloud.google.com/monitoring/dashboards "
    echo -e "Documentation: https://cloud.google.com/monitoring/workspaces/create"
    echo 
fi

EXISTING_DASHBOARDS=$(curl -s -X GET "${DYNATRACE_URL}api/config/v1/dashboards" -H "Accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY"  | jq '.dashboards[].name | select (. |contains("Google"))')
if [[ "${DYNATRACE_ACCESS_KEY}" != "" ]]; then
    echo -e
    echo -e "\e[93mWARNING: \e[37mFound existing Google dashboards in [${DYNATRACE_URL}] tenant:"
    echo $EXISTING_DASHBOARDS
    echo
fi

for FILEPATH in ./config/*.yaml ./config/*.yml
do 
  DASHBOARDS_NUMBER=$(yq r --length "$FILEPATH" dashboards)
  if [ "$DASHBOARDS_NUMBER" != "" ]; then
    MAX_INDEX=-1
    ((MAX_INDEX += DASHBOARDS_NUMBER))
    for INDEX in $(seq 0 "$MAX_INDEX");
    do
      DASHBOARD_PATH=$(yq r -j "$FILEPATH" dashboards[$INDEX].dashboard | tr -d '"')
      DASHBOARD_JSON=$(cat "./$DASHBOARD_PATH")
      DASHBOARD_NAME=$(cat "./$DASHBOARD_PATH" | jq .dashboardMetadata.name)
      DASHBOARD_EXISTS=$(echo $EXISTING_DASHBOARDS | grep "$DASHBOARD_NAME")
      if ! [[ "${DASHBOARD_EXISTS}" != "" ]]; then              
        echo "- Create [$DASHBOARD_NAME] dashboard from file [$DASHBOARD_PATH]"
        curl -X POST "${DYNATRACE_URL}api/config/v1/dashboards" \
            -H "Accept: application/json; charset=utf-8" \
            -H "Content-Type: application/json; charset=utf-8" \
            -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" \
            -d "$DASHBOARD_JSON"
      else
        echo "- Dashboard [$DASHBOARD_NAME] already exists on cluster, skipping"
      fi
      echo ""
    done
  fi
done


echo "- cleaning up"

cd ..
echo "- removing archive [$FUNCTION_ZIP_PACKAGE]"
rm ./$FUNCTION_ZIP_PACKAGE

echo "- removing temporary directory [$FUNCTION_ZIP_PACKAGE]"
rm -r ./$GCP_FUNCTION_NAME
