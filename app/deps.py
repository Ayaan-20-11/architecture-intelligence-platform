from collections.abc import Iterator

import neo4j
from fastapi import Request

from app.graph.repository import open_session
from app.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_driver(request: Request) -> neo4j.Driver:
    return request.app.state.driver


def get_read_session(request: Request) -> Iterator[neo4j.Session]:
    settings = get_settings(request)
    driver = get_driver(request)
    with open_session(driver, database=settings.config.graph.database, read_only=True) as session:
        yield session
