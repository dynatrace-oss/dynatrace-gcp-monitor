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


if [ -z "$GCP_PROJECT" ]; then
  GCP_PROJECT=$(gcloud config get-value project 2>/dev/null)
fi

echo "- Deploying dynatrace-gcp-function in [$GCP_PROJECT]"

if [ -z "$SA_NAME" ]; then
  SA_NAME="dynatrace-gcp-function-sa"
fi

if [ -z "$DEPLOYMENT_TYPE" ]; then
  DEPLOYMENT_TYPE="all"
  echo "Deploying metrics and logs ingest"
elif [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == metrics ]]; then
  echo "Deploying $DEPLOYMENT_TYPE ingest"
  else
  echo "Invalid DEPLOYMENT_TYPE specified: $DEPLOYMENT_TYPE. use one of: 'all', 'metrics', 'logs'"
  exit 1
fi

# TODO validate required params present
# TODO validate connected to kube cluster

echo "- 1. Create dynatrace namespace in k8s cluster."
DT_NS=$(kubectl get namespace dynatrace --ignore-not-found)
if [ -z "$DT_NS" ]; then
  kubectl create namespace dynatrace
else
  echo "namespace dyntrace already exists";
fi;

echo "- 2. Create IAM service account."
gcloud iam service-accounts create "$SA_NAME"

echo "- 3. Configure the IAM service account for Workload Identity."
gcloud iam service-accounts add-iam-policy-binding --role roles/iam.workloadIdentityUser --member "serviceAccount:$GCP_PROJECT.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]" "$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"

echo "- 4. Create dynatrace-gcp-function IAM role(s)."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml
  gcloud iam roles create $SA_NAME.logs --project=$GCP_PROJECT --file=dynatrace-gcp-function-logs-role.yaml
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml
  gcloud iam roles create $SA_NAME.metrics --project=$GCP_PROJECT --file=dynatrace-gcp-function-metrics-role.yaml
fi

echo "- 5. Grant the required IAM policies to the service account."
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role=projects/$GCP_PROJECT/roles/$SA_NAME.logs
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --role=projects/$GCP_PROJECT/roles/$SA_NAME.metrics
fi

echo "- 6. Enable the APIs required for monitoring."
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com

echo "- 7. Install dynatrace-gcp-funtion with helm chart."
wget https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/latest/download/dynatrace-gcp-function.tgz
helm install dynatrace-gcp-function.tgz --set --generate-name

echo "- 8. Create an annotation for the service account."
kubectl annotate serviceaccount --namespace dynatrace dynatrace-gcp-function-sa iam.gke.io/gcp-service-account=$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com

echo "- deployment complete, check the installation status bu running:"
if [[ $DEPLOYMENT_TYPE == logs ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs"
fi

if [[ $DEPLOYMENT_TYPE == metrics ]] || [[ $DEPLOYMENT_TYPE == all ]]; then
  echo "kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics"
fi
