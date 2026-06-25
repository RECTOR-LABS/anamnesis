"""CI-runnable checks for the WebUI entrypoint (app.py).

app.py lives at the repo root (outside the importable src/ tree, like the MCP entrypoint), so
it is loaded by file path — mirroring tests/test_mcp_server_registration.py. The WebUI import
is deferred inside app.main(), so loading the module here never requires qwen-agent[gui].
"""
import importlib.util
import pathlib

_APP = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def _load_app():
    spec = importlib.util.spec_from_file_location("anamnesis_app", _APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chatbot_config_carries_demo_affordances():
    app = _load_app()
    cfg = app.CHATBOT_CONFIG
    assert isinstance(cfg["prompt.suggestions"], list) and cfg["prompt.suggestions"]
    assert cfg["verbose"] is True
    assert "Anamnesis" in cfg["input.placeholder"]  # our English placeholder, not the default


def test_main_is_callable():
    app = _load_app()
    assert callable(app.main)
