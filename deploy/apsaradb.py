"""Alibaba Cloud ApsaraDB for MongoDB connection — the managed memory store.

This module is Anamnesis's proof-of-Alibaba-Cloud-deployment artifact: MONGODB_URI
points at an ApsaraDB-for-MongoDB instance and all memory persistence flows through
this client. It is the file linked as deployment proof in the Devpost submission.

Smoke (gate #2): ``PYTHONPATH=src python deploy/apsaradb.py`` -> ``ApsaraDB OK``.
Prereqs: ``pip install pymongo`` and MONGODB_URI set in .env.
"""

from __future__ import annotations

from pymongo import MongoClient

from anamnesis.config import ANAMNESIS_DB, require


def connect() -> MongoClient:
    """Open a client to the ApsaraDB-for-MongoDB (Alibaba Cloud) instance.

    The connection string is read from MONGODB_URI (env only). A bounded
    server-selection timeout turns an unreachable instance into a fast, actionable
    failure rather than a long hang.
    """
    return MongoClient(require("MONGODB_URI"), serverSelectionTimeoutMS=10000)


def ping() -> None:
    """Confirm the ApsaraDB instance is reachable; prints ``ApsaraDB OK``."""
    connect().admin.command("ping")
    print(f"ApsaraDB OK (db: {ANAMNESIS_DB})")


if __name__ == "__main__":
    ping()
