import asyncio
from asyncio import AbstractEventLoop

from aiohttp import web
from aiohttp.web_app import Application
from aiohttp.web_runner import AppRunner

from lib.context import LoggingContext, get_int_environment_value

logging_context = LoggingContext("webserver")

HEALTH_CHECK_PORT = get_int_environment_value("HEALTH_CHECK_PORT", 8080)


def run_webserver_on_asyncio_loop_forever():
    try:
        webserver_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(webserver_loop)

        logging_context.log("Setting up webserver... \n")

        application: Application = web.Application()
        application.add_routes([web.get('/health', health_endpoint)])

        app_runner: AppRunner = web.AppRunner(application)
        webserver_loop.run_until_complete(app_runner.setup())
        site = web.TCPSite(app_runner, '0.0.0.0', HEALTH_CHECK_PORT)
        webserver_loop.run_until_complete(site.start())

        webserver_loop.run_forever()
    finally:
        print("Closing AsyncIO loop...")
        close_and_cleanup(application, app_runner, webserver_loop)
        webserver_loop.close()


async def health_endpoint(request):
    return web.Response(status=200)


def close_and_cleanup(application: Application, app_runner: AppRunner, webserver_loop: AbstractEventLoop):
    if application is not None:
        webserver_loop.run_until_complete(application.shutdown())
    if app_runner is not None:
        webserver_loop.run_until_complete(app_runner.cleanup())
    if application is not None:
        webserver_loop.run_until_complete(application.cleanup())
