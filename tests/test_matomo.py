import asyncio

import httpx

from markrounding import matomo


def test_sanitize_path_masks_report_token():
    assert matomo.sanitize_path("/report/upiJEBrghzlm71gddjXqtwJO") == "/report/_token_"
    assert matomo.sanitize_path("/regatta/varregattan") == "/regatta/varregattan"
    assert matomo.sanitize_path("/") == "/"


def test_sanitize_referrer_masks_report_token():
    assert (
        matomo.sanitize_referrer("https://markrounding.example/report/upiJEBrghzlm71gddjXqtwJO")
        == "https://markrounding.example/report/_token_"
    )
    assert (
        matomo.sanitize_referrer("https://markrounding.example/report/abc?x=1#y")
        == "https://markrounding.example/report/_token_?x=1#y"
    )
    assert matomo.sanitize_referrer("https://example.org/regatta/x") == "https://example.org/regatta/x"
    assert matomo.sanitize_referrer("") == ""


def test_should_track_documents_only():
    assert matomo.should_track("GET", "/", 200)
    assert matomo.should_track("GET", "/regatta/varregattan", 200)
    assert matomo.should_track("GET", "/report/abc", 200)
    # API polling, assets and files are excluded
    assert not matomo.should_track("GET", "/api/regattas", 200)
    assert not matomo.should_track("GET", "/assets/index-abc.js", 200)
    assert not matomo.should_track("GET", "/favicon.ico", 200)
    assert not matomo.should_track("POST", "/", 200)
    assert not matomo.should_track("GET", "/finns-inte", 404)


def test_opted_out():
    assert matomo.opted_out({"dnt": "1"})
    assert matomo.opted_out({"sec-gpc": "1"})
    assert not matomo.opted_out({})


def test_build_params_without_token(monkeypatch):
    from markrounding import config

    monkeypatch.setattr(config, "MATOMO_SITE_ID", "7")
    monkeypatch.setattr(config, "MATOMO_TOKEN", "")
    params = matomo.build_params(
        url="https://x.se/", user_agent="UA", lang="sv", referrer="", client_ip="1.2.3.4"
    )
    assert params["idsite"] == "7"
    assert "token_auth" not in params
    assert "cip" not in params
    assert "urlref" not in params


def test_build_params_with_token(monkeypatch):
    from markrounding import config

    monkeypatch.setattr(config, "MATOMO_SITE_ID", "7")
    monkeypatch.setattr(config, "MATOMO_TOKEN", "secret")
    params = matomo.build_params(
        url="https://x.se/", user_agent="UA", lang="sv", referrer="https://y.se", client_ip="1.2.3.4"
    )
    assert params["token_auth"] == "secret"
    assert params["cip"] == "1.2.3.4"
    assert params["urlref"] == "https://y.se"


def _send_with(handler) -> None:
    async def run() -> None:
        matomo._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await matomo._send({"idsite": "7", "token_auth": "secret"})
        finally:
            await matomo._client.aclose()
            matomo._client = None

    asyncio.run(run())


def test_send_logs_rejection_as_warning(monkeypatch, caplog):
    from markrounding import config

    monkeypatch.setattr(config, "MATOMO_URL", "https://stats.example")
    with caplog.at_level("WARNING", logger="markrounding.matomo"):
        _send_with(lambda request: httpx.Response(400, text="requires valid token_auth"))
    assert "HTTP 400" in caplog.text and "requires valid token_auth" in caplog.text


def test_send_success_is_quiet(monkeypatch, caplog):
    from markrounding import config

    monkeypatch.setattr(config, "MATOMO_URL", "https://stats.example")
    with caplog.at_level("WARNING", logger="markrounding.matomo"):
        _send_with(lambda request: httpx.Response(204))
    assert caplog.text == ""
