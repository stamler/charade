###################
# main.py
# Called by WSGI to run the falcon app, the entry point

import os
#os.chdir(os.path.dirname(os.path.realpath(__file__)))

import logging
import logging.config

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': { 'simple': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
        } },
    'handlers': { 'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter': 'simple'
        } },
    'root': { 'level': 'DEBUG', 'handlers': ['console'] },
}
logging.config.dictConfig(LOGGING)
log = logging.getLogger()


import falcon
from .config import config
from .database import db_obj
from .Resource import Resource
from .middleware import AzureADTokenValidator, CORSComponent, CacheController
from typing import Any, Dict


# Create the falcon API instance (a WSGI app). We are doing
# this inside of a function because it will simplify testing
# later on. The falcon testing system can instantiate an app 
# instance by calling create()
def create(cfg: Dict[str, Any]) -> falcon.API:

    # Initialize validation middleware
    validator = AzureADTokenValidator(cfg['azure_tenant'], cfg['azure_app_id'])

    # Initialize other middleware
    cors = CORSComponent()
    cache_controller = CacheController()

    app = falcon.API(
            # The JSON API spec requires this media type
            media_type ="application/vnd.api+json",
            middleware = [ cors, validator, cache_controller ] )

    # instantiate resources and map routes to them
    for _, res_config in db_obj.resources.items():
        resource = Resource(res_config)
        for uri in res_config['URIs']:
            app.add_route(uri, resource)

    return app

# uwsgi.ini expects callable named 'app'
app = create(config)
