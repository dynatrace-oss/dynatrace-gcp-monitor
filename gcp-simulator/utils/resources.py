from dataclasses import field
from typing import List, Dict, Optional
import random
import asyncio
from dataclasses import dataclass, field


class Latency:
    def __init__(self, latency_ms: int, jitter_ms: int):
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms

    async def delay(self):
        await asyncio.sleep(
            self.latency_ms / 1000.0
            + self.jitter_ms / 2000.0 * random.gammavariate(1, 0.5)
        )


@dataclass
class Metadata:
    type: str = ""
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Value:
    int64Value: str = ""


@dataclass
class Interval:
    startTime: str = ""
    endTime: str = ""


@dataclass
class Point:
    interval: Interval = field(default_factory=Interval)
    value: Value = field(default_factory=Value)


@dataclass
class Metric:
    metric: Metadata = field(default_factory=Metadata)
    resource: Metadata = field(default_factory=Metadata)
    points: List[Point] = field(default_factory=list)
    metricKind: str = "DELTA"
    valueType: str = "INT64"


@dataclass
class TS:
    timeSeries: List[Metric] = field(default_factory=list)
    unit: str = "1"
    nextPageToken: str = None


class Pagination:
    def __init__(self, page_size: int = 50, offset: int = 0):
        self.offset: int = offset
        self.page_size = page_size

    def update(self, pageSize: int = 0, pageToken: str = "next-page-token-0"):
        return Pagination(
            pageSize or self.page_size, int(pageToken.replace("next-page-token-", ""))
        )

    def filter(self, data: list):
        return data[self.offset : self.offset + self.page_size]

    def apply(self, data, data_key: str):
        response = data if type(data) == dict else vars(data)
        token = self.next_token(response[data_key])
        response[data_key] = self.filter(response[data_key])
        if token:
            response["nextPageToken"] = token
        return data

    def next_token(self, data: list):
        if len(data) > self.offset + self.page_size:
            return "next-page-token-" + str(self.offset + self.page_size)
        else:
            return None
