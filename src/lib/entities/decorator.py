""" This module contains logic responsible for decorating functions as entity extractors. """

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

from functools import wraps
from typing import Dict, Iterable, Text

from lib.context import MetricsContext
from lib.entities.model import Entity, ExtractEntitesFunc
from lib.metrics import GCPService

entities_extractors: Dict[Text, ExtractEntitesFunc] = {}


def entity_extractor(service_type: Text):
    """
    Denotes a function responsible for extracting additional info about GCP service.

    Function wrapped by this decorator should be placed under "lib.entities.extractors"
    package, or otherwise it will not be automatically called.
    The decorator extends given function by uploading retrieved data to dynatrace server.
    """

    def register_extractor(fun: ExtractEntitesFunc) -> ExtractEntitesFunc:
        @wraps(fun)
        async def get_and_upload(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
            try:
                entities = await fun(ctx, project_id, svc_def)
            except Exception as e:
                ctx.log(f"Failed to finish entity extractor task, reason is {type(e).__name__} {e}")
                return []

            return entities

        entities_extractors[service_type] = get_and_upload
        return get_and_upload

    return register_extractor
