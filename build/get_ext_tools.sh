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
set -e

EXT_DIR=ext_tools
WGET_CACHE="$HOME/.wgetcache"

wget_cache(){
  local URL=$1
  local TARGET=$2

  local FILE="${WGET_CACHE}/${URL/https:\/\//}"
  if [ ! -f "$FILE" ]; then
    echo "Downloading $URL ..."
    mkdir -p "$(dirname "$FILE" )"
    wget -nv "${URL}" -O "$FILE"

  else
    echo "Using cached $URL -> $FILE"
  fi

  cp "$FILE" "$TARGET"
}

get_ext() {
  local URL=$1
  local NAME=$2

  shift 2

  while [ "$#" -ge 2 ]
  do
     local ARCH_SRC=$1
     local ARCH_DST=$2

     local FILE="$EXT_DIR/${NAME}_${ARCH_DST}"
     wget_cache "${URL}${ARCH_SRC}" "$FILE" && chmod -v +x "$FILE"
     shift 2
  done
}

get_ext https://github.com/stedolan/jq/releases/download/jq-1.5/jq jq -linux64 linux_x64
get_ext https://github.com/mikefarah/yq/releases/download/v4.9.8/yq yq _linux_amd64 linux_x64

cd ext_tools
sha256sum -c sha256sums.txt
ls -lh .