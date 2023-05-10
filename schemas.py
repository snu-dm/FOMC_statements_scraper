import datetime
from sqlalchemy import (
    Table,
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    DateTime,
    SmallInteger,
    ForeignKey,
    Index,
    ARRAY,
    Boolean,
)
from sqlalchemy.sql.schema import MetaData

metadata = MetaData()


stocks = Table(
    'stocks', metadata,
    Column('stockid', Integer, primary_key=True, autoincrement=True),
    Column('path', String, nullable=False),
    Column('name', String, nullable=False),
    Column('code', String),
    Column('year', Integer),
    Column('quarter', Integer),
    Column('itemtype', String),
    Column('itemindex', String),
    Column('extension', String),
    Column('created', DateTime, default=datetime.datetime.utcnow),
    Column('lastmodified', DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow),
)

minutes = Table(
    'minutes', metadata,
    Column('minuteid', Integer, primary_key=True, autoincrement=True),
    Column('organization', String),
    Column('path', String, nullable=False),
    Column('date', DateTime),
    Column('extension', String),
    Column('created', DateTime, default=datetime.datetime.utcnow),
    Column('lastmodified', DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
)

statements = Table(
    'statements', metadata,
    Column('statementid', Integer, primary_key=True, autoincrement=True),
    Column('path', String, nullable=False),
    Column('organization', String),
    Column('documentdate', DateTime),
    Column('meetingdate_start', DateTime),
    Column('meetingdate_end', DateTime),
    Column('created', DateTime, default=datetime.datetime.utcnow),
    Column('lastmodified', DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
)

