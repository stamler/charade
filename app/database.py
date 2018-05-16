import mysql.connector
import json
import logging
import config
import os.path
from collections import defaultdict

class Database(object):

    def __init__(self, config_dict):
        self.log = logging.getLogger(__name__)
        self.log.debug("__init__ Database")

        # Configuration-related initialization
        self.dbconfig = config_dict['mysql']
        self.appconfig = config_dict['app']
        self.max_multi_responses = self.appconfig.get('max_multi_responses', 5)
        self.custom_queries = self.appconfig.get('custom_queries', None)

        # If we're running inside docker, update the mysql host to
        # the docker host for tunnelling (expect the host is tunneling)
        # this will become more fine-grained later with an ENV in Dockerfile
        if os.path.isfile('/app/isContainerized'):
            self.log.debug("App detected it is running in a container")
            self.dbconfig['host'] = "host.docker.internal"

        # Connect to the database
        print(self.dbconfig)
        self.__cnx = mysql.connector.connect(**self.dbconfig)
        self.__cnx.set_converter_class(CustomMySQLConverter)

    def get_connection(self):
        return self.__cnx

    # Read the database and load in table and column names, including VIEWS.
    # This info is used to generate resource objects and routes
    def get_resources(self):
        cnx = self.get_connection()
        cursor = cnx.cursor()

        # describe the root resource
        resources = { "Root": { "Title_Case": "Root", "CamelCase": "Root",
                                "snake_case": "root", "table": None,
                                "URIs":["/"], "object":None,
                                "children":[] }}

        # Get schema dict where keys are 'table_name' and values
        # are lists of column name/type tuples for that table
        query_schema = ("SELECT table_name, column_name, column_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s "
                    "ORDER BY table_name, ordinal_position")
        cursor.execute(query_schema,(self.dbconfig['database'],))
        schema = defaultdict(list)
        for (table_name, column_name, column_type) in cursor:
            schema[table_name].append((column_name, column_type))

        # Get primary keys for each table (NOT VIEW) in the database
        pks = {}
        query_pks = ("SELECT table_name, column_name "
                    "FROM information_schema.key_column_usage "
                    "WHERE table_schema = %s AND constraint_name = 'PRIMARY' "
                    "GROUP BY table_name")
        cursor.execute(query_pks,(self.dbconfig['database'],))
        for (table_name, column_name) in cursor:
            pks[table_name] = column_name

        # side-effect of get_resources() call is update of self.table_columns
        self.table_columns = {}

        # From schema dict create a list of resource dicts each having
        # keys for the table name and uri_template skipping "tables_to_exclude"
        # Also create a self.table_columns dict where keys are table names
        # and values are a column list
        for (k,v) in schema.items():

            # Set the self.table_columns
            self.table_columns[k] = v

            if k in self.appconfig["tables_to_exclude"]:
                continue

            snake_case = self.strip_prefix(k)
            camel_case = self.snake_to_camel(snake_case)
            uri_base = '/' + camel_case
            # Create 2nd URI with the field expression for {id}
            uri_id = uri_base + r"/{id:int(min=0)}"

            # Add each table and corresponding URIs to resources dict
            resources[camel_case] = {}
            resources[camel_case]['Title_Case'] = self.snake_to_title(snake_case)
            resources[camel_case]['CamelCase'] = camel_case
            resources[camel_case]['snake_case'] = snake_case
            resources[camel_case]['table'] = k
            resources[camel_case]['URIs'] = [uri_base, uri_id]
            resources[camel_case]['object'] = None
            resources[camel_case]['children'] = []
            if pks.get(k, None):
                resources[camel_case]['pk'] = pks.pop(k)

        cursor.close()
        return resources

    # Build child_resources dict where keys are resource name (CamelCase)
    # and values are dicts with keys pk (refd_col),
    # resource (CamelCase) and fk (col).
    def get_child_resources(self):
        cnx = self.get_connection()
        cursor = cnx.cursor()
        query_child_tables = ("SELECT table_name, column_name, "
                 "referenced_table_name, referenced_column_name "
                 "FROM information_schema.key_column_usage "
                 "WHERE table_schema = %s "
                 "AND referenced_table_name IS NOT NULL "
                 "ORDER BY referenced_table_name")
        child_resources = defaultdict(list)
        cursor.execute(query_child_tables,(self.dbconfig['database'],))
        for (table, col, refd_table, refd_col) in cursor:
            child_resources[self.snake_to_camel(self.strip_prefix(refd_table))].append({ "pk":refd_col, "fk": col,
                    "object_name": self.snake_to_camel(self.strip_prefix(table)) })
        cursor.close()
        return child_resources

    # Remove the tables_prefix
    def strip_prefix(self, the_input):
        return the_input.replace(self.appconfig['tables_prefix'],"")

    # Convert snake_case to Human Readable (Title Case)
    def snake_to_title(self, the_input):
        return ' '.join(w.capitalize() for w in (the_input.rsplit('_')))

    # Convert snake_case to CamelCase
    def snake_to_camel(self, the_input):
        return ''.join(w.capitalize() for w in (the_input.rsplit('_')))

class CustomMySQLConverter(mysql.connector.conversion.MySQLConverter):
    """ A mysql.connector Converter that handles List and Dict type
    and spits out bytes as json """

    def _list_to_mysql(self, value):
        return json.dumps(value).encode()

    def _dict_to_mysql(self, value):
        return json.dumps(value).encode()

db_obj = Database(config.config)
