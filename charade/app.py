###################
# main.py
# Called by WSGI to run the falcon app, the entry point

import os
#os.chdir(os.path.dirname(os.path.realpath(__file__)))

import falcon
from .config import config
from .database import db_obj
from .Resource import Resource
from .middleware import AzureADTokenValidator, CORSComponent, CacheController

# Create the falcon API instance (a WSGI app)
def create():

    # Initialize validation middleware
    azure_cfg = config['azure_ad']
    validator = AzureADTokenValidator(azure_cfg['tenant_name'], azure_cfg['app_id'])

    # Initialize other middleware
    cors = CORSComponent()
    cache_controller = CacheController()

    app = falcon.API(
            media_type="application/vnd.api+json",
            middleware = [ cors, validator, cache_controller ] )

    # instantiate resources and map routes to them
    for _, res_config in db_obj.resources.items():
        resource = Resource(res_config)
        for uri in res_config['URIs']:
            app.add_route(uri, resource)

    return app

# uwsgi.ini expects callable named 'app'
app = create()
