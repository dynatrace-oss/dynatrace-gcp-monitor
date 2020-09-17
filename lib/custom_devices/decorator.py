""" This module contains logic responsible for decorating functions as custom device extractors. """

from functools import wraps
from typing import Any, Collection, Dict, Iterable, Text

import asyncio

from lib.context import Context
from lib.metrics import GCPService
from lib.custom_devices.model import CustomDevice, ExtractCustomDevicesFunc


custom_devices_extractors: Dict[Text, ExtractCustomDevicesFunc] = {}


def _upload_custom_devices(ctx: Context, entities: Iterable[CustomDevice]):
    """ Upload custom device information to dynatrace server. """
    return asyncio.gather(
        *[
            ctx.session.post(
                url=f"{ctx.dynatrace_url}/api/v2/entities/custom",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Api-Token {ctx.dynatrace_api_key}",
                    "Content-Type": "application/json"
                },
                data=entity.to_json_payload(),
                raise_for_status=True,
            ) for entity in entities
        ],
        return_exceptions=True
    )


def _verbose_cd_upload_results(upload_results: Collection[Any]) -> None:
    """Print out any failures that may have occurred for metadata upload."""
    all_tasks = len(upload_results)
    failures = [x for x in upload_results if isinstance(x, Exception)]
    failure_count = len(failures)

    if not failures:
        return

    print("{0} out of {1} custom device uploads have failed.".format(failure_count, all_tasks))
    for failure in failures:
        print("Custom device metadata upload failure details: {}".format(failure))


def custom_device_extractor(service_type: Text):
    """
    Denotes a function responsible for extracting additional info about GCP service.

    Function wrapped by this decorator should be placed under "lib.custom_devices.extractors"
    package, or otherwise it will not be automatically called.
    The decorator extends given function by uploading retrieved data to dynatrace server.
    """
    def register_extractor(fun: ExtractCustomDevicesFunc) -> ExtractCustomDevicesFunc:
        @wraps(fun)
        async def get_and_upload(ctx: Context, svc_def: GCPService) -> Iterable[CustomDevice]:
            print("Starting download of metadata for service '{}'".format(svc_def.name))
            try:
                entities = await fun(ctx, svc_def)
            except Exception as e:
                print(f"Failed to finish custom device extractor task, reason is {type(e).__name__} {e}")
                return []

            print("Download of metadata for service '{}' finished".format(svc_def.name))

            return entities

        custom_devices_extractors[service_type] = get_and_upload
        return get_and_upload

    return register_extractor
