""" This module contains data model definition dealing with custom devices. """

from dataclasses import dataclass
from json import dumps
from typing import Callable, FrozenSet, Iterable, NamedTuple, Text

from lib.context import Context
from lib.metrics import GCPService


CdProperty = NamedTuple(
    "CdProperty", [
        ("key", Text),
        ("value", Text)
    ]
)


@dataclass(frozen=True)
class CustomDevice:  # pylint: disable=R0902
    """ Represents information about single custom device."""
    custom_device_id: Text
    display_name: Text
    group: Text
    ip_addresses: FrozenSet[str]
    listen_ports: FrozenSet[str]
    favicon_url: Text
    dtype: Text
    properties: Iterable[CdProperty]
    tags: FrozenSet[str]
    dns_names: FrozenSet[str]

    def to_json_payload(self) -> Text:
        """ Get json representation of this class instance. """
        return dumps({
            "customDeviceId": self.custom_device_id,
            "displayName": self.display_name,
            "group": self.group,
            "ipAddresses": [str(x) for x in self.ip_addresses],
            "listenPorts": [int(x) for x in self.listen_ports],
            "faviconUrl": self.favicon_url,
            "type": self.dtype,
            "properties": {props.key: props.value for props in self.properties},
            "tags": [str(x) for x in self.tags],
            "dnsNames": [str(x) for x in self.dns_names]
        })


ExtractCustomDevicesFunc = Callable[[Context, GCPService], Iterable[CustomDevice]]
