import pytest

from anamnesis.config import helius_rpc_url, require


def test_require_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("ANAMNESIS_SMOKE_VAR", "secret-value")
    assert require("ANAMNESIS_SMOKE_VAR") == "secret-value"


def test_require_raises_actionable_error_when_missing(monkeypatch):
    monkeypatch.delenv("ANAMNESIS_SMOKE_VAR", raising=False)
    with pytest.raises(RuntimeError, match="ANAMNESIS_SMOKE_VAR is not set"):
        require("ANAMNESIS_SMOKE_VAR")


def test_require_treats_empty_string_as_missing(monkeypatch):
    monkeypatch.setenv("ANAMNESIS_SMOKE_VAR", "")
    with pytest.raises(RuntimeError):
        require("ANAMNESIS_SMOKE_VAR")


def test_helius_rpc_url_embeds_key_from_env(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "test-key-123")
    assert helius_rpc_url() == "https://mainnet.helius-rpc.com/?api-key=test-key-123"
