import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession

from lib.autodiscovery.autodiscovery_config import get_resources_mapping
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
            self.resource_to_disovery = read_autodiscovery_config_yaml()["autodicovery_config"][
                "searched_resources"
            ]
            self.resources_to_extensions_mapping = get_resources_mapping()
            self.autodiscovery_metric_block_list = read_autodiscovery_block_list_yaml()[
                "block_list"
            ]

        except Exception as e:
            self.logging_context.log(
                f"Error during init autodiscovery config. Autodiscovery is disabled; {type(e).__name__} : {e}"
            )
            self.autodiscovery_enabled = False

    async def _check_resources_to_discover(
        self, services: List[GCPService]
    ) -> Dict[str, AutodiscoveryResourceLinking]:
        """
        Check resources for autodiscovery compatibility.

        This function examines a list of GCP services and their configurations to
        determine if any autodiscovery resources shoud be linked with existing services.
        """
        prepared_resources = {}

        enabled_services_identifiers = {}
        disabled_services_identifiers = {}

        # Iterate through all existing and enabled services in the extensions of the current configuration
        for service in services:
            extension_name = service.extension_name.split(".")[-1]
            identifier = ServiceStub(extension_name, service.name, service.feature_set)
            if service.is_enabled:
                enabled_services_identifiers[identifier] = service
            else:
                disabled_services_identifiers[identifier] = service

        # Try to match every resoruce to autodiscovery with enabled services in extensions
        for resource in self.resource_to_disovery:
            # Check if the resource already exists in one of the extensions
            if resource in self.resources_to_extensions_mapping:
                possible_linking = []
                disabled_linking = []

                # Check which required services are enabled and which are disabled
                for required_service in self.resources_to_extensions_mapping[resource]:
                    if required_service in enabled_services_identifiers:
                        possible_linking.append(enabled_services_identifiers[required_service])
                    if required_service in disabled_services_identifiers:
                        disabled_linking.append(disabled_services_identifiers[required_service])

                # Check if there is at least one enabled service in extension that match with the same resources,
                if possible_linking:
                    prepared_resources[resource] = AutodiscoveryResourceLinking(
                        possible_service_linking=possible_linking,
                        disabled_services_for_resource=disabled_linking,
                    )
                else:
                    self.logging_context.error(
                        f"Can't add resource {resource}. Make sure if extension {self.resources_to_extensions_mapping[resource][0].extension_name} with proper services is enabled."
                    )

            # Resource is unknown (custom)
            else:
                prepared_resources[resource] = None

        return prepared_resources

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
                f"Unable to prepare new metrics for autodiscovery; {type(e).__name__} : {e} "
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
            for metric in metric_list:
                logging_context.log(
                    f"In resource: [{resource_name}] found metric: [{metric.google_metric}]"
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
