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

from typing import Any, Callable, Dict, Iterable, List, Text

import mmh3

from lib.metrics import GCPService


ExtractPropertyFunc = Callable[[Dict[Text, Any]], Text]
LabelToApiRspMapping = Dict[Text, ExtractPropertyFunc]


def _create_mmh3_hash(components: Iterable[Text]) -> Text:
    """Generate MM3 hash out of arguments."""
    return str(mmh3.hash(  # pylint: disable=I1101
        ":".join(str(x) for x in components)
    ))


def get_func_create_entity_id(
        mapping: LabelToApiRspMapping
) -> Callable[[Dict[Text, Any], GCPService], Text]:
    """Create function responsible for entity id creation."""
    label_to_api_response_mapping = mapping

    def _create_entity_id(rsp: Dict[Text, Any], svc_def: GCPService) -> Text:
        cd_id_components: List[Text] = [svc_def.name]

        for quasi_label in svc_def.dimensions:
            lbl = quasi_label.key_for_get_func_create_entity_id
            component = ""

            if lbl not in label_to_api_response_mapping:
                continue

            component = label_to_api_response_mapping[lbl](rsp)
            if not component:
                continue

            cd_id_components.append(component)

        return _create_mmh3_hash(cd_id_components)

    return _create_entity_id
