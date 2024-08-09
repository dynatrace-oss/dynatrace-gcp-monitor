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
import time
import zipfile
from io import BytesIO
from typing import NamedTuple, List, Dict, Optional

import yaml
from aiohttp import ClientSession
import os

from lib.configuration import config
from lib.context import LoggingContext
from lib.metrics import GCPService
from lib.utilities import get_autodiscovery_flag_per_service, read_activation_yaml, get_activation_config_per_service, \
    load_activated_feature_sets, get_service_activation_dict, create_default_monitoring_config

ExtensionsFetchResult = NamedTuple("ExtensionsFetchResult",
                                   [("services", List[GCPService]),
                                    ("extension_versions", Dict[str, str]),
                                    ("not_configured_services", List[str])],)

ExtensionCacheEntry = NamedTuple('ExtensionCacheEntry', [('version', str), ('definition', Dict)])
EXTENSIONS_CACHE_BY_NAME: Dict[str, ExtensionCacheEntry] = {}
DEFAULT_GOOGLE_EXTENSIONS = [
    "com.dynatrace.extension.google-api",
    "com.dynatrace.extension.google-app-engine",
    "com.dynatrace.extension.google-bigquery",
    "com.dynatrace.extension.google-cloud-functions",
    "com.dynatrace.extension.google-cloud-run",
    "com.dynatrace.extension.google-cloud-storage",
    "com.dynatrace.extension.google-compute-engine",
    "com.dynatrace.extension.google-datastore",
    "com.dynatrace.extension.google-filestore",
    "com.dynatrace.extension.google-kubernetes-engine",
    "com.dynatrace.extension.google-load-balancing",
    "com.dynatrace.extension.google-pubsub",
    "com.dynatrace.extension.google-pubsub-lite",
    "com.dynatrace.extension.google-sql"
]


class ExtensionsFetcher:

    def __init__(self, dt_session: ClientSession, dynatrace_url: str, dynatrace_access_key: str, logging_context: LoggingContext):
        self.dt_session = dt_session
        self.dynatrace_url = dynatrace_url
        self.dynatrace_access_key = dynatrace_access_key
        self.logging_context = logging_context

    async def execute(self) -> ExtensionsFetchResult:
        extension_name_to_version_dict = await self._get_extensions_dict_from_dynatrace_cluster()
        configured_services = []
        not_configured_services = []
        project_id = config.project_id()
        for extension_name, extension_version in extension_name_to_version_dict.items():
            activation_dict = {'services': []}
            extension_configuration = await self.get_extension_configuration_from_cache_or_download(
                extension_name, extension_version
            )
            if "gcp" in extension_configuration:
                extension_configuration_services = extension_configuration.get("gcp")
                services = [service.get("service") for service in extension_configuration_services]
                services = list(set(services))
                monitoring_configurations, status = await self._get_monitoring_configuration(extension_name)
                project_ids = [monitoring_config.get("value").get("gcp").get("gcpMonitorID") for monitoring_config in monitoring_configurations]
                if (not monitoring_configurations or project_id not in project_ids) and extension_name in DEFAULT_GOOGLE_EXTENSIONS and status == int(200):
                    monitoring_configurations = create_default_monitoring_config(extension_name, extension_version)
                    await self._post_monitoring_configuration(extension_name, monitoring_configurations)

                activation_dict['services'].extend(get_service_activation_dict(services, monitoring_configurations, extension_version))

                activation_config_per_service = get_activation_config_per_service(activation_dict)
                autodiscovery_per_service = get_autodiscovery_flag_per_service(activation_dict)
                feature_sets_from_activation_config = load_activated_feature_sets(self.logging_context, activation_dict)

                services_for_extension, not_configured_services_for_extension = await self._get_service_configs_for_extension(
                    extension_name,
                    activation_config_per_service,
                    feature_sets_from_activation_config,
                    autodiscovery_per_service,
                    extension_configuration_services
                )

                configured_services.extend(services_for_extension)
                not_configured_services.extend(not_configured_services_for_extension)
            else:
                self.logging_context.log(f"Incorrect extension fetched from Dynatrace cluster. {extension_name}-{extension_version} has no 'gcp' section and will be skipped")

        if not_configured_services:
            self.logging_context.log(f"Following services (enabled in extensions) are filtered out,"
                                     f" because not enabled in deployment config: {not_configured_services}")
        return ExtensionsFetchResult(services=configured_services,
                                     extension_versions=extension_name_to_version_dict,
                                     not_configured_services=not_configured_services)

    async def _get_extensions_dict_from_dynatrace_cluster(self) -> Dict[str, str]:
        dynatrace_extensions = await self._get_extension_list_from_dynatrace_cluster()
        return self._deduplicate_extensions(dynatrace_extensions) if dynatrace_extensions else {}

    async def _post_monitoring_configuration(self, service, monitoring_configuration):
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions/{service}/monitoringConfigurations"
        headers = {"Authorization": f"Api-Token {self.dynatrace_access_key}",
                   "Accept": "application/json; charset=utf-8",
                   "Content-Type": "application/json; charset=utf-8"}
        response = await self.dt_session.post(url,
                                              headers=headers,
                                              data=json.dumps(monitoring_configuration),
                                              verify_ssl=config.require_valid_certificate())

        if response.status != 200:
            self.logging_context.log(
                f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
        else:
            self.logging_context.log(f"Extension {service} was created in tenant with default monitoring configuration")

    async def _get_monitoring_configuration(self, service):
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions/{service}/monitoringConfigurations"
        headers = {"Authorization": f"Api-Token {self.dynatrace_access_key}",
                   "Accept": "application/json; charset=utf-8"}
        response = await self.dt_session.get(url, headers=headers, verify_ssl=config.require_valid_certificate())
        if response.status != 200:
            self.logging_context.log(
                f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
            return [], response.status
        response_json = await response.json()
        monitoring_configurations = response_json.get("items", [])
        return monitoring_configurations, response.status

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
        activation_config_per_service,
        feature_sets_from_activation_config,
        autodiscovery_per_service: Dict[str, bool],
        extension_configuration_services
    ) -> (List[GCPService], List):

        all_services = []
        not_configured_services = []
        for service in extension_configuration_services:
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
        if extension_name in EXTENSIONS_CACHE_BY_NAME and EXTENSIONS_CACHE_BY_NAME[extension_name].version == extension_version:
            extension_configuration = EXTENSIONS_CACHE_BY_NAME[extension_name].definition
        else:
            self.logging_context.log(f"Downloading and preparing extension {extension_name} ({extension_version})")
            extension_configuration = await self._fetch_extension_configuration_from_dt(extension_name, extension_version)
            EXTENSIONS_CACHE_BY_NAME[extension_name] = ExtensionCacheEntry(extension_version, extension_configuration)
        return extension_configuration

    async def _fetch_extension_configuration_from_dt(self, extension_name, extension_version):
        extension_zip = await self._get_extension_zip_from_dynatrace_cluster(extension_name, extension_version)
        extension_configuration = self._load_extension_config_from_zip(extension_name, extension_zip) if extension_zip else {}
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
