import json
from os.path import join, dirname
from jsonschema import validate

def assert_valid_schema(data: str, schema_file: str):
    """ return nothing if given data is valid 
        else raise exceptions """

    schema = _load_json_schema_from_file(schema_file)
    return validate(data, schema)

def _load_json_schema_from_file(filename: str) -> str:
    with open(join(dirname(__file__), filename)) as schema_file:
        return json.loads(schema_file.read())