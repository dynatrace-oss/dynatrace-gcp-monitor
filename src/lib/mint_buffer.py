import asyncio
import collections
import time
from asyncio import Task
from typing import List, Callable, Any, Deque

from lib.context import MetricsContext
from lib.metrics import IngestLine


class MintBuffer:
    def __init__(self, callback: Callable[[List[IngestLine]], Any], context: MetricsContext, batch_size: int=2000):
        self.data: Deque[IngestLine] = collections.deque()
        self.batch_size: int = batch_size
        self.push_tasks: List[Task] = []
        self.push_callback: Callable[[List[IngestLine]], Any] = callback
        self.lines_per_minute_limit = 1000000
        self.context = context

    async def push(self, lines: List[IngestLine]):
        self.data.extend(lines)
        await self.flush(False)

    async def execute_with_limits(self, my_time: float, batch: List[IngestLine]):
        async with self.context._sem:
            await self.push_callback(batch)

        # try:
        #     if my_time > time.time():
        #         await asyncio.sleep(my_time - time.time())
        #
        #     await self.sem.acquire()
        #     self.push_callback(batch)
        # finally:
        #     self.sem.release()


    async def flush(self, force: bool = False):
        while len(self.data) > 0 and (force or len(self.data) >= self.batch_size):
            batch = [self.data.popleft() for _i in range(min(self.batch_size, len(self.data)))]
            my_time = self.context._next_time
            self.context._next_time = len(batch) / self.lines_per_minute_limit / 60.0 + max(self.context._next_time, time.time())

            async with self.context._sem:
                if my_time > time.time():
                    await asyncio.sleep(my_time - time.time())

                # if len(self.push_tasks) == self.concurent_limit:
                #     await asyncio.wait_for(self.push_tasks[0])
                #     self.push_tasks.popleft()

                self.push_tasks.append(asyncio.create_task(self.execute_with_limits(my_time, batch)))

        self.push_tasks[:] = [x for x in self.push_tasks if not x.done()]

    async def wait_for_all(self):
        await asyncio.gather(*self.push_tasks, return_exceptions=True)
