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

wget https://get.helm.sh/helm-v3.5.3-linux-amd64.tar.gz

FILE=./helm-v3.5.3-linux-amd64.tar.gz
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 0
fi

tar -zxvf helm-v3.5.3-linux-amd64.tar.gz

FILE=./linux-amd64/helm
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 0
fi

sudo mv linux-amd64/helm /usr/local/bin/helm
helm package ./k8s/helm-chart/dynatrace-gcp-function

FILE=./dynatrace-gcp-function-0.1.0.tgz
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 0
fi
#helm package ./k8s/helm-chart/dynatrace-gcp-function -d ./artefacts