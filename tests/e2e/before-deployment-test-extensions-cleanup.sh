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

# Get installed extensions with their versions directly from the listing
EXTENSIONS_JSON=$(curl -s -k -X GET "${DYNATRACE_URL}api/v2/extensions?pageSize=100" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}")
INSTALLED_EXTENSIONS=$(echo "$EXTENSIONS_JSON" | "$TEST_JQ" -r '.extensions[] | "\(.extensionName)|\(.version)"' 2>/dev/null)

for entry in ${INSTALLED_EXTENSIONS}; do
    extension=$(echo "$entry" | cut -d'|' -f1)
    VERSION=$(echo "$entry" | cut -d'|' -f2)
    echo "${extension}"
    echo "Deactivating configuration:"
    curl -s -k -X DELETE "${DYNATRACE_URL}api/v2/extensions/${extension}/environmentConfiguration" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '.version // "none"'
    if [ -n "$VERSION" ] && [ "$VERSION" != "null" ]; then
        echo "Deleting extension version ${VERSION}:"
        curl -s -k -X DELETE "${DYNATRACE_URL}api/v2/extensions/${extension}/${VERSION}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '"\(.extensionName // "unknown"):\(.version // "unknown")"'
    else
        echo "WARNING: No version found for ${extension}, skipping delete"
    fi
    echo
done

for metric in $("$TEST_JQ" -r '.[].key' < tests/e2e/extensions/data/metadata.json); do
    OBJECT_ID=$(curl -s -k -X GET "${DYNATRACE_URL}api/v2/settings/objects?schemaIds=builtin%3Ametric.metadata&scopes=metric-${metric}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" | "$TEST_JQ" -r '.items[].objectId' 2>/dev/null)
    echo "${metric}"
    curl -s -k -X DELETE "${DYNATRACE_URL}api/v2/settings/objects/${OBJECT_ID}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" > /dev/null
done
