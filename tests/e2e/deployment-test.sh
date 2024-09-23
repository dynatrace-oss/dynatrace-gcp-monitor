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

source ./tests/e2e/lib-tests.sh

while (( "$#" )); do
    case "$1" in
            "--logs")
                DEPLOYMENT_TYPE="logs"
                shift
            ;;

            "--metrics")
                DEPLOYMENT_TYPE="metrics"
                shift
            ;;

            "--all")
                DEPLOYMENT_TYPE="all"
                shift
            ;;

            *)
            echo "Unknown param $1"
            print_help
            exit 1
    esac
done

# Create Pub/Sub topic and subscription.
gcloud config set project "${GCP_PROJECT_ID}"


create_sample_app

generate_load_on_sample_app
