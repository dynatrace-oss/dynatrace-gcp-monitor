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
set -e

mkdir -p artefacts
mkdir -p ./helm-deployment-package/gcp_iam_roles

cp -r ./k8s/helm-chart/dynatrace-gcp-function ./helm-deployment-package

cp ./scripts/lib.sh ./helm-deployment-package
cp ./scripts/deploy-helm.sh ./helm-deployment-package

cp ./gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml ./helm-deployment-package/gcp_iam_roles/
cp ./gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml ./helm-deployment-package/gcp_iam_roles/

tar -cf ./artefacts/helm-deployment-package.tar ./helm-deployment-package
