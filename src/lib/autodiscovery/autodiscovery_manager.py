from typing import Any, Dict, List, NamedTuple, Optional

import yaml

from lib.autodiscovery.autodiscovery import AutodiscoveryResourceLinking, enrich_services_with_autodiscovery_metrics
from lib.context import LoggingContext
from lib.metrics import AutodiscoveryGCPService, GCPService

GcpServiceStub = NamedTuple(
    "GcpServiceStub", [("extension_name", str), ("service_name", str), ("feature_set", str)]
)

AutodiscoveryResource = NamedTuple(
    "GcpServiceStub", [("extension_name", str), ("service_name", str), ("feature_set", str)]
)



class AutodiscoveryManager:
    autodiscovery_config: Dict[str, Any]
    autodiscovery_resource_mapping: Dict[str, Any]
    last_autodiscovered_metric_list_names: Dict[str, Any]
    logging_context = LoggingContext("AUTODISCOVERY_MANAGER")
    autodiscovery_enabled: bool

    @staticmethod
    def generate_resource_mapping(mapping_yaml: Dict[str, Any]) -> Dict[str, Any]:
        resource_mapping = {}
        for extension in mapping_yaml["gcp_extension_mapping"]:
            for service in extension["services"]:
                for monitored_resource in service.get("monitored_resources", []):
                    resource_key = monitored_resource.get("value")
                    if resource_key is not None:
                        resource_mapping.setdefault(resource_key, []).append(
                            (
                                extension["extension_name"],
                                service["service_name"],
                                service["feature_set"],
                            )
                        )
        return {key: list(set(value)) for key, value in resource_mapping.items()}

    async def check_resources_to_autodiscovery(
        self, services: List[GCPService]
    ) -> Dict[str, AutodiscoveryResourceLinking]:
        prepared_resources = {}

        searched_resources = self.autodiscovery_config["searched_resources"]

        enabled_services_identifiers = {}
        disabled_services_identifiers = {}

        for service in services:
            # com.dynatrace.extension.<%=extensionName%>
            extension_name = service.extension_name.split(".")[-1]
            identifier = (extension_name, service.name, service.feature_set)
            if service.is_enabled:
                enabled_services_identifiers[identifier] = service
            else:
                disabled_services_identifiers[identifier] = service

        for resource in searched_resources:
            if resource in self.autodiscovery_resource_mapping:
                flag = False
                possible_linking = []
                disabled_linking = []
                for possible_identifier in self.autodiscovery_resource_mapping[resource]:
                    if possible_identifier in enabled_services_identifiers:
                        flag = True
                        possible_linking.append(enabled_services_identifiers[possible_identifier])
                    if possible_identifier in disabled_services_identifiers:
                        disabled_linking.append(disabled_services_identifiers[possible_identifier])
                if flag:
                    prepared_resources[resource] = AutodiscoveryResourceLinking(
                        possible_service_linking=possible_linking,
                        disabled_services_for_resource=disabled_linking,
                    )

                else:
                    self.logging_context.log(
                        f"Can't add resource {resource}. Make shure extension {self.autodiscovery_resource_mapping[resource][0]} is enabled."
                    )

            else:
                prepared_resources[resource] = None

        return prepared_resources

    def __init__(self):
        self.last_autodiscovered_metric_list_names = {}
        self.autodiscovery_enabled = True

        try:
            with open("autodiscovery-config.yaml", "r") as file_config:
                self.autodiscovery_config = yaml.safe_load(file_config)["autodicovery_config"]
            with open("autodiscovery-mapping.yaml", "r") as file_mapping:
                self.autodiscovery_resource_mapping = self.generate_resource_mapping(
                    yaml.safe_load(file_mapping)
                )
        except Exception as e:
            self.logging_context.log(f"Error during init autodiscovery config; {e}")
            self.autodiscovery_enabled = False

    async def get_autodiscovery_service(
        self, services: List[GCPService]
    ) -> Optional[AutodiscoveryGCPService]:
        resources_to_discovery = await self.check_resources_to_autodiscovery(services)

        if resources_to_discovery:
            autodiscovery_service = AutodiscoveryGCPService()
            autodiscovery_result = await enrich_services_with_autodiscovery_metrics(
                services,
                self.last_autodiscovered_metric_list_names,
                resources_to_discovery,
            )
            self.last_autodiscovered_metric_list_names = autodiscovery_result.discovered_metric_list
            if any(autodiscovery_result.autodiscovered_resources_to_metrics):
                autodiscovery_service.set_metrics(
                    autodiscovery_result.autodiscovered_resources_to_metrics, resources_to_discovery
                )
                return autodiscovery_service

        self.logging_context.log(
            "No resources to discover, add proper in autodisovery-config.yaml or make shure you enabled proper extensions"
        )
        return None
