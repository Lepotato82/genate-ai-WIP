"""Unit tests for agents/hero_image_providers.py (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_fetch_pollinations_success(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "POLLINATIONS_TIMEOUT_SECONDS", 30)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.url = "https://image.pollinations.ai/prompt/encoded"

    mock_inst = MagicMock()
    mock_inst.get = MagicMock(return_value=mock_resp)
    mock_inst.__enter__ = lambda self: mock_inst
    mock_inst.__exit__ = lambda *args: None

    mock_cls = MagicMock(return_value=mock_inst)
    monkeypatch.setattr("agents.hero_image_providers.httpx.Client", mock_cls)

    from agents.hero_image_providers import fetch_pollinations

    url, err = fetch_pollinations("soft blue gradient abstract")
    assert err is None
    assert url == "https://image.pollinations.ai/prompt/encoded"
    called_url = mock_inst.get.call_args[0][0]
    assert "pollinations.ai/prompt/" in called_url


def test_fetch_pollinations_bad_content_type(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "POLLINATIONS_TIMEOUT_SECONDS", 30)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}

    mock_inst = MagicMock()
    mock_inst.get = MagicMock(return_value=mock_resp)
    mock_inst.__enter__ = lambda self: mock_inst
    mock_inst.__exit__ = lambda *args: None

    monkeypatch.setattr("agents.hero_image_providers.httpx.Client", MagicMock(return_value=mock_inst))

    from agents.hero_image_providers import fetch_pollinations

    url, err = fetch_pollinations("x")
    assert url is None
    assert err and "content-type" in err


def test_fetch_hero_image_none_provider(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "HERO_IMAGE_PROVIDER", "none")

    from agents.hero_image_providers import fetch_hero_image

    url, err = fetch_hero_image("any prompt")
    assert url is None
    assert err is None


def test_fetch_fal_requires_key(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "HERO_IMAGE_PROVIDER", "fal")
    monkeypatch.setattr(settings, "FAL_API_KEY", "")

    from agents.hero_image_providers import fetch_hero_image

    url, err = fetch_hero_image("prompt")
    assert url is None
    assert err and "FAL_API_KEY" in err
