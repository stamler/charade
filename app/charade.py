###################
# main.py
# Called by WSGI to run the falcon app, the entry point

import os
os.chdir(os.path.dirname(os.path.realpath(__file__)))

import falcon
import config
from ResourceManager import rm_obj
from middleware import AzureADTokenValidator, CORSComponent, CacheController

# Initialize validation middleware
azure_cfg = config.config['azure_ad']
validator = AzureADTokenValidator(azure_cfg['tenant_name'], azure_cfg['app_id'])

# Initialize other middleware
cors = CORSComponent()
cache_controller = CacheController()

# Create the falcon API instance (a WSGI app)
app = falcon.API(middleware = [ cors, cache_controller ]) #validator ])

# hook up the routes from the ResourceManager
rm_obj.add_routes(app)
