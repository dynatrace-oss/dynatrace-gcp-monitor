from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import yaml

from lib.autodiscovery.autodiscovery import (
    AutodiscoveryResourceLinking,
    enrich_services_with_autodiscovery_metrics,
)
from lib.context import LoggingContext
from lib.metrics import AutodiscoveryGCPService, GCPService
from lib.utilities import read_autodiscovery_block_list_yaml, read_autodiscovery_config_yaml
from pathlib import Path


@dataclass(frozen=True)
class ServiceStub:
    extension_name: str
    service_name: str
    feature_set_name: str


class AutodiscoveryManager:
    autodiscovery_config: Dict[str, Any]
    autodiscovery_resource_mapping: Dict[str, List[ServiceStub]]
    autodiscovery_metric_block_list: List[str]
    last_autodiscovered_metric_list_names: Dict[str, Any]
    logging_context = LoggingContext("AUTODISCOVERY_MANAGER")
    autodiscovery_enabled: bool

    def __init__(self):
        self.autodiscovery_config = {}
        self.autodiscovery_resource_mapping = {}
        self.autodiscovery_metric_block_list = []
        self.last_autodiscovered_metric_list_names = {}
        self.autodiscovery_enabled = True

        self._load_config()

    def _load_config(self):
        try:
            self.autodiscovery_config = read_autodiscovery_config_yaml()["autodicovery_config"]

            with open("./lib/autodiscovery/config/autodiscovery-mapping.yaml", "r") as file_mapping:
                self.autodiscovery_resource_mapping = self.generate_resource_mapping(
                    yaml.safe_load(file_mapping)
                )

            self.autodiscovery_metric_block_list = read_autodiscovery_block_list_yaml()
        except Exception as e:
            self.logging_context.log(
                f"Error during init autodiscovery config; {type(e).__name__} : {e}"
            )
            self.autodiscovery_enabled = False

    @staticmethod
    def generate_resource_mapping(mapping_yaml: Dict[str, Any]) -> Dict[str, List[ServiceStub]]:
        resource_mapping = {}
        for extension in mapping_yaml["gcp_extension_mapping"]:
            for service in extension["services"]:
                for monitored_resource in service.get("monitored_resources", []):
                    resource_name = monitored_resource.get("value")
                    if resource_name is not None:
                        resource_mapping.setdefault(resource_name, []).append(
                            ServiceStub(
                                extension_name=extension["extension_name"],
                                service_name=service["service_name"],
                                feature_set_name=service["feature_set"],
                            )
                        )
        return {
            resource_name: list(set(service_stub))
            for resource_name, service_stub in resource_mapping.items()
        }

    async def check_resources_to_autodiscovery(
        self, services: List[GCPService]
    ) -> Dict[str, AutodiscoveryResourceLinking]:
        prepared_resources = {}

        enabled_services_identifiers = {}
        disabled_services_identifiers = {}

        for service in services:
            # com.dynatrace.extension.<%=extensionName%>
            extension_name = service.extension_name.split(".")[-1]
            identifier = ServiceStub(extension_name, service.name, service.feature_set)
            if service.is_enabled:
                enabled_services_identifiers[identifier] = service
            else:
                disabled_services_identifiers[identifier] = service

        for resource in self.autodiscovery_config["searched_resources"]:
            if resource in self.autodiscovery_resource_mapping:
                possible_linking = []
                disabled_linking = []

                for required_service in self.autodiscovery_resource_mapping[resource]:
                    if required_service in enabled_services_identifiers:
                        possible_linking.append(enabled_services_identifiers[required_service])
                    if required_service in disabled_services_identifiers:
                        disabled_linking.append(disabled_services_identifiers[required_service])

                if possible_linking:
                    prepared_resources[resource] = AutodiscoveryResourceLinking(
                        possible_service_linking=possible_linking,
                        disabled_services_for_resource=disabled_linking,
                    )

                else:
                    self.logging_context.log(
                        f"Can't add resource {resource}. Make sure if extension {self.autodiscovery_resource_mapping[resource][0].extension_name} with proper services is enabled."
                    )

            else:
                prepared_resources[resource] = None

        return prepared_resources

    async def get_autodiscovery_service(
        self, services: List[GCPService]
    ) -> Optional[AutodiscoveryGCPService]:
        if self.autodiscovery_enabled:
            resources_to_discovery = await self.check_resources_to_autodiscovery(services)

            if resources_to_discovery:
                autodiscovery_service = AutodiscoveryGCPService()
                autodiscovery_result = await enrich_services_with_autodiscovery_metrics(
                    services,
                    self.last_autodiscovered_metric_list_names,
                    resources_to_discovery,
                    self.autodiscovery_metric_block_list,
                )
                self.last_autodiscovered_metric_list_names = (
                    autodiscovery_result.discovered_metric_list
                )
                if any(autodiscovery_result.autodiscovered_resources_to_metrics):
                    autodiscovery_service.set_metrics(
                        autodiscovery_result.autodiscovered_resources_to_metrics,
                        resources_to_discovery,
                        autodiscovery_result.resource_dimensions,
                    )
                    return autodiscovery_service

            self.logging_context.log(
                "No resources find to autodiscovery. Please ensure that you have either added them in the autodiscoveryResourcesYaml file or verified that the necessary extensions are enabled."
            )
        return None
