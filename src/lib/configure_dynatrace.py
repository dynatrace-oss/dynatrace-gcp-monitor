import json
import os
from os import listdir
from os.path import isfile
from typing import List, Optional, Dict, Callable

import yaml
from aiohttp import ClientSession

from lib.context import LoggingContext
from lib.credentials import fetch_dynatrace_url, fetch_dynatrace_api_key
from lib.fast_check import get_dynatrace_token_metadata
from main import is_yaml_file


class ConfigureDynatrace:

    class DtApi:
        def __init__(self, dt_session: ClientSession, dynatrace_url: str, dynatrace_api_key: str, ):
            self.dt_session = dt_session
            self.dynatrace_url = dynatrace_url.rstrip('/')
            self.dynatrace_api_key = dynatrace_api_key

        async def call(self, method: str, path: str, json_data: Optional[Dict] = None, timeout: Optional[int] = 2):
            return await self.dt_session.request(
                method=method,
                url=f"{self.dynatrace_url}{path}",
                headers={
                    "Authorization": f"Api-Token {self.dynatrace_api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=timeout,
                json=json_data)

    async def post_dashboard(self, dt_api: DtApi, path: str, name:str, remove_owner: bool, timeout: Optional[int] = 2) -> str:
        try:
            with open(path, encoding="utf-8") as dashboard_file:
                 dashboard_json = json.load(dashboard_file) 
            if remove_owner:                                         
                del dashboard_json["dashboardMetadata"]["owner"]
            response = await dt_api.call("POST", "/api/config/v1/dashboards", dashboard_json, timeout)
            if response.status != 201:
                response_json= await response.json()
                if not remove_owner and 'owner' in json.dumps(response_json):
                    await self.post_dashboard(dt_api, path, name, True)
                else:
                    self.logging_context.log(f'Unable to create dashboard {name} in Dynatrace: {response.status}, url: {response.url}, reason: {response.reason}, message {response_json}')                                
            else:
                self.logging_context.log(f"Installed dashboard {name}")
                response_json = await response.json()
                return response_json.get("id", "")
        except Exception as e:
            self.logging_context.log(f'Unable to create dashboard in Dynatrace. Error details: {e}')

    async def get_existing_dashboards(self, dt_api: DtApi, timeout: Optional[int] = 2) -> List[dict]:
        try:
            response = await dt_api.call("GET", "/api/config/v1/dashboards", timeout=timeout)
            response.raise_for_status()
            dashboards_json = await response.json()
            all_dashboards = [dashboard["name"] for dashboard in dashboards_json.get("dashboards", [])]
            return all_dashboards
        except Exception as e:
            self.logging_context.log(f'Unable to get existing dashboards config. Error details: {e}')
            return []

    async def get_existing_alerts(self, dt_api: DtApi, timeout: Optional[int] = 2) -> List[dict]:
        try:
            response = await dt_api.call("GET", "/api/config/v1/anomalyDetection/metricEvents", timeout=timeout)
            response.raise_for_status()
            response_json = await response.json()
            all_alerts = [alert["id"] for alert in response_json.get("values", [])]
            return all_alerts
        except Exception as e:
            self.logging_context.log(f'Unable to get existing dashboards config. Error details: {e}')
            return []

    def get_ext_resources(self, list_name: str, item_name: str, properties_extractor: Callable[[Dict], Dict]) -> List[Dict]:
        try:
            if "GCP_SERVICES" in os.environ:
                selected_services_string = os.environ.get("GCP_SERVICES", "")
                selected_services = selected_services_string.split(",") if selected_services_string else []
                working_directory = os.path.dirname(os.path.realpath(__file__))
                config_directory = os.path.join(working_directory, "../config")
                config_files = [
                    file for file
                    in listdir(config_directory)
                    if os.path.splitext(os.path.basename(file))[0] in selected_services and isfile(os.path.join(config_directory, file)) and is_yaml_file(file)
                ]
                resources = []
                for file in config_files:
                    config_file_path = os.path.join(config_directory, file)
                    try:
                        with open(config_file_path, encoding="utf-8") as config_file:
                            config_yaml = yaml.safe_load(config_file)
                            for resource in config_yaml.get(list_name, []):
                                resource_file_path = os.path.join(working_directory, '../', resource.get(item_name, {}))
                                with open(resource_file_path, encoding="utf-8") as resource_file:
                                    resource_json = json.load(resource_file)
                                    properties = properties_extractor(resource_json)
                                    properties["path"] = resource_file_path
                                    resources.append(properties)
                    except Exception as error:
                        self.logging_context.log(
                            f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
                        continue
                return resources
            else:
                return []
        except Exception as e:
            self.logging_context.log(f'Unable to get available dashboards. Error details: {e}')
            return []
            
    def __init__(self, gcp_session: ClientSession, dt_session: ClientSession, logging_context: LoggingContext):
        self.gcp_session = gcp_session
        self.dt_session = dt_session
        self.logging_context = logging_context

    async def import_dashboards(self, dt_api: DtApi):
        existing_dashboards = await self.get_existing_dashboards(dt_api)
        available_dashboards = self.get_ext_resources("dashboards", "dashboard", lambda x: {
            'name': x.get("dashboardMetadata", {}).get("name", "")})
        dashboards_to_install = [dash for dash in available_dashboards if dash["name"] not in existing_dashboards]

        self.logging_context.log(f"Available dashboards: {[dash['name'] for dash in available_dashboards]}")
        if dashboards_to_install:
            self.logging_context.log(f"New dashboards to install: {[dash['name'] for dash in dashboards_to_install]}")
            for dashboard in dashboards_to_install:
                dashboard_id = await self.post_dashboard(dt_api, dashboard["path"], dashboard["name"], False)
                if dashboard_id:
                    try:
                        response = await dt_api.call("PUT", f"/api/config/v1/dashboards/{dashboard_id}/shareSettings",
                                                     {"id": f"{dashboard_id}",
                                                      "published": "true",
                                                      "enabled": "true",
                                                      "publicAccess": {
                                                          "managementZoneIds": [],
                                                          "urls": {}
                                                      }, "permissions": [
                                                         {"type": "ALL", "permission": "VIEW"}
                                                        ]
                                                      }
                                                     )
                        response.raise_for_status()
                    except Exception as e:
                        self.logging_context.log(
                            f"Unable to apply permissions for dashboard {dashboard_id}, details: {e}")
        else:
            self.logging_context.log(
                f"All dashboards already installed, skipping. (if you wish to upgrade a dashboard, please delete it first)")

    async def import_alerts(self, dt_api: DtApi):
        existing_alerts = await self.get_existing_alerts(dt_api)
        available_alerts = self.get_ext_resources("alerts", "path", lambda x: {
            "id": x.get("id", ""), "name": x.get("name", "")})
        alerts_to_install = [alert for alert in available_alerts if alert["id"] not in existing_alerts]
        self.logging_context.log(f"Available alerts: {[alert['name'] for alert in available_alerts]}")
        if alerts_to_install:
            self.logging_context.log(f"New alerts to install: {[alert['name'] for alert in alerts_to_install]}")
            for alert in alerts_to_install:
                try:
                    with open(alert["path"], encoding="utf-8") as alert_file:
                        alert_json = json.load(alert_file)
                        response = await dt_api.call("PUT", f"/api/config/v1/anomalyDetection/metricEvents/{alert['id']}", alert_json)
                        response.raise_for_status()
                        self.logging_context.log(f"Installed alert {alert['name']}")
                except Exception as e:
                    self.logging_context.log(
                        f"Unable to install alert  {alert['name']}, details: {e}")
        else:
            self.logging_context.log(
                f"All alerts already installed, skipping. (if you wish to upgrade an alert, please delete it first)")

    async def _init_(self):        
        dynatrace_url = await fetch_dynatrace_url(self.gcp_session, "", "")
        self.logging_context.log(f"Using Dynatrace endpoint: {dynatrace_url}")
        dynatrace_access_key = await fetch_dynatrace_api_key(self.gcp_session,"", "")
        dt_api = self.DtApi(self.dt_session, dynatrace_url, dynatrace_access_key)

        scopes = await get_dynatrace_token_metadata(self.dt_session, self.logging_context, dynatrace_url, dynatrace_access_key)
        has_write_config_permission=any(s in scopes.get('scopes', []) for s in ["WriteConfig", "ReadConfig"])        
        if not has_write_config_permission:
            self.logging_context.log("Missing ReadConfig/WriteConfig permission for Dynatrace API token, skipping dashboards configuration")
        else:
            dashboards_import = os.environ.get("IMPORT_DASHBOARDS", "TRUE").upper() in ["TRUE", "YES"]
            alerts_import = os.environ.get("IMPORT_ALERTS", "TRUE").upper() in ["TRUE", "YES"]

            if dashboards_import:
                await self.import_dashboards(dt_api)
            else:
                self.logging_context.log("Dashboards import disabled")

            if alerts_import:
                await self.import_alerts(dt_api)
            else:
                self.logging_context.log("Alerts import disabled")

    def __await__(self):
        return self._init_().__await__()