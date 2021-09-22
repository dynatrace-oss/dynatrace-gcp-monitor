from aiohttp import ClientSession

from lib.context import MetricsContext

_SERVICE_USAGE_ROOT = "https://serviceusage.googleapis.com/v1"


async def get_all_disabled_apis(context: MetricsContext, session: ClientSession, token: str, project_id: str):
    url = f"{_SERVICE_USAGE_ROOT}/projects/{project_id}/services?filter=state:DISABLED"
    headers = {"Authorization": "Bearer {token}".format(token=token)}
    disabled_apis = set()
    try:
        response = await session.get(url, headers=headers)
        if response.status != 200:
            context.log(f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
            return set()
        disabled_services_json = await response.json()
        disabled_services = disabled_services_json.get("services", [])
        disabled_apis.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        while disabled_services_json.get("nextPageToken"):
            url = f"{url}&pageToken={disabled_services_json['nextPageToken']}"
            response = await session.get(url, headers=headers)
            if response.status == 200:
                disabled_services_json = await response.json()
                disabled_services = disabled_services_json.get("services", [])
                disabled_apis.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        return disabled_apis
    except Exception as e:
        context.log(f'Cannot get disabled APIs: {_SERVICE_USAGE_ROOT}/projects/{project_id}/services?filter = state:DISABLED. {e}')
        return disabled_apis
