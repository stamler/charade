###################
# main.py
# Called by WSGI to run the falcon app, the entry point

import os
os.chdir(os.path.dirname(os.path.realpath(__file__)))

import falcon
import config
from database import db_obj
from Resource import Resource
from middleware import AzureADTokenValidator, CORSComponent, CacheController

# Initialize validation middleware
azure_cfg = config.config['azure_ad']
validator = AzureADTokenValidator(azure_cfg['tenant_name'], azure_cfg['app_id'])

# Initialize other middleware
cors = CORSComponent()
cache_controller = CacheController()

# Create the falcon API instance (a WSGI app)
app = falcon.API(middleware = [ cors, validator, cache_controller ])

# instantiate resources, hook up routes and store references to them in db_obj
for _, res_config in db_obj.resources.items():
    resource = Resource(res_config)
    for uri in res_config['URIs']:
        app.add_route(uri, resource)
