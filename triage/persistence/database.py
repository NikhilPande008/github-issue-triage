from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_engine_from_url(database_url: str):
    return create_engine(database_url)


def create_session_factory(database_url: str) -> sessionmaker:
    return sessionmaker(bind=create_engine_from_url(database_url), expire_on_commit=False)
