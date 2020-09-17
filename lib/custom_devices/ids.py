""" This module contains logic responsible for creation of custom device ids and group ids. """

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


def get_func_create_custom_device_id(
        mapping: LabelToApiRspMapping
) -> Callable[[Dict[Text, Any], GCPService], Text]:
    """Create function responsible for custom device id creation."""
    label_to_api_response_mapping = mapping

    def _create_custom_device_id(rsp: Dict[Text, Any], svc_def: GCPService) -> Text:
        cd_id_components: List[Text] = [svc_def.name]

        for quasi_label in svc_def.dimensions:
            lbl = quasi_label.source
            component = ""

            if lbl not in label_to_api_response_mapping:
                continue

            component = label_to_api_response_mapping[lbl](rsp)
            if not component:
                continue

            cd_id_components.append(component)

        return _create_mmh3_hash(cd_id_components)

    return _create_custom_device_id
