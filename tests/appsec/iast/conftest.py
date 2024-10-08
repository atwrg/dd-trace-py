import logging
import re

import pytest

from ddtrace.appsec._common_module_patches import patch_common_modules
from ddtrace.appsec._common_module_patches import unpatch_common_modules
from ddtrace.appsec._constants import IAST
from ddtrace.appsec._iast import oce
from ddtrace.appsec._iast._iast_request_context import end_iast_context
from ddtrace.appsec._iast._iast_request_context import set_iast_request_enabled
from ddtrace.appsec._iast._iast_request_context import start_iast_context
from ddtrace.appsec._iast._patches.json_tainting import patch as json_patch
from ddtrace.appsec._iast._patches.json_tainting import unpatch_iast as json_unpatch
from ddtrace.appsec._iast.processor import AppSecIastSpanProcessor
from ddtrace.appsec._iast.taint_sinks._base import VulnerabilityBase
from ddtrace.appsec._iast.taint_sinks.command_injection import patch as cmdi_patch
from ddtrace.appsec._iast.taint_sinks.command_injection import unpatch as cmdi_unpatch
from ddtrace.appsec._iast.taint_sinks.header_injection import patch as header_injection_patch
from ddtrace.appsec._iast.taint_sinks.header_injection import unpatch as header_injection_unpatch
from ddtrace.appsec._iast.taint_sinks.weak_cipher import patch as weak_cipher_patch
from ddtrace.appsec._iast.taint_sinks.weak_cipher import unpatch_iast as weak_cipher_unpatch
from ddtrace.appsec._iast.taint_sinks.weak_hash import patch as weak_hash_patch
from ddtrace.appsec._iast.taint_sinks.weak_hash import unpatch_iast as weak_hash_unpatch
from ddtrace.contrib.sqlite3.patch import patch as sqli_sqlite_patch
from ddtrace.contrib.sqlite3.patch import unpatch as sqli_sqlite_unpatch
from tests.utils import override_env
from tests.utils import override_global_config


@pytest.fixture
def no_request_sampling(tracer):
    with override_env(
        {
            "DD_IAST_REQUEST_SAMPLING": "100",
            "DD_IAST_MAX_CONCURRENT_REQUEST": "100",
        }
    ):
        oce.reconfigure()
        yield


def iast_span(tracer, env, request_sampling="100", deduplication=False):
    # TODO!! DELETE ME!!!
    try:
        from ddtrace.contrib.langchain.patch import patch as langchain_patch
        from ddtrace.contrib.langchain.patch import unpatch as langchain_unpatch
    except Exception:
        langchain_patch = lambda: True  # noqa: E731
        langchain_unpatch = lambda: True  # noqa: E731
    try:
        from ddtrace.contrib.sqlalchemy.patch import patch as sqlalchemy_patch
        from ddtrace.contrib.sqlalchemy.patch import unpatch as sqlalchemy_unpatch
    except Exception:
        sqlalchemy_patch = lambda: True  # noqa: E731
        sqlalchemy_unpatch = lambda: True  # noqa: E731
    try:
        from ddtrace.contrib.psycopg.patch import patch as psycopg_patch
        from ddtrace.contrib.psycopg.patch import unpatch as psycopg_unpatch
    except Exception:
        psycopg_patch = lambda: True  # noqa: E731
        psycopg_unpatch = lambda: True  # noqa: E731

    env.update({"DD_IAST_REQUEST_SAMPLING": request_sampling})
    iast_span_processor = AppSecIastSpanProcessor()
    VulnerabilityBase._reset_cache_for_testing()
    with override_global_config(dict(_iast_enabled=True, _deduplication_enabled=deduplication)), override_env(env):
        oce.reconfigure()
        with tracer.trace("test") as span:
            span.span_type = "web"
            weak_hash_patch()
            weak_cipher_patch()
            sqli_sqlite_patch()
            json_patch()
            psycopg_patch()
            sqlalchemy_patch()
            cmdi_patch()
            header_injection_patch()
            langchain_patch()
            iast_span_processor.on_span_start(span)
            patch_common_modules()
            yield span
            unpatch_common_modules()
            iast_span_processor.on_span_finish(span)
            weak_hash_unpatch()
            weak_cipher_unpatch()
            sqli_sqlite_unpatch()
            json_unpatch()
            psycopg_unpatch()
            sqlalchemy_unpatch()
            cmdi_unpatch()
            header_injection_unpatch()
            langchain_unpatch()


def iast_context(env, request_sampling="100", deduplication=False):
    try:
        from ddtrace.contrib.langchain.patch import patch as langchain_patch
        from ddtrace.contrib.langchain.patch import unpatch as langchain_unpatch
    except Exception:
        langchain_patch = lambda: True  # noqa: E731
        langchain_unpatch = lambda: True  # noqa: E731
    try:
        from ddtrace.contrib.sqlalchemy.patch import patch as sqlalchemy_patch
        from ddtrace.contrib.sqlalchemy.patch import unpatch as sqlalchemy_unpatch
    except Exception:
        sqlalchemy_patch = lambda: True  # noqa: E731
        sqlalchemy_unpatch = lambda: True  # noqa: E731
    try:
        from ddtrace.contrib.psycopg.patch import patch as psycopg_patch
        from ddtrace.contrib.psycopg.patch import unpatch as psycopg_unpatch
    except Exception:
        psycopg_patch = lambda: True  # noqa: E731
        psycopg_unpatch = lambda: True  # noqa: E731

    env.update({"DD_IAST_REQUEST_SAMPLING": request_sampling, "_DD_APPSEC_DEDUPLICATION_ENABLED": str(deduplication)})
    VulnerabilityBase._reset_cache_for_testing()
    with override_global_config(dict(_iast_enabled=True, _deduplication_enabled=deduplication)), override_env(env):
        oce.reconfigure()
        start_iast_context()
        oce.acquire_request(None)
        set_iast_request_enabled(True)
        weak_hash_patch()
        weak_cipher_patch()
        sqli_sqlite_patch()
        json_patch()
        psycopg_patch()
        sqlalchemy_patch()
        cmdi_patch()
        header_injection_patch()
        langchain_patch()
        patch_common_modules()
        yield
        unpatch_common_modules()
        weak_hash_unpatch()
        weak_cipher_unpatch()
        sqli_sqlite_unpatch()
        json_unpatch()
        psycopg_unpatch()
        sqlalchemy_unpatch()
        cmdi_unpatch()
        header_injection_unpatch()
        langchain_unpatch()
        end_iast_context()
        oce.release_request()


@pytest.fixture
def iast_context_defaults():
    yield from iast_context(dict(DD_IAST_ENABLED="true"))


@pytest.fixture
def iast_context_deduplication_enabled(tracer):
    yield from iast_context(dict(DD_IAST_ENABLED="true"), deduplication=True)


@pytest.fixture
def iast_span_defaults(tracer):
    # TODO!! DELETE ME!!!
    yield from iast_span(tracer, dict(DD_IAST_ENABLED="true"))


@pytest.fixture
def iast_span_deduplication_enabled(tracer):
    # TODO!! DELETEME
    yield from iast_span(tracer, dict(DD_IAST_ENABLED="true"), deduplication=True)


# The log contains "[IAST]" but "[IAST] create_context" or "[IAST] reset_context" are valid
IAST_VALID_LOG = re.compile(r"(?=.*\[IAST\] )(?!.*\[IAST\] (create_context|reset_context))")


@pytest.fixture(autouse=True)
def check_native_code_exception_in_each_python_aspect_test(request, caplog):
    if "skip_iast_check_logs" in request.keywords:
        yield
    else:
        with override_env({IAST.ENV_DEBUG: "true"}), caplog.at_level(logging.DEBUG):
            yield

        log_messages = [record.message for record in caplog.get_records("call")]

        for message in log_messages:
            if IAST_VALID_LOG.search(message):
                pytest.fail(message)
        # TODO(avara1986): iast tests throw a timeout in gitlab
        #   list_metrics_logs = list(telemetry_writer._logs)
        #   assert len(list_metrics_logs) == 0
