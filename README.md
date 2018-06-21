# charade

Realtime JSON API translator for SQLAlchemy models

MIT License

Copyright (c) 2018 Dean Stamler

Charade is a Python WSGI application that connects to any database supported by SQLAlchemy and loads the schema defined in model.py. It then presents a sensible JSON API based on that schema. If no model.py is provided, it will use SQLAlchemy Automap to reflect and generate an API automatically. Middleware is provided to authenticate against Microsoft Azure AD.

Charade is built, tested, and deployed inside a Docker container.

## Installation

1. Set mysql and AzureAD environment variables in Dockerfile
2. cd /path/to/charade
3. [optional] edit config.py
4. docker build -t charade .

## Run

docker run -v /path/to/app:/app -p 9090:9090 charade

## Roadmap

- N-to-N relationship behaviour (Users to Projects)
    Users detail should list Projects
      /Users/{id}/Projects
    Projects detail should list Users
      /Projects/{id}/Users
- If a table has more than one foreign key and those FKs each reference tables
  with no Foreign keys, build a many-to-many relationship endpoint:
      i.e. /TableA/{id}/TableB

## API

```http
GET       /
GET       /Resources
GET       /Resources/id
POST      /Resources
PUT/PATCH /Resources/id
DELETE    /Resources/id
```

## Versioned sections of a table

- Move the current FK into the primary table. For example, Computers should have a locations_id column that's an FK referencing locations.id. The old way was to have a joiner table and this is much more complex to query and insert to.
- When inserting a new item into the primary table (ie Computers) include an FK if desired but it's not necessary.
- When updating an item in the primary table (ie Computers) use the runtime inspection API before a flush to verify whether specified attributes have changed. [InstanceState](http://docs.sqlalchemy.org/en/latest/orm/internals.html#sqlalchemy.orm.state.InstanceState) and AttributeState may be the tools used. If one of the specified attributes has been changed, save the _previous value_ to a separate versions table  defined in the model (ie ComputerLocations_history).
