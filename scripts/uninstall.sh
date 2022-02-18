#!/usr/bin/env bash
#     Copyright 2022 Dynatrace LLC
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

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./scripts/lib.sh
source "$WORKING_DIR/lib.sh"
init_ext_tools

FUNCTION_REPOSITORY_RELEASE_URL=$(curl -s "https://api.github.com/repos/dynatrace-oss/dynatrace-gcp-function/releases" -H "Accept: application/vnd.github.v3+json" | "$JQ" 'map(select(.assets[].name == "dynatrace-gcp-function.zip" and .prerelease != true)) | sort_by(.created_at) | last | .assets[] | select( .name =="dynatrace-gcp-function.zip") | .browser_download_url' -r)
readonly FUNCTION_REPOSITORY_RELEASE_URL
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml
readonly FUNCTION_ZIP_PACKAGE=dynatrace-gcp-function.zip
WORKING_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TMP_FUNCTION_DIR=$(mktemp -d)

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring / uninstall script"
echo -e "\033[0;37m"

if ! command -v gcloud &>/dev/null; then
  echo -e "\e[93mWARNING: \e[37mGoogle Cloud CLI is required to uninstall Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:"
  echo -e
  echo -e "https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version"
  echo -e
  echo
  exit
fi

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
    echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, extracting default from release"
    wget -q "$FUNCTION_REPOSITORY_RELEASE_URL" -O "$WORKING_DIR"/$FUNCTION_ZIP_PACKAGE
    unzip -o -q "$WORKING_DIR"/$FUNCTION_ZIP_PACKAGE -d "$TMP_FUNCTION_DIR" || exit
    mv "$TMP_FUNCTION_DIR"/$FUNCTION_ACTIVATION_CONFIG $FUNCTION_ACTIVATION_CONFIG
    echo
fi

GCP_SERVICE_ACCOUNT=$("$YQ" e '.googleCloud.common.serviceAccount' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SERVICE_ACCOUNT
GCP_PUBSUB_TOPIC=$("$YQ" e  '.googleCloud.metrics.pubSubTopic' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_PUBSUB_TOPIC
GCP_FUNCTION_NAME=$("$YQ" e '.googleCloud.metrics.function' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_FUNCTION_NAME
GCP_SCHEDULER_NAME=$("$YQ" e '.googleCloud.metrics.scheduler' $FUNCTION_ACTIVATION_CONFIG)
readonly GCP_SCHEDULER_NAME
DYNATRACE_URL_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceUrlSecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_URL_SECRET_NAME
DYNATRACE_ACCESS_KEY_SECRET_NAME=$("$YQ" e '.googleCloud.common.dynatraceAccessKeySecretName' $FUNCTION_ACTIVATION_CONFIG)
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME
readonly SELF_MONITORING_DASHBOARD_NAME="dynatrace-gcp-function Self monitoring"

GCP_ACCOUNT=$(gcloud config get-value account)
echo -e "You are now logged in as [$GCP_ACCOUNT]"
echo
DEFAULT_PROJECT=$(gcloud config get-value project)

echo "Please provide the GCP project from which monitoring function should be removed. Default value: [$DEFAULT_PROJECT] (current project)"
while ! [[ "${GCP_PROJECT}" =~ ^[a-z]{1}[a-z0-9-]{5,29}$ ]]; do
    read -p -r "Enter GCP project ID: " -i "$DEFAULT_PROJECT" -e GCP_PROJECT
done
echo ""

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project "$GCP_PROJECT"

echo "Discovering instances to remove"
REMOVE_FUNCTION=$(gcloud functions list --filter=name:"$GCP_FUNCTION_NAME" --format="value(name)")
if [[ $REMOVE_FUNCTION ]]; then
    echo "found function [$REMOVE_FUNCTION]"
fi

REMOVE_TOPIC=$(gcloud pubsub topics list --filter=name:"$GCP_PUBSUB_TOPIC" --format="value(name)")
if [[ $REMOVE_TOPIC ]]; then
    echo "found pub/sub topic [$REMOVE_TOPIC]"
fi

REMOVE_SECRET_URL=$(gcloud secrets list --filter=name:"$DYNATRACE_URL_SECRET_NAME" --format="value(name)")
if [[ $REMOVE_SECRET_URL ]]; then
    echo "found secret [$REMOVE_SECRET_URL]"
fi

REMOVE_SECRET_TOKEN=$(gcloud secrets list --filter=name:"$DYNATRACE_ACCESS_KEY_SECRET_NAME" --format="value(name)")
if [[ $REMOVE_SECRET_TOKEN ]]; then
    echo "found secret [$REMOVE_SECRET_TOKEN]"
fi

REMOVE_SERVICE_ACCOUNT=$(gcloud iam service-accounts list --filter=name:"$GCP_SERVICE_ACCOUNT" --format="value(email)")
if [[ $REMOVE_SERVICE_ACCOUNT ]]; then
    echo "found service account [$REMOVE_SERVICE_ACCOUNT]"
fi

REMOVE_JOB=$(gcloud scheduler jobs list --filter=name:"$GCP_SCHEDULER_NAME" --format="value(name)")
if [[ $REMOVE_JOB ]]; then
    echo "found scheduler [$REMOVE_JOB]"
fi

REMOVE_DASHBOARD=$(gcloud monitoring dashboards list --filter=displayName:"$SELF_MONITORING_DASHBOARD_NAME" --format="value(name)")
if [[ $REMOVE_DASHBOARD ]]; then
    echo "found dashboard [$REMOVE_DASHBOARD]"
fi

if ! [[ $REMOVE_DASHBOARD ]] & ! [[ $REMOVE_JOB ]] & ! [[ $REMOVE_FUNCTION ]] & ! [[ $REMOVE_SECRET_URL ]] & ! [[ $REMOVE_SECRET_TOKEN ]] & ! [[ $REMOVE_SERVICE_ACCOUNT ]]; then
    echo -e "\e[93mWARNING: \e[37mNo resources found. Operation canceled."
    exit
fi

echo -e
echo -e "\e[93mWARNING: \e[37mAll of the resources listed above will be deleted."
echo -e ""
while ! [[ "${CONFIRM_DELETE}" =~ ^(y|n|Y|N)$ ]]; do
    read -p -r "Do you want to continue (Y/n)?"  -e CONFIRM_DELETE
done
echo ""

if [[ $CONFIRM_DELETE =~ (y|Y) ]]; then
  if [[ $REMOVE_DASHBOARD ]]; then
    for DASHBOARD in $REMOVE_DASHBOARD; do
      echo -e "Removing dashboard [$DASHBOARD]"
      gcloud monitoring dashboards delete "$DASHBOARD" --quiet
    done
  fi
  if [[ $REMOVE_JOB ]]; then
    for JOB in $REMOVE_JOB; do
      echo -e "Removing job [$JOB]"
      gcloud scheduler jobs delete "$JOB" --quiet
    done
  fi
  if [[ $REMOVE_FUNCTION ]]; then
    for FUNCTION in $REMOVE_FUNCTION; do
      echo -e "Removing function [$FUNCTION]"
      gcloud functions delete "$FUNCTION" --quiet
    done
  fi
  if [[ $REMOVE_TOPIC ]]; then
    for TOPIC in $REMOVE_TOPIC; do
      echo -e "Removing pub/sub topic [$TOPIC]"
      gcloud pubsub topics delete "$TOPIC" --quiet
    done
  fi
  if [[ $REMOVE_SECRET_URL ]]; then
    for SECRET_URL in $REMOVE_SECRET_URL; do
      echo -e "Removing secret [$SECRET_URL]"
      gcloud secrets delete "$SECRET_URL" --quiet
    done
  fi
  if [[ $REMOVE_SECRET_TOKEN ]]; then
    for SECRET_TOKEN in $REMOVE_SECRET_TOKEN; do
      echo -e "Removing secret [$SECRET_TOKEN]"
      gcloud secrets delete "$SECRET_TOKEN" --quiet
    done
  fi
  if [[ $REMOVE_SERVICE_ACCOUNT ]]; then
    for SERVICE_ACCOUNT in $REMOVE_SERVICE_ACCOUNT; do
      echo -e "Removing service account [$SERVICE_ACCOUNT] IAM role bindings"
      ROLES=$(gcloud projects get-iam-policy "$DEFAULT_PROJECT" --flatten="bindings[].members" --format='value(bindings.role)' --filter="bindings.members:$SERVICE_ACCOUNT")
      for ROLE in $ROLES; do
        echo -e "Removing IAM role [$ROLE] for service account [$SERVICE_ACCOUNT]"
        gcloud projects remove-iam-policy-binding "$DEFAULT_PROJECT" --role="$ROLE" --member="serviceAccount:$SERVICE_ACCOUNT" --quiet >/dev/null
      done
      echo -e "Removing service account [$SERVICE_ACCOUNT]"
      gcloud iam service-accounts delete "$SERVICE_ACCOUNT" --quiet
    done
  fi
  echo -e "\e[92mOK: \e[37mOperation completed."
else
  echo -e "\e[93mWARNING: \e[37mOperation canceled."
fi
