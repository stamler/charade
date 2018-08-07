###################
# main.py
# Called by WSGI to run the falcon app, the entry point

# setup logging before any more imports
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

import logging
import logging.config
logging.config.dictConfig(LOGGING)
log = logging.getLogger()

import falcon
import json
from .config import config
import charade.database as database
import charade.sentinel as sentinel
from .Resource import Resource
from .middleware import AzureADTokenValidator, CORSComponent, CacheController
from typing import Any, Dict

# Instantiate an app by calling create(), useful for testing
def create(cfg: Dict[str, Any]) -> falcon.API:
    # Initialize database, using either model.py or reflection (automap_base)
    database.init(cfg)

    # Bind the Sentinel module to our existing database engine 
    sentinel.Base.metadata.bind = database.engine
    
    app = falcon.API(
            # The JSON API spec requires this media type
            media_type ="application/vnd.api+json",
            middleware = [ CORSComponent(), 
                AzureADTokenValidator(cfg['azure_tenant'], cfg['azure_app_id']), 
                CacheController() ] )

    # instantiate resources and map routes to them
    for _, res_config in database.resources.items():
        resource = Resource(res_config)
        for uri in res_config['URIs']:
            app.add_route(uri, resource)

    app.set_error_serializer(error_serializer)

    return app

# JSON API-compliant serializer for error objects
def error_serializer(req, resp, exception):
    resp.body = json.dumps({ "errors": [ exception.to_dict() ] })

# uwsgi.ini expects callable named 'app'
app = create(config)
