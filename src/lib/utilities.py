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
import os
from typing import List

import yaml

from lib.context import LoggingContext


def chunks(full_list: List, chunk_size: int) -> List[List]:
    chunk_size = max(1, chunk_size)
    return [full_list[i:i + chunk_size] for i in range(0, len(full_list), chunk_size)]


def read_activation_yaml():
    activation_file_path = '/code/config/activation/gcp_services.yaml'
    try:
        with open(activation_file_path, encoding="utf-8") as activation_file:
            activation_yaml = yaml.safe_load(activation_file)
    except Exception:
        activation_yaml = yaml.safe_load(os.environ.get("ACTIVATION_CONFIG", ""))
    if not activation_yaml:
        activation_yaml = {}
    return activation_yaml


def get_activation_config_per_service(activation_yaml):
    return {service_activation.get('service'): service_activation for service_activation in
            activation_yaml['services']} if activation_yaml and activation_yaml['services'] else {}


def load_activated_feature_sets(logging_context: LoggingContext, activation_yaml) -> List[str]:
    services_whitelist = []
    for service in activation_yaml.get("services", []):
        feature_sets = service.get("featureSets", [])
        for feature_set in feature_sets:
            services_whitelist.append(f"{service.get('service')}/{feature_set}")
        if not feature_sets:
            logging_context.error(f"No feature set in given {service} service.")

    return services_whitelist


def print_dynatrace_logo():
    print("                      ,,,,,..")
    print("                  ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,.")
    print("               ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,")
    print("            .,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,     ,,")
    print("          ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,    .,,,,")
    print("       ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,     ,,,,,,,.")
    print("    .,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,.    ,,,,,,,,,,,")
    print("  ,,,,,,,,,,,,,,,,,......  ......,,,,,,,    .,,,,,,,,,,,,,")
    print(",,                                        ,,,,,,,,,,,,,,,,")
    print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,")
    print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,.")
    print(",,,,,,,,,,,,,,,,,       Dynatrace        .,,,,,,,,,,,,,,,,.")
    print(",,,,,,,,,,,,,,,,, dynatrace-gcp-function .,,,,,,,,,,,,,,,,,")
    print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,,")
    print(",,,,,,,,,,,,,,,,,                        ,,,,,,,,,,,,,,,,,,")
    print(",,,,,,,,,,,,,,,,,                        ,,,,,,,,,,,,,,,,,,")
    print(".,,,,,,,,,,,,,,,                         ,,,,,,,,,,,,,,,,,")
    print(".,,,,,,,,,,,,,    .,,,,,,,,,,,,,,,,,,.   ,,,,,,,,,,,,,,,")
    print(" ,,,,,,,,,,     ,,,,,,,,,,,,,,,,,,,,,,  .,,,,,,,,,,,,.")
    print(" ,,,,,,,     ,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,,,,,,,,")
    print(" ,,,,,    .,,,,,,,,,,,,,,,,,,,,,,,,,,.  ,,,,,,,,")
    print("  ,     ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,,,,")
    print("     ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,")
    print("")
