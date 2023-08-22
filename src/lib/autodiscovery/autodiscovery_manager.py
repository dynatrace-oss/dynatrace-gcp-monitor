import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List

from lib.autodiscovery.autodiscovery import enrich_services_with_autodiscovery_metrics
from lib.configuration import config
from lib.metrics import GCPService

AUTODISCOVERY_QUERY_INTERVAL_SEC = config.get_autodiscovery_querry_interval() * 60


class AutodiscoveryManager:
    autodiscovery_task: asyncio.Task
    autodiscovered_metrics_cache: List[GCPService]
    autodiscovered_extension_versions_hash: int
    time_since_last_autodiscovery: datetime
    query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)
    last_autodiscovered_metric_list_names: Dict[str, Any]

    @staticmethod
    async def initialize(services: List[GCPService], current_extension_versions: Dict[str, str]):
        autodiscovery_manager = AutodiscoveryManager(services, current_extension_versions)
        await autodiscovery_manager._refresh_autodiscovery_task(
            services, current_extension_versions
        )
        return autodiscovery_manager

    def __init__(self, services: List[GCPService], current_extension_versions: Dict[str, str]):
        self.last_autodiscovered_metric_list_names = {}
        self.autodiscovered_metrics_cache = []
        self.autodiscovered_extension_versions_hash = hash(
            tuple(sorted(current_extension_versions.items()))
        )
        self.query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)
        self.autodiscovery_task = asyncio.create_task(
            enrich_services_with_autodiscovery_metrics(
                services, self.last_autodiscovered_metric_list_names
            )
        )
        self.time_since_last_autodiscovery = datetime.now()

    async def _refresh_autodiscovery_task(self, services, new_extension_versions_hash):
        if self.autodiscovery_task is not None:
            result = await self.autodiscovery_task
            self.autodiscovered_metrics_cache = result.enriched_services
            self.last_autodiscovered_metric_list_names = result.discovered_metric_list
        self.autodiscovery_task = asyncio.create_task(
            enrich_services_with_autodiscovery_metrics(
                services, self.last_autodiscovered_metric_list_names
            )
        )
        self.autodiscovered_extension_versions_hash = new_extension_versions_hash
        self.time_since_last_autodiscovery = datetime.now()

    async def _handle_autodiscovery_task_result(self):
        result = await self.autodiscovery_task
        self.autodiscovered_metrics_cache = result.enriched_services
        self.last_autodiscovered_metric_list_names = result.discovered_metric_list
        self.autodiscovery_task = None

    async def get_cached_or_refreshed_metrics(
        self, services: List[GCPService], new_extension_versions: Dict[str, str]
    ):
        new_extension_versions_hash = hash(tuple(sorted(new_extension_versions.items())))
        time_now = datetime.now()
        delta = time_now - self.time_since_last_autodiscovery

        if self.autodiscovery_task is not None and self.autodiscovery_task.done():
            await self._handle_autodiscovery_task_result()

        if (
            new_extension_versions_hash != self.autodiscovered_extension_versions_hash
            or delta > self.query_interval
        ):
            await self._refresh_autodiscovery_task(services, new_extension_versions_hash)

        return self.autodiscovered_metrics_cache
