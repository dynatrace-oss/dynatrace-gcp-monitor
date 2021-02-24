import os

import aiohttp


def init_dt_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(trust_env=(os.environ.get("USE_PROXY", "").upper() in ["ALL", "DT_ONLY"]))


def init_gcp_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(trust_env=(os.environ.get("USE_PROXY", "").upper() in ["ALL", "GCP_ONLY"]))
