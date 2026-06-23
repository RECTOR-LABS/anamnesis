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

from anamnesis import config
from anamnesis.memory.repository import InMemoryRepository

# A dedicated, disposable database for the contract tests — deliberately NOT the
# configured production db (config.ANAMNESIS_DB), so running the contract against a
# live MONGODB_URI can never drop real forensic memory.
CONTRACT_DB = "anamnesis_contract_test"


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

    # Enforce the disposable-DB invariant instead of trusting the literals differ: a
    # rename or an ANAMNESIS_DB override that collides here would drop production memory.
    if CONTRACT_DB == config.ANAMNESIS_DB:
        raise RuntimeError(
            f"contract DB {CONTRACT_DB!r} must differ from the production db "
            "(config.ANAMNESIS_DB); refusing to run to avoid dropping real memory"
        )

    if uri := os.environ.get("MONGODB_URI"):
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    else:
        import mongomock

        client = mongomock.MongoClient()
    try:
        client.drop_database(CONTRACT_DB)  # isolate this test from any prior run
        yield MongoRepository(client, CONTRACT_DB)
    finally:
        try:
            client.drop_database(CONTRACT_DB)
        finally:
            client.close()  # always release the client, even if cleanup raised
