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

import asyncio
import os
import time
import traceback
from datetime import datetime
from os import listdir
from os.path import isfile
from typing import Any, Dict, List, Optional

import aiohttp
import yaml

from lib.context import Context
from lib.credentials import create_token, get_project_id_from_environment, fetch_dynatrace_api_key, fetch_dynatrace_url
from lib.entities import entities_extractors
from lib.entities.model import Entity
from lib.metric_ingest import fetch_metric, push_ingest_lines, flatten_and_enrich_metric_results
from lib.metrics import GCPService, Metric
from lib.self_monitoring import push_self_monitoring_time_series


def dynatrace_gcp_extension(event, context: Dict[Any, Any] = None, project_id: Optional[str] = None):
    try:
        selected_services = None
        if "GCP_SERVICES" in os.environ:
            selected_services_string = os.environ.get("GCP_SERVICES", "")
            selected_services = selected_services_string.split(",") if selected_services_string else []

        asyncio.run(handle_event(event, context, project_id, selected_services))
    except Exception as e:
        traceback.print_exc()
        raise e


def is_yaml_file(f: str) -> bool:
    return f.endswith(".yml") or f.endswith(".yaml")


async def handle_event(event: Dict, context: Dict, project_id: Optional[str], selected_services: List[str]):
    services = load_supported_services(selected_services)

    async with aiohttp.ClientSession() as session:
        setup_start_time = time.time()
        token = await create_token(session)

        if not isinstance(token, str):
            raise Exception(f"Failed to fetch access token, got non string value: {token}")

        print("Successfully obtained access token")

        if not project_id:
            project_id = get_project_id_from_environment()

        dynatrace_api_key = await fetch_dynatrace_api_key(session=session, project_id=project_id, token=token)
        dynatrace_url = await fetch_dynatrace_url(session=session, project_id=project_id, token=token)

        print_metric_ingest_input = \
            "PRINT_METRIC_INGEST_INPUT" in os.environ and os.environ["PRINT_METRIC_INGEST_INPUT"].upper() == "TRUE"

        context = Context(
            session=session,
            project_id=project_id,
            token=token,
            execution_time=datetime.utcnow(),
            execution_interval_seconds=60 * 1,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            print_metric_ingest_input=print_metric_ingest_input
        )
        context.setup_execution_time = (time.time() - setup_start_time)

        fetch_gcp_data_start_time = time.time()
        fetch_metric_tasks = []
        topology_tasks = []
        for service in services:
            if service.name in entities_extractors:
                topology_task = entities_extractors[service.name](context, service)
                topology_tasks.append(topology_task)
            for metric in service.metrics:
                fetch_metric_task = run_fetch_metric(
                    context=context,
                    service=service,
                    metric=metric
                )
                fetch_metric_tasks.append(fetch_metric_task)

        all_results = await asyncio.gather(
            asyncio.gather(*fetch_metric_tasks, return_exceptions=True),
            asyncio.gather(*topology_tasks, return_exceptions=True)
        )
        fetch_metric_results = all_results[0]
        fetch_topology_results = all_results[1]

        context.fetch_gcp_data_execution_time = time.time() - fetch_gcp_data_start_time
        print(f"Fetched GCP data in {context.fetch_gcp_data_execution_time} s")

        entity_id_map = build_entity_id_map(fetch_topology_results)
        flat_metric_results = flatten_and_enrich_metric_results(fetch_metric_results, entity_id_map)

        await push_ingest_lines(context, flat_metric_results)

        await push_self_monitoring_time_series(context)

    # Noise on windows at the end of the logs is caused by https://github.com/aio-libs/aiohttp/issues/4324


def build_entity_id_map(fetch_topology_results: List[List[Entity]]) -> Dict[str, Entity]:
    result = {}
    for result_set in fetch_topology_results:
        for entity in result_set:
            result[entity.id] = entity
    return result


def load_supported_services(selected_services: List[str]) -> List[GCPService]:
    working_directory = os.path.dirname(os.path.realpath(__file__))
    config_directory = os.path.join(working_directory, "config")
    config_files = [
        file for file
        in listdir(config_directory)
        if isfile(os.path.join(config_directory, file)) and is_yaml_file(file)
    ]

    services = []
    for file in config_files:
        config_file_path = os.path.join(config_directory, file)
        try:
            with open(config_file_path, encoding="utf-8") as config_file:
                config_yaml = yaml.safe_load(config_file)
                technology_name = config_yaml.get("technology", {}).get("name", "N/A")
                for service_yaml in config_yaml.get("gcp", {}):
                    # If whitelist of services exists and current service is not present in it, skip
                    should_skip = selected_services and \
                                  (service_yaml.get("service", "None") not in selected_services)
                    if should_skip:
                        continue
                    services.append(GCPService(tech_name=technology_name, **service_yaml))
        except Exception as error:
            print(f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
            continue
    return services


async def run_fetch_metric(
        context: Context,
        service: GCPService,
        metric: Metric
):
    try:
        return await fetch_metric(context, service, metric)
    except Exception as e:
        print(f"Failed to finish task for [{metric.google_metric}], reason is {type(e).__name__} {e}")
        return []
