import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from lib.autodiscovery.autodiscovery import AutodiscoveryContext
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

    autodiscovery_task: asyncio.Task
    autodiscovered_cached_service: Optional[AutodiscoveryGCPService]
    autodiscovered_extension_versions_hash: int
    time_since_last_autodiscovery: datetime
    query_interval: timedelta
    autodiscovery_manager: AutodiscoveryContext
    lock: asyncio.Lock
    notify_event: asyncio.Event
    observers: List

    @staticmethod
    async def create(
        services: List[GCPService],
        autodiscovery_manager: AutodiscoveryContext,
        current_extension_versions: Dict[str, str],
    ):
        observer_list = []
        init_task_finished = asyncio.Event()

        observer_list.append(lambda: init_task_finished.set())

        autodiscovery_executor = AutodiscoveryTaskExecutor(
            services, autodiscovery_manager, current_extension_versions, observer_list
        )

        await init_task_finished.wait()

        return autodiscovery_executor

    def __init__(
        self,
        services: List[GCPService],
        autodiscovery_manager: AutodiscoveryContext,
        current_extension_versions: Dict[str, str],
        init_observer_list: List,
    ):
        self.autodiscovery_manager = autodiscovery_manager
        self.autodiscovered_cached_service = None
        self.autodiscovered_extension_versions_hash = hash(
            tuple(sorted(current_extension_versions.items()))
        )

        autodiscovery_query_interval = config.get_autodiscovery_querry_interval()
        self.query_interval = timedelta(minutes=max(autodiscovery_query_interval, 60))

        self.cached_services = services[:]
        self.autodiscovery_task = asyncio.create_task(self._init_autodiscovery_task())
        self.time_since_last_autodiscovery = datetime.now()
        self.lock = asyncio.Lock()
        self.observers = init_observer_list

    def _notify_observers(self):
        while self.observers:
            observer_function = self.observers.pop()
            observer_function()

    async def add_observer(self, function):
        async with self.lock:
            self.observers.append(function)

    async def _update_extensions(
        self, new_extension_versions: Dict[str, str], services: List[GCPService]
    ):
        new_extension_versions_hash = hash(tuple(sorted(new_extension_versions.items())))
        if new_extension_versions_hash != self.autodiscovered_extension_versions_hash:
            async with self.lock:
                self.notify_event.set()
                self.autodiscovered_extension_versions_hash = new_extension_versions_hash
                self.cached_services = services[:]

    async def _init_autodiscovery_task(self):
        while True:
            try:
                result = await self.autodiscovery_manager.get_autodiscovery_service(
                    self.cached_services
                )
                async with self.lock:
                    if result:
                        self.autodiscovered_cached_service = result
                    self._notify_observers()
                await asyncio.wait_for(
                    self.notify_event.wait(), timeout=self.query_interval.total_seconds()
                )
                async with self.lock:
                    self.notify_event.clear()

                logging_context.log(
                    "New extensions versions detected. Proceeding next autodiscovery task"
                )
            except asyncio.TimeoutError:
                logging_context.log("Query time elapsed. Preparing for the next autodiscovery.")
            except Exception as e:
                logging_context.error(f"Error ocured: {type(e).__name__} : {e} ")
                self._notify_observers()

    async def process_autodiscovery_result(
        self, services: List[GCPService], new_extension_versions: Dict[str, str]
    ) -> List[GCPService]:
        await self._update_extensions(new_extension_versions, services)

        async with self.lock:
            if self.autodiscovered_cached_service:
                services.append(self.autodiscovered_cached_service)
            else:
                logging_context.error(
                    "Autodiscovery couldn't find any metrics for the given resources."
                )
            return services
