import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from lib.autodiscovery.autodiscovery import enrich_services_with_autodiscovery_metrics
from lib.autodiscovery.autodiscovery_manager import AutodiscoveryManager
from lib.configuration import config
from lib.metrics import AutodiscoveryGCPService, GCPService

AUTODISCOVERY_QUERY_INTERVAL_SEC = config.get_autodiscovery_querry_interval() * 60


class AutodiscoveryTaskExecutor:
    autodiscovery_task: Optional[asyncio.Task]
    autodiscovered_cached_service: Optional[AutodiscoveryGCPService]
    autodiscovered_extension_versions_hash: int
    time_since_last_autodiscovery: datetime
    query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)
    autodiscovery_manager: AutodiscoveryManager

    @staticmethod
    async def init(
        services: List[GCPService],
        autodiscovery_manager: AutodiscoveryManager,
        current_extension_versions: Dict[str, str],
    ):
        autodiscovery_task = AutodiscoveryTaskExecutor(
            services, autodiscovery_manager, current_extension_versions
        )
        await autodiscovery_task._refresh_autodiscovery_task(services, current_extension_versions)
        return autodiscovery_task

    def __init__(
        self,
        services: List[GCPService],
        autodiscovery_manager: AutodiscoveryManager,
        current_extension_versions: Dict[str, str],
    ):
        self.autodiscovery_manager = autodiscovery_manager
        self.autodiscovered_cached_service = None
        self.autodiscovered_extension_versions_hash = hash(
            tuple(sorted(current_extension_versions.items()))
        )
        self.query_interval = timedelta(seconds=AUTODISCOVERY_QUERY_INTERVAL_SEC)
        self.autodiscovery_task = asyncio.create_task(
            self.autodiscovery_manager.get_autodiscovery_service(services)
        )
        self.time_since_last_autodiscovery = datetime.now()

    async def _refresh_autodiscovery_task(self, services, new_extension_versions_hash):
        if self.autodiscovery_task is not None:
            self.autodiscovered_cached_service = await self.autodiscovery_task
        self.autodiscovery_task = asyncio.create_task(
            self.autodiscovery_manager.get_autodiscovery_service(services)
        )
        self.autodiscovered_extension_versions_hash = new_extension_versions_hash
        self.time_since_last_autodiscovery = datetime.now()

    async def _handle_autodiscovery_task_result(self):
        if self.autodiscovery_task:
            self.autodiscovered_cached_service = await self.autodiscovery_task
            self.autodiscovery_task = None

    async def get_cached_or_refreshed_metrics(
        self, services: List[GCPService], new_extension_versions: Dict[str, str]
    ):
        new_extension_versions_hash = hash(tuple(sorted(new_extension_versions.items())))
        delta = datetime.now() - self.time_since_last_autodiscovery

        if self.autodiscovery_task is not None and self.autodiscovery_task.done():
            await self._handle_autodiscovery_task_result()

        if (
            new_extension_versions_hash != self.autodiscovered_extension_versions_hash
            or delta > self.query_interval
        ):
            await self._refresh_autodiscovery_task(services, new_extension_versions_hash)

        if self.autodiscovered_cached_service:
            services.append(self.autodiscovered_cached_service)    
        else :
            print("### AD - Service is None")
        return services
