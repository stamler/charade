import mysql.connector
from os import path
from sqlalchemy import create_engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.base import Engine
from typing import Any, Dict
import logging

Session: sessionmaker
engine: Engine
resources: Dict[str, Any]

def init(config: Dict[str, Any]) -> None:
    log = logging.getLogger(__name__)
    log.debug("__init__ Database")

    # If we're running inside docker on a mac, we can access the outside
    # world using host.docker.internal
    if path.isfile('/app/isContainerized'):
        log.debug("Charade thinks it's running in a container\n"
                    "If true, DB connection may fail due to networking.\n"
                    "On Docker for Mac, try host.docker.internal")

    global engine
    engine = create_engine(config['db'], pool_pre_ping=True)

    try:
        from .model import Base
        Base.metadata.bind = engine
        #bind_engine(engine)
        LoadedBase = Base
        log.debug("Found and loaded model.py")
    except ModuleNotFoundError:
        from sqlalchemy.ext.automap import automap_base

        # Automap with database reflection
        LoadedBase = automap_base()
        LoadedBase.prepare(engine, reflect=True)
        log.debug("model.py not found, running with automap")
    
    global Session
    Session = sessionmaker(bind=engine)

    global resources
    resources = __get_resources(LoadedBase)

# Read the database and load in table and column names, EXCLUDING VIEWS.
# NB previous version without SQLALchemy included VIEWS
# This info is used to generate resource objects and routes
# A useful addition to this would be to generate schemas for each Resource
# These schemas would then be sent to the client when the app is loaded
# so that when the user creates a new resource object it can be validated
# in the client prior to POSTing or PUTing to save a round trip
# The client UI could also go a step further and present different input
# types based on the schema provided by this API. The format of this
# schema should be something like http://json-schema.org 

# Ideally Marshmallow https://marshmallow-sqlalchemy.readthedocs.io
# or a similar package could validate the input once it had been POSTed or
# PUT on the server. But there should be only one place to actually 
# configure the schema for all of charade and this should probably be the 
# SQLAlchemy model. Then the marshmallow schema would be based on that and 
# the generation of a JSON Schema would also follow from that to the client.
# In this way modifications to the backend would drive automatic 
# modifications to the client.
def __get_resources(Base) -> Dict[str, Any]:
    # describe the root resource
    resources: Dict[str, Any] = { "Root": { "URIs":["/"], "sqla_obj":None }}

    for subclass in Base.__subclasses__():
        # Build a json-schema for each table so the UI can build forms
        json_schema: Dict[str, Any] = { 
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": subclass.__name__,
            "type": "object",
            "properties": {},
            "required": [], # base this on NULL allowance in DB
            "additionalProperties": False
        }
        for c in inspect(subclass).columns:
            # Skip the primary key in the JSON SCHEMA since it should be
            # assigned exclusively by the backend. The client will preserve
            # this key when doing an update but there's no need for the 
            # user to edit/see it.
            # NB: Handles the case of composite primary keys by skipping
            # all columns marked as primary key. Is there another way to
            # define composite primary keys where c.primary_key isn't set?
            if c.primary_key:
                continue

            json_schema['properties'][c.name] = {
                "type": __sqla_to_json_type(c.type),
                "title": c.info.get('title'),
                "attrs": { "placeholder": c.info.get('placeholder') } }

            # add columns that are not nullable to required
            if c.nullable == False:
                json_schema['required'].append(c.name)

        # create baseURI plus URI with field expression for {id}
        uri_base = '/' + subclass.__name__
        uri_id = uri_base + r"/{id:int(min=0)}"

        resources[subclass.__name__] = {
            "json_schema": json_schema,
            "URIs": [uri_base, uri_id],
            "sqla_obj": subclass
        }

    return resources

def __sqla_to_json_type(sqla_type) -> str:
    # 6 primitive types:
    # array, boolean, object, string, null, number
    # TODO: include validation parameters like length, regexes
    # confirming to JSON schema
    type_map: Dict[str, str] = {
        "int":"integer",
        "str":"string",
        "datetime":"string",
        "date":"string",
        "bool":"boolean"
    }
    return type_map[ sqla_type.python_type.__name__ ]
