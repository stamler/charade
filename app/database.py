import mysql.connector
import json
import logging
import config
import os.path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import DatabaseError

class Database(object):

    def __init__(self, config_dict):
        # Configure logging
        self.log = logging.getLogger()
        self.log.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self.log.addHandler(ch)
        self.log.debug("__init__ Database")

        # Configuration-related initialization
        self.dbconfig = config_dict['mysql']
        self.appconfig = config_dict['app']

        # PENDING_DELETION These 2 lines may become Vestigial after full SQLAlchemy transition
        self.max_multi_responses = self.appconfig.get('max_multi_responses', 5)

        # If we're running inside docker, update the mysql host to
        # the docker host for tunnelling (expect the host is tunneling)
        # this will become more fine-grained later with an ENV in Dockerfile
        if os.path.isfile('/app/isContainerized'):
            self.log.debug("App detected it is running in a container")
            self.dbconfig['host'] = "host.docker.internal"

        self.Base = automap_base()
        connection_string = "mysql+mysqlconnector://{}:{}@{}/{}".format(
                self.dbconfig['user'], self.dbconfig['password'],
                self.dbconfig['host'], self.dbconfig['database']
            )
        engine = create_engine(connection_string, pool_pre_ping=True)
        try:
            self.Base.prepare(engine, reflect=True, classname_for_table=self.custom_classname)
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
        resources = { "Root": { "Title_Case": "Root", "URIs":["/"], 
                                "object":None, "sqla_obj":None
                                }}

        #self.table_columns = {}

        for subclass in self.Base.__subclasses__():

            if subclass.__table__.name in self.appconfig["tables_to_exclude"]:
                continue

            snake_case = self.strip_prefix(subclass.__table__.name)
            uri_base = '/' + subclass.__name__
            # Create 2nd URI with the field expression for {id}
            uri_id = uri_base + r"/{id:int(min=0)}"

            resources[subclass.__name__] = {}
            resources[subclass.__name__]['Title_Case'] = self.snake_to_title(snake_case)
            resources[subclass.__name__]['json_schema'] = None
            resources[subclass.__name__]['URIs'] = [uri_base, uri_id]
            resources[subclass.__name__]['object'] = None
            resources[subclass.__name__]['sqla_obj'] = subclass

        return resources

    # custom class names
    def custom_classname(self, base, tablename, table):
        return self.snake_to_camel(self.strip_prefix(tablename))

    # Remove the tables_prefix
    def strip_prefix(self, the_input):
        return the_input.replace(self.appconfig['tables_prefix'],"")

    # Convert snake_case to Human Readable (Title Case)
    def snake_to_title(self, the_input):
        return ' '.join(w.capitalize() for w in (the_input.rsplit('_')))

    # Convert snake_case to CamelCase
    def snake_to_camel(self, the_input):
        return ''.join(w.capitalize() for w in (the_input.rsplit('_')))

db_obj = Database(config.config)
