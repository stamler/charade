# charade

A Simultaneous Translator for mysql and JSON

MIT License

Copyright (c) 2018 Dean Stamler

Charade is a Python WSGI application that connects to a mysql database, loads the schema, and then presents a sensible JSON API based on that schema. Through configuration, it can also provide finer control over the JSON API it generates. Authentication is provided by Microsoft Azure AD.

Charade is built, tested, and deployed inside a Docker container.

## Installation

1. Set mysql and AzureAD environment variables in Dockerfile
2. cd /path/to/charade
3. [optional] edit config.py
4. docker build -t charade .

## Run

docker run -v /path/to/app:/app -p 9090:9090 charade

## TODO

- Validate both Authentication and Authorization including group membership
- Implement some type of RBAC
- Let's Encrypt integration in the docker container
- Write tests for the AzureADTokenValidator
- Ensure all output (including errors) conforms to [JSON API](http://jsonapi.org/schema)
- Finish all GET requests without customizations
- Build out generalized POST for creating new mysql objects
- Write other Tests and TEST
- Clean up the code and make it generic for deployment
- Build in ability to run against other databases like SQLite, PostgreSQL, or Redshift
- Validator against [JSON schema](http://falcon.readthedocs.io/en/stable/api/media.html?#validating-media)
- Make the only necessary configuration based on an SQLAlchemy model, including validation
- Support versioned one-to-many relationships with joiner tables in SQLAlchemy model config

## Roadmap

- Leverage SQL Alchemy for versioned [joins with history](https://stackoverflow.com/questions/50840869). Some examples are [here](http://docs.sqlalchemy.org/en/latest/orm/examples.html#module-examples.versioned_rows). This is the most [terse example](http://docs.sqlalchemy.org/en/latest/_modules/examples/versioned_rows/versioned_rows.html). Some further potentially useful background [is here](http://docs.sqlalchemy.org/en/latest/orm/nonstandard_mappings.html).
- Foreign Key Handling:
  1-to-N relationship behaviour (SoftwareTitles to SoftwareKeys):
    SoftwareTitles detail should list SoftwareKeys
      /SoftwareTitles/{id}/SoftwareKeys
- 1-to-N relationship behaviour (current and historical) (Locations to Computers)
    Locations detail should list Computers
      /Locations/{id}/Computers
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
GET       /Resources
GET       /Resources/id
POST      /Resources
PUT/PATCH /Resources/id
DELETE    /Resources/id
```

## REST functionality

- Access Control including restriction to users on a specific Azure AD tenant perhaps based on a users table
- Validation of received values against column_type and translation as need (such as datetime)
- Make the code clearer for table, column and type access, perhaps using named tuples
- PATCH and GET where IDs are specified
- POST with multiple entries (likely an extension of the base software like middleware or a plugin)
- More complex queries (likely an extension of the base software like middleware or a plugin)
