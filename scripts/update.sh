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


readonly FUNCTION_REPOSITORY_RELEASE_URL=https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/download/release-0.0.2
readonly FUNCTION_RAW_REPOSITORY_URL=https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring / update script"
echo -e "\033[0;37m"

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
    echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, downloading default"
    wget -q $FUNCTION_RAW_REPOSITORY_URL/$FUNCTION_ACTIVATION_CONFIG -O $FUNCTION_ACTIVATION_CONFIG
    echo
fi

readonly GCP_SERVICE_ACCOUNT=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.serviceAccount')
readonly GCP_PUBSUB_TOPIC=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.pubSubTopic')
readonly GCP_FUNCTION_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.function')
readonly GCP_SCHEDULER_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.scheduler')
readonly GCP_SCHEDULER_CRON=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.metrics.schedulerSchedule')
readonly DYNATRACE_URL_SECRET_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.dynatraceUrlSecretName')
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.dynatraceAccessKeySecretName')
readonly FUNCTION_GCP_SERVICES=$(yq r $FUNCTION_ACTIVATION_CONFIG 'activation.metrics.services | join(",")') 
readonly DASHBOARDS_TO_ACTIVATE=$(yq r -j -P $FUNCTION_ACTIVATION_CONFIG 'activation.metrics.services' | jq -r .[]) 
readonly PRINT_METRIC_INGEST_INPUT=$(yq r $FUNCTION_ACTIVATION_CONFIG 'debug.printMetricIngestInput')
readonly DEFAULT_GCP_FUNCTION_SIZE=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.cloudFunctionSize')


if ! command -v gcloud &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37mGoogle Cloud CLI is required to install Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:"
    echo -e
    echo -e "https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version"
    echo -e
    echo 
    exit
fi


GCP_ACCOUNT=$(gcloud config get-value account)
echo -e "You are now logged in as [$GCP_ACCOUNT]"
echo
DEFAULT_PROJECT=$(gcloud config get-value project)

echo "Please provide the GCP project name where Dynatrace function should be deployed to. Default value: [$DEFAULT_PROJECT] (current project)"
while ! [[ "${GCP_PROJECT}" =~ ^[a-z]{1}[a-z0-9-]{5,29}$ ]]; do
    read -p "Enter GCP project name: " -i $DEFAULT_PROJECT -e GCP_PROJECT
done
echo ""

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

echo -e
echo "- downloading functions source [$FUNCTION_REPOSITORY_RELEASE_URL/$FUNCTION_ZIP_PACKAGE]"
wget -q $FUNCTION_REPOSITORY_RELEASE_URL/$FUNCTION_ZIP_PACKAGE  -O $FUNCTION_ZIP_PACKAGE 


echo "- extracting archive [$FUNCTION_ZIP_PACKAGE]"
mkdir -p $GCP_FUNCTION_NAME
unzip -o -q ./$FUNCTION_ZIP_PACKAGE -d ./$GCP_FUNCTION_NAME
cd ./$GCP_FUNCTION_NAME

echo "- deploy the function [$GCP_FUNCTION_NAME]"
gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --trigger-topic="$GCP_PUBSUB_TOPIC" --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only

echo "- cleaning up"
cd ..

echo "- removing archive [$FUNCTION_ZIP_PACKAGE]"
rm ./$FUNCTION_ZIP_PACKAGE

echo "- removing temporary directory [$FUNCTION_ZIP_PACKAGE]"
rm -r ./$GCP_FUNCTION_NAME