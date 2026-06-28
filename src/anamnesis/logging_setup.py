"""Quiet noisy HTTP-client loggers so the Helius api-key is never logged to the console.

httpx logs a request line ("HTTP Request: POST <url> ...") at INFO. The Helius request URL
carries the api-key as a query string (``helius.py`` builds ``...?api-key=<key>``), so when
something turns on INFO logging — FastMCP in the MCP child process, or qwen-agent in the WebUI
process — that line prints the key to the console. The error paths already scrub the key
(``helius._rpc``), but the INFO request line is httpx's own and bypasses them. Raising the
httpx/httpcore loggers to WARNING drops those INFO request lines while still surfacing genuine
HTTP warnings/errors.

Called from every process entrypoint that drives HTTP under verbose logging: the WebUI
(``app.py``), the MCP server (``mcp/solana_forensics_mcp.py``), and the demo seed/metric
(``demo_seed.main``).
"""
import logging

# httpx emits the request line; httpcore (its transport) can emit connection-level INFO too.
_HTTP_LOGGERS = ("httpx", "httpcore")


def quiet_http_loggers() -> None:
    """Raise httpx/httpcore to WARNING so their INFO request lines — which include the Helius
    api-key in the URL — are not logged.

    This suppresses *all* httpx/httpcore INFO (connection notices included), not just the request
    line — a deliberate trade-off; their WARNING/ERROR still surface. Setting an explicit level on
    these loggers overrides the root level for their own records, so this holds even when FastMCP
    or qwen-agent later configure global INFO logging, and call order relative to them does not
    matter.
    """
    for name in _HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
