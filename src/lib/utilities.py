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
from os import listdir
from os.path import isfile
from typing import List, Dict

import yaml
import json
import re
from itertools import chain

from lib.configuration import config
from lib.context import LoggingContext
from lib.metrics import GCPService


def chunks(full_list: List, chunk_size: int) -> List[List]:
    chunk_size = max(1, chunk_size)
    return [full_list[i:i + chunk_size] for i in range(0, len(full_list), chunk_size)]


def safe_read_yaml(filepath: str, alternative_environ_name: str):
    logging_context = LoggingContext(None)
    try:
        with open(filepath, encoding="utf-8") as activation_file:
            yaml_dict = yaml.safe_load(activation_file)
    except Exception as e:
        if isinstance(e, yaml.YAMLError):
            logging_context.t_error(str(e))
        yaml_dict = yaml.safe_load(os.environ.get(alternative_environ_name, ""))
    if not yaml_dict:
        yaml_dict = {}
    return yaml_dict


def read_activation_yaml():
    return safe_read_yaml('/code/config/activation/gcp_services.yaml', "ACTIVATION_CONFIG")


def read_autodiscovery_config_yaml():
    return safe_read_yaml('/code/config/activation/autodiscovery-config.yaml', "AUTODISCOVERY_RESOURCES_YAML")


def read_filter_out_list_yaml() -> list:
    loaded_yaml = safe_read_yaml("/code/config/activation/metrics-filter-out.yaml",
                                 "EXCLUDED_METRICS_AND_DIMENSIONS") or {}
    excluded_metrics = loaded_yaml.get("filter_out") or []

    for metric in excluded_metrics:
        metric["dimensions"] = set(metric.get("dimensions") or [])

    return excluded_metrics


def read_autodiscovery_block_list_yaml():
    return safe_read_yaml('/code/config/activation/autodiscovery-block-list.yaml', "AUTODISCOVERY_BLOCK_LIST_YAML")


def read_autodiscovery_resources_mapping():
    return safe_read_yaml('./lib/autodiscovery/config/autodiscovery-mapping.yaml', "AUTODISCOVERY_RESOURCES_MAPPING")


def get_service_activation_dict(services, monitoring_configurations, extension_active_version):
    gcp_monitor_uuid = config.read_gcp_monitor_uuid()

    def process_item(item):
        item_value = item.get("value")
        if not item_value:
            return []

        uuids = item_value.get("gcp").get("gcpMonitorID")
        enabled = item_value.get("enabled")
        version = item_value.get('version')

        if enabled and (gcp_monitor_uuid in uuids or uuids == "") and version == extension_active_version:
            value = item_value.copy()
            gcp = value.pop('gcp', {})
            value.update(gcp)
            return [dict(value, service=service) for service in services]
        return []

    processed_items = chain.from_iterable(map(process_item, monitoring_configurations))

    return processed_items


def create_default_monitoring_config(extension_name, version) -> List[Dict]:
    monitoring_configuration = {
        "scope": "ag_group-default",
        "value": {
            "enabled": True,
            "description": f"default_{extension_name}",
            "version": f"{version}",
            "featureSets": [
                "default_metrics"
            ],
            "vars": {
                "filter_conditions": "null"
            },
            "gcp": {
                "autodiscovery": False,
                "gcpMonitorID": f"{config.read_gcp_monitor_uuid()}"
            }
        }
    }
    return [monitoring_configuration]


def get_activation_config_per_service(activation_yaml):
    return {service_activation.get('service'): service_activation for service_activation in
            activation_yaml['services']} if activation_yaml and activation_yaml['services'] else {}


def load_activated_feature_sets(logging_context: LoggingContext, activation_yaml) -> List[str]:
    services_allow_list = []
    for service in activation_yaml.get("services", []):
        feature_sets = service.get("featureSets", [])
        for feature_set in feature_sets:
            services_allow_list.append(f"{service.get('service')}/{feature_set}")
        if not feature_sets:
            logging_context.error(f"No feature set in given {service} service.")

    return services_allow_list


def get_autodiscovery_flag_per_service(activation_dict) -> Dict[str, bool]:
    enabled_autodiscovery = {}
    for service in activation_dict.get("services", []):
        service_name = service.get("service", "")
        autodiscovery_enabled_flag = service.get("autodiscovery", False)
        if isinstance(autodiscovery_enabled_flag, bool) and autodiscovery_enabled_flag:
            enabled_autodiscovery[service_name] = True
        elif service_name in enabled_autodiscovery and enabled_autodiscovery[service_name]:
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


# For test_integration_metric.py
def load_supported_services() -> List[GCPService]:
    context = LoggingContext(None)
    activation_yaml = read_activation_yaml()
    activation_config_per_service = get_activation_config_per_service(activation_yaml)
    feature_sets_from_activation_config = load_activated_feature_sets(context, activation_yaml)

    working_directory = os.path.dirname(os.path.realpath(__file__))
    config_directory = os.path.join(working_directory, "config")
    config_files = [
        file for file
        in listdir(config_directory)
        if isfile(os.path.join(config_directory, file)) and is_yaml_file(file)
    ]

    services = []
    for file in config_files:
        config_file_path = os.path.join(config_directory, file)
        try:
            with open(config_file_path, encoding="utf-8") as config_file:
                config_yaml = yaml.safe_load(config_file)
                technology_name = extract_technology_name(config_yaml)

                for service_yaml in config_yaml.get("gcp", {}):
                    service_name = service_yaml.get("service", "None")
                    feature_set = service_yaml.get("featureSet", "default_metrics")
                    # If allow_list of services exists and current service is not present in it, skip
                    # If allow_list is empty - no services explicitly selected - load all available
                    allow_list_exists = feature_sets_from_activation_config.__len__() > 0
                    if f'{service_name}/{feature_set}' in feature_sets_from_activation_config or not allow_list_exists:
                        activation = activation_config_per_service.get(service_name, {})
                        services.append(GCPService(tech_name=technology_name, **service_yaml, activation=activation))

        except Exception as error:
            context.log(f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
            continue
    feature_sets = [f"{service.name}/{service.feature_set}" for service in services]
    if feature_sets:
        context.log("Selected feature sets: " + ", ".join(feature_sets))
    else:
        context.log("Empty feature sets. GCP services not monitored.")
    return services
