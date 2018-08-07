# sentinel, the authorization mechanism and used by the middleware

import logging
log = logging.getLogger(__name__)

from sqlalchemy import Table, Column, Integer, ForeignKey, Index, String
from sqlalchemy.orm import relationship, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.expression import insert, literal_column
from sqlalchemy.engine.base import Engine
from typing import Any, List, Tuple


# This declaration is annotated with a comment for 
# mypy because of https://github.com/python/mypy/issues/2477
Base = declarative_base() # type: Any

# Use the provided engine to interact with the database
# https://docs.python.org/3.6/tutorial/classes.html#python-scopes-and-namespaces
def bind_engine(engine: Engine) -> None:
    log.debug("bind_engine() called on sentinel")
    Base.metadata.bind = engine

# Determine whether request is authorized by searching for one or more
# relationships (rows) in the database where both the request and provided
# group_oid can be linked. If 'row' is none, then the request is unauthorized
def authorized(groups: List[str], method: str, resource: str) -> bool:
    # create a new session on every call so changes to db are always reflected
    # Not the best way http://docs.sqlalchemy.org/en/latest/orm/session_basics.html
    #TODO: Fix it, even though it works now, by better understanding sessions
    session = Session(Base.metadata.bind)
    query = session.query(Permissions.group_oid, Roles.name,
                Requests.verb, Requests.resource).\
                join(Roles).\
                join(requests_roles).\
                join(Requests).\
                filter(Permissions.group_oid.in_(groups)).\
                filter(Requests.verb == method).\
                filter(Requests.resource == resource)
    row = query.first()
    if row is None:
        log.debug("Sentinel denied: {} {}".format(method, resource))
        return False
    else:
        log.debug("Sentinel allowed: {}".format(row))
        return True

# The association table for the many-to-many relationship 
# between Requests and Roles. No primary key
requests_roles = Table('_sentinel_requests_roles', Base.metadata,
    Column('requests_id', Integer, ForeignKey('_sentinel_requests.id')),
    Column('roles_id', Integer, ForeignKey('_sentinel_roles.id'))
)

# Requests are endpoints (resource strings not including baseURL)
# with corresponding verbs (HTTP methods). They are keyed to an id. When an
# authenticated request is made sentinel looks up the roles containing the
# request. It then queries permissions for groups that have this role. The 
# request is allowed only if at least one of the groups in the token is 
# assigned a corresponding role. 
class Requests(Base):
    __tablename__ = '_sentinel_requests'
    __table_args__ = (
        Index('request_set', 'verb', 'resource', unique=True),
    )

    id = Column(Integer, primary_key=True)
    verb = Column(String(10), info={'title':'Verb','placeholder':'HTTP method'}, nullable=False)
    resource = Column(String(24), info={'title':'Resource','placeholder': 'Resource Name with preceeding /'}, nullable=False)

    roles = relationship("Roles", secondary=requests_roles,
                                            back_populates="requests")

# Roles bundle together multiple requests so they can have permissions
# assigned to a user or group as a set. They are just a name and an id.
class Roles(Base):
    __tablename__ = '_sentinel_roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(32), info={'title':'Name','placeholder':'Descriptive Role Name'}, nullable=False)

    requests = relationship("Requests", secondary=requests_roles,
                                            back_populates="roles")

# Permissions are mapped sets of Roles and Group OIDs. Group OIDs are managed 
# by AzureAD and provided to charade in the request's bearer token.
class Permissions(Base):
    __tablename__ = '_sentinel_permissions'
    __table_args__ = (
        Index('permission_set', 'group_oid', 'roles_id', unique=True),
    )

    id = Column(Integer, primary_key=True)
    group_oid = Column(String(40), info={'title':'OID','placeholder':'Group OID from Azure AD'}, nullable=False)
    roles_id = Column(ForeignKey('_sentinel_roles.id'), nullable=False, index=True)

    roles = relationship('Roles')

# Populate Requests Table. Run only once at db creation
# to set up all of the API requests for every class.
# Resource URLs are given ids on tens, tens+0 being GET
# Aborts on non-empty table

def init_sentinel_tables(session: Session):

    try:
        # Make sure every table is empty before proceeding
        assert(session.query(requests_roles).first() is None)
        assert(session.query(Requests).first() is None)
        assert(session.query(Roles).first() is None)
        assert(session.query(Permissions).first() is None)
        
        session.add(Requests(id=1,verb='GET',resource='/'))
    
        # First populate requests for every endpoint
        tens = 10
        for subclass in Base.__subclasses__():
            resource = '/' + subclass.__name__
            session.add(Requests(id=tens,verb='GET',resource=resource))
            session.add(Requests(id=tens+1,verb='POST',resource=resource))
            session.add(Requests(id=tens+2,verb='PATCH',resource=resource))
            session.add(Requests(id=tens+3,verb='DELETE',resource=resource))
            session.commit()
            tens += 10

        # Then populate basic standard roles
        session.add(Roles(id=1,name='UNRESTRICTED_ALL'))
        session.add(Roles(id=1000,name='READ_ALL'))
        session.commit()

        # Then populate requests_roles (the join table)
        # INSERT INTO charade_requests_roles (requests_id, roles_id)
        # SELECT id, 1 FROM charade_requests WHERE verb='GET';
        # http://docs.sqlalchemy.org/en/latest/changelog/migration_09.html#insert-from-select
        # http://docs.sqlalchemy.org/en/latest/core/dml.html#sqlalchemy.sql.expression.Insert.from_select
        s = session.query(Requests.id, literal_column("1000")).\
            filter(Requests.verb == 'GET')
        ins = insert(requests_roles).\
            from_select(['requests_id', 'roles_id'], s)
        session.execute(ins)

        # INSERT INTO charade_requests_roles (requests_id, roles_id)
        # SELECT id, 1000 FROM charade_requests;
        s = session.query(Requests.id, literal_column("1"))
        ins = insert(requests_roles).from_select(['requests_id', 'roles_id'], s)
        session.execute(ins)
        session.commit()
        
    except AssertionError:
        log.debug("At least one table is not empty. No changes made.")

def create_sentinel_tables(engine: Engine, rebuild=False):
    if rebuild:
        # Delete all tables that exist and recreate them
        # TODO: !! Confirm that this Base is not shared with model.py!!
        # otherwise set tables=[] to restrict to these tables
        drop_sentinel_tables(engine)

    # Create any tables that don't exist
    log.debug("Creating sentinel tables...")
    Base.metadata.create_all(engine, checkfirst=True)

def drop_sentinel_tables(engine: Engine):
    log.debug("Dropping sentinel tables...")
    Base.metadata.drop_all(engine)
