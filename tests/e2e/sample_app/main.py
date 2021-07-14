from flask import escape

def sample_app(request):

    request_args = request.args
    deployment_type = 'None'
    build_id = 'None'

    if request_args and 'deployment_type' in request_args:
        deployment_type = request_args['deployment_type']

    if request_args and 'build_id' in request_args:
        build_id = request_args['build_id']
        
    return f"TYPE: {deployment_type}, BUILD: {build_id}, INFO: This is sample app"
