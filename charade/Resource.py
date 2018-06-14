##################
# Resource.py
# Implements a Resource class based on a database table

import falcon
import json
import logging
from .database import db_obj
from sqlalchemy.inspection import inspect
from sqlalchemy import exc
from sqlalchemy import orm

class Resource(object):
    def __init__(self, res):
        self.log = logging.getLogger()
        self.sqla_obj = res.get('sqla_obj', None)
        if (self.sqla_obj):
            self.name = self.sqla_obj.__name__
            self.__primary_key__ = [k.name for k in inspect(
                                            self.sqla_obj).primary_key][0]
            self.db_table = self.sqla_obj.__table__.name
            self.is_root = False
        else:
            self.is_root = True
            self.name = "Root"
        self.log.debug("__init__ Resource: " + self.name)


    # Handle GET requests to a resource that represents all rows of a single
    # table in the database. If the request contains an id "field expression"
    # then return a single object.
    # ASSUME col 0 of the table in question is called 'id' and type INTEGER
    def on_get(self, req, resp, id=None):
        if self.is_root:
            resp.status = falcon.HTTP_200
            data = []
            for k, v in db_obj.resources.items():
                if k == 'Root':
                    continue
                resource = {
                    "type": "Resource",
                    "id": k,
                    "attributes": {
                        "json_schema": v['json_schema']
                    }
                }
                data.append(resource)
            body = { 'data': data }
            resp.body = json.dumps(body, default=str)
            return

        session = db_obj.get_session()

        included = {}
        if id is not None:
            # a single object was requested
            # The JSON API spec requires that we return one of:
            #   - a single resource object OR resource identifier object
            #   - null

            row = session.query(self.sqla_obj).get(id)
            if (row is not None):
                data = self.__row_to_resource(row)
                resp.status = falcon.HTTP_200

                # get any related child resources here and put them
                # inside included {} declared above

            else:
                # JSON API spec requires 'null' if a resource could
                # but does not exist at this address. In practice
                # this likely won't be used because we're returning 404
                data = None
                resp.status = falcon.HTTP_404

        else:
            # a collection was requested
            # The JSON API spec requires that we return one of:
            #   - an array of resource objects OR resource identifier objects
            #   - an empty array []
            
            rows = session.query(self.sqla_obj)

            # Apply query string filters. If there is more than one value
            # for a given key, return resources matching ANY of those values.
            for k, v in self.validate_params(req.params).items():
                if v.__class__.__name__ != 'list':
                    # filter method expects a list in the in_() clause
                    # https://stackoverflow.com/questions/7942547
                    v = [v]
                rows = rows.filter(getattr(self.sqla_obj, k).in_(v))

            rows = rows.all()
            data = []
            for row in rows:
                data.append(self.__row_to_resource(row))

            resp.status = falcon.HTTP_200


        if resp.status == falcon.HTTP_200:
            body = {'data': data }
            if len(included) > 0:
                body['included'] = included
        else:
            body = { "errors":["Something went south."]}

        resp.body = json.dumps(body, default=str)

    # Create a JSON API resource object from an SQLAlchemy row
    # http://jsonapi.org/format/#document-resource-objects
    def __row_to_resource(self, row):
        attributes = {c.key: getattr(row, c.key)
                for c in inspect(row).mapper.column_attrs}

        # spec requires id to be a string and a type in every object
        resource = {
            "type": self.name, 
            "id": str(attributes['id']) 
        }
        del(attributes['id'])

        # spec requires remaining attributes under "attributes"
        resource['attributes'] = attributes

        return resource

    def on_delete(self, req, resp, id=None):
        if self.is_root or id is None:
            resp.status = falcon.HTTP_405
            body = { 'errors': ['Cannot delete this resource'] }
            resp.body = json.dumps(body, default=str)
            return

        session = db_obj.get_session()

        try:
            # Delete the item with given id
            item = session.query(self.sqla_obj).filter_by(id=id).one()
            session.delete(item)
            session.commit()
            resp.status = falcon.HTTP_200
            body = { 'data': "Deleted item from {} with id {}".format(
                                                        self.name,id) }
            resp.body = json.dumps(body, default=str)
        except orm.exc.NoResultFound as e:
            resp.status = falcon.HTTP_404
            body = { 'errors': ["{} has no item with id {}".format(
                                                        self.name, id)] }
            resp.body = json.dumps(body, default=str)
            return
        except orm.exc.MultipleResultsFound as e:
            resp.status = falcon.HTTP_500
            body = { 'errors': ["{} has multiple items with id: {}. {}".format(
                                                        self.name, id, e)] }
            resp.body = json.dumps(body, default=str)
            return
        except exc.SQLAlchemyError as e:
            session.rollback()
            resp.status = falcon.HTTP_500
            body = { 'errors': [e] }
            resp.body = json.dumps(body, default=str)

    # Handle POST requests to a resource and creates a new row in the table
    # represented by the resource. This method handles incomplete fields-
    # that is to say that fields not provided will be assumed NULL in the
    # database. As a result if the database requires NOT NULL then INSERT will
    # fail and the database will return an error. Assumes the first column
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
        if self.is_root:
            resp.status = falcon.HTTP_405
            body = { 'errors': ['Cannot create resources here'] }
            resp.body = json.dumps(body, default=str)
            return

        # Prevent blocking condition by ensuring content_length > 0
        if req.content_length:
            # capture the request body into data
            data = json.load(req.stream)
            if data.__class__.__name__ == 'dict':
                # Processing a single objects
                resp.status, body = self._insert_into_db( data )
                resp.body = json.dumps({'data':body})
            elif data.__class__.__name__ == 'list':
                # Processing an array of objects
                length = len(data)
                self.log.debug("{} items POSTed.".format(length))
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

    # Validate that the given keys are in the target table
    # then return a python obj to be used as argument for new item constructor
    # This would be a good place for validation (Marshmallow?)
    def gen_insert_dict(self, data):
        col_names = [c.name for c in inspect(self.sqla_obj).columns]
        values = {k: v for k, v in data.items() if k in col_names }
        # serialize python lists and dicts to JSON in the database.
        # Marshmallow should do this eventually
        for k, v in values.items():
            if (v.__class__.__name__ in ['list', 'dict']):
                values[k] = json.dumps(v).encode()
        return values

    def _insert_into_db(self, data):
        session = db_obj.get_session()
        response_body = {}
        if data.__class__.__name__ == 'list':
            # Inserting multiple items (list)
            # http://docs.sqlalchemy.org/en/latest/_modules/examples/performance/bulk_inserts.html
            session.bulk_insert_mappings(self.sqla_obj,
                                    [self.gen_insert_dict(d) for d in data])
            try:
                session.commit()
                response_body['rowcount'] = len(data)
                status = falcon.HTTP_201
            except exc.SQLAlchemyError as e:
                session.rollback()
                response_body['errors'] = ["{}. Rolled back changes.".format(e)]
                status = falcon.HTTP_500

        else:
            # Inserting a single item (dict)
            item_params = self.gen_insert_dict(data)
            item = self.sqla_obj(**item_params)
            session.add(item)
            try:
                session.commit()
                response_body['rowcount'] = 1
                response_body['id'] = item.id
                status = falcon.HTTP_201
            except exc.SQLAlchemyError as e:
                response_body['errors'] = ["{}. Rolled back changes.".format(e)]
                status = falcon.HTTP_500

        return status, response_body

    # Remove query string params that don't match table column names
    # In falcon, where the parameter appears multiple times in the 
    # query string, the value mapped to that parameter key will be a list
    # of all the values in the order seen, otherwise a string.
    # TODO: Actually validate each parameter against the allowed types
    def validate_params(self, params):
        return {k: v for k, v in params.items() 
                                    if k in inspect(self.sqla_obj).columns}
