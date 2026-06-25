"""Phase-0 access smoke (gate #2): confirm the ApsaraDB for MongoDB instance is
reachable and authenticated with the configured URI — the managed store that doubles
as the mandatory "uses Alibaba Cloud" deployment proof artifact.

Prereqs: ``pip install pymongo`` and ANAMNESIS_MONGODB_URI set in .env.
Run:     ``PYTHONPATH=src python scripts/check_mongo.py``
Expect:  ``ANAMNESIS_DB '<db>' reachable -> OK (<n> collections)``.

The URI carries credentials, so it is NEVER printed — on failure only the exception
*type* is surfaced (pymongo errors can echo the connection string), never its message.
"""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from anamnesis.config import ANAMNESIS_DB, require


def main() -> None:
    # require() raises an actionable error if unset; the value (with credentials) is never printed.
    uri = require("ANAMNESIS_MONGODB_URI")
    # Bound server selection so a wrong/unreachable URI fails in ~10s instead of the 30s default.
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")  # server reachable + handshake
        collections = client[ANAMNESIS_DB].list_collection_names()  # auth + DB access
    except PyMongoError as e:
        # pymongo error text can include the host / connection string — surface only the
        # exception type, never str(e), to keep credentials out of logs (see the Helius
        # api-key-leak lesson: secrets travel in driver error messages).
        raise SystemExit(
            f"FAIL: cannot reach ANAMNESIS_MONGODB_URI ({type(e).__name__}). "
            "Check the URI, the DB user/password, and the instance IP allowlist."
        ) from None
    finally:
        client.close()
    print(f"ANAMNESIS_DB '{ANAMNESIS_DB}' reachable -> OK ({len(collections)} collections)")


if __name__ == "__main__":
    main()
