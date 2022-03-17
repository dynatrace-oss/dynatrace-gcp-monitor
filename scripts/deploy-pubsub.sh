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

readonly GCP_RESOURCE_NAME_REGEX="^[a-zA-Z][-a-zA-Z0-9._~%+]{3,255}$"

print_help()
{
   printf "
usage: deploy-pubsub.sh --topic-name TOPIC_NAME --subscription-name SUBSCRIPTION_NAME

arguments:
    -h, --help              Show this help message and exit
    --topic-name TOPIC_NAME
                            Topic name e.g. dynatrace-gcp-log-forwarder
    --subscription-name SUBSCRIPTION_NAME
                            Subscription ID of log sink Pub/Sub subscription e.g. dynatrace-gcp-log-forwarder-sub
    "
}

check_arg()
{
    CLI_ARGUMENT_NAME=$1
    ARGUMENT=$2
    if [ -z "$ARGUMENT" ]
    then
        echo "No $CLI_ARGUMENT_NAME"
        exit 1
    else
        if [[ $ARGUMENT == goog* ]] || ! [[ "$ARGUMENT" =~ $GCP_RESOURCE_NAME_REGEX ]]
        then
            echo "Not correct $CLI_ARGUMENT_NAME. Must be 3–255 characters, start with a letter and contain only the following characters: letters, numbers, dashes (-), full stops (.), underscores (_), tildes (~), percents (%) or plus signs (+). Cannot start with goog."
            exit 1
        fi
    fi
}

while (( "$#" )); do
    case "$1" in
            "-h" | "--help")
                print_help
                exit 0
            ;;

            "--topic-name")
                TOPIC_NAME=$2
                shift; shift
            ;;

            "--subscription-name")
                SUBSCRIPTION_NAME=$2
                shift; shift
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

check_arg --topic-name "$TOPIC_NAME"
check_arg --subscription-name "$SUBSCRIPTION_NAME"


if ! gcloud pubsub topics create "${TOPIC_NAME}"; then
    exit 2
fi

gcloud pubsub subscriptions create "${SUBSCRIPTION_NAME}" --topic="${TOPIC_NAME}" --ack-deadline=120 --message-retention-duration=1d