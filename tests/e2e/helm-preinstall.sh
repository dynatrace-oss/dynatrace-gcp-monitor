#!/usr/bin/env bash
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

# Install kubectl.
curl -sSLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && sudo mv kubectl /usr/local/bin/kubectl

# Install helm.
wget --no-verbose https://get.helm.sh/helm-v3.5.3-linux-amd64.tar.gz
FILE=./helm-v3.5.3-linux-amd64.tar.gz
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 1
fi
tar -zxvf helm-v3.5.3-linux-amd64.tar.gz
FILE=./linux-amd64/helm
if [ ! -f "$FILE" ]; then
    echo "$FILE does not exist. Can't create helm chart."
    exit 1
fi

sudo mv linux-amd64/helm /usr/local/bin/helm