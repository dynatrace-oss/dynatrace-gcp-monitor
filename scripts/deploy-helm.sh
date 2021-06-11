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
usage: deploy-helm.sh [--service-account SA_NAME] [--role-name ROLE_NAME]

arguments:
    -h, --help              Show this help message and exit
    --service-account SA_NAME
                            IAM service account name
                            By default 'dynatrace-gcp-function-sa' will be used.
    --role-name ROLE_NAME
                            IAM role name prefix
                            By default 'dynatrace_function' will be used as prefix (e.g. dynatrace_function.metrics).
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

            "--service-account")
                SA_NAME=$2
                shift; shift
            ;;

            "--role-name")
                ROLE_NAME=$2
                shift; shift
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

readonly GCP_PROJECT=$(helm show values ./dynatrace-gcp-function --jsonpath "{.gcpProjectId}")
readonly DEPLOYMENT_TYPE=$(helm show values ./dynatrace-gcp-function --jsonpath "{.deploymentType}")
readonly DYNATRACE_ACCESS_KEY=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceAccessKey}")
readonly DYNATRACE_URL=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceUrl}")
readonly DYNATRACE_LOG_INGEST_URL=$(helm show values ./dynatrace-gcp-function --jsonpath "{.dynatraceLogIngestUrl}")
readonly LOGS_SUBSCRIPTION_ID=$(helm show values ./dynatrace-gcp-function --jsonpath "{.logsSubscriptionId}")

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
fi

if [[ $DEPLOYMENT_TYPE == all ]] || [[ $DEPLOYMENT_TYPE == logs ]]; then
  check_if_parameter_is_empty "$DYNATRACE_LOG_INGEST_URL" "DYNATRACE_LOG_INGEST_URL"
  check_if_parameter_is_empty "$LOGS_SUBSCRIPTION_ID" "LOGS_SUBSCRIPTION_ID"
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
echo "- 7. Install dynatrace-gcp-function with helm chart."
helm install ./dynatrace-gcp-function --generate-name --namespace dynatrace

echo
echo "- Deployment complete, check if containers are running:"
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs"
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics"
fi
