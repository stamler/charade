##################
# Resource.py
# Implements a Resource class based on a database table

import falcon
import json
import mysql.connector
import logging
from database import db_obj

class Resource(object):
    def __init__(self, name, res):
        self.log = logging.getLogger(__name__)
        self.log.debug("__init__ Resource: " + name)

        if res and res.get('table', None):
            self.name = name
            self.__primary_key__ = res.get('pk', 'id')
            self.db_table = res['table']
            # list of tuples (column_name, column_type)
            self.db_table_columns = db_obj.table_columns[res['table']]
            self._load_sql()
            self.is_root = False
        else:
            self.name = "Root"
            self.is_root = True

    # Handle GET requests to a resource that represents all rows of a single
    # table in the database. If the request contains an id field expression
    # then return a single object.
    # ASSUME col 0 of the table in question is called 'id' and type INTEGER
    def on_get(self, req, resp, id=None):
        if self.is_root:
            resp.status = falcon.HTTP_200
            resp.content_type = falcon.MEDIA_HTML
            body = { 'data': db_obj.resources }
            resp.body = json.dumps(body, default=str)
            return

        try:
            cnx = db_obj.get_connection()
            cursor = cnx.cursor()
            query = self.get_query

            included = {}
            if id is not None:
                # a single object was requested
                query += " WHERE {} = %s".format(self.get_id_key)
                cursor.execute(query, (id,))

                # fetch all rows to determine rowcount otherwise it's -1
                rows = cursor.fetchall()
                assert len(rows) > -1

                if len(rows) == 0:
                    resp.status = falcon.HTTP_404
                elif cursor.rowcount > 1:
                    # multiple rows means database key not unique
                    resp.status = falcon.HTTP_500
                else:
                    data = dict(zip(cursor.column_names, rows[0]))
                    resp.status = falcon.HTTP_200

                    # get any related child resources here and put them
                    # inside included {} declared above

            else:
                # a collection was requested
                where_clause, vals = self.gen_get_tuple(req.params)
                query += where_clause
                if len(vals) > 0:
                    cursor.execute(query, vals)
                else:
                    cursor.execute(query)
                data = []
                for row in cursor:
                    data.append(dict(zip(cursor.column_names, row)))
                resp.status = falcon.HTTP_200

            cursor.close()

            if resp.status == falcon.HTTP_200:
                body = {'data': data }
                if len(included) > 0:
                    body['included'] = included
            else:
                body = { "errors":["Something went south."]}

            resp.body = json.dumps(body, default=str)

        except mysql.connector.Error as e:
            resp.body = { "errors": [str(cursor.statement) + " ERROR: {}".format(e)] }

        except ValueError as f:
            resp.body = { "errors":[f] }

    # Handle POST requests to a resource and creates a new row in the table
    # represented by the resource. This method handles incomplete fields-
    # that is to say that fields not provided will be assumed NULL in the
    # database. As a result if the database requires NOT NULL then INSERT will
    # fail and the databse will return an error. Assumes the first column
    # of the table in question is called 'id' and type INTEGER, which is
    # assigned automatically after INSERT and returned in the response

    # Behaviour is based on POST body content:
    # If the content is an object (dict) then it is treated as a single object
    # to post and a single HTTP response will be issued.
    # If the content is an array (list), even a single-element list, then
    # multiple objects will be POSTed and a single HTTP 207 Multi response
    # https://httpstatuses.com/207 will encapsulate a corresponding HTTP
    # responses for each of the POSTed objects in the list based on the results
    # of each individual element POSTed.
    # The API thus supports posting 1 OR Multiple resources to an
    # endpoint and replying according to the Principle of Least Astonishment
    # https://apihandyman.io/api-design-tips-and-tricks-getting-creating-updating-or-deleting-multiple-resources-in-one-api-call/#single-and-multiple-creations-with-the-same-endpoint

    def on_post(self, req, resp):
        # Prevent blocking condition by ensuring content_length > 0
        if req.content_length:
            # capture the request body into data
            data = json.load(req.stream)
            if data.__class__.__name__ == 'dict':
                self.log.debug("Single object POSTed.")
                resp.status, body = self._insert_into_db( data )
                resp.body = json.dumps({'data':body})
            elif data.__class__.__name__ == 'list':
                # Processing an array of objects
                length = len(data)
                self.log.debug("List of {} items POSTed.".format(length))
                if length > db_obj.max_multi_responses:
                    self.log.debug("Multi-response max exceeded. Batching.")
                    # INSERT all data items in one shot and give one response
                    resp.status, body = self._insert_into_db( data )
                    resp.body = json.dumps({'data':body})
                else:
                    # Perform separate INSERT for each item in the data list
                    # then encapsulate each response into a multi 207 with
                    # corresponding client_id
                    resps = []
                    skips = 0 # count of items skipped due to missing client_id
                    for d in data:
                        # Skip items with no client_id (unique id distinct from
                        # the database generated by the consumer) since it's
                        # needed to reference items in the 207 multi response
                        client_id = d.pop('client_id', None)
                        if client_id is None:
                            skips += 1
                            continue

                        status, body = self._insert_into_db(d)
                        self.log.debug("client_id: {} status: {}".format(
                                                        client_id, status) )

                        resps.append({ "client_id": client_id, "status": status,
                                        "headers": None, "body": body } )

                    self.log.debug("Skipped {} items missing client_id".format(skips))
                    resp.status = falcon.HTTP_207
                    resp.body = json.dumps({'data':resps})

            else:
                resp.status = falcon.HTTP_500
                resp.body = json.dumps({'errors':["Unrecognized data POSTed"]})

    # SOME VALIDATION SHOULD HAPPEN HERE IN gen_insert_tuple:
    # Given a dict of query parameters submitted to the resource, validate that
    # they match the column type in the database and groom/convert them if
    # possible according to standard type mappings
    #   python datetime -> SQL datetime
    #   string -> varchar(size)
    #   int -> int(size) unsigned
    #   string -> char(size)
    # https://robertheaton.com/2014/02/09/pythons-pass-by-object-reference-as-explained-by-philip-k-dick/
    def gen_insert_tuple(self, data):
        # Process and validate the data into parameters for the sql_op.
        # First we create a NULL params list of len(table columns).
        # We then pick all of the request items whose keys match table
        # columns and insert them into the NULL params list at the correct
        # indices. The database will reject sql_ops if we attempt to
        # INSERT NULL values into a column set to NOT NULL
        params = [None] * len(self.db_table_columns[1:])
        for k, v in data.items():
            indices = [i for i, t in enumerate(self.db_table_columns[1:]) if k == t[0]]
            if len(indices) == 1:
                # There is exactly one matching key in the request.
                # json.load ensures this by keeping only the last key:value
                # pair it sees when loading from a source with duplicate
                # keys so by the time we reach this point there will be
                # either 0 or 1 elements in the indices list.
                params[indices[0]] = v
        return tuple(params)

    def _insert_into_db(self, data):
        try:
            cnx = db_obj.get_connection()
            cursor = cnx.cursor()
            sql_op = "INSERT INTO {} ({}) VALUES ({})".format( self.db_table,
                    ', '.join([x[0] for x in self.db_table_columns[1:]]),
                    ', '.join(["%s"] * len(self.db_table_columns[1:])) )
            response_body = {}

            if data.__class__.__name__ == 'list':
                insert_data = map(self.gen_insert_tuple, data)

                cnx.start_transaction()
                cursor.executemany(sql_op, insert_data)
                self.log.debug("Affected rows count: {}".format(cursor.rowcount))
                if cursor.rowcount == len(data):
                    response_body['rowcount'] = cursor.rowcount
                    status = falcon.HTTP_201
                    cnx.commit()
                    self.log.debug("response body: {}".format(response_body))
                else:
                    error = ("Row count ({}) doesn't match data length ({}). "
                             "Rolled back.".format(cursor.rowcount, len(data)))
                    response_body['error'] = error
                    status = falcon.HTTP_500
                    cnx.rollback()
                    self.log.debug("response body: {}".format(response_body))
            else:
                params = self.gen_insert_tuple(data)
                sql_op += "; SELECT LAST_INSERT_ID()"

                # Execute the sql_op (insert the new record and get the row id)
                # There will be multiple results
                for result in cursor.execute(sql_op, params, multi=True):
                    if result.with_rows:
                        # Get id of the created resource from LAST_INSERT_ID()
                        # It's the first element of the tuple in the only row.
                        response_body['id'] = result.fetchall()[0][0]
                    else:
                        # The number of affected rows should be exactly 1
                        if result.rowcount == 1:
                            status = falcon.HTTP_201
                            response_body['rowcount'] = result.rowcount
                        else:
                            status = falcon.HTTP_500
                cnx.commit()

            cursor.close()
            return status, response_body

        except mysql.connector.Error as e:
            return (falcon.HTTP_500,
                            str(cursor.statement) + " ERROR: {}".format(e) )

    # get the value of nested keys in a dictionary.
    # If any of the keys doesn't exist return None.
    def _safeget(self, dictionary, *keys):
        for key in keys:
            try:
                dictionary = dictionary[key]
            except KeyError:
                return None
        return dictionary

    # Load custom queries from config or, if no custom queries are given,
    # load default queries and set them as properties of the resource object
    def _load_sql(self):
        self.get_query = self._safeget(db_obj.custom_queries,
                                       self.db_table,'get','query')
        self.get_id_key = self._safeget(db_obj.custom_queries,
                                        self.db_table,'get','id_key')

        # If config has no query, use the defaults
        if self.get_query is None:
            self.get_query = "SELECT {} FROM {}".format(
                    ', '.join([x[0] for x in self.db_table_columns]),
                    self.db_table
                )
            self.get_id_key = self.__primary_key__
        else:
            if self.get_id_key is None:
                raise(ValueError("Config error: Query provided without id_key"))
            self.log.debug("Using custom query(ies) on {}".format(self.db_table))

    # Given request params, keep the valid ones for the resource then
    # generate a tuple in the correct order for SQL execute()
    def gen_get_tuple(self, params):
        # Handle query params as follows:
        # TODO: Handle multiple values for same key as SQL 'OR' in WHERE

        # Create an empty list of parameter filter_values
        filter_values = []
        where_clause = ""
        # for each non-id entry in self.db_table_columns ...
        for column, _ in self.db_table_columns[1:]:
            # ... that is also a key in the request query parameters
            if column in params:
                if len(filter_values) == 0:
                    # it's the first matching param, create WHERE Clause
                    where_clause = " WHERE {} = %s ".format(column)
                else:
                    # not the first matching param, add to the WHERE clause
                    where_clause += "AND {} = %s ".format(column)
                # then add its value to the filter_values list
                filter_values.append(params[column])
        # When the process is done, make filters into a tuple ...
        return where_clause, tuple(filter_values)
