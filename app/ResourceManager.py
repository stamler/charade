import logging
import json
from Resource import Resource
from database import db_obj

class ResourceManager(object):
    def __init__(self):

        # Configure logging
        self.log = logging.getLogger()
        self.log.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self.log.addHandler(ch)
        self.log.debug("__init__ ResourceManager")

        # Variable initialization
        self.child_resources = db_obj.get_child_resources()
        self.resources = db_obj.get_resources()

        # instantiate resource objects and store references to them
        # within self.resources
        for name, resource in self.resources.items():
            resource['object'] = Resource(name, resource)

        # Enumerate child_resources and populate children property of
        # corresponding parent resource with object references and foreign keys
        for parent, properties in self.child_resources.items():
            for obj in properties:
                self.resources[parent]['children'].append({
                    "object":self.resources[obj['object_name']],
                    "fk": obj['fk']
                })

    def add_routes(self, app):
        # add routes to resources
        for _, resource in self.resources.items():
            for uri in resource['URIs']:
                app.add_route(uri, resource['object'])

rm_obj = ResourceManager()
