import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from lib.autodiscovery.autodiscovery import enrich_services_with_autodiscovery_metrics
from lib.metrics import GCPService

AUTODISCOVERY_QUERY_INTERVAL_SEC = 60


class AutodiscoveryManager:
    autodiscovery_task: asyncio.Task
    autodiscovered_metrics_cache: List[GCPService]
    autodiscovered_extension_versions_hash: int
    time_since_last_autodiscovery: datetime
    query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)

    @staticmethod
    async def initialize(services: List[GCPService], current_extension_versions: Dict[str, str]):
        autodiscovery_manager = AutodiscoveryManager(services, current_extension_versions)
        await autodiscovery_manager.autodiscovery_task
        return autodiscovery_manager

    def __init__(self, services: List[GCPService], current_extension_versions: Dict[str, str]):
        self.autodiscovered_metrics_cache = []
        self.autodiscovered_extension_versions_hash = hash(
            tuple(sorted(current_extension_versions.items()))
        )
        self.query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)
        self.autodiscovery_task = asyncio.create_task(
            enrich_services_with_autodiscovery_metrics(services)
        )
        self.time_since_last_autodiscovery = datetime.now()

    async def _try_refresh_autodiscovery_task(self, services, new_extension_versions_hash):
        print("Refreshing autodiscovery task as it is done!")
        self.autodiscovered_metrics_cache = await self.autodiscovery_task
        self.autodiscovery_task = asyncio.create_task(
            enrich_services_with_autodiscovery_metrics(services)
        )
        self.autodiscovered_extension_versions_hash = new_extension_versions_hash
        self.time_since_last_autodiscovery = datetime.now()

    async def force_autodiscovery_update(self, services, new_extension_versions_hash):
        if self.autodiscovery_task.done():
            await self._try_refresh_autodiscovery_task(services, new_extension_versions_hash)
        else:
            self.autodiscovered_metrics_cache = await self.autodiscovery_task

    async def get_cached_or_refreshed_metrics(
        self, services: List[GCPService], new_extension_versions: Dict[str, str]
    ):
        new_extension_versions_hash = hash(tuple(sorted(new_extension_versions.items())))
        time_now = datetime.now()
        delta = time_now - self.time_since_last_autodiscovery

        if (
            new_extension_versions_hash != self.autodiscovered_extension_versions_hash
            or delta > self.query_interval
            or self.autodiscovery_task.done()
        ):
            await self._try_refresh_autodiscovery_task(services, new_extension_versions_hash)

        return self.autodiscovered_metrics_cache
