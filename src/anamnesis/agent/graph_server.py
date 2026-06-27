"""A minimal static file server for rendered relationship-graph HTML (B.2).

Decoupled from the Qwen-Agent WebUI (which wraps Gradio and does not cleanly expose its
FastAPI app): app.py runs this in a daemon thread over config.GRAPHS_DIR so the agent's
cluster_graph links resolve. Stdlib-only (no qwen-agent), so it imports in CI.
"""
from __future__ import annotations

import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def make_graph_server(directory: str, port: int) -> ThreadingHTTPServer:
    """Build (but do not start) a threaded HTTP server serving `directory`.

    The directory is created if absent so the server binds cleanly before any graph is
    written. Call `.serve_forever()` (typically in a daemon thread) to run it; pass port=0
    for an OS-assigned port (used in tests). Binds 127.0.0.1 only (never 0.0.0.0): the
    rendered graphs are served behind the host's reverse proxy, never directly on the LAN.
    """
    os.makedirs(directory, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    return ThreadingHTTPServer(("127.0.0.1", port), handler)
