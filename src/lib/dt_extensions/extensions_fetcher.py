#   Copyright 2023 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import json
import zipfile
from io import BytesIO
from typing import NamedTuple, List, Dict, Optional, Tuple, Any

import yaml
from aiohttp import ClientSession
import os

from lib.configuration import config
from lib.context import LoggingContext
from lib.metrics import GCPService
from lib.utilities import get_autodiscovery_flag_per_service, read_activation_yaml, get_activation_config_per_service, \
    load_activated_feature_sets, read_activation_json, get_list_of_users

ExtensionsFetchResult = NamedTuple("ExtensionsFetchResult",
                                   [("services", List[GCPService]), ("extension_versions", Dict[str, str])], )

ExtensionCacheEntry = NamedTuple('ExtensionCacheEntry', [('version', str), ('definition', Dict)])
EXTENSIONS_CACHE_BY_NAME: Dict[str, ExtensionCacheEntry] = {}


class ExtensionsFetcher:

    def __init__(self, dt_session: ClientSession, dynatrace_url: str, dynatrace_access_key: str,
                 logging_context: LoggingContext):
        self.dt_session = dt_session
        self.dynatrace_url = dynatrace_url
        self.dynatrace_access_key = dynatrace_access_key
        self.logging_context = logging_context

    async def execute(self) -> Tuple[ExtensionsFetchResult, List[Any]]:
        extension_name_to_version_dict = await self._get_extensions_dict_from_dynatrace_cluster()
        # activation_yaml = read_activation_yaml()
        activation_json = read_activation_json()
        activation_config_per_service = get_activation_config_per_service(activation_json)
        autodiscovery_per_service = get_autodiscovery_flag_per_service(activation_json)
        feature_sets_from_activation_config = load_activated_feature_sets(self.logging_context, activation_json)

        configured_services = []
        not_configured_services = []

        for extension_name, extension_version in extension_name_to_version_dict.items():
            services_for_extension, not_configured_services_for_extension = await self._get_service_configs_for_extension(
                extension_name, extension_version, activation_config_per_service, feature_sets_from_activation_config,
                autodiscovery_per_service)
            configured_services.extend(services_for_extension)
            not_configured_services.extend(not_configured_services_for_extension)
        if not_configured_services:
            self.logging_context.log(f"Following services (enabled in extensions) are filtered out,"
                                     f" because not enabled in deployment config: {not_configured_services}")
        return ExtensionsFetchResult(services=configured_services,
                                     extension_versions=extension_name_to_version_dict), not_configured_services

    async def _get_extensions_dict_from_dynatrace_cluster(self) -> Dict[str, str]:
        dynatrace_extensions = await self._get_extension_list_from_dynatrace_cluster()
        return self._deduplicate_extensions(dynatrace_extensions) if dynatrace_extensions else {}

    async def _get_extension_list_from_dynatrace_cluster(self) -> List[Dict]:
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions"
        headers = {"Authorization": f"Api-Token {self.dynatrace_access_key}",
                   "Accept": "application/json; charset=utf-8"}
        params = {"name": "com.dynatrace.extension.google"}
        response = await self.dt_session.get(url, headers=headers, params=params,
                                             verify_ssl=config.require_valid_certificate())
        if response.status != 200:
            self.logging_context.log(
                f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
            return []
        response_json = await response.json()
        dynatrace_extensions = response_json.get("extensions", [])
        next_page_key = response_json.get("nextPageKey")
        while next_page_key:
            params = {"nextPageKey": next_page_key}
            response = await self.dt_session.get(url, headers=headers, params=params,
                                                 verify_ssl=config.require_valid_certificate())
            next_page_key = None
            if response.status == 200:
                response_json = await response.json()
                dynatrace_extensions.extend(response_json.get("extensions", []))
                next_page_key = response_json.get("nextPageKey")
        return dynatrace_extensions

    def _deduplicate_extensions(self, dynatrace_extensions: List[Dict]) -> Dict[str, str]:
        dynatrace_extensions_dict = {}
        for extension in dynatrace_extensions:
            if extension.get("extensionName") not in dynatrace_extensions_dict:
                dynatrace_extensions_dict[extension.get("extensionName")] = extension.get("version")
            elif int(extension.get("version").replace('.', '')) > int(
                    dynatrace_extensions_dict[extension.get("extensionName")].replace('.', '')):
                dynatrace_extensions_dict[extension.get("extensionName")] = extension.get("version")
        return dynatrace_extensions_dict

    async def _get_service_configs_for_extension(
            self,
            extension_name: str,
            extension_version: str,
            activation_config_per_service,
            feature_sets_from_activation_config,
            autodiscovery_per_service: Dict[str, bool],
    ) -> (List[GCPService], List):
        extension_configuration = await self.get_extension_configuration_from_cache_or_download(
            extension_name, extension_version
        )

        if "gcp" not in extension_configuration:
            self.logging_context.log(
                f"Incorrect extension fetched from Dynatrace cluster. {extension_name}-{extension_version} has no 'gcp' section and will be skipped"
            )
            return []

        all_services = []
        not_configured_services = []
        for service in extension_configuration.get("gcp"):
            service_name = service.get("service")
            feature_set = f"{service_name}/{service.get('featureSet')}"
            activation = activation_config_per_service.get(service_name, {})
            is_configured = feature_set in feature_sets_from_activation_config
            all_services.append(
                GCPService(
                    **service,
                    activation=activation,
                    is_enabled=is_configured,
                    extension_name=extension_name,
                    autodiscovery_enabled=autodiscovery_per_service.get(service_name, False)
                )
            )
            if not is_configured:
                not_configured_services.append(feature_set)
        return all_services, not_configured_services

    async def get_extension_configuration_from_cache_or_download(self, extension_name, extension_version):
        if extension_name in EXTENSIONS_CACHE_BY_NAME and EXTENSIONS_CACHE_BY_NAME[
            extension_name].version == extension_version:
            extension_configuration = EXTENSIONS_CACHE_BY_NAME[extension_name].definition
        else:
            self.logging_context.log(f"Downloading and preparing extension {extension_name} ({extension_version})")
            extension_configuration = await self._fetch_extension_configuration_from_dt(extension_name,
                                                                                        extension_version)
            EXTENSIONS_CACHE_BY_NAME[extension_name] = ExtensionCacheEntry(extension_version, extension_configuration)
        return extension_configuration

    async def _fetch_extension_configuration_from_dt(self, extension_name, extension_version):
        extension_zip = await self._get_extension_zip_from_dynatrace_cluster(extension_name, extension_version)
        extension_configuration = self._load_extension_config_from_zip(extension_name,
                                                                       extension_zip) if extension_zip else {}
        return extension_configuration

    async def _get_extension_zip_from_dynatrace_cluster(self, extension_name, extension_version) -> Optional[bytes]:
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions/{extension_name}/{extension_version}"
        headers = {
            "Authorization": f"Api-Token {self.dynatrace_access_key}",
            "Accept": "application/octet-stream"
        }
        response = await self.dt_session.get(url, headers=headers, verify_ssl=config.require_valid_certificate())
        if response.status != 200:
            self.logging_context.log(
                f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
            return None
        return await response.read()

    def _load_extension_config_from_zip(self, extension_name: str, extension_zip: bytes) -> Dict:
        activation_yaml = {}
        try:
            with zipfile.ZipFile(BytesIO(extension_zip)) as parent_extension_zip:
                with zipfile.ZipFile(parent_extension_zip.open("extension.zip")) as extension_zip:
                    with extension_zip.open("extension.yaml") as activation_file:
                        activation_yaml = yaml.safe_load(activation_file)
        except Exception:
            self.logging_context.t_exception(f"Cannot load extension {extension_name}")
        return activation_yaml
