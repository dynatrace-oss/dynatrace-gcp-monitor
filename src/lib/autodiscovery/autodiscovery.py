import time
from dataclasses import asdict
import traceback
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession

from lib.autodiscovery.autodiscovery_config import get_resources_mapping, get_services_to_resources
from lib.autodiscovery.autodiscovery_utils import (
    get_existing_metrics,
    get_metric_descriptors,
    logging_context,
    send_metric_metadata,
)
from lib.autodiscovery.models import AutodiscoveryResourceLinking, AutodiscoveryResult, ServiceStub
from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.context import LoggingContext
from lib.credentials import create_token
from lib.metrics import AutodiscoveryGCPService, GCPService, Metric
from lib.utilities import (
    read_autodiscovery_block_list_yaml,
    read_autodiscovery_config_yaml,
    read_activation_json
)
from main import get_metric_context


class AutodiscoveryContext:
    resource_to_disovery: Dict[str, Any]
    resources_to_extensions_mapping: Dict[str, List[ServiceStub]]
    autodiscovery_metric_block_list: List[str]
    last_autodiscovered_metric_list_names: Dict[str, Any]
    logging_context = LoggingContext("AUTODISCOVERY")
    autodiscovery_enabled: bool

    def __init__(self):
        self.resource_to_disovery = {}
        self.resources_to_extensions_mapping = {}
        self.autodiscovery_metric_block_list = []
        self.last_autodiscovered_metric_list_names = {}
        self.autodiscovery_enabled = True

        self._load_yamls()

    def _load_yamls(self):
        try:
            resource_to_disovery = (
                read_autodiscovery_config_yaml()
                .get("autodicovery_config", {})
                .get("searched_resources", {})
            )
            self.resource_to_disovery = (
                resource_to_disovery if resource_to_disovery is not None else {}
            )

            self.resources_to_extensions_mapping = get_resources_mapping()
            self.services_to_resources_mapping = get_services_to_resources()
            activation_json = read_activation_json().get("services", [])
            autodiscovery_metric_block_list = []
            for item in activation_json:
                block_list = item.get('blockList', [])
                autodiscovery_metric_block_list.extend(block_list)

            self.autodiscovery_metric_block_list = (
                autodiscovery_metric_block_list
                if autodiscovery_metric_block_list is not None
                else []
            )

        except Exception as e:
            self.logging_context.log(
                f"Error during init autodiscovery config. Autodiscovery is now disabled; {type(e).__name__} : {e}\n  {traceback.format_exc()}"
            )
            self.autodiscovery_enabled = False

    async def _get_resources_from_config(self) -> Dict[str, AutodiscoveryResourceLinking]:
        """
        Check resources for autodiscovery from autodiscovery-values.yaml
        """

        prepared_resources = {}

        for resource in self.resource_to_disovery:
            if resource in self.resources_to_extensions_mapping:
                log_message_list = ""
                reqiured_services = self.resources_to_extensions_mapping[resource]

                for service in reqiured_services:
                    log_message_list += f"\nIn extension: {service.extension_name} Service: {service.service_name} Feature Set: {service.feature_set_name}"

                self.logging_context.error(
                    f"Resource {resource} can't be added in searched_resources autodiscovery config. You can add this resource to autodiscovery by enabling one of the following: {log_message_list}"
                )

            else:
                prepared_resources[resource] = None

        return prepared_resources

    async def _check_resources_to_discover(
        self, services: List[GCPService]
    ) -> Dict[str, AutodiscoveryResourceLinking]:
        resources: Dict[str, AutodiscoveryResourceLinking] = {}

        # Get resource to discover from enabled extensions
        for service in services:
            extension_name = service.extension_name.split(".")[-1]
            identifier = ServiceStub(extension_name, service.name, service.feature_set)
            if service.autodiscovery_enabled and identifier in self.services_to_resources_mapping:
                prepared_resources = self.services_to_resources_mapping[identifier]

                for resource in prepared_resources:
                    autodiscovery = resources.get(
                        resource,
                        AutodiscoveryResourceLinking(
                            possible_service_linking=[], disabled_services_for_resource=[]
                        ),
                    )

                    if service.is_enabled:
                        autodiscovery.possible_service_linking.append(service)
                    else:
                        autodiscovery.disabled_services_for_resource.append(service)

                    resources[resource] = autodiscovery
        
        # Filter if there are any resouce linking for all resources
        resources = {resource: linking for resource, linking in resources.items() if len(linking.possible_service_linking) > 0}

        # Get resources to discover from config
        config_resources = await self._get_resources_from_config()

        for resource_name, value in config_resources.items():
            if resource_name not in resources:
                resources[resource_name] = value
            else:
                self.logging_context.error("Attempted to add a resource that is already registered")

        return resources

    async def get_autodiscovery_service(
        self, services: List[GCPService]
    ) -> Optional[AutodiscoveryGCPService]:
        """
        Retrieve an AutodiscoveryGCPService if autodiscovery is enabled and resources are discovered.

        This function checks if autodiscovery is enabled and, if so, attempts to discover
        resources for monitoring. If resources are discovered, it returns AutodiscoveryGCPService
        containing the discovered metrics and resource dimensions.
        """
        if not self.autodiscovery_enabled:
            return None

        resources_to_discovery = await self._check_resources_to_discover(services)

        if not resources_to_discovery:
            self.logging_context.log(
                "Autodiscovery didn't find any resources to monitor. Ensure they're listed in autodiscoveryResourcesYaml."
            )
            return None

        try:
            async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
                token = await create_token(self.logging_context, gcp_session)
                if not token:
                    logging_context.error(
                        "Autodiscovery disabled. Unable to acquire authorization token."
                    )
                    return None

                autodiscovery_fetch_result = await self._run_autodiscovery(
                    gcp_session,
                    dt_session,
                    token,
                    resources_to_discovery,
                )

                if any(autodiscovery_fetch_result.autodiscovered_resources_to_metrics):
                    autodiscovery_service = AutodiscoveryGCPService()

                    autodiscovery_service.set_metrics(
                        autodiscovery_fetch_result.autodiscovered_resources_to_metrics,
                        resources_to_discovery,
                        autodiscovery_fetch_result.resource_dimensions,
                    )
                    return autodiscovery_service

        except Exception as e:
            self.logging_context.error(
                f"Unable to prepare new metrics for autodiscovery; {type(e).__name__} : {e} \n  {traceback.format_exc()}"
            )

        return None

    async def _run_autodiscovery(
        self,
        gcp_session: ClientSession,
        dt_session: ClientSession,
        token: str,
        autodiscovery_resources: Dict[str, AutodiscoveryResourceLinking],
    ) -> AutodiscoveryResult:
        """
        Discover and add metrics to a monitoring system using autodiscovery.

        This function orchestrates the autodiscovery process for metrics associated with Google Cloud Platform (GCP)
        services. It retrieves metric descriptors, filters and adds new metrics based on specified criteria, and
        sends metric metadata to a monitoring system.

        """
        start_time = time.time()
        logging_context.log("Adding metrics using autodiscovery")
        metric_context = await get_metric_context(gcp_session, dt_session, token, logging_context)

        discovered_metric_descriptors, resource_dimensions = await get_metric_descriptors(
            metric_context,
            gcp_session,
            token,
            autodiscovery_resources,
            self.autodiscovery_metric_block_list,
        )

        existing_resources_to_metrics = await get_existing_metrics(autodiscovery_resources)

        autodiscovery_resources_to_metrics = {}

        for descriptor, project_ids in discovered_metric_descriptors.items():
            monitored_resource = descriptor.monitored_resources_types[0]
            if descriptor.value not in existing_resources_to_metrics[monitored_resource]:
                autodiscovery_resources_to_metrics.setdefault(monitored_resource, []).append(
                    Metric(
                        **(asdict(descriptor)), autodiscovered_metric=True, project_ids=project_ids
                    )
                )

        for resource_name, metric_list in autodiscovery_resources_to_metrics.items():
            logging_context.log(
                f"Discovered {len(metric_list)} metrics for [{resource_name}] resource."
            )

        self.last_autodiscovered_metric_list_names = await send_metric_metadata(
            autodiscovery_resources_to_metrics,
            metric_context,
            self.last_autodiscovered_metric_list_names,
        )

        end_time = time.time()

        logging_context.log(f"Elapsed time in autodiscovery: {end_time-start_time} s")

        return AutodiscoveryResult(
            autodiscovered_resources_to_metrics=autodiscovery_resources_to_metrics,
            resource_dimensions=resource_dimensions,
        )
