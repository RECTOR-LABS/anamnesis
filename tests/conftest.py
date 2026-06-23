"""Shared pytest fixtures and the --store backend switch for the repository contract.

Imports resolve via [tool.pytest.ini_options] pythonpath = ["src"]. The `repo`
fixture lets the A.2/A.3 repository + memory tests run unchanged against either
backend, proving the in-memory fake and the Mongo store agree on the same bodies:

    pytest                  # in-memory fake (default; no DB)
    pytest --store=mongo    # MongoRepository — mongomock when MONGODB_URI is unset
                            # (access-independent CI), real ApsaraDB when it is set
"""
from __future__ import annotations

import os

import pytest

from anamnesis.config import ANAMNESIS_DB
from anamnesis.memory.repository import InMemoryRepository


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--store",
        action="store",
        default="memory",
        choices=("memory", "mongo"),
        help="Repository backend for the contract tests (memory | mongo).",
    )


@pytest.fixture
def repo(request: pytest.FixtureRequest):
    """A fresh, isolated Repository for the selected --store backend."""
    if request.config.getoption("--store") == "memory":
        yield InMemoryRepository()
        return

    # Mongo backend: real ApsaraDB when MONGODB_URI is set, else mongomock so the
    # contract still runs (and verifies the query translation) without a server.
    from anamnesis.memory.mongo_store import MongoRepository

    uri = os.environ.get("MONGODB_URI")
    if uri:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    else:
        import mongomock

        client = mongomock.MongoClient()
    client.drop_database(ANAMNESIS_DB)  # isolate this test from any prior state
    try:
        yield MongoRepository(client, ANAMNESIS_DB)
    finally:
        client.drop_database(ANAMNESIS_DB)
        client.close()
