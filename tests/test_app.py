import falcon
import pytest
import json
from falcon import testing

# Set logging level for SQLAlchemy
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

# Initialize the database (from sentinel.py and model.py)
from .config import test_cfg
from sqlalchemy import create_engine
from charade import sentinel
from charade import model
engine = create_engine(test_cfg['db'])
model.Base.metadata.drop_all(engine)
model.Base.metadata.create_all(engine)
sentinel.Base.metadata.drop_all(engine)
sentinel.Base.metadata.create_all(engine)

#TODO: PROBLEM!!! The creation of default row entries by init_sentinel_tables 
# does not reflect the resources in init_model_tables() because the two do 
# not share a common set of MetaData !!!!
# The base used by sentinel.py will always be its own base. What we need to do
# is pass in a base from the fully initialized app after all tables are present.
# This can be achieved by getting a session from database after create() is 
# called and passing it to init_sentinel_tables() instead of an engine.
# We should therefore cleanup the above variable "engine" prior to proceeding
# not sure how to do that or if it's necessary

# Initialize the app for testing
from charade.app import create
from sqlalchemy.orm import Session
api = create(test_cfg)
permissions = {
    test_cfg.get('UNRESTRICTED_ALL_group_oid'): 1,
    test_cfg.get('READ_ALL_group_oid'): 1000
}
sentinel.init_sentinel_tables(Session(engine), model.Base, permissions)
# TODO: delete session and engine used for setup here?

# testing imports
from .assertions import assert_valid_schema

# configure test request headers
media = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json" 
}
auth = {"Authorization": test_cfg['Token'] }


@pytest.fixture
def client():
    return testing.TestClient(api)

# G1: Test get on root unauthenticated 
def test_get_root_unauthenticated(client):
    response = client.simulate_get('/', headers=media)
    assert response.headers['Content-Type'] == "application/vnd.api+json"
    assert response.status == falcon.HTTP_UNAUTHORIZED
    assert response.json['errors'][0]['title'] == "No authorization header provided."
    assert_valid_schema(response.json,"jsonapi.schema.json")

def test_get_root_authenticated(client):
    response = client.simulate_get('/', headers={**media, **auth})
    assert response.headers['Content-Type'] == "application/vnd.api+json"
    assert response.status == falcon.HTTP_OK
    assert_valid_schema(response.json,"jsonapi.schema.json")
    assert_valid_schema(response.json, "root.schema.json" )

# P1: Test POST of valid single object
def test_post_single_locations_authenticated(client):
    # Post body is a JSON API Resource Object
    P1 = { "data": { 
            "type": "Locations",
            "attributes": { 
                "name": "Test Location P1", 
                "address": "123 Sesame St", 
                "city": "Anytown" 
            }}}

    response = client.simulate_post('/Locations', 
        headers={**media, **auth},
        body=json.dumps(P1) # use body since json overwites Content-Type in header
        )
    assert response.headers['Content-Type'] == "application/vnd.api+json"
    assert '/Locations/' in response.headers['Location'] 
    assert response.status == falcon.HTTP_201
    data = response.json['data']
    assert data['type'] == 'Locations'
    assert 'id' in data
    assert data['attributes'] == P1['data']['attributes']


# P2: Test POST multiple objects
def test_post_two_locations_authenticated(client):
    # Post body is *LIKE* a JSON API Resource Object 
    # but "data" is an array of resource objects making 
    # it non-compliant
    P2 = { "data": [{
            "client_id": "P2-1",
            "type": "Locations",
            "attributes": { 
                "name": "Test Location P2 (1 of 2)", 
                "address": "234 Sesame St", 
                "city": "Happyville" 
            }},{
            "client_id": "P2-2", 
            "type": "Locations",
            "attributes": { 
                "name": "Test Location P2 (2 of 2)", 
                "address": "345 Sesame St", 
                "city": "Joyville"
            }}]
        }
    response = client.simulate_post('/Locations', 
        headers={**media, **auth},
        body=json.dumps(P2) # use body since json= overwites Content-Type in header
        )
    assert response.headers['Content-Type'] == "application/vnd.api+json"
    assert response.status == falcon.HTTP_201
    assert response.json['data']['rowcount'] == 2



# G2: Test GET data POSTed in P1 is correct
# G3: Test GET data POSTed in P2 is correct
# G5: Test GET all resources number matches
# D1: Test DELETE first item from P2
# G6: Test GET item deleted in D1, confirm it is gone
# D2: Test DELETE item from P1
# D3: Test DELETE all non-first items from P2
# D4: Test DELETE all items from P3
# G7: Test GET all resources returns zero