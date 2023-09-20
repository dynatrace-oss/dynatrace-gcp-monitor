from typing import Dict, List

from lib import utilities
from lib.autodiscovery.models import ServiceStub


def get_resources_mapping() -> Dict[str, List[ServiceStub]]:
    mapping_yaml = utilities.read_autodiscovery_resources_mapping()

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
