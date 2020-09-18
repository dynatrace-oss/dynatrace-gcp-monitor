#!/bin/bash 
readonly GCP_SERVICE_ACCOUNT=dynatrace-gcp-service
readonly GCP_PUBSUB_TOPIC=dynatrace-gcp-service-invocation
readonly GCP_FUNCTION_NAME=dynatrace-gcp-function
readonly GCP_SCHEDULER_NAME=dynatrace-gcp-schedule
readonly GCP_SCHEDULER_CRON="* * * * *"
readonly FUNCTION_REPOSITORY=GITHUB_BUILD_ZIP
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


echo "Please provide the URL used to access Dynatrace, for example: https://mytenant.live.dynatrace.com/"
while ! [[ "${DYNATRACE_URL}" =~ ^https:\/\/[a-z0-9-]{8}\.(live|sprint|dev)\.(dynatrace|dynatracelabs)\.com\/$ ]]; do
    read -p "Enter Dynatrace tenant URI: " DYNATRACE_URL
done
echo ""

echo "Please log in to Dynatrace, and generate API token (Settings->Integration->Dynatrace API). The token requires grant of 'Ingest data points' scope"
 while ! [[ "${DYNATRACE_ACCESS_KEY}" != "" ]]; do
    read -p "Enter Dynatrace API token: " DYNATRACE_ACCESS_KEY  
done
echo ""

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

echo "- enable googleapis [secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudmonitoring.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com]"
gcloud services enable secretmanager.googleapis.com cloudfunctions.googleapis.com cloudapis.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com pubsub.googleapis.com

echo "- create the pubsub topic [$GCP_PUBSUB_TOPIC]"
gcloud pubsub topics create "$GCP_PUBSUB_TOPIC"

echo "- create secrets [DYNATRACE_URL, DYNATRACE_ACCESS_KEY]"
stty -echo
echo "$DYNATRACE_URL" | gcloud secrets create DYNATRACE_URL --data-file=- --replication-policy=automatic
echo "$DYNATRACE_ACCESS_KEY" | gcloud secrets create DYNATRACE_ACCESS_KEY --data-file=- --replication-policy=automatic
stty echo

echo "- create service account [$GCP_SERVICE_ACCOUNT with permissions [roles/monitoring.editor, roles/monitoring.viewer, roles/secretmanager.secretAccessor, roles/secretmanager.viewer, roles/cloudfunctions.viewer, roles/cloudsql.viewer, roles/compute.viewer, roles/file.viewer, roles/pubsub.viewer"
gcloud iam service-accounts create "$GCP_SERVICE_ACCOUNT"
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/monitoring.editor
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/monitoring.viewer
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/compute.viewer
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/cloudsql.viewer
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/cloudfunctions.viewer
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/file.viewer
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/pubsub.viewer

gcloud secrets add-iam-policy-binding DYNATRACE_URL --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding DYNATRACE_URL --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer

gcloud secrets add-iam-policy-binding DYNATRACE_ACCESS_KEY --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding DYNATRACE_ACCESS_KEY --member="serviceAccount:$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.viewer

echo "- deploy the function [$GCP_FUNCTION_NAME]"
gcloud functions -q deploy "$GCP_FUNCTION_NAME" --entry-point=dynatrace_gcp_extension --runtime=python37 --trigger-topic="$GCP_PUBSUB_TOPIC" --source=$FUNCTION_REPOSITORY --service-account="$GCP_SERVICE_ACCOUNT@$GCP_PROJECT.iam.gserviceaccount.com" --ingress-settings=internal-only

echo "- schedule the runs"
gcloud scheduler jobs create pubsub "$GCP_SCHEDULER_NAME" --topic="$GCP_PUBSUB_TOPIC" --schedule="$GCP_SCHEDULER_CRON" --message-body="x"

#. ./setup_alerting.sh