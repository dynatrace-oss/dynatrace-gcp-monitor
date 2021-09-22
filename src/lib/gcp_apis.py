from aiohttp import ClientSession

from lib.context import MetricsContext

_SERVICE_USAGE_ROOT = "https://serviceusage.googleapis.com/v1"


async def get_all_disabled_services(context: MetricsContext, session: ClientSession, token: str, project_id: str):
    url = f"{_SERVICE_USAGE_ROOT}/projects/{project_id}/services?filter=state:DISABLED"
    headers = {"Authorization": "Bearer {token}".format(token=token)}
    disabled_services_set = set()
    try:
        response = await session.get(url, headers=headers)
        if response.status != 200:
            context.log(f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
            return set()
        disabled_services_json = await response.json()
        disabled_services = disabled_services_json.get("services", [])
        disabled_services_set.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        while disabled_services_json.get("nextPageToken"):
            url = f"{url}&pageToken={disabled_services_json['nextPageToken']}"
            response = await session.get(url, headers=headers)
            if response.status == 200:
                disabled_services_json = await response.json()
                disabled_services = disabled_services_json.get("services", [])
                disabled_services_set.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        return disabled_services_set
    except Exception as e:
        context.log(f'Cannot get disabled services: {_SERVICE_USAGE_ROOT}/projects/{project_id}/services?filter = state:DISABLED. {e}')
        return disabled_services_set
