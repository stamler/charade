import mysql.connector
import logging
from .config import config as gc
from os import path
from sqlalchemy import create_engine, MetaData
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import DatabaseError
from typing import Any, Dict

class Database(object):

    def __init__(self, config: Dict[str, Any]) -> None:
        # Configure logging
        self.log = logging.getLogger()
        self.log.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self.log.addHandler(ch)
        self.log.debug("__init__ Database")

        # TODO: PENDING_DELETION These 2 lines may become 
        # Vestigial after full SQLAlchemy transition
        self.max_multi_responses = config.get('max_multi_responses', 5)

        # If we're running inside docker on a mac, we can access the outside
        # world using host.docker.internal
        if path.isfile('/app/isContainerized'):
            self.log.debug("Charade thinks it's running in a container\n"
                        "If true, DB connection may fail due to networking.\n"
                        "On Docker for Mac, try host.docker.internal")

        engine = create_engine(config['db'], pool_pre_ping=True)
        try:

            # TODO: load charade_middleware_authorization config and add 
            # configure Base, then load model.py. If model.py isn't
            # found, then automap the rest

            from .model import Base
            self.Base = Base
            self.log.debug("Found and loaded model.py")
        except ModuleNotFoundError as e:
            from sqlalchemy.ext.automap import automap_base

            # str() verifies that the loaded value is a string.
            # tables_prefix is used by custom_classname. May be 
            # deprecated once authorization classes/tables are implemented
            self.tables_prefix: str = str(config['tables_prefix'])

            # Automap with database reflection
            Base = automap_base()
            Base.prepare(engine, reflect=True, 
                                classname_for_table=self.custom_classname)
            self.Base = Base
            self.log.debug("model.py not found, running with automap")

        try:
            # TODO: There's an issue in these two try/except blocks.
            # the DatabaseError needs to be caught precisely after the first
            # connection is attempted regardless of whether or not model.py
            # or automap is used. Ideally a single try-block with multiple
            # except blocks is the solution.
            self.session = Session(engine)
        except DatabaseError as e:
            self.log.error("No Database Connection: {}".format(e))
            # TODO: Handle this exception safely. Perhaps restart the server?

        # Load resources once and cache them
        self.resources = self.__get_resources()

    def get_session(self) -> Session:
        return self.session

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
    def __get_resources(self) -> Dict[str, Any]:
        # describe the root resource
        resources: Dict[str, Any] = { "Root": { "URIs":["/"], "sqla_obj":None }}

        for subclass in self.Base.__subclasses__():
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
                    "type": self.__sqla_to_json_type(c.type),
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

    def __sqla_to_json_type(self, sqla_type) -> str:
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

    # custom class names (strip prefix, convert to CamelCase)
    def custom_classname(self, base, tablename: str, table) -> str:
        no_prefix = tablename.replace(self.tables_prefix,"")
        return ''.join(w.capitalize() for w in (no_prefix.rsplit('_')))

db_obj = Database(gc)
