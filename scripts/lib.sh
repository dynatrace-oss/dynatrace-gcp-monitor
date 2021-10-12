#!/usr/bin/env bash
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

readonly EXTENSION_MANIFEST_FILE=extensions-list.txt
readonly DYNATRACE_URL_REGEX="^(https?:\/\/[-a-zA-Z0-9@:%._+~=]{1,256}\/?)(\/e\/[a-z0-9-]{36}\/?)?$"
readonly ACTIVE_GATE_TARGET_URL_REGEX="^https:\/\/[-a-zA-Z0-9@:%._+~=]{1,256}\/e\/[-a-z0-9]{1,36}[\/]{0,1}$"

warn() {
  MESSAGE=$1
  echo -e >&2
  echo -e "\e[93mWARNING: \e[37m${MESSAGE}" >&2
  echo -e >&2
}

err() {
  MESSAGE=$1
  echo -e >&2
  echo -e "\e[91mERROR: \e[37m${MESSAGE}" >&2
  echo -e >&2
}

onFailure() {
    err " - deployment failed, please examine error messages and run again"
    exit 2
}

versionNumber() {
   echo "$@" | awk -F. '{ printf("%d%03d%03d%03d\n", $1,$2,$3,$4); }';
}

dt_api()
{
  URL=$1
  if [ $# -eq 3 ]; then
    METHOD="$2"
    DATA=("-d" "$3")
  else
    METHOD="GET"
  fi
  if RESPONSE=$(curl -k -s -X $METHOD "${DYNATRACE_URL}${URL}" -w "<<HTTP_CODE>>%{http_code}" -H "Accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" "${DATA[@]}"); then
    CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<< "$RESPONSE")
    sed -r 's/(.*)<<HTTP_CODE>>.*$/\1/' <<< "$RESPONSE"
    if [ "$CODE" -ge 400 ]; then
      return 255
    fi
  fi
}

check_if_parameter_is_empty() {
  PARAMETER=$1
  PARAMETER_NAME=$2
  if [ -z "${PARAMETER}" ]; then
    echo "Missing required parameter: ${PARAMETER_NAME}"
    exit
  fi
}

check_url() {
  URL=$1
  REGEX=$2
  MESSAGE=$3
  if ! [[ "${URL}" =~ ${REGEX} ]]; then
    err "${MESSAGE}"
    exit 1
  fi
}

check_api_token() {
  if RESPONSE=$(dt_api "/api/v2/apiTokens/lookup" "POST" "{\"token\":\"$DYNATRACE_ACCESS_KEY\"}"); then
    for REQUIRED in "${API_TOKEN_SCOPES[@]}"; do
      if ! grep -q "${REQUIRED}" <<<"$RESPONSE"; then
        err "Missing permission for the API token: ${REQUIRED}."
        echo "Please enable all required permissions: ${API_TOKEN_SCOPES[*]} for chosen deployment type: ${DEPLOYMENT_TYPE}"
        exit 1
      fi
    done
  else
    warn "Failed to connect to endpoint ${URL} to check API token permissions. It can be ignored if Dynatrace does not allow public access."
  fi
}

get_extensions_zip_packages() {
  curl -s -O "${EXTENSION_S3_URL}/${EXTENSION_MANIFEST_FILE}"
  mkdir -p ./extensions

  grep -v '^ *#' < "${EXTENSION_MANIFEST_FILE}" | while IFS= read -r EXTENSION_FILE_NAME
  do
    (cd ./extensions && curl -s -O "${EXTENSION_S3_URL}/${EXTENSION_FILE_NAME}")
  done
}

get_activated_extensions_on_cluster() {
  if RESPONSE=$(dt_api "/api/v2/extensions"); then
    echo "${RESPONSE}" | sed -r 's/<<HTTP_CODE>>.*$//' | jq -r '.extensions[] | select(.extensionName) | "\(.extensionName):\(.version)"'
  else
    err "- Dynatrace Cluster failed on ${DYNATRACE_URL}/api/v2/extensions endpoint."
    exit
  fi
}

upload_extension_to_cluster() {
  EXTENSION_ZIP=$1
  EXTENSION_VERSION=$2

  UPLOAD_RESPONSE=$(curl -s -k -X POST "${DYNATRACE_URL}/api/v2/extensions" -w "<<HTTP_CODE>>%{http_code}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" -H "Content-Type: multipart/form-data" -F "file=@${EXTENSION_ZIP};type=application/zip")
  CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<<"$UPLOAD_RESPONSE")

  if [[ "${CODE}" -ge "400" ]]; then
    warn "- Extension ${EXTENSION_ZIP} upload failed with error code: ${CODE}"
  else
    UPLOADED_EXTENSION=$(echo "${UPLOAD_RESPONSE}" | sed -r 's/<<HTTP_CODE>>.*$//' | jq -r '.extensionName')

    if ! RESPONSE=$(dt_api "/api/v2/extensions/${UPLOADED_EXTENSION}/environmentConfiguration" "PUT" "{\"version\": \"${EXTENSION_VERSION}\"}"); then
      warn "- Activation ${EXTENSION_ZIP} failed."
    else
      echo "- Extension ${UPLOADED_EXTENSION}:${EXTENSION_VERSION} activated."
    fi
  fi
}

services_setup_in_config() {
  SERVICES_FROM_ACTIVATION_CONFIG=$1

  # Add '/default' to service name when featureSet is missing
  for i in "${!SERVICES_FROM_ACTIVATION_CONFIG[@]}"; do
    if ! [[ "${SERVICES_FROM_ACTIVATION_CONFIG[$i]}" == *"/"* ]];then
      SERVICES_FROM_ACTIVATION_CONFIG[$i]="${SERVICES_FROM_ACTIVATION_CONFIG[$i]}/default"
    fi
  done
  echo "${SERVICES_FROM_ACTIVATION_CONFIG[*]}"
}

activate_extension_on_cluster() {
  EXTENSION_ZIP=$1

  EXTENSION_NAME=${EXTENSION_ZIP:0:${#EXTENSION_ZIP}-10}
  EXTENSION_VERSION=${EXTENSION_ZIP: -9:5}
  EXTENSION_IN_DT=$(echo "${EXTENSIONS_FROM_CLUSTER[*]}" | grep "${EXTENSION_NAME}:")

  if [ -z "${EXTENSION_IN_DT}" ]; then
    # missing extension in cluster installing it
    upload_extension_to_cluster "${EXTENSION_ZIP}" "${EXTENSION_VERSION}"
  elif [ "$(versionNumber ${EXTENSION_VERSION})" -gt "$(versionNumber ${EXTENSION_IN_DT: -5})" ]; then
    # cluster has never version warning and install if flag was set
    if [ -n "${UPGRADE_EXTENSIONS}" ]; then
      upload_extension_to_cluster "${EXTENSION_ZIP}" "${EXTENSION_VERSION}"
    else
      warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT: -5} installed on the cluster, use '--upgrade-extensions' to uprgate to: ${EXTENSION_NAME}:${EXTENSION_VERSION}"
    fi
  elif [ "$(versionNumber ${EXTENSION_VERSION})" -lt "$(versionNumber ${EXTENSION_IN_DT: -5})" ]; then
    warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT: -5} installed on the cluster is newer than ${EXTENSION_NAME}:${EXTENSION_VERSION}"
  fi
}

get_extensions_from_dynatrace() {
  EXTENSIONS_FROM_CLUSTER=$1

  mkdir -p ./extensions
  mkdir -p ./extensions_from_cluster

  cd ./extensions_from_cluster || exit

  EXTENSIONS_TO_DOWNLOAD="com.dynatrace.extension.google"
  readarray -t EXTENSIONS_FROM_CLUSTER_ARRAY <<<"$( echo "${EXTENSIONS_FROM_CLUSTER}" | sed 's/ /\n/' | grep "$EXTENSIONS_TO_DOWNLOAD" )"
  for i in "${!EXTENSIONS_FROM_CLUSTER_ARRAY[@]}"; do
    EXTENSION_NAME="$(cut -d':' -f1 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"
    EXTENSION_VERSION="$(cut -d':' -f2 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"
    
    curl -k -s -X GET "${DYNATRACE_URL}/api/v2/extensions/${EXTENSION_NAME}/${EXTENSION_VERSION}" -H "Accept: application/octet-stream" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" -o "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip"
    if [ -f "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ] && [[ "$EXTENSION_NAME" =~ ^com.dynatrace.extension.(google.*)$ ]]; then
      find ../extensions -regex ".*${BASH_REMATCH[1]}.*" -exec rm -rf {} \;
      mv "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ../extensions
    fi
  done
  
  cd ../ || exit
  rm -rf ../extensions_from_cluster
}

upload_correct_extension_to_dynatrace() {
  SERVICES_FROM_ACTIVATION_CONFIG_STR=$1

  cd ./extensions || exit

  for EXTENSION_ZIP in *.zip; do
    EXTENSION_FILE_NAME="$(basename "$EXTENSION_ZIP" .zip)"
    
    unzip -j -q "$EXTENSION_ZIP" "extension.zip"
    unzip -p -q "extension.zip" "extension.yaml" >"$EXTENSION_FILE_NAME".yaml
    
    EXTENSION_GCP_CONFIG=$(yq e '.gcp' "$EXTENSION_FILE_NAME".yaml)

    # Get all service/featureSet pairs defined in extensions
    SERVICES_FROM_EXTENSIONS=$(echo "$EXTENSION_GCP_CONFIG" | yq e -j | jq -r 'to_entries[] | "\(.value.service)/\(.value.featureSet)"')
    
    for SERVICE_FROM_EXTENSION in $SERVICES_FROM_EXTENSIONS; do
      SERVICE_FROM_EXTENSION="${SERVICE_FROM_EXTENSION/null/default}"
      # Check if service should be monitored
      if [[ "$SERVICES_FROM_ACTIVATION_CONFIG_STR" == *"$SERVICE_FROM_EXTENSION"* ]]; then
        activate_extension_on_cluster "$EXTENSION_ZIP"
        break
      fi
    done
    rm extension.zip
    rm "$EXTENSION_FILE_NAME".yaml
    rm "$EXTENSION_ZIP"
  done
}
