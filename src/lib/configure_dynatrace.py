import asyncio
import re
import os
from os import listdir
from os.path import isfile
from typing import NamedTuple, List, Optional, Dict 

from aiohttp import ClientSession

from lib.context import LoggingContext

from lib.fast_check import get_dynatrace_token_metadata
from lib.credentials import fetch_dynatrace_url, fetch_dynatrace_api_key
import yaml
import json
from main import is_yaml_file


class ConfigureDynatrace:
    async def post_dashboard(self, dynatrace_url: str, dynatrace_api_key: str, path: str, name:str, remove_owner: bool, timeout: Optional[int] = 2) -> List[Dict]:
        try:
            with open(path, encoding="utf-8") as dashboard_file:
                 dashboard_json = json.load(dashboard_file) 
            if remove_owner:                                         
                del dashboard_json["dashboardMetadata"]["owner"]
            response = await self.session.post(              
                url=f"{dynatrace_url.rstrip('/')}/api/config/v1/dashboards",
                headers={
                    "Authorization": f"Api-Token {dynatrace_api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=timeout,
                json=dashboard_json)
            if response.status != 201:
                response_json=  await response.json()                
                if not remove_owner and 'owner' in json.dumps(response_json):
                    await self.post_dashboard(dynatrace_url, dynatrace_api_key, path, name, True)
                else:
                    self.logging_context.log(f'Unable to create dashboard {name} in Dynatrace: {response.status}, url: {response.url}, reason: {response.reason}, message {response_json}')                                
            else:
                self.logging_context.log(f"Installed dashboard {name}")
        except Exception as e:
            self.logging_context.log(f'Unable to create dashboard in Dynatrace. Error details: {e}')

    async def get_existing_dashboards(self, dynatrace_url: str, dynatrace_api_key: str, timeout: Optional[int] = 2) -> List[dict]:
        try:
            response = await self.session.get(
                url=f"{dynatrace_url.rstrip('/')}/api/config/v1/dashboards",
                headers={
                    "Authorization": f"Api-Token {dynatrace_api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=timeout)
            if response.status != 200:
                self.logging_context.log(f'Unable to get existing dashboards config: {response.status}, url: {response.url}, reason: {response.reason}')
                return {}

            dashboards_json=  await response.json()
            all_dashboards = [dashboard["name"] for dashboard in dashboards_json.get("dashboards",[])]
            return all_dashboards
        except Exception as e:
            self.logging_context.log(f'Unable to get existing dashboards config. Error details: {e}')
            return []


    async def get_available_dashboards(self) -> List[Dict]:
        try:
            selected_services = None
            if "GCP_SERVICES" in os.environ:
                selected_services_string = os.environ.get("GCP_SERVICES", "")
                selected_services = selected_services_string.split(",") if selected_services_string else []
                working_directory = os.path.dirname(os.path.realpath(__file__))
                config_directory = os.path.join(working_directory, "../config")
                config_files = [
                    file for file
                    in listdir(config_directory)
                    if isfile(os.path.join(config_directory, file)) and is_yaml_file(file)
                ]
                dashboards = []
                for file in config_files:
                    config_file_path = os.path.join(config_directory, file)
                    try:
                        with open(config_file_path, encoding="utf-8") as config_file:
                            config_yaml = yaml.safe_load(config_file)
                            for dashboard in config_yaml.get("dashboards", []):                        
                                dashboard_file_path = os.path.join(working_directory, '../', dashboard.get("dashboard",{}))                                                                
                                with open(dashboard_file_path, encoding="utf-8") as dashboard_file:
                                    dashboard_json = json.load(dashboard_file) 
                                    dashboard_name = dashboard_json.get("dashboardMetadata",{}).get("name",{})
                                    dashboards.append({"path": dashboard_file_path,"name": dashboard_name})                            
                    except Exception as error:
                         self.logging_context.log(f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
                         continue                
                return dashboards   
            else:
                return []
        except Exception as e:
            self.logging_context.log(f'Unable to get available dashboards. Error details: {e}')
            return []
            

    def __init__(self, session: ClientSession, logging_context: LoggingContext):
        self.session = session
        self.logging_context = logging_context
            
    async def _init_(self):        
        dynatrace_url = await fetch_dynatrace_url(self.session, "", "")
        dynatrace_access_key = await fetch_dynatrace_api_key(self.session,"", "")
        scopes = await  get_dynatrace_token_metadata(self.session, self.logging_context, dynatrace_url, dynatrace_access_key)
        has_write_config_permission=any(s in scopes.get('scopes', []) for s in ["WriteConfig", "ReadConfig"])        
        if not has_write_config_permission:
            self.logging_context.log("Missing ReadConfig/WriteConfig permission for Dynatrace API token, skipping dashboards configuration")
        else:
            existing_dashboards = await self.get_existing_dashboards(dynatrace_url, dynatrace_access_key)                                
            available_dashboards = await self.get_available_dashboards()
            dashboards_to_install = [dash for dash in available_dashboards if dash["name"] not in existing_dashboards]

            self.logging_context.log(f"Available dashboards: {[dash['name'] for dash in available_dashboards]}")
            if dashboards_to_install:
                self.logging_context.log(f"New dashboards to install: {[dash['name'] for dash in dashboards_to_install]}")
                for dashboard in dashboards_to_install:
                    await self.post_dashboard(dynatrace_url, dynatrace_access_key, dashboard["path"], dashboard["name"], False)
            else :
                self.logging_context.log(f"All dashboards already installed, skipping. (if you wish to upgrade a dashboard, please delete it first)")
    def __await__(self):
        return self._init_().__await__()        