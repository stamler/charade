import mysql.connector
import logging
from .config import config as global_configuration
from os import path
from sqlalchemy import create_engine, MetaData
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import DatabaseError

class Database(object):

    def __init__(self, config):
        # Configure logging
        self.log = logging.getLogger()
        self.log.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self.log.addHandler(ch)
        self.log.debug("__init__ Database")

        # PENDING_DELETION These 2 lines may become Vestigial after full SQLAlchemy transition
        self.max_multi_responses = config.get('max_multi_responses', 5)

        # If we're running inside docker on a mac, we can access the outside
        # world using host.docker.internal
        if path.isfile('/app/isContainerized'):
            self.log.debug("App detected it is running in a container "
                        "DB connection may fail due to networking.\n"
                        "If running Docker for Mac, try host.docker.internal")

        engine = create_engine(config['db'], pool_pre_ping=True)
        try:
            # produce our own MetaData object
            metadata = MetaData()

            # reflect entire database unless "tables_to_include" is in config
            metadata.reflect(engine, only=config.get('tables_to_include', None))

            # we can then produce a set of mappings from this MetaData.
            self.Base = automap_base(metadata=metadata)

            self.Base.prepare(classname_for_table=self.custom_classname)
            self.session = Session(engine)
        except DatabaseError as e:
            self.log.error("No Database Connection: {}".format(e))
            # TODO: Handle this exception safely. Perhaps restart the server?

        # Load resources once and cache them
        self.resources = self.__get_resources()

    def get_session(self):
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
    def __get_resources(self):
        # describe the root resource
        resources = { "Root": { "URIs":["/"], "sqla_obj":None }}

        for subclass in self.Base.__subclasses__():
            # Build a json-schema for each table so the UI can build forms
            json_schema = { 
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": subclass.__name__,
                "type": "object",
                "properties": {},
                "required": [], # base this on NULL allowance in DB
                "additionalProperties": False
            }
            for c in inspect(subclass).columns:
                json_schema['properties'][c.name] = {}
                json_schema['properties'][c.name]["type"] =  (
                                            self.__sqla_to_json_type(c.type) )

                # add columns that are not nullable to required
                # TODO: This adds the primary key, which could present
                # an issue when we're POSTing since POSTs don't include
                # primary keys. PUTs do so we'll leave it for now but this
                # should be handled, likely in the client since charade
                # can't know which method the schema is going to be used for
                if c.nullable == False:
                    json_schema['required'].append(c.name)

            # create baseURI plus URI with field expression for {id}
            uri_base = '/' + subclass.__name__
            uri_id = uri_base + r"/{id:int(min=0)}"

            resources[subclass.__name__] = {}            
            resources[subclass.__name__]['json_schema'] = json_schema
            resources[subclass.__name__]['URIs'] = [uri_base, uri_id]
            resources[subclass.__name__]['sqla_obj'] = subclass

        return resources

    def __sqla_to_json_type(self, sqla_type):
        # 6 primitive types:
        # array, boolean, object, string, null, number
        #TODO: include validation parameters like length, regexes
        # confirming to JSON schema
        type_map = {
            "int":"integer",
            "str":"string",
            "datetime":"string",
            "date":"string"
        }
        return type_map[ sqla_type.python_type.__name__ ]

    # custom class names
    def custom_classname(self, base, tablename, table):
        return self.snake_to_camel(self.strip_prefix(tablename))

    # Remove the tables_prefix
    def strip_prefix(self, the_input):
        return the_input.replace(global_configuration['tables_prefix'],"")

    # Convert snake_case to CamelCase
    def snake_to_camel(self, the_input):
        return ''.join(w.capitalize() for w in (the_input.rsplit('_')))

db_obj = Database(global_configuration)
