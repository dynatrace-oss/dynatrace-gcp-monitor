#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import logging


def e2e_test_sample_app(request):
    request_args = request.args
    deployment_type = 'None'
    build_id = 'None'

    if request_args and 'deployment_type' in request_args:
        deployment_type = request_args['deployment_type']

    if request_args and 'build_id' in request_args:
        build_id = request_args['build_id']

    logging.info(f"TYPE: {deployment_type}, BUILD: {build_id}, INFO: This is sample app")

    return "This is sample app"
