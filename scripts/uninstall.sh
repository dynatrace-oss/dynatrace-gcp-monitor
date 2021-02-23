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
readonly FUNCTION_RAW_REPOSITORY_URL=https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master
readonly FUNCTION_ACTIVATION_CONFIG=activation-config.yaml

echo -e "\033[1;34mDynatrace function for Google Cloud Platform monitoring / uninstall script"
echo -e "\033[0;37m"

if [ ! -f $FUNCTION_ACTIVATION_CONFIG ]; then
    echo -e "INFO: Configuration file [$FUNCTION_ACTIVATION_CONFIG] missing, downloading default"
    wget -q $FUNCTION_RAW_REPOSITORY_URL/$FUNCTION_ACTIVATION_CONFIG -O $FUNCTION_ACTIVATION_CONFIG
    echo
fi


readonly GCP_SERVICE_ACCOUNT=$(yq r activation-config.yaml 'googleCloud.common.serviceAccount')
readonly GCP_PUBSUB_TOPIC=$(yq r activation-config.yaml 'googleCloud.metrics.pubSubTopic')
readonly GCP_FUNCTION_NAME=$(yq r activation-config.yaml 'googleCloud.metrics.function')
readonly GCP_SCHEDULER_NAME=$(yq r activation-config.yaml 'googleCloud.metrics.scheduler')
readonly GCP_SCHEDULER_CRON=$(yq r activation-config.yaml 'googleCloud.metrics.schedulerSchedule')
readonly DYNATRACE_URL_SECRET_NAME=$(yq r activation-config.yaml 'googleCloud.common.dynatraceUrlSecretName')
readonly DYNATRACE_ACCESS_KEY_SECRET_NAME=$(yq r activation-config.yaml 'googleCloud.common.dynatraceAccessKeySecretName')
readonly ACTIVATION_SERVICES=$(yq r activation-config.yaml 'activation.metrics.services | join(",")') 
readonly PRINT_METRIC_INGEST_INPUT=$(yq r activation-config.yaml 'debug.printMetricIngestInput')
readonly DEFAULT_GCP_FUNCTION_SIZE=$(yq r activation-config.yaml 'googleCloud.common.cloudFunctionSize')
readonly SELF_MONITORING_DASHBOARD_NAME="dynatrace-gcp-function Self monitoring"
readonly USE_PROXY=$(yq r $FUNCTION_ACTIVATION_CONFIG 'googleCloud.common.useProxy')


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

echo "Please provide the GCP project, form which monitoring function should be removed. Default value: [$DEFAULT_PROJECT] (current project)"
while ! [[ "${GCP_PROJECT}" =~ ^[a-z]{1}[a-z0-9-]{5,29}$ ]]; do
    read -p "Enter GCP project ID: " -i $DEFAULT_PROJECT -e GCP_PROJECT
done
echo ""

echo "- set current project to [$GCP_PROJECT]"
gcloud config set project $GCP_PROJECT

echo "Discovering instances to remove"    
REMOVE_FUNCTION=$(gcloud functions list --filter=name:dynatrace-gcp-function --format="value(name)")
if [[ $REMOVE_FUNCTION ]]; then
    echo "found function [$REMOVE_FUNCTION]"
fi

REMOVE_TOPIC=$(gcloud pubsub topics list --filter=name:dynatrace-gcp-service-invocation --format="value(name)")
if [[ $REMOVE_TOPIC ]]; then
    echo "found pub/sub topic [$REMOVE_TOPIC]"
fi

REMOVE_SECRET_URL=$(gcloud secrets list --filter=name:$DYNATRACE_URL_SECRET_NAME --format="value(name)" )
if [[ $REMOVE_SECRET_URL ]]; then
    echo "found secret [$REMOVE_SECRET_URL]"
fi

REMOVE_SECRET_TOKEN=$(gcloud secrets list --filter=name:$DYNATRACE_ACCESS_KEY_SECRET_NAME --format="value(name)")
if [[ $REMOVE_SECRET_TOKEN ]]; then
    echo "found secret [$REMOVE_SECRET_TOKEN]"
fi

REMOVE_SERVICE_ACCOUNT=$(gcloud iam service-accounts list --filter=name:$GCP_SERVICE_ACCOUNT --format="value(email)")
if [[ $REMOVE_SERVICE_ACCOUNT ]]; then
    echo "found service account [$REMOVE_SERVICE_ACCOUNT]"
fi

REMOVE_JOB=$(gcloud scheduler jobs list --filter=name:dynatrace-gcp-schedule --format="value(name)")
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
    read -p "Do you want to continue (Y/n)?"  -e CONFIRM_DELETE
done
echo ""

if [[ $CONFIRM_DELETE =~ (y|Y) ]]; then
    if [[ $REMOVE_DASHBOARD ]]; then
        for DASHBOARD in $REMOVE_DASHBOARD
        do
            echo -e "Removing dashboard [$DASHBOARD]"
            gcloud monitoring dashboards delete "$DASHBOARD" --quiet
        done
    fi
    if [[ $REMOVE_JOB ]]; then
        for JOB in $REMOVE_JOB
        do
            echo -e "Removing job [$JOB]"
            gcloud scheduler jobs delete "$JOB" --quiet
        done
    fi
    if [[ $REMOVE_FUNCTION ]]; then
        for FUNCTION in $REMOVE_FUNCTION
        do
            echo -e "Removing function [$FUNCTION]"
            gcloud functions delete "$FUNCTION" --quiet
        done
    fi
    if [[ $REMOVE_TOPIC ]]; then
        for TOPIC in $REMOVE_TOPIC
        do
            echo -e "Removing pub/sub topic [$TOPIC]"
            gcloud pubsub topics delete "$TOPIC" --quiet
        done
    fi
    if [[ $REMOVE_SECRET_URL ]]; then
        for SECRET_URL in $REMOVE_SECRET_URL
        do
            echo -e "Removing secret [$SECRET_URL]"
            gcloud secrets delete "$SECRET_URL" --quiet
        done
    fi
    if [[ $REMOVE_SECRET_TOKEN ]]; then
        for SECRET_TOKEN in $REMOVE_SECRET_TOKEN
        do
            echo -e "Removing secret [$SECRET_TOKEN]"
            gcloud secrets delete "$SECRET_TOKEN" --quiet
        done
    fi
    if [[ $REMOVE_SERVICE_ACCOUNT ]]; then
        for SERVICE_ACCOUNT in $REMOVE_SERVICE_ACCOUNT
        do
            echo -e "Removing service account [$SERVICE_ACCOUNT] IAM role bindings"
            ROLES=$(gcloud projects get-iam-policy $DEFAULT_PROJECT --flatten="bindings[].members" --format='value(bindings.role)' --filter="bindings.members:$SERVICE_ACCOUNT")
            for ROLE in $ROLES
            do
                echo -e "Removing IAM role [$ROLE] for service account [$SERVICE_ACCOUNT]"
                gcloud projects remove-iam-policy-binding $DEFAULT_PROJECT --role=$ROLE --member="serviceAccount:$SERVICE_ACCOUNT" --quiet
            done 
            echo -e "Removing service account [$SERVICE_ACCOUNT]"
            gcloud iam service-accounts delete "$SERVICE_ACCOUNT" --quiet
        done
    fi
    echo -e "\e[92mOK: \e[37mOperation completed."
else
    echo -e "\e[93mWARNING: \e[37mOperation canceled."
fi