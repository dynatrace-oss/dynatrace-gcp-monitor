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
from typing import List, Dict

import yaml

from lib.context import LoggingContext

HOSTNAME = os.environ.get("HOSTNAME", "")

K8S_CONTAINER_NAME_PREFIX = "dynatrace-gcp-monitor"


def chunks(full_list: List, chunk_size: int) -> List[List]:
    chunk_size = max(1, chunk_size)
    return [full_list[i:i + chunk_size] for i in range(0, len(full_list), chunk_size)]

def safe_read_yaml(filepath: str, alternative_environ_name: str):
    try:
        with open(filepath, encoding="utf-8") as activation_file:
            yaml_dict = yaml.safe_load(activation_file)
    except Exception:
        yaml_dict = yaml.safe_load(os.environ.get(alternative_environ_name, ""))
    if not yaml_dict:
        yaml_dict = {}
    return yaml_dict

def read_activation_yaml():
    return safe_read_yaml('/code/config/activation/gcp_services.yaml', "ACTIVATION_CONFIG" )

def read_autodiscovery_config_yaml():
    return safe_read_yaml('/code/config/activation/autodiscovery-config.yaml', "AUTODISCOVERY_RESOURCES_YAML" )

def read_autodiscovery_block_list_yaml():
    return safe_read_yaml('/code/config/activation/autodiscovery-block-list.yaml', "AUTODISCOVERY_BLOCK_LIST_YAML" )

def read_autodiscovery_resources_mapping():
    return safe_read_yaml('./lib/autodiscovery/config/autodiscovery-mapping.yaml', "AUTODISCOVERY_RESOURCES_MAPPING")

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


def get_autodiscovery_flag_per_service(activation_yaml) -> Dict[str, bool]:
    enabled_autodiscovery = {}
    for service in activation_yaml.get("services", []):
        service_name = service.get("service", "")
        autodiscovery_enabled_flag = service.get("allowAutodiscovery", False)
        if isinstance(autodiscovery_enabled_flag, bool) and autodiscovery_enabled_flag is True:
            enabled_autodiscovery[service_name] = True
        else:
            enabled_autodiscovery[service_name] = False

    return enabled_autodiscovery


def is_yaml_file(f: str) -> bool:
    return f.endswith(".yml") or f.endswith(".yaml")


def extract_technology_name(config_yaml):
    technology_name = config_yaml.get("technology", {})
    if isinstance(technology_name, Dict):
        technology_name = technology_name.get("name", "N/A")
    return technology_name


def is_deployment_running_inside_cloud_function():
    return K8S_CONTAINER_NAME_PREFIX not in HOSTNAME
