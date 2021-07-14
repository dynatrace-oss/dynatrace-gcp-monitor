from flask import escape
import logging

def sample_app(request):

    request_args = request.args
    deployment_type = 'None'
    build_id = 'None'

    if request_args and 'deployment_type' in request_args:
        deployment_type = request_args['deployment_type']

    if request_args and 'build_id' in request_args:
        build_id = request_args['build_id']
    
    logging.info(f"TYPE: {deployment_type}, BUILD: {build_id}, INFO: This is sample app")

    return "This is sample app"
