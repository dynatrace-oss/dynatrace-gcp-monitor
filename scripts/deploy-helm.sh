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
    --service-account SA_NAME
                            IAM service account name
                            By default 'dynatrace-gcp-function-sa' will be used.
    --role-name ROLE_NAME
                            IAM role name prefix
                            By default 'dynatrace_function' will be used as prefix (e.g. dynatrace_function.metrics).
    --create-autopilot-cluster
                            Create new GKE Autopilot cluster and deploy dynatrace-gcp-function into it.
    --autopilot-cluster-name CLUSTER_NAME
                            Name of new GKE Autopilot cluster to be created if '--create-autopilot-cluster option' was selected.
                            By default 'dynatrace-gcp-function' will be used.
    -q, --quiet
                            Reduce output verbosity, progress messages and errors are still printed.
    -h, --help
                            Show this help message and exit
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

CMD_OUT_PIPE="/dev/stdout"
AUTOPILOT_CLUSTER_NAME="dynatrace-gcp-function"

while (( "$#" )); do
    case "$1" in
            "--service-account")
                SA_NAME=$2
                shift; shift
            ;;

            "--role-name")
                ROLE_NAME=$2
                shift; shift
            ;;

            "--create-autopilot-cluster")
                CREATE_AUTOPILOT_CLUSTER="Y"
                shift
            ;;

            "--autopilot-cluster-name")
                AUTOPILOT_CLUSTER_NAME=$2
                shift; shift
            ;;

            "-q" | "--quiet")
                CMD_OUT_PIPE="/dev/null"
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

GCP_PROJECT=$(helm show values ./dynatrace-gcp-function --jsonpath "{.gcpProjectId}")
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

  readonly LOGS_SUBSCRIPTION_FULL_ID="projects/$GCP_PROJECT/subscriptions/$LOGS_SUBSCRIPTION_ID"

  if ! [[ $(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(name)") ]];
  then
    echo "Pub/Sub subscription '$LOGS_SUBSCRIPTION_FULL_ID' does not exist"
    exit 1
  fi

  INVALID_PUBSUB=false

  readonly ACK_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(ackDeadlineSeconds)")
  if [[ "$ACK_DEADLINE" != "120" ]];
  then
    echo "Invalid Pub/Sub subscription Acknowledgement Deadline - should be '120's (2 minutes), was '$ACK_DEADLINE's"
    INVALID_PUBSUB=true
  fi

  readonly MESSAGE_RETENTION_DEADLINE=$(gcloud pubsub subscriptions describe "$LOGS_SUBSCRIPTION_FULL_ID" --format="value(messageRetentionDuration)")
  if [[ "$MESSAGE_RETENTION_DEADLINE" != "86400s" ]];
  then
    echo "Invalid Pub/Sub subscription Acknowledge Deadline - should be '86400s' (24 hours), was '$MESSAGE_RETENTION_DEADLINE'"
    INVALID_PUBSUB=true
  fi

  if "$INVALID_PUBSUB";
  then
    exit 1
  fi

  ACTIVE_GATE_CONNECTIVITY=Y
  ACTIVE_GATE_STATE=$(curl -ksS "${DYNATRACE_LOG_INGEST_URL}/rest/health") || ACTIVE_GATE_CONNECTIVITY=N
  if [[ "$ACTIVE_GATE_CONNECTIVITY" != "Y" ]]
  then
        echo -e "\e[93mWARNING: \e[37mUnable to connect to ActiveGate endpoint $DYNATRACE_LOG_INGEST_URL. It can be ignored if ActiveGate host network configuration doeas not allow acces from outside of k8s cluster."
  fi
  if [[ "$ACTIVE_GATE_STATE" != "RUNNING" && "$ACTIVE_GATE_CONNECTIVITY" == "Y" ]]
  then
    echo "ActiveGate endpoint $DYNATRACE_LOG_INGEST_URL is not reporting RUNNING state. Please validate 'dynatraceLogIngestUrl' parameter value and ActiveGate host health."
    exit 1
  fi
fi

if [[ $CREATE_AUTOPILOT_CLUSTER == "Y" ]]; then
  SELECTED_REGION=$(gcloud config get-value compute/region 2>/dev/null)
  if [ -z "$SELECTED_REGION" ]; then
    echo
    echo - e "\e[93mWARNING: \e[37mDefault region not set. Set default region by running 'gcloud config set compute/region <REGION>'."
    exit 1
  fi
  echo
  echo "- Create and connect GKE Autopilot k8s cluster ${AUTOPILOT_CLUSTER_NAME}."
  gcloud container clusters create-auto "${AUTOPILOT_CLUSTER_NAME}" --project "${GCP_PROJECT}" > ${CMD_OUT_PIPE}
  gcloud container clusters get-credentials "${AUTOPILOT_CLUSTER_NAME}" --project ${GCP_PROJECT} > ${CMD_OUT_PIPE}
fi;


echo
echo "- 1. Create dynatrace namespace in k8s cluster."
if [[ $(kubectl get namespace dynatrace --ignore-not-found) ]]; then
  echo "namespace dynatrace already exists";
else
  kubectl create namespace dynatrace > ${CMD_OUT_PIPE}
fi;

echo
echo "- 2. Create IAM service account."
if [[ $(gcloud iam service-accounts list --filter="name ~ serviceAccounts/$SA_NAME@" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Service Account [$SA_NAME] already exists, skipping"
else
    gcloud iam service-accounts create "$SA_NAME" > ${CMD_OUT_PIPE}
fi

echo
echo "- 3. Configure the IAM service account for Workload Identity."
gcloud iam service-accounts add-iam-policy-binding "$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role roles/iam.workloadIdentityUser --member "serviceAccount:$GCP_PROJECT.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]"  > ${CMD_OUT_PIPE}

echo
echo "- 4. Create dynatrace-gcp-function IAM role(s)."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml -O dynatrace-gcp-function-logs-role.yaml  > ${CMD_OUT_PIPE}
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.logs" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.logs"
    gcloud iam roles update $ROLE_NAME.logs --project="$GCP_PROJECT" --file=dynatrace-gcp-function-logs-role.yaml > ${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.logs --project="$GCP_PROJECT" --file=dynatrace-gcp-function-logs-role.yaml > ${CMD_OUT_PIPE}
  fi
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml -O dynatrace-gcp-function-metrics-role.yaml  > ${CMD_OUT_PIPE}
  if [[ $(gcloud iam roles list --filter="name:$ROLE_NAME.metrics" --project="$GCP_PROJECT" --format="value(name)") ]]; then
    echo "Updating existing IAM role $ROLE_NAME.metrics"
    gcloud iam roles update $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=dynatrace-gcp-function-metrics-role.yaml  > ${CMD_OUT_PIPE}
  else
    gcloud iam roles create $ROLE_NAME.metrics --project="$GCP_PROJECT" --file=dynatrace-gcp-function-metrics-role.yaml > ${CMD_OUT_PIPE}
  fi
fi

echo
echo "- 5. Grant the required IAM policies to the service account."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.logs"  > ${CMD_OUT_PIPE}
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role="projects/$GCP_PROJECT/roles/$ROLE_NAME.metrics"  > ${CMD_OUT_PIPE}
fi

echo
echo "- 6. Enable the APIs required for monitoring."
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com  > ${CMD_OUT_PIPE}

echo
echo "- 7. Install dynatrace-gcp-function with helm chart."
helm install ./dynatrace-gcp-function --generate-name --namespace dynatrace  > ${CMD_OUT_PIPE}

echo
echo "- Deployment complete, check if containers are running:"  > ${CMD_OUT_PIPE}
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs"  > ${CMD_OUT_PIPE}
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics"  > ${CMD_OUT_PIPE}
fi
