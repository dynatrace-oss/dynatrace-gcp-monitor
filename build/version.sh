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

echo  "Travis tag     '$TRAVIS_TAG'"
echo  "Travis commit  '$TRAVIS_COMMIT'"

version=""

if [ -n "$TRAVIS_TAG" ]
 then
     version="$TRAVIS_TAG"
elif [ -n "$TRAVIS_COMMIT" ]
 then
    version=$TRAVIS_COMMIT
fi


if [ -n "$version" ]
then
    echo "Writing version $version..."
    printf "%s" "$version" > ./src/version.txt
else 
    echo "WARN Unknown version, version not updated"
fi