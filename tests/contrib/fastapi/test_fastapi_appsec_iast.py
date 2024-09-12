import json
import sys
import typing

from fastapi import Cookie
from fastapi import Header
from fastapi import Request
from fastapi import __version__ as _fastapi_version
from fastapi.responses import JSONResponse
import pytest

from ddtrace.appsec._constants import IAST
from ddtrace.appsec._handlers import _on_asgi_request_parse_body
from ddtrace.appsec._iast import oce
from ddtrace.appsec._iast._patch import _on_iast_fastapi_patch
from ddtrace.appsec._iast.constants import VULN_SQL_INJECTION
from ddtrace.appsec._iast.taint_sinks.header_injection import patch as patch_header_injection
from ddtrace.contrib.sqlite3.patch import patch as patch_sqlite_sqli
from ddtrace.internal import core
from tests.appsec.iast.iast_utils import get_line_and_hash
from tests.utils import override_env
from tests.utils import override_global_config


IAST_ENV = {"DD_IAST_REQUEST_SAMPLING": "100"}

TEST_FILE_PATH = "tests/contrib/fastapi/test_fastapi_appsec_iast.py"

fastapi_version = tuple([int(v) for v in _fastapi_version.split(".")])


def _aux_appsec_prepare_tracer(tracer):
    _on_iast_fastapi_patch()
    patch_sqlite_sqli()
    patch_header_injection()
    oce.reconfigure()

    tracer._iast_enabled = True
    # Hack: need to pass an argument to configure so that the processors are recreated
    tracer.configure(api_version="v0.4")


def get_response_body(response):
    return response.text


def get_root_span(spans):
    return spans.pop_traces()[0][0]


@pytest.fixture
def setup_core_ok_after_test():
    yield
    core.on("asgi.request.parse.body", _on_asgi_request_parse_body, "await_receive_and_body")


@pytest.mark.usefixtures("setup_core_ok_after_test")
def test_query_param_source(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html")
    async def test_route(request: Request):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        query_params = request.query_params.get("iast_queryparam")
        ranges_result = get_tainted_ranges(query_params)

        return JSONResponse(
            {
                "result": query_params,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html?iast_queryparam=test1234",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.parameter"


@pytest.mark.usefixtures("setup_core_ok_after_test")
def test_header_value_source(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html")
    async def test_route(request: Request):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        query_params = request.headers.get("iast_header")
        ranges_result = get_tainted_ranges(query_params)

        return JSONResponse(
            {
                "result": query_params,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html",
            headers={"iast_header": "test1234"},
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.header"


@pytest.mark.usefixtures("setup_core_ok_after_test")
@pytest.mark.skipif(sys.version_info < (3, 9), reason="typing.Annotated was introduced on 3.9")
@pytest.mark.skipif(fastapi_version < (0, 95, 0), reason="Header annotation doesn't work on fastapi 94 or lower")
def test_header_value_source_typing_param(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html")
    async def test_route(iast_header: typing.Annotated[str, Header()] = None):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        ranges_result = get_tainted_ranges(iast_header)

        return JSONResponse(
            {
                "result": iast_header,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        _aux_appsec_prepare_tracer(tracer)

        resp = client.get(
            "/index.html",
            headers={"iast-header": "test1234"},
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.header"


@pytest.mark.usefixtures("setup_core_ok_after_test")
def test_cookies_source(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html")
    async def test_route(request: Request):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        query_params = request.cookies.get("iast_cookie")
        ranges_result = get_tainted_ranges(query_params)
        return JSONResponse(
            {
                "result": query_params,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html",
            cookies={"iast_cookie": "test1234"},
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.cookie.value"


@pytest.mark.usefixtures("setup_core_ok_after_test")
@pytest.mark.skipif(sys.version_info < (3, 9), reason="typing.Annotated was introduced on 3.9")
@pytest.mark.skipif(fastapi_version < (0, 95, 0), reason="Cookie annotation doesn't work on fastapi 94 or lower")
def test_cookies_source_typing_param(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html")
    async def test_route(iast_cookie: typing.Annotated[str, Cookie()] = "ddd"):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        ranges_result = get_tainted_ranges(iast_cookie)

        return JSONResponse(
            {
                "result": iast_cookie,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html",
            cookies={"iast_cookie": "test1234"},
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.cookie.value"


@pytest.mark.usefixtures("setup_core_ok_after_test")
def test_path_param_source(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html/{item_id}")
    async def test_route(item_id):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        ranges_result = get_tainted_ranges(item_id)

        return JSONResponse(
            {
                "result": item_id,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html/test1234/",
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "test1234"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 8
        assert result["ranges_origin"] == "http.request.path.parameter"


def test_path_source(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/path_source/")
    async def test_route(request: Request):
        from ddtrace.appsec._iast._taint_tracking import get_tainted_ranges
        from ddtrace.appsec._iast._taint_tracking import origin_to_str

        path = request.url.path
        ranges_result = get_tainted_ranges(path)

        return JSONResponse(
            {
                "result": path,
                "is_tainted": len(ranges_result),
                "ranges_start": ranges_result[0].start,
                "ranges_length": ranges_result[0].length,
                "ranges_origin": origin_to_str(ranges_result[0].source.origin),
            }
        )

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/path_source/",
        )
        assert resp.status_code == 200
        result = json.loads(get_response_body(resp))
        assert result["result"] == "/path_source/"
        assert result["is_tainted"] == 1
        assert result["ranges_start"] == 0
        assert result["ranges_length"] == 13
        assert result["ranges_origin"] == "http.request.path"


def test_fastapi_sqli_path_param(fastapi_application, client, tracer, test_spans):
    @fastapi_application.get("/index.html/{param_str}")
    async def test_route(param_str):
        import sqlite3

        from ddtrace.appsec._iast._taint_tracking import is_pyobject_tainted
        from ddtrace.appsec._iast._taint_tracking.aspects import add_aspect

        assert is_pyobject_tainted(param_str)

        con = sqlite3.connect(":memory:")
        cur = con.cursor()
        # label test_fastapi_sqli_path_parameter
        cur.execute(add_aspect("SELECT 1 FROM ", param_str))

    # test if asgi middleware is ok without any callback registered
    core.reset_listeners(event_id="asgi.request.parse.body")

    with override_global_config(dict(_iast_enabled=True, _deduplication_enabled=False)), override_env(IAST_ENV):
        # disable callback
        _aux_appsec_prepare_tracer(tracer)
        resp = client.get(
            "/index.html/sqlite_master/",
        )
        assert resp.status_code == 200

        span = test_spans.pop_traces()[1][0]
        assert span.get_metric(IAST.ENABLED) == 1.0

        loaded = json.loads(span.get_tag(IAST.JSON))

        assert loaded["sources"] == [
            {"origin": "http.request.path.parameter", "name": "param_str", "value": "sqlite_master"}
        ]

        line, hash_value = get_line_and_hash(
            "test_fastapi_sqli_path_parameter", VULN_SQL_INJECTION, filename=TEST_FILE_PATH
        )
        vulnerability = loaded["vulnerabilities"][0]
        assert vulnerability["type"] == VULN_SQL_INJECTION
        assert vulnerability["evidence"] == {
            "valueParts": [
                {"value": "SELECT "},
                {"redacted": True},
                {"value": " FROM "},
                {"value": "sqlite_master", "source": 0},
            ]
        }
        assert vulnerability["location"]["line"] == line
        assert vulnerability["location"]["path"] == TEST_FILE_PATH
        assert vulnerability["hash"] == hash_value