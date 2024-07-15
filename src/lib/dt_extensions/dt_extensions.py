from typing import Dict, Optional, List

from aiohttp import ClientSession

from lib.clientsession_provider import init_gcp_client_session, init_dt_client_session
from lib.configuration import config
from lib.context import LoggingContext
from lib.credentials import fetch_dynatrace_url, fetch_dynatrace_api_key, create_token
from lib.dt_extensions.extensions_fetcher import ExtensionsFetchResult, ExtensionsFetcher
from lib.metrics import GCPService

logging_context = LoggingContext("EXTENSIONS")


async def prepare_services_config_for_next_polling(current_services: List[GCPService], current_extension_versions: Dict[str,str]) -> ExtensionsFetchResult:
    try:
        async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
            token = await create_token(logging_context, gcp_session)
            if not token:
                raise Exception('Failed to fetch token')

            extensions_fetch_result = await extensions_fetch(gcp_session, dt_session, token)
            if not extensions_fetch_result:
                raise Exception('Extension fetch failed')

            return extensions_fetch_result
    except Exception as e:
        logging_context.error(f'Failed to prepare new services configuration from extensions, will reuse previous configuration; {str(e)}')
        return ExtensionsFetchResult(current_services,current_extension_versions)


async def extensions_fetch(gcp_session: ClientSession, dt_session: ClientSession, token: str) -> Optional[ExtensionsFetchResult]:
    extension_fetcher_result, not_configured_services = await ExtensionsFetcher(
        dt_session=dt_session,
        dynatrace_url=await fetch_dynatrace_url(gcp_session, config.project_id(), token),
        dynatrace_access_key=await fetch_dynatrace_api_key(gcp_session, config.project_id(), token),
        logging_context=logging_context
    ).execute()

    if extension_fetcher_result.services:
        feature_sets_names = [f"{service.name}/{service.feature_set}" for service in extension_fetcher_result.services]
        logging_context.log(f'Services config prepared from extensions & deployment configuration: {list(set(feature_sets_names) - set(not_configured_services))}')
        return extension_fetcher_result
    else:
        logging_context.log("Extensions fetch resulted in empty list of services. Check on the Dynatrace Hub and enable Google extensions to start monitoring the desired services.")
        return None
