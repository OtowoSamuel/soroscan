"""Tests for SECRET_KEY startup warning (issue #423)."""
import logging
import importlib
import sys


def _reload_settings_with_key(monkeypatch, key: str):
    """Reload soroscan.settings with a patched SECRET_KEY env var."""
    monkeypatch.setenv("SECRET_KEY", key)
    # Remove cached module so settings re-evaluates
    mod_name = "soroscan.settings"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def test_warns_for_short_key(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="soroscan.security"):
        _reload_settings_with_key(monkeypatch, "short")
    assert any("SECRET_KEY" in r.message for r in caplog.records)


def test_warns_for_known_default(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="soroscan.security"):
        _reload_settings_with_key(monkeypatch, "django-insecure-change-this-in-production")
    assert any("SECRET_KEY" in r.message for r in caplog.records)


def test_no_warning_for_strong_key(monkeypatch, caplog):
    strong = "a" * 60  # 60 chars, not a known default
    with caplog.at_level(logging.WARNING, logger="soroscan.security"):
        _reload_settings_with_key(monkeypatch, strong)
    assert not any("SECRET_KEY" in r.message for r in caplog.records)
