#!/bin/bash
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

onFailure() {
    echo -e "- deployment failed, please examine error messages and run again"
    exit 2
}
trap onFailure ERR

check_if_parameter_is_empty()
{
  PARAMETER=$1
  PARAMETER_NAME=$2
  if [ -z "$PARAMETER" ]
  then
    echo "Missing required parameter: $PARAMETER_NAME"
    exit
  fi
}

print_help()
{
   printf "
usage: deploy-helm.sh --deployment-type DEPLOYMENT_TYPE --dynatrace-access-key DYNATRACE_ACCESS_KEY [--gcp-project GCP_PROJECT] [--service-account SA_NAME] [--role-name ROLE_NAME] [--dynatrace-url DYNATRACE_URL] [--gcp-services GCP_SERVICES] [--service-usage-booking SERVICE_USAGE_BOOKING] [--use-proxy USE_PROXY] [--http-proxy HTTP_PROXY] [--https-proxy HTTPS_PROXY] [--dynatrace-log-ingest-url DYNATRACE_LOG_INGEST_URL] [--logs-subscription-id LOGS_SUBSCRIPTION_ID] [--require-valid-certificate REQUIRE_VALID_CERTIFICATE] [--enable-self-monitoring SELF_MONITORING_ENABLED]

arguments:
    -h, --help              Show this help message and exit
    --deployment-type DEPLOYMENT_TYPE
                            The solution you want to deploy: 'metrics', 'logs', 'all'
    --gcp-project GCP_PROJECT
                            GCP project ID where Dynatrace GCP Function should be deployed.
                            For 'logs' and 'all' deployment use GCP project of log sink pubsub subscription
                            By default your current project will be used
    --service-account SA_NAME
                            IAM service account name
                            By default 'dynatrace-gcp-function-sa' will be used.
    --role-name ROLE_NAME
                            IAM role name prefix
                            By default 'dynatrace_function' will be used as prefix (e.g. dynatrace_function.metrics).
    --dynatrace-access-key DYNATRACE_ACCESS_KEY
                            Dynatrace API token with permissions:
                            'Ingest logs' for deployment type 'all' or 'logs'
                            'Ingest metrics', 'Read configuration', 'Write configuration' for deployment type 'all' or 'metrics'
                            Required for 'metrics', 'logs' and 'all' deployments
    --dynatrace-url DYNATRACE_URL
                            Dynatrace environment endpoint, for example: https://environment-id.live.dynatrace.com
                            Required for 'metrics', 'logs' and 'all' deployments
    --gcp-services GCP_SERVICES
                            Comma separated list of GCP services, which should be queried for metrics and ingested into Dynatrace
                            Required for 'metrics' and 'all' deployments
    --service-usage-booking SERVICE_USAGE_BOOKING
                            Service usage booking determines a caller-specified project for quota and billing purposes.
                            if set to 'source' (default): monitoring API calls are booked towards project where K8S container is running
                            if set to 'destination': monitoring API calls are booked towards project which is monitored
                            REQUIRES serviceusage.services.use Permission granted for Service Account!
                            Optional for 'metrics' and 'all' deployments.
    --use-proxy USE_PROXY
                            useProxy: depending on value of this flag, function will use proxy settings for either Dynatrace, GCP API or both.
                            if set to ALL: proxy settings will be used for requests to Dynatrace and GCP API
                            if set to DT_ONLY: proxy settings will be used only for requests to Dynatrace
                            if set to GCP_ONLY: proxy settings will be used only for requests to GCP API
                            if not set: default, proxy settings won't be used
                            Optional for 'metrics' and 'all' deployments
    --http-proxy HTTP_PROXY
                            http proxy address; to be used in conjunction with USE_PROXY
                            Optional for 'metrics' and 'all' deployments
    --https-proxy HTTPS_PROXY
                            https proxy address; to be used in conjunction with USE_PROXY
                            Optional for 'metrics' and 'all' deployments
    --dynatrace-log-ingest-url DYNATRACE_LOG_INGEST_URL
                            ActiveGate endpoint used to ingest logs to Dynatrace, for example: https://environemnt-active-gate-url:9999/e/environment-id
                            Required for 'logs' and 'all' deployments
    --logs-subscription-id LOGS_SUBSCRIPTION_ID
                            Subscription id of log sink pubsub subscription
                            Required for 'logs' and 'all' deployments
    --require-valid-certificate REQUIRE_VALID_CERTIFICATE
                            If true/yes function requires valid SSL certificates when communicating with Dynatrace cluster.
                            May be used to bypass SSL certificates errors when traffic is proxied through Active Gate with self-signed certificate.
                            By default certificates are validated.
    --enable-self-monitoring SELF_MONITORING_ENABLED
                            Send custom metrics to GCP to diagnose quickly if your dynatrace-gcp-function processes and sends metrics/logs to Dynatrace properly.
                            By default custom metrics are not sent to GCP.
    "
}

if ! command -v gcloud &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37mGoogle Cloud CLI is required to deploy the Dynatrace GCP Function. Go to following link in your browser and download latest version of Cloud SDK:"
    echo -e
    echo -e "https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version"
    echo -e
    echo
    exit
fi

if ! command -v kubectl &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37mKubernetes CLI is required to deploy the Dynatrace GCP Function. Go to following link in your browser and install kubectl in the most convenient way to you:"
    echo -e
    echo -e "https://kubernetes.io/docs/tasks/tools/"
    echo -e
    echo
    exit
fi

if ! command -v helm &> /dev/null
then

    echo -e "\e[93mWARNING: \e[37mHelm is required to deploy the Dynatrace GCP Function. Go to following link in your browser and install Helm in the most convenient way to you:"
    echo -e
    echo -e "https://helm.sh/docs/intro/install/"
    echo -e
    echo
    exit
fi

while (( "$#" )); do
    case "$1" in
            "-h" | "--help")
                print_help
                exit 0
            ;;

            "--gcp-project")
                GCP_PROJECT=$2
                shift; shift
            ;;

            "--service-account")
                SA_NAME=$2
                shift; shift
            ;;

            "--role-name")
                ROLE_NAME=$2
                shift; shift
            ;;

            "--deployment-type")
                DEPLOYMENT_TYPE=$2
                shift; shift
            ;;

            "--dynatrace-url")
                DYNATRACE_URL=$2
                shift; shift
            ;;

            "--dynatrace-access-key")
                DYNATRACE_ACCESS_KEY=$2
                shift; shift
            ;;

            "--gcp-services")
                GCP_SERVICES=$2
                shift; shift
            ;;

            "--dynatrace-log-ingest-url")
                DYNATRACE_LOG_INGEST_URL=$2
                shift; shift
            ;;

            "--logs-subscription-id")
                LOGS_SUBSCRIPTION_ID=$2
                shift; shift
            ;;

            "--require-valid-certificate")
                REQUIRE_VALID_CERTIFICATE=$2
                shift; shift
            ;;

            "--enable-self-monitoring")
                SELF_MONITORING_ENABLED=$2
                shift; shift
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

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

check_if_parameter_is_empty "$DYNATRACE_ACCESS_KEY" "DYNATRACE_ACCESS_KEY"

if [ -z "$DEPLOYMENT_TYPE" ]; then
  DEPLOYMENT_TYPE="all"
  echo "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
  echo "Deploying $DEPLOYMENT_TYPE ingest"
else
  echo "Invalid DEPLOYMENT_TYPE: $DEPLOYMENT_TYPE. use one of: 'all', 'metrics', 'logs'"
  exit 1
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
  check_if_parameter_is_empty "$DYNATRACE_URL" "DYNATRACE_URL"
  check_if_parameter_is_empty "$GCP_SERVICES" "GCP_SERVICES"
  GCP_SERVICES=$(echo "$GCP_SERVICES" | sed 's/,/\\,/g')
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then
  check_if_parameter_is_empty "$DYNATRACE_LOG_INGEST_URL" "DYNATRACE_LOG_INGEST_URL"
  check_if_parameter_is_empty "$LOGS_SUBSCRIPTION_ID" "LOGS_SUBSCRIPTION_ID"
fi

if [ -z "$SERVICE_USAGE_BOOKING" ]; then
  SERVICE_USAGE_BOOKING="source"
fi

echo
echo "- 1. Create dynatrace namespace in k8s cluster."
if [[ $(kubectl get namespace dynatrace --ignore-not-found) ]]; then
  echo "namespace dynatrace already exists";
else
  kubectl create namespace dynatrace
fi;

echo
echo "- 2. Create IAM service account."
if [[ $(gcloud iam service-accounts list --filter="name ~ serviceAccounts/$SA_NAME@" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Service Account [$SA_NAME] already exists, skipping"
else
    gcloud iam service-accounts create "$SA_NAME"
fi

echo
echo "- 3. Configure the IAM service account for Workload Identity."
gcloud iam service-accounts add-iam-policy-binding --role roles/iam.workloadIdentityUser --member "serviceAccount:$GCP_PROJECT.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]" "$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"

echo
echo "- 4. Create dynatrace-gcp-function IAM role(s)."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml -O dynatrace-gcp-function-logs-role.yaml
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.logs" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.logs"
    gcloud iam roles update $ROLE_NAME.logs --project="$GCP_PROJECT" --file=dynatrace-gcp-function-logs-role.yaml --quiet
  else
    gcloud iam roles create $ROLE_NAME.logs --project="$GCP_PROJECT" --file=dynatrace-gcp-function-logs-role.yaml
  fi
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml -O dynatrace-gcp-function-metrics-role.yaml
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.metrics" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.metrics"
    gcloud iam roles update $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=dynatrace-gcp-function-metrics-role.yaml --quiet
  else
    gcloud iam roles create $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=dynatrace-gcp-function-metrics-role.yaml
  fi
fi

echo
echo "- 5. Grant the required IAM policies to the service account."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.logs"
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.metrics"
fi

echo
echo "- 6. Enable the APIs required for monitoring."
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com

echo
echo "- 7. Install dynatrace-gcp-funtion with helm chart."
wget https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/latest/download/dynatrace-gcp-function.tgz -O dynatrace-gcp-function.tgz
helm install dynatrace-gcp-function.tgz --set gcpProjectId="$GCP_PROJECT",deploymentType="$DEPLOYMENT_TYPE",dynatraceUrl="$DYNATRACE_URL",dynatraceAccessKey="$DYNATRACE_ACCESS_KEY",gcpServices="$GCP_SERVICES",serviceUsageBooking="$SERVICE_USAGE_BOOKING",useProxy="$USE_PROXY",httpProxy="$HTTP_PROXY",httpsProxy="$HTTPS_PROXY",requireValidCertificate="$REQUIRE_VALID_CERTIFICATE",selfMonitoringEnabled="$SELF_MONITORING_ENABLED",dynatraceLogIngestUrl="$DYNATRACE_LOG_INGEST_URL",logsSubscriptionProject="$GCP_PROJECT",logsSubscriptionId="$LOGS_SUBSCRIPTION_ID" --generate-name --namespace dynatrace

echo
echo "- 8. Create an annotation for the service account."
kubectl annotate serviceaccount --namespace dynatrace "dynatrace-gcp-function-sa iam.gke.io/gcp-service-account=$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --overwrite

echo
echo "- Deployment complete, check if containers are running:"
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs"
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics"
fi
