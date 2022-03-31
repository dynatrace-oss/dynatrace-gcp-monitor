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

START_LOAD_GENERATION=$(date -u +%s%3N)
export START_LOAD_GENERATION

./tests/e2e/deployment-test-cloud-function.sh
sleep 420

END_LOAD_GENERATION=$(date -u +%s%3N)
export END_LOAD_GENERATION

pytest "tests/e2e/extensions" -v
pytest "tests/e2e/metrics" -v
