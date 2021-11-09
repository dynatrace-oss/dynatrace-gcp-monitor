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

helm -n dynatrace ls --all --short | grep dynatrace-gcp-function | xargs -L1 helm -n dynatrace delete

gcloud pubsub subscriptions list --format="value(name)" | grep e2e_test_subscription_ | xargs -r -n1 gcloud pubsub subscriptions delete
gcloud pubsub topics list --format="value(name)" | grep e2e_test_topic_ | xargs -r -n1 gcloud pubsub topics delete
gcloud logging sinks list --format="value(name)" | grep e2e_test_log_router_ | xargs -r -n1 gcloud logging sinks delete
gcloud iam service-accounts list --format="value(email)" | grep e2e-test-sa- | xargs -r -n1 gcloud iam service-accounts delete
gcloud iam roles list --format="value(name)" --project="${GCP_PROJECT_ID}" | grep e2e_test_ | xargs -r -n1 basename |  xargs -r -n1 gcloud iam roles delete --project="${GCP_PROJECT_ID}"
gcloud container images list-tags "${GCR_NAME}" --format="value(tags)" | grep e2e-travis-test- | xargs -r -n1 echo "${GCR_NAME}" | tr ' ' ':' | xargs -r -n1 gcloud container images delete
gcloud functions delete "${CLOUD_FUNCTION_NAME}"
