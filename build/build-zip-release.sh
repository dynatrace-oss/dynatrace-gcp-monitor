#!/bin/bash
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

if [[ "${E2E:-}" != "true" ]]; then
  readonly VERSION=$(cat ./build/version | awk 'BEGIN { FS="." } { $3++;  if ($3 > 999) { $3=0; $2++; if ($2 > 99) { $2=0; $1++ } } } { printf "%s.%s.%s", $1, $2, $3 }')
  readonly PACKAGE_PATH="./build/dist/$VERSION"
  echo $VERSION > ./build/version
  mkdir -p $PACKAGE_PATH
  (cd ./src/; zip -r ../$PACKAGE_PATH/dynatrace-gcp-function.zip ./ -x '*__pycache__*')
else
  (cd ./src/; zip -r ../dynatrace-gcp-function.zip ./ -x '*__pycache__*')
fi