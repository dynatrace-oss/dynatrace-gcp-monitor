import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from lib.autodiscovery.autodiscovery_manager import AutodiscoveryManager
from lib.configuration import config
from lib.context import LoggingContext
from lib.metrics import AutodiscoveryGCPService, GCPService


logging_context = LoggingContext("AUTODISCOVERY_TASK")


class AutodiscoveryTaskExecutor:
    """
    The AutodiscoveryTaskExecutor class manages autodiscovery-related tasks and caching of autodiscovered services.

    This class coordinates the execution of autodiscovery tasks, caching of autodiscovered services, and
    refreshing of autodiscovery tasks based on specified criteria.
    """

    autodiscovery_task: Optional[asyncio.Task]
    autodiscovered_cached_service: Optional[AutodiscoveryGCPService]
    autodiscovered_extension_versions_hash: int
    time_since_last_autodiscovery: datetime
    query_interval: timedelta
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
        await autodiscovery_task.get_task_result()
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

        autodiscovery_query_interval = config.get_autodiscovery_querry_interval()
        if autodiscovery_query_interval >= 60:
            self.query_interval = timedelta(minutes=autodiscovery_query_interval)
        else:
            logging_context.log(
                "Query interval for autodiscovery cannot be smaller than 60 minutes. Run with default 60 minutes interval"
            )
            self.query_interval = timedelta(minutes=60)

        self.autodiscovery_task = asyncio.create_task(
            self.autodiscovery_manager.get_autodiscovery_service(services)
        )
        self.time_since_last_autodiscovery = datetime.now()

    async def get_task_result(self):
        if self.autodiscovery_task is not None:
            autodiscovery_service_result = await self.autodiscovery_task
            if autodiscovery_service_result:
                self.autodiscovered_cached_service = autodiscovery_service_result

    async def _refresh_autodiscovery_task(
        self, services, new_extension_versions_hash, force_refresh=False
    ):
        if not force_refresh and self.autodiscovery_task and not self.autodiscovery_task.done():
            return

        await self.get_task_result()

        self.autodiscovery_task = asyncio.create_task(
            self.autodiscovery_manager.get_autodiscovery_service(services)
        )

        self.autodiscovered_extension_versions_hash = new_extension_versions_hash
        self.time_since_last_autodiscovery = datetime.now()

    async def _handle_autodiscovery_task_result(self):
        if self.autodiscovery_task:
            autodiscovery_service_result = await self.autodiscovery_task
            if autodiscovery_service_result:
                self.autodiscovered_cached_service = autodiscovery_service_result
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
        else:
            logging_context.log("Autodiscovery couldn't find any metrics for the given resources.")
        return services
