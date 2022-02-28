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

source ./tests/e2e/lib-tests.sh

cd ./e2e_test || exit 1

echo -e "Y" | ./uninstall.sh
gcloud functions delete "$CLOUD_FUNCTION_NAME"

# testing message
INSTALLED_EXTENSIONS=$(curl -s -k -X GET "${DYNATRACE_URL}api/v2/extensions" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '.extensions[].extensionName')

for extension in ${INSTALLED_EXTENSIONS}; do
    VERSION=$(curl -s -k -X GET "${DYNATRACE_URL}api/v2/extensions/${extension}/environmentConfiguration" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '.version')
    echo "${extension}"
    echo "Deactivated configuration version:"
    curl -s -k -X DELETE "${DYNATRACE_URL}api/v2/extensions/${extension}/environmentConfiguration" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '.version'
    echo "Extension deleted:"
    curl -s -k -X DELETE "${DYNATRACE_URL}api/v2/extensions/${extension}/${VERSION}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '"\(.extensionName):\(.version)"'
    echo
done