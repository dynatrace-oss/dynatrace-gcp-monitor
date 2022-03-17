""" This module contains data model definition dealing with entites. """

#     Copyright 2020 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

from dataclasses import dataclass
from json import dumps
from typing import Callable, FrozenSet, Iterable, NamedTuple, Text, List

from lib.context import MetricsContext
from lib.metrics import GCPService


CdProperty = NamedTuple(
    "CdProperty", [
        ("key", Text),
        ("value", Text)
    ]
)


@dataclass(frozen=True)
class Entity:  # pylint: disable=R0902
    """ Represents information about single entity."""
    id: Text
    display_name: Text
    group: Text
    ip_addresses: List[str]
    listen_ports: List[str]
    favicon_url: Text
    dtype: Text
    properties: Iterable[CdProperty]
    tags: List[str]
    dns_names: List[str]


ExtractEntitiesFunc = Callable[[MetricsContext, str, GCPService], Iterable[Entity]]


@dataclass(frozen=True)
class EntitiesExtractorData:
    extractor: ExtractEntitiesFunc
    used_api: Text
