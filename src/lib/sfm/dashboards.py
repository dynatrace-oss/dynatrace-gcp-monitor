import json
import os
from typing import Dict

from lib.context import SfmDashboardsContext
from operation_mode import OperationMode


async def import_self_monitoring_dashboard(context: SfmDashboardsContext):
    if context.operation_mode == OperationMode.Metrics:
        dashboard_filename = "dynatrace-gcp-function_self_monitoring.json"
    elif context.operation_mode == OperationMode.Logs:
        dashboard_filename = "dynatrace-gcp-function-log-self-monitoring.json"
    else:
        context.log(f"Lack of self monitoring dashboard for '{context.operation_mode}' operation mode")
        return

    working_directory = os.path.dirname(os.path.realpath(__file__))
    dashboards_directory = os.path.join(working_directory, "../dashboards")
    dashboard_file_path = os.path.join(dashboards_directory, dashboard_filename)

    try:
        with open(dashboard_file_path, encoding="utf-8") as dashboard_file:
            dashboard = json.load(dashboard_file)

            if await is_self_monitoring_dashboard_exists(context, dashboard.get('displayName')):
                context.log(f"The self monitoring dashboard '{dashboard.get('displayName')}' already exists")
            else:
                await create_new_dashboard(context, dashboard)
    except Exception as e:
        context.log(f"Failed to import a self monitoring dashboard, because: {e}")


async def create_new_dashboard(context: SfmDashboardsContext, dashboard: Dict):
    response = await context.gcp_session.request(
        "POST",
        url=f"https://monitoring.googleapis.com/v1/projects/{context.project_id_owner}/dashboards",
        data=json.dumps(dashboard),
        headers={"Authorization": f"Bearer {context.token}"}
    )

    if response.status > 202:
        response_body = await response.json()
        context.log(f"Failed to create self monitoring dashboard due to '{response_body}'")
    else:
        context.log(f"The self monitoring dashboard '{dashboard.get('displayName')}' correctly imported")


async def is_self_monitoring_dashboard_exists(context: SfmDashboardsContext, dashboard_display_name: str) -> bool:
    response = await context.gcp_session.request(
        'GET',
        url=f"https://monitoring.googleapis.com/v1/projects/{context.project_id_owner}/dashboards",
        headers={"Authorization": f"Bearer {context.token}"}
    )
    if response.status <= 202:
        response_json = await response.json()
        return dashboard_display_name in [dashboard.get("displayName") for dashboard in response_json.get("dashboards")]
    elif response.status == 403:
        raise PermissionError('Failed to list GCP monitoring dashboards due to missing permissions')
    else:
        raise Warning(f'Failed to list GCP monitoring dashboards, http response status = {response.status}')
