import os

import yaml
import zipfile
from io import BytesIO
from typing import NamedTuple, List, Dict, Optional

from aiohttp import ClientSession

from lib.context import LoggingContext, get_should_require_valid_certificate, get_selected_services
from lib.metrics import GCPService

ExtensionsFetchResult = NamedTuple('ExtensionsFetchResult', [('services', List[GCPService])])


def load_activated_service_names(logging_context: LoggingContext) -> List[str]:
    activation_file_path = '/code/config/activation/gcp_services.yaml'
    try:
        with open(activation_file_path, encoding="utf-8") as activation_file:
            activation_yaml = yaml.safe_load(activation_file)
    except Exception:
        activation_yaml = yaml.safe_load(os.environ.get("ACTIVATION_CONFIG", ""))
    if not activation_yaml:
        return []
    services_whitelist = []
    for service in activation_yaml.get('services', []):
        feature_sets = service.get("featureSets", [])
        for feature_set in feature_sets:
            services_whitelist.append(f"{service.get('service')}/{feature_set}")
        if not feature_sets:
            logging_context.error(f"No feature set in given {service} service.")

    return services_whitelist


class ExtensionsFetcher:

    def __init__(self, dt_session: ClientSession, dynatrace_url: str, dynatrace_access_key: str, logging_context: LoggingContext):
        self.dt_session = dt_session
        self.dynatrace_url = dynatrace_url
        self.dynatrace_access_key = dynatrace_access_key
        self.logging_context = logging_context

    async def execute(self) -> ExtensionsFetchResult:
        extension_name_to_version_dict = await self._get_extensions_dict_from_dynatrace_cluster()
        services = []
        for extension_name, extension_version in extension_name_to_version_dict.items():
            services_for_extension = await self._get_service_configs_for_extension(extension_name, extension_version)
            services.extend(services_for_extension)
        configured_services = self._filter_out_not_configured_services(services) if services else []
        return ExtensionsFetchResult(services=configured_services)

    async def _get_extensions_dict_from_dynatrace_cluster(self) -> Dict[str, str]:
        dynatrace_extensions = await self._get_extension_list_from_dynatrace_cluster()
        return self._deduplicate_extensions(dynatrace_extensions) if dynatrace_extensions else {}

    async def _get_extension_list_from_dynatrace_cluster(self) -> List[Dict]:
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions"
        headers = {"Authorization": f"Api-Token {self.dynatrace_access_key}", "Accept": "application/json; charset=utf-8"}
        params = {"name": "com.dynatrace.extension.google"}
        response = await self.dt_session.get(url, headers=headers, params=params,
                                             verify_ssl=get_should_require_valid_certificate())
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
                                                 verify_ssl=get_should_require_valid_certificate())
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

    async def _get_service_configs_for_extension(self, extension_name: str, extension_version: str) -> List[GCPService]:
        extension_zip = await self._get_extension_zip_from_dynatrace_cluster(extension_name, extension_version)
        extension_configuration = self._load_extension_config_from_zip(extension_name, extension_zip) if extension_zip else {}
        if "gcp" not in extension_configuration:
            self.logging_context.log(f"Incorrect extension fetched from Dynatrace cluster. {extension_name}-{extension_version} has no 'gcp' section and will be skipped")
            return []
        return [GCPService(**feature_set) for feature_set in extension_configuration.get("gcp")]

    async def _get_extension_zip_from_dynatrace_cluster(self, extension_name, extension_version) -> Optional[bytes]:
        url = f"{self.dynatrace_url.rstrip('/')}/api/v2/extensions/{extension_name}/{extension_version}"
        headers = {
            "Authorization": f"Api-Token {self.dynatrace_access_key}",
            "Accept": "application/octet-stream"
        }
        response = await self.dt_session.get(url, headers=headers, verify_ssl=get_should_require_valid_certificate())
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

    def _filter_out_not_configured_services(self, services_from_extensions: List[GCPService]) -> List[GCPService]:
        services_from_env = set(load_activated_service_names(self.logging_context))
        services_from_extensions_dict = {}
        for gcp_service_config in services_from_extensions:
            service_name = gcp_service_config.name
            feature_set = gcp_service_config.feature_set if gcp_service_config.feature_set != 'default_metrics' else ''
            services_from_extensions_dict[f"{service_name}/{feature_set}"] = gcp_service_config

        services_in_env_but_no_in_extensions = services_from_env.difference(set(services_from_extensions_dict.keys()))
        if services_in_env_but_no_in_extensions:
            self.logging_context.log(
                f"Following services are not found in extensions, but defined in 'gcpServicesYaml' env: {services_in_env_but_no_in_extensions}")
        services_not_configured = set(services_from_extensions_dict.keys()).difference(services_from_env)
        if services_not_configured:
            self.logging_context.log(f"Following services from extensions are filtered out, because not found in 'gcpServicesYaml' env: {services_not_configured}")
            return [services_from_extensions_dict[service_name] for service_name in services_from_extensions_dict.keys()
                    if service_name not in services_not_configured]
        else:
            return services_from_extensions
