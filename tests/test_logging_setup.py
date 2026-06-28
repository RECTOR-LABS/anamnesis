import logging

from anamnesis.logging_setup import quiet_http_loggers


def test_quiet_http_loggers_drops_httpx_info_so_api_key_url_is_not_logged():
    # FastMCP / qwen-agent enable INFO globally, which lets httpx log every request line — and
    # the Helius request URL carries ?api-key=<secret>. After quieting, httpx/httpcore must no
    # longer emit INFO (killing that console leak) while still surfacing real WARNING/ERROR.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.INFO)
    try:
        quiet_http_loggers()
        for name in ("httpx", "httpcore"):
            log = logging.getLogger(name)
            assert log.level == logging.WARNING
            assert not log.isEnabledFor(logging.INFO)
            assert log.isEnabledFor(logging.WARNING)
    finally:
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.NOTSET)
