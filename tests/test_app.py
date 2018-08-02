# library imports
import falcon
import pytest
import json
from falcon import testing
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# project imports
from charade import sentinel
from charade import model
from charade.app import create

# testing imports
from .assertions import assert_valid_schema
from .config import test_cfg

# configure test request headers
media = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json" 
}
auth = {"Authorization": test_cfg['Token'] }

# Initialize the app for testing
api = create(test_cfg)

# Initialize the database (from sentinel.py and model.py) here
# Mock empty database that matches production parameters
engine = create_engine(test_cfg['db'])
# TODO: fold these into init_sentinel_tables() and init_model_tables()
# and include verification of emptiness prior to create_all()
model.Base.metadata.create_all(engine)
sentinel.Base.metadata.create_all(engine)
session = Session(engine)
sentinel.init_sentinel_tables(session)

@pytest.fixture
def client():
    return testing.TestClient(api)

# G1: Test all methods on root, both authenticated and unauthenticated 
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
                "name": "Test Location", 
                "address": "123 Sesame St", 
                "city": "Anytown" 
            }}}

    response = client.simulate_post('/Locations', 
        headers={**media, **auth},
        body=json.dumps(P1) # use body since json overwites Content-Type in header
        )
    assert response.headers['Content-Type'] == "application/vnd.api+json"
    assert response.status == falcon.HTTP_201
    assert response.json['data']['rowcount'] == 1

# P2: Test POST multiple objects less than max_multi
# P3: Test POST multiple objects greater than max_multi
# G2: Test GET data POSTed in P1 is correct
# G3: Test GET data POSTed in P2 is correct
# G4: Test GET data POSTed in P3 is correct
# G5: Test GET all resources number matches
# D1: Test DELETE first item from P2
# G6: Test GET item deleted in D1, confirm it is gone
# D2: Test DELETE item from P1
# D3: Test DELETE all non-first items from P2
# D4: Test DELETE all items from P3
# G7: Test GET all resources returns zero