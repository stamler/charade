import mysql.connector
import json
import logging
import config
import os.path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base

class Database(object):

    def __init__(self, config_dict):
        self.log = logging.getLogger(__name__)
        self.log.debug("__init__ Database")

        # Configuration-related initialization
        self.dbconfig = config_dict['mysql']
        self.appconfig = config_dict['app']

        # PENDING_DELETION These 2 lines may become Vestigial after full SQLAlchemy transition
        self.max_multi_responses = self.appconfig.get('max_multi_responses', 5)
        self.custom_queries = self.appconfig.get('custom_queries', None)

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
        engine = create_engine(connection_string)
        self.Base.prepare(engine, reflect=True, classname_for_table=self.custom_classname)
        self.session = Session(engine)

        # PENDING_DELETION Vestigial code (2 lines) to be deleted after transition to SQLAlchemy
        self.__cnx = mysql.connector.connect(**self.dbconfig)
        self.__cnx.set_converter_class(CustomMySQLConverter)

    # PENDING_DELETION Vestigial method to be deleted with SQLAlchemy functionality
    def get_connection(self):
        return self.__cnx

    def get_session(self):
        return self.session

    # Read the database and load in table and column names, EXCLUDING VIEWS.
    #NB previous version without SQLALchemy included VIEWS
    # This info is used to generate resource objects and routes
    def get_resources(self):
        # describe the root resource
        resources = { "Root": { "Title_Case": "Root", "CamelCase": "Root",
                                "snake_case": "root", "table": None,
                                "URIs":["/"], "object":None,
                                "children":[] }}

        self.table_columns = {}

        for subclass in self.Base.__subclasses__():
            # dict key is table_name, value is list of
            # tuples of format (column_name, column_type)
            self.table_columns[subclass.__table__.name] = [(c.name, c.type) for c in subclass.__table__.columns]

            if subclass.__table__.name in self.appconfig["tables_to_exclude"]:
                continue

            snake_case = self.strip_prefix(subclass.__table__.name)
            camel_case = subclass.__name__
            uri_base = '/' + camel_case
            # Create 2nd URI with the field expression for {id}
            uri_id = uri_base + r"/{id:int(min=0)}"

            resources[camel_case] = {}
            resources[camel_case]['Title_Case'] = self.snake_to_title(snake_case)
            resources[camel_case]['CamelCase'] = camel_case
            resources[camel_case]['snake_case'] = snake_case
            resources[camel_case]['table'] = subclass.__table__.name
            resources[camel_case]['URIs'] = [uri_base, uri_id]
            resources[camel_case]['object'] = None
            resources[camel_case]['children'] = []

        return resources

    # PENDING_DELETION Vestigial method may be replaced with SQLAlchemy functionality
    def get_child_resources(self):
        return {}

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

# PENDING_DELETION This class will become Vestigial after full SQLAlchemy transition
class CustomMySQLConverter(mysql.connector.conversion.MySQLConverter):
    """ A mysql.connector Converter that handles List and Dict type
    and spits out bytes as json """

    def _list_to_mysql(self, value):
        return json.dumps(value).encode()

    def _dict_to_mysql(self, value):
        return json.dumps(value).encode()

db_obj = Database(config.config)
