"""
SQLAlchemy engine — import this wherever a DB connection is needed.
"""

from sqlalchemy import create_engine

from config.settings import DB

engine = create_engine(DB.url, pool_pre_ping=True)
