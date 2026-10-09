"""The access log stays on, but the report token never reaches it."""

import logging

from markrounding import accesslog


def access_record(args: tuple) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d', args, None
    )


def test_masks_token_in_spa_and_api_paths():
    f = accesslog.MaskSecretsFilter()
    for path, expected in [
        ("/report/upiJEBrghzlm71gddjXqtwJO", "/report/_token_"),
        ("/api/report/upiJEBrghzlm71gddjXqtwJO/races/2/roundings", "/api/report/_token_/races/2/roundings"),
        ("/api/report/abc?x=1", "/api/report/_token_?x=1"),
        ("/regatta/varregattan", "/regatta/varregattan"),
    ]:
        record = access_record(("10.0.0.1:5000", "GET", path, "1.1", 200))
        assert f.filter(record)
        assert record.getMessage() == f'10.0.0.1:5000 - "GET {expected} HTTP/1.1" 200'


def test_does_not_depend_on_tuple_position():
    # If uvicorn ever reorders its args, the path is still masked.
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, "%s %s %s", ("GET", 200, "/report/abc"), None
    )
    accesslog.MaskSecretsFilter().filter(record)
    assert record.getMessage() == "GET 200 /report/_token_"


def test_leaves_non_path_strings_alone():
    record = access_record(("10.0.0.1:5000", "GET", "/x", "1.1", 200))
    record.args = ("report/abc is not a path",)
    record.msg = "%s"
    accesslog.MaskSecretsFilter().filter(record)
    assert record.getMessage() == "report/abc is not a path"


def test_installed_by_create_app_once(client):
    filters = [f for f in logging.getLogger("uvicorn.access").filters
               if isinstance(f, accesslog.MaskSecretsFilter)]
    assert len(filters) == 1
