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

readonly EXTENSION_MANIFEST_FILE=extensions-list.txt
# shellcheck disable=SC2034  # Unused variables left for readability
readonly DYNATRACE_URL_REGEX="^(https?:\/\/[-a-zA-Z0-9@:%._+~=]{1,255}\/?)(\/e\/[a-z0-9-]{1,36}\/?)?$"
readonly EXTENSION_ZIP_REGEX="^(.*)-([0-9.]*).zip$"
EXTENSIONS_TMPDIR=$(mktemp -d)
CLUSTER_EXTENSIONS_TMPDIR=$(mktemp -d)
WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FULL_LOG_FILE="${WORKING_DIR}/dynatrace_gcp_$(date '+%Y-%m-%d_%H:%M:%S').log"
touch "$FULL_LOG_FILE"

debug() {
  MESSAGE=$1
  echo -e | tee -a "$FULL_LOG_FILE" &> /dev/null
  echo -e "DEBUG: ${MESSAGE}" | tee -a "$FULL_LOG_FILE" &> /dev/null
  echo -e | tee -a "$FULL_LOG_FILE" &> /dev/null
  echo -e "DEBUG: ${MESSAGE}"
}

info() {
  MESSAGE=$1
  echo -e "${MESSAGE}" | tee -a "$FULL_LOG_FILE"
}

warn() {
  MESSAGE=$1
  echo -e | tee -a "$FULL_LOG_FILE"
  echo -e "\e[93mWARNING: \e[37m${MESSAGE}" | tee -a "$FULL_LOG_FILE"
  echo -e | tee -a "$FULL_LOG_FILE"
}

err() {
  MESSAGE=$1
  echo -e | tee -a "$FULL_LOG_FILE"
  echo -e "\e[91mERROR: \e[37m${MESSAGE}" | tee -a "$FULL_LOG_FILE"
  echo -e | tee -a "$FULL_LOG_FILE"
}

system_info() {
  debug "Current shell version: $($(ps -p $$ -ocomm= | sed s/-//g) --version)"
  debug "CLOUD_SHELL=${CLOUD_SHELL}"
}
system_info

clean() {
  info "- removing extensions files"
  rm -rf $EXTENSION_MANIFEST_FILE "$CLUSTER_EXTENSIONS_TMPDIR" "$EXTENSIONS_TMPDIR"

  if [ -n "$GCP_FUNCTION_NAME" ]; then
    info "- removing archive [$FUNCTION_ZIP_PACKAGE]"
    rm "$WORKING_DIR"/"$FUNCTION_ZIP_PACKAGE"

    info "- removing temporary directory [$GCP_FUNCTION_NAME]"
    rm -r "${WORKING_DIR:?}"/"$GCP_FUNCTION_NAME"
  fi
}

ctrl_c() {
  clean
  err " - deployment failed, script was break by CTRL-C"
  exit 3
}

onFailure() {
  err " - deployment failed, please examine error messages and run again"
  exit 2
}

versionNumber() {
  echo "$@" | awk -F. '{ printf("%d%03d%03d%03d\n", $1,$2,$3,$4); }'
}

test_req_yq() {
  if command -v "$YQ" &>/dev/null ; then
    VERSION_YQ=$("$YQ" --version | cut -d' ' -f3 | tr -d '"')
    if [ "$VERSION_YQ" == "version" ]; then
      VERSION_YQ=$("$YQ" --version | cut -d' ' -f4 | tr -d '"')
    fi
  fi

  if [ -z "$VERSION_YQ" ] || [ "$(versionNumber "$VERSION_YQ")" -lt "$(versionNumber '4.9.8')" ]; then
    err 'yq (4.9.x+) is required to install Dynatrace function. Please refer to following links for installation instructions:
      YQ: https://github.com/mikefarah/yq
      Example command to install yq:
      sudo wget https://github.com/mikefarah/yq/releases/download/v4.9.8/yq_linux_amd64 -O /usr/bin/yq && sudo chmod +x /usr/bin/yq'
    exit 1
  fi
}

test_req_jq() {
  if ! command -v "$JQ" &>/dev/null; then
    err 'jq is required to install Dynatrace function. Please refer to following links for installation instructions:
    JQ: https://stedolan.github.io/jq/download/"
    Example command to install jq:
    sudo wget https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 -O /usr/bin/jq && sudo chmod +x /usr/bin/jq'
    exit 1
  fi
}

test_req_gcloud() {
  if ! command -v gcloud &>/dev/null; then
    err 'Google Cloud CLI is required to install Dynatrace function. Go to following link in your browser and download latest version of Cloud SDK:
      https://cloud.google.com/sdk/docs#install_the_latest_cloud_tools_version_cloudsdk_current_version'
    exit
  fi
}

test_req_unzip() {
  if ! command -v unzip &>/dev/null; then
    err 'unzip is required to install Dynatrace function'
    exit
  fi
}

test_req_kubectl() {
  if ! command -v kubectl &>/dev/null; then
    err 'Kubernetes CLI is required to deploy the Dynatrace GCP Function. Go to following link in your browser and install kubectl in the most convenient way to you:
    https://kubernetes.io/docs/tasks/tools/'
    exit
  fi
}

test_req_helm() {
  if ! command -v helm &>/dev/null; then
    err 'Helm is required to deploy the Dynatrace GCP Function. Go to following link in your browser and install Helm in the most convenient way to you:
    https://helm.sh/docs/intro/install/'
    exit
  fi
}

init_ext_tools() {
  local OS
  local HW
  
  OS=$(uname -s)
  HW=$(uname -m)


  case "$OS $HW" in
    "Linux x86_64")
      ARCH=linux_x64
    ;;
    *)
      warn "Architecture '$OS $HW' not supported"
      ARCH=""
    ;;
  esac

  if [ -z "$YQ" ]; then
    YQ=yq
  fi

  if [ -z "$JQ" ]; then
    JQ=jq
  fi

  if [ -n "$ARCH" ]; then
     # Always use internal tools on supported architectures
     YQ="$WORKING_DIR/ext_tools/yq_$ARCH"
     JQ="$WORKING_DIR/ext_tools/jq_$ARCH"
  fi

  test_req_yq
  test_req_jq
}

dt_api() {
  URL=$1
  if [ $# -eq 3 ]; then
    METHOD="$2"
    DATA=("-d" "$3")
  else
    METHOD="GET"
  fi
  if RESPONSE=$(curl -k -s -X $METHOD "${DYNATRACE_URL}${URL}" -w "<<HTTP_CODE>>%{http_code}" -H "Accept: application/json; charset=utf-8" -H "Content-Type: application/json; charset=utf-8" -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" "${DATA[@]}" | tee -a "$FULL_LOG_FILE"); then
    CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<<"$RESPONSE")
    sed -r 's/(.*)<<HTTP_CODE>>.*$/\1/' <<<"$RESPONSE"
    if [ "$CODE" -ge 400 ]; then
      warn "Received ${CODE} response from ${DYNATRACE_URL}${URL}"
      return 1
    fi
  else
    warn "Unable to connect to ${DYNATRACE_URL}"
    return 2
  fi
}

check_if_parameter_is_empty() {
  PARAMETER=$1
  PARAMETER_NAME=$2
  ADDITIONAL_MESSAGE=$3
  if [ -z "${PARAMETER}" ] || [ "$PARAMETER" = "<PLACEHOLDER>" ]; then
    info "Missing required parameter: ${PARAMETER_NAME}. ${ADDITIONAL_MESSAGE}"
    exit
  fi
}

check_url() {
  URL=$1
  REGEXES=${*:2:$#-2} # all arguments except first and last
  MESSAGE=${*: -1} # last argument

  for REGEX in $REGEXES
  do
    if [[ "$URL" =~ $REGEX ]]; then
      return 0
    fi
  done

  err "$MESSAGE"
  exit 1
}

check_api_token() {
  if RESPONSE=$(dt_api "/api/v2/apiTokens/lookup" "POST" "{\"token\":\"$DYNATRACE_ACCESS_KEY\"}"); then
    for REQUIRED in "${API_TOKEN_SCOPES[@]}"; do
      if ! grep -q "${REQUIRED}" <<<"$RESPONSE"; then
        err "Missing permission for the API token: ${REQUIRED}."
        info "Please enable all required permissions: ${API_TOKEN_SCOPES[*]} for chosen deployment type: ${DEPLOYMENT_TYPE}"
        exit 1
      fi
    done
  else
    warn "Failed to connect to endpoint ${URL} to check API token permissions. It can be ignored if Dynatrace does not allow public access."
  fi
}

check_s3_url() {
  if [ -z "$EXTENSION_S3_URL" ]; then
    EXTENSION_S3_URL="https://dynatrace-gcp-extensions.s3.amazonaws.com"
  else
    warn "Development mode on: custom S3 url link."
  fi
}

validate_gcp_config_in_extensions() {
  cd "${EXTENSIONS_TMPDIR}" || exit
  for EXTENSION_ZIP in *.zip; do
    unzip "${EXTENSION_ZIP}" -d "$EXTENSION_ZIP-tmp" | tee -a "$FULL_LOG_FILE" >/dev/null
    cd "$EXTENSION_ZIP-tmp" || exit
    unzip "extension.zip" "extension.yaml" | tee -a "$FULL_LOG_FILE" >/dev/null
    if [[ $("$YQ" e 'has("gcp")' extension.yaml) == "false" ]]; then
      warn "- Extension $EXTENSION_ZIP definition is incorrect. The definition must contain 'gcp' section. The extension won't be uploaded."
      rm -rf "../${EXTENSION_ZIP}"
    elif [[ $("$YQ" e '.gcp.[] | has("featureSet")' extension.yaml) =~ "false" ]]; then
      warn "- Extension $EXTENSION_ZIP definition is incorrect. Every service requires defined featureSet"
      rm -rf "../${EXTENSION_ZIP}"
    else
      echo -n "." | tee -a "$FULL_LOG_FILE"
    fi
    cd ..
    rm -r "$EXTENSION_ZIP-tmp"
  done
  cd "${WORKING_DIR}" || exit
}

get_extensions_zip_packages() {
  curl -O "${EXTENSION_S3_URL}/${EXTENSION_MANIFEST_FILE}" | tee -a "$FULL_LOG_FILE" &> /dev/null
  EXTENSIONS_LIST=$(grep "^google.*\.zip" <"$EXTENSION_MANIFEST_FILE" | tee -a "$FULL_LOG_FILE")
  if [ -z "$EXTENSIONS_LIST" ]; then
    err "Empty extensions manifest file downloaded"
    exit 1
  fi

  echo "${EXTENSIONS_LIST}" | while IFS= read -r EXTENSION_FILE_NAME; do
    echo -n "." | tee -a "$FULL_LOG_FILE"
    (cd "${EXTENSIONS_TMPDIR}" && curl -s -O "${EXTENSION_S3_URL}/${EXTENSION_FILE_NAME}")
  done
}

get_activated_extensions_on_cluster() {
  if RESPONSE=$(dt_api "/api/v2/extensions?pageSize=100"); then
    EXTENSIONS=$(echo "${RESPONSE}" | sed -r 's/<<HTTP_CODE>>.*$//' | "$JQ" -r '.extensions[] | select(.extensionName) | "\(.extensionName):\(.version)"')
    NEXT_PAGE_KEY=$(echo "${RESPONSE}" | "$JQ" -r '.nextPageKey')
    while [[ "$NEXT_PAGE_KEY" != "null" ]]; do
      RESPONSE=$(dt_api "/api/v2/extensions?nextPageKey=$NEXT_PAGE_KEY")
      NEXT_PAGE_KEY=$(echo "${RESPONSE}" | "$JQ" -r '.nextPageKey')
      EXTENSIONS_FROM_NEXT_PAGE=$(echo "${RESPONSE}" | sed -r 's/<<HTTP_CODE>>.*$//' | "$JQ" -r '.extensions[] | select(.extensionName) | "\(.extensionName):\(.version)"')
      EXTENSIONS_FROM_NEXT_PAGE=$(echo -e "\n$EXTENSIONS_FROM_NEXT_PAGE")
      EXTENSIONS=("${EXTENSIONS[@]}" "${EXTENSIONS_FROM_NEXT_PAGE[@]}")
    done
    info "${EXTENSIONS[@]}"
  else
    err "- Dynatrace Cluster failed on ${DYNATRACE_URL}/api/v2/extensions endpoint."
    exit
  fi
}

upload_extension_to_cluster() {
  EXTENSION_ZIP=$1
  EXTENSION_VERSION=$2

  UPLOAD_RESPONSE=$(curl -s -k -X POST "${DYNATRACE_URL}/api/v2/extensions" -w "<<HTTP_CODE>>%{http_code}" -H "accept: application/json; charset=utf-8" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" -H "Content-Type: multipart/form-data" -F "file=@${EXTENSION_ZIP};type=application/zip"  | tee -a "$FULL_LOG_FILE")
  CODE=$(sed -rn 's/.*<<HTTP_CODE>>(.*)$/\1/p' <<<"$UPLOAD_RESPONSE")

  if [[ "${CODE}" -ge "400" ]]; then
    warn "- Extension ${EXTENSION_ZIP} upload failed with error code: ${CODE}"
    ((AMOUNT_OF_NOT_UPLOADED_EXTENSIONS+=1))
  else
    UPLOADED_EXTENSION=$(echo "${UPLOAD_RESPONSE}" | sed -r 's/<<HTTP_CODE>>.*$//' | "$JQ" -r '.extensionName')

    if ! RESPONSE=$(dt_api "/api/v2/extensions/${UPLOADED_EXTENSION}/environmentConfiguration" "PUT" "{\"version\": \"${EXTENSION_VERSION}\"}"); then
      warn "- Activation ${EXTENSION_ZIP} failed."
      ((AMOUNT_OF_NOT_ACTIVATED_EXTENSIONS+=1))
    else
      info ""
      info "- Extension ${UPLOADED_EXTENSION}:${EXTENSION_VERSION} activated."
    fi
  fi
}

activate_extension_on_cluster() {
  EXTENSIONS_FROM_CLUSTER=$1
  EXTENSION_ZIP=$2

  if [[ "$EXTENSION_ZIP" =~ $EXTENSION_ZIP_REGEX ]]; then
    EXTENSION_NAME="${BASH_REMATCH[1]}"
    EXTENSION_VERSION="${BASH_REMATCH[2]}"
  fi
  EXTENSION_IN_DT=$(echo "${EXTENSIONS_FROM_CLUSTER[*]}" | grep "${EXTENSION_NAME}:")

  if [ -z "${EXTENSION_IN_DT}" ]; then
    # missing extension in cluster installing it
    upload_extension_to_cluster "${EXTENSION_ZIP}" "${EXTENSION_VERSION}"
  # example of extension from DT: com.dynatrace.extension.google-kubernetes-engine:0.0.10
  # $EXTENSION_IN_DT##*: -> removes everything before ':', e.g. we will get '0.0.10'
  elif [ "$(versionNumber "${EXTENSION_VERSION}")" -gt "$(versionNumber "${EXTENSION_IN_DT##*:}")" ]; then
    # cluster has newer version warning and install if flag was set
    if [ -n "${UPGRADE_EXTENSIONS}" ]; then
      upload_extension_to_cluster "${EXTENSION_ZIP}" "${EXTENSION_VERSION}"
    else
      warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT##*:} installed on the cluster, use '--upgrade-extensions' to upgrade to: ${EXTENSION_NAME}:${EXTENSION_VERSION}"
      ((AMOUNT_OF_EXTENSIONS_TO_UPLOAD-=1))
    fi
  elif [ "$(versionNumber "${EXTENSION_VERSION}")" -lt "$(versionNumber "${EXTENSION_IN_DT##*:}")" ]; then
    warn "Extension not uploaded. Current active extension ${EXTENSION_NAME}:${EXTENSION_IN_DT##*:} installed on the cluster is newer than ${EXTENSION_NAME}:${EXTENSION_VERSION}"
    ((AMOUNT_OF_EXTENSIONS_TO_UPLOAD-=1))
  fi
}

get_extensions_from_dynatrace() {
  EXTENSIONS_FROM_CLUSTER=$1

  cd "${CLUSTER_EXTENSIONS_TMPDIR}" || exit

  EXTENSIONS_TO_DOWNLOAD="com.dynatrace.extension.google"
  readarray -t EXTENSIONS_FROM_CLUSTER_ARRAY <<<"$(echo "${EXTENSIONS_FROM_CLUSTER}" | sed 's/ /\n/' | grep "$EXTENSIONS_TO_DOWNLOAD")"
  for i in "${!EXTENSIONS_FROM_CLUSTER_ARRAY[@]}"; do
    EXTENSION_NAME="$(cut -d':' -f1 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"
    EXTENSION_VERSION="$(cut -d':' -f2 <<<"${EXTENSIONS_FROM_CLUSTER_ARRAY[$i]}")"

    curl -k -s -X GET "${DYNATRACE_URL}/api/v2/extensions/${EXTENSION_NAME}/${EXTENSION_VERSION}" -H "Accept: application/octet-stream" -H "Authorization: Api-Token ${DYNATRACE_ACCESS_KEY}" -o "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" | tee -a "$FULL_LOG_FILE"
    if [ -f "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" ] && [[ "$EXTENSION_NAME" =~ ^com.dynatrace.extension.(google.*)$ ]]; then
      find "${EXTENSIONS_TMPDIR}" -regex ".*${BASH_REMATCH[1]}.*" -exec rm -rf {} \;
      mv "${EXTENSION_NAME}-${EXTENSION_VERSION}.zip" "${EXTENSIONS_TMPDIR}"
    fi
  done

  cd "${WORKING_DIR}" || exit
  rm -rf "${CLUSTER_EXTENSIONS_TMPDIR}"
}

upload_correct_extension_to_dynatrace() {
  SERVICES_FROM_ACTIVATION_CONFIG_STR=$1

  cd "${EXTENSIONS_TMPDIR}" || exit

  AMOUNT_OF_EXTENSIONS_TO_UPLOAD=0
  AMOUNT_OF_NOT_UPLOADED_EXTENSIONS=0
  AMOUNT_OF_NOT_ACTIVATED_EXTENSIONS=0

  for EXTENSION_ZIP in *.zip; do
    EXTENSION_FILE_NAME="$(basename "$EXTENSION_ZIP" .zip)"

    unzip -j -q "$EXTENSION_ZIP" "extension.zip"
    unzip -p -q "extension.zip" "extension.yaml" >"$EXTENSION_FILE_NAME".yaml

    EXTENSION_GCP_CONFIG=$("$YQ" e '.gcp' "$EXTENSION_FILE_NAME".yaml)

    # Get all service/featureSet pairs defined in extensions
    SERVICES_FROM_EXTENSIONS=$(echo "$EXTENSION_GCP_CONFIG" | "$YQ" e -j | "$JQ" -r 'to_entries[] | "\(.value.service)/\(.value.featureSet)"' 2>/dev/null | tee -a "$FULL_LOG_FILE")

    for SERVICE_FROM_EXTENSION in $SERVICES_FROM_EXTENSIONS; do
      # Check if service should be monitored
      if [[ "$SERVICES_FROM_ACTIVATION_CONFIG_STR" == *"$SERVICE_FROM_EXTENSION"* ]]; then
        if [ -n "$GCP_FUNCTION_NAME" ]; then
          CONFIG_NAME=$("$YQ" e '.name' "$EXTENSION_FILE_NAME".yaml)
          if [[ "$CONFIG_NAME" =~ ^.*\.(.*)$ ]]; then
            echo "gcp:" >"$WORKING_DIR"/"$GCP_FUNCTION_NAME"/config/"${BASH_REMATCH[1]}".yaml
            echo "$EXTENSION_GCP_CONFIG" >>"$WORKING_DIR"/"$GCP_FUNCTION_NAME"/config/"${BASH_REMATCH[1]}".yaml
          fi
        fi
        ((AMOUNT_OF_EXTENSIONS_TO_UPLOAD+=1))
        activate_extension_on_cluster "$EXTENSIONS_FROM_CLUSTER" "$EXTENSION_ZIP"
        break
      fi
      echo -n "." | tee -a "$FULL_LOG_FILE"
    done
    rm extension.zip
    rm "$EXTENSION_FILE_NAME".yaml
    rm "$EXTENSION_ZIP"
  done

  if [[ "$AMOUNT_OF_EXTENSIONS_TO_UPLOAD" -eq "$AMOUNT_OF_NOT_UPLOADED_EXTENSIONS" ]]; then
    err "Uploading all GCP extensions to Dynatrace failed. It can be a temporary problem with the cluster. Please run deployment script again in a while."
    exit 1
  fi

  if [[ "$AMOUNT_OF_EXTENSIONS_TO_UPLOAD" -eq "$AMOUNT_OF_NOT_ACTIVATED_EXTENSIONS" ]]; then
    err "Activating all GCP extensions on Dynatrace failed. It can be a temporary problem with the cluster. Please try activate your extensions on the cluster manually in a while."
  else
    AMOUNT_OF_ALL_FAILED_EXTENSIONS=$((AMOUNT_OF_NOT_UPLOADED_EXTENSIONS + AMOUNT_OF_NOT_ACTIVATED_EXTENSIONS))
    if [[ "$AMOUNT_OF_EXTENSIONS_TO_UPLOAD" -eq "$AMOUNT_OF_ALL_FAILED_EXTENSIONS" ]]; then
      err "Uploading and activating GCP extensions on Dynatrace failed.
      It can be a temporary problem with the cluster. Please run deployment script again in a while.
      For not activated but uploaded extensions - please try activate them on the cluster manually in a while."
    fi
  fi

  cd "${WORKING_DIR}" || exit
}
