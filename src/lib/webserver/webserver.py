from aiohttp import web
from aiohttp.web_app import Application
from aiohttp.web_runner import AppRunner

from lib.context import LoggingContext

logging_context = LoggingContext("webserver")

APP: Application = None
RUNNER: AppRunner = None


def setup_webserver_on_asyncio_loop(loop, port):
    global APP, RUNNER
    logging_context.log("Setting up webserver... \n")

    APP = web.Application()
    APP.add_routes([web.get('/health', health_endpoint)])

    RUNNER = web.AppRunner(APP)
    loop.run_until_complete(RUNNER.setup())
    site = web.TCPSite(RUNNER, '0.0.0.0', port)
    loop.run_until_complete(site.start())


async def health_endpoint(request):
    return web.Response(status=200)


def close_and_cleanup(loop):
    global APP, RUNNER
    if APP is not None:
        loop.run_until_complete(APP.shutdown())
    if RUNNER is not None:
        loop.run_until_complete(RUNNER.cleanup())
    if APP is not None:
        loop.run_until_complete(APP.cleanup())
