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

readonly GCP_SERVICE_ACCOUNT=dynatrace-gcp-service
readonly GCP_PUBSUB_TOPIC=dynatrace-gcp-service-invocation
readonly GCP_FUNCTION_NAME=dynatrace-gcp-function
readonly GCP_SCHEDULER_NAME=dynatrace-gcp-schedule
readonly GCP_SCHEDULER_CRON="* * * * *"
readonly FUNCTION_REPOSITORY=GITHUB_RELEASES
echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring"
echo -e "\033[0;37m"


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

echo "- deploy the function [$GCP_FUNCTION_NAME]"
gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --trigger-topic="$GCP_PUBSUB_TOPIC" --source=$FUNCTION_REPOSITORY --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only
