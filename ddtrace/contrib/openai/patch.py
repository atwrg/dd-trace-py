import os
import sys

from openai import version

from ddtrace import config
from ddtrace.internal.llmobs.integrations import OpenAIIntegration
from ddtrace.internal.logger import get_logger
from ddtrace.internal.schema import schematize_service_name
from ddtrace.internal.utils.formats import asbool
from ddtrace.internal.utils.formats import deep_getattr
from ddtrace.internal.utils.version import parse_version
from ddtrace.internal.wrapping import wrap

from ...pin import Pin
from . import _endpoint_hooks
from .utils import _format_openai_api_key


log = get_logger(__name__)


config._add(
    "openai",
    {
        "logs_enabled": asbool(os.getenv("DD_OPENAI_LOGS_ENABLED", False)),
        "metrics_enabled": asbool(os.getenv("DD_OPENAI_METRICS_ENABLED", True)),
        "span_prompt_completion_sample_rate": float(os.getenv("DD_OPENAI_SPAN_PROMPT_COMPLETION_SAMPLE_RATE", 1.0)),
        "log_prompt_completion_sample_rate": float(os.getenv("DD_OPENAI_LOG_PROMPT_COMPLETION_SAMPLE_RATE", 0.1)),
        "span_char_limit": int(os.getenv("DD_OPENAI_SPAN_CHAR_LIMIT", 128)),
    },
)


def get_version():
    # type: () -> str
    return version.VERSION


OPENAI_VERSION = parse_version(get_version())


if OPENAI_VERSION >= (1, 0, 0):
    _RESOURCES = {
        "models.Models": {
            "list": _endpoint_hooks._ModelListHook,
            "retrieve": _endpoint_hooks._ModelRetrieveHook,
            "delete": _endpoint_hooks._ModelDeleteHook,
        },
        "completions.Completions": {
            "create": _endpoint_hooks._CompletionHook,
        },
        "chat.Completions": {
            "create": _endpoint_hooks._ChatCompletionHook,
        },
        "edits.Edits": {
            "create": _endpoint_hooks._EditHook,
        },
        "images.Images": {
            "generate": _endpoint_hooks._ImageCreateHook,
            "edit": _endpoint_hooks._ImageEditHook,
            "create_variation": _endpoint_hooks._ImageVariationHook,
        },
        "audio.Transcriptions": {
            "create": _endpoint_hooks._AudioTranscriptionHook,
        },
        "audio.Translations": {
            "create": _endpoint_hooks._AudioTranslationHook,
        },
        "embeddings.Embeddings": {
            "create": _endpoint_hooks._EmbeddingHook,
        },
        "moderations.Moderations": {
            "create": _endpoint_hooks._ModerationHook,
        },
        "files.Files": {
            "create": _endpoint_hooks._FileCreateHook,
            "retrieve": _endpoint_hooks._FileRetrieveHook,
            "list": _endpoint_hooks._FileListHook,
            "delete": _endpoint_hooks._FileDeleteHook,
            "retrieve_content": _endpoint_hooks._FileDownloadHook,
        },
        "fine_tunes.FineTunes": {
            "create": _endpoint_hooks._FineTuneCreateHook,
            "retrieve": _endpoint_hooks._FineTuneRetrieveHook,
            "list": _endpoint_hooks._FineTuneListHook,
            "cancel": _endpoint_hooks._FineTuneCancelHook,
            "list_events": _endpoint_hooks._FineTuneListEventsHook,
        },
    }
else:
    _RESOURCES = {
        "model.Model": {
            "list": _endpoint_hooks._ListHook,
            "retrieve": _endpoint_hooks._RetrieveHook,
        },
        "completion.Completion": {
            "create": _endpoint_hooks._CompletionHook,
        },
        "chat_completion.ChatCompletion": {
            "create": _endpoint_hooks._ChatCompletionHook,
        },
        "edit.Edit": {
            "create": _endpoint_hooks._EditHook,
        },
        "image.Image": {
            "create": _endpoint_hooks._ImageCreateHook,
            "create_edit": _endpoint_hooks._ImageEditHook,
            "create_variation": _endpoint_hooks._ImageVariationHook,
        },
        "audio.Audio": {
            "transcribe": _endpoint_hooks._AudioTranscriptionHook,
            "translate": _endpoint_hooks._AudioTranslationHook,
        },
        "embedding.Embedding": {
            "create": _endpoint_hooks._EmbeddingHook,
        },
        "moderation.Moderation": {
            "create": _endpoint_hooks._ModerationHook,
        },
        "file.File": {
            # File.list() and File.retrieve() share the same underlying method as Model.list() and Model.retrieve()
            # which means they are already wrapped
            "create": _endpoint_hooks._FileCreateHook,
            "delete": _endpoint_hooks._DeleteHook,
            "download": _endpoint_hooks._FileDownloadHook,
        },
        "fine_tune.FineTune": {
            # FineTune.list()/retrieve() share the same underlying method as Model.list() and Model.retrieve()
            # FineTune.delete() share the same underlying method as File.delete()
            # which means they are already wrapped
            # FineTune.list_events does not have an async version, so have to wrap it separately
            "create": _endpoint_hooks._FineTuneCreateHook,
            "cancel": _endpoint_hooks._FineTuneCancelHook,
        },
    }


def _wrap_classmethod(obj, wrapper):
    wrap(obj.__func__, wrapper)


def patch():
    # Avoid importing openai at the module level, eventually will be an import hook
    import openai

    if getattr(openai, "__datadog_patch", False):
        return

    Pin().onto(openai)
    integration = OpenAIIntegration(integration_config=config.openai, openai=openai)

    if OPENAI_VERSION >= (1, 0, 0):
        if OPENAI_VERSION >= (1, 8, 0):
            wrap(openai._base_client.SyncAPIClient._process_response, _patched_convert(openai, integration))
            wrap(openai._base_client.AsyncAPIClient._process_response, _patched_convert(openai, integration))
        else:
            wrap(openai._base_client.BaseClient._process_response, _patched_convert(openai, integration))
        wrap(openai.OpenAI.__init__, _patched_client_init(openai, integration))
        wrap(openai.AsyncOpenAI.__init__, _patched_client_init(openai, integration))
        wrap(openai.AzureOpenAI.__init__, _patched_client_init(openai, integration))
        wrap(openai.AsyncAzureOpenAI.__init__, _patched_client_init(openai, integration))

        for resource, method_hook_dict in _RESOURCES.items():
            if deep_getattr(openai.resources, resource) is None:
                continue
            for method_name, endpoint_hook in method_hook_dict.items():
                sync_method = deep_getattr(openai.resources, "%s.%s" % (resource, method_name))
                async_method = deep_getattr(
                    openai.resources, "%s.%s" % (".Async".join(resource.split(".")), method_name)
                )
                wrap(sync_method, _patched_endpoint(openai, integration, endpoint_hook))
                wrap(async_method, _patched_endpoint_async(openai, integration, endpoint_hook))
    else:
        import openai.api_requestor

        wrap(openai.api_requestor._make_session, _patched_make_session)
        wrap(openai.util.convert_to_openai_object, _patched_convert(openai, integration))

        for resource, method_hook_dict in _RESOURCES.items():
            if deep_getattr(openai.api_resources, resource) is None:
                continue
            for method_name, endpoint_hook in method_hook_dict.items():
                sync_method = deep_getattr(openai.api_resources, "%s.%s" % (resource, method_name))
                async_method = deep_getattr(openai.api_resources, "%s.a%s" % (resource, method_name))
                _wrap_classmethod(sync_method, _patched_endpoint(openai, integration, endpoint_hook))
                _wrap_classmethod(async_method, _patched_endpoint_async(openai, integration, endpoint_hook))

        # FineTune.list_events is the only traced endpoint that does not have an async version, so have to wrap it here.
        _wrap_classmethod(
            openai.api_resources.fine_tune.FineTune.list_events,
            _patched_endpoint(openai, integration, _endpoint_hooks._FineTuneListEventsHook),
        )

    openai.__datadog_patch = True


def unpatch():
    # FIXME: add unpatching. The current wrapping.unwrap method requires
    #        the wrapper function to be provided which we don't keep a reference to.
    pass


def _patched_client_init(openai, integration):
    """
    Patch for `openai.OpenAI/AsyncOpenAI` client init methods to add the client object to the OpenAIIntegration object.
    """

    def patched_client_init(func, args, kwargs):
        func(*args, **kwargs)
        client = args[0]
        integration._client = client
        api_key = kwargs.get("api_key")
        if api_key is None:
            api_key = client.api_key
        if api_key is not None:
            integration.user_api_key = api_key
        return

    return patched_client_init


def _patched_make_session(func, args, kwargs):
    """Patch for `openai.api_requestor._make_session` which sets the service name on the
    requests session so that spans from the requests integration will use the service name openai.
    This is done so that the service break down will include OpenAI time spent querying the OpenAI backend.

    This should technically be a ``peer.service`` but this concept doesn't exist yet.
    """
    session = func(*args, **kwargs)
    service = schematize_service_name("openai")
    Pin.override(session, service=service)
    return session


def _traced_endpoint(endpoint_hook, integration, pin, args, kwargs):
    span = integration.trace(pin, endpoint_hook.OPERATION_ID)
    openai_api_key = _format_openai_api_key(kwargs.get("api_key"))
    err = None
    if openai_api_key:
        # API key can either be set on the import or per request
        span.set_tag_str("openai.user.api_key", openai_api_key)
    try:
        # Start the hook
        hook = endpoint_hook().handle_request(pin, integration, span, args, kwargs)
        hook.send(None)

        resp, err = yield

        # Record any error information
        if err is not None:
            span.set_exc_info(*sys.exc_info())
            integration.metric(span, "incr", "request.error", 1)

        # Pass the response and the error to the hook
        try:
            hook.send((resp, err))
        except StopIteration as e:
            if err is None:
                return e.value
    finally:
        # Streamed responses will be finished when the generator exits, so finish non-streamed spans here.
        # Streamed responses with error will need to be finished manually as well.
        if not kwargs.get("stream") or err is not None:
            span.finish()
            integration.metric(span, "dist", "request.duration", span.duration_ns)


def _patched_endpoint(openai, integration, patch_hook):
    def patched_endpoint(func, args, kwargs):
        # FIXME: this is a temporary workaround for the fact that our bytecode wrapping seems to modify
        #        a function keyword argument into a cell when it shouldn't. This is only an issue on
        #        Python 3.11+.
        if sys.version_info >= (3, 11) and kwargs.get("encoding_format", None):
            kwargs["encoding_format"] = kwargs["encoding_format"].cell_contents

        pin = Pin._find(openai, args[0])
        if not pin or not pin.enabled():
            return func(*args, **kwargs)

        g = _traced_endpoint(patch_hook, integration, pin, args, kwargs)
        g.send(None)
        resp, err = None, None
        try:
            resp = func(*args, **kwargs)
            return resp
        except Exception as e:
            err = e
            raise
        finally:
            try:
                g.send((resp, err))
            except StopIteration as e:
                if err is None:
                    # This return takes priority over `return resp`
                    return e.value  # noqa: B012

    return patched_endpoint


def _patched_endpoint_async(openai, integration, patch_hook):
    # Same as _patched_endpoint but async
    async def patched_endpoint(func, args, kwargs):
        # FIXME: this is a temporary workaround for the fact that our bytecode wrapping seems to modify
        #        a function keyword argument into a cell when it shouldn't. This is only an issue on
        #        Python 3.11+.
        if sys.version_info >= (3, 11) and kwargs.get("encoding_format", None):
            kwargs["encoding_format"] = kwargs["encoding_format"].cell_contents

        pin = Pin._find(openai, args[0])
        if not pin or not pin.enabled():
            return await func(*args, **kwargs)
        g = _traced_endpoint(patch_hook, integration, pin, args, kwargs)
        g.send(None)
        resp, err = None, None
        try:
            resp = await func(*args, **kwargs)
            return resp
        except Exception as e:
            err = e
            raise
        finally:
            try:
                g.send((resp, err))
            except StopIteration as e:
                if err is None:
                    # This return takes priority over `return resp`
                    return e.value  # noqa: B012

    return patched_endpoint


def _patched_convert(openai, integration):
    def patched_convert(func, args, kwargs):
        """Patch convert captures header information in the openai response"""
        pin = Pin.get_from(openai)
        if not pin or not pin.enabled():
            return func(*args, **kwargs)

        span = pin.tracer.current_span()
        if not span:
            return func(*args, **kwargs)

        if OPENAI_VERSION < (1, 0, 0):
            resp = args[0]
            if not isinstance(resp, openai.openai_response.OpenAIResponse):
                return func(*args, **kwargs)
            headers = resp._headers
        else:
            resp = kwargs.get("response", {})
            headers = resp.headers
        # This function is called for each chunk in the stream.
        # To prevent needlessly setting the same tags for each chunk, short-circuit here.
        if span.get_tag("openai.organization.name") is not None:
            return func(*args, **kwargs)
        if headers.get("openai-organization"):
            org_name = headers.get("openai-organization")
            span.set_tag_str("openai.organization.name", org_name)

        # Gauge total rate limit
        if headers.get("x-ratelimit-limit-requests"):
            v = headers.get("x-ratelimit-limit-requests")
            if v is not None:
                integration.metric(span, "gauge", "ratelimit.requests", int(v))
                span.set_metric("openai.organization.ratelimit.requests.limit", int(v))
        if headers.get("x-ratelimit-limit-tokens"):
            v = headers.get("x-ratelimit-limit-tokens")
            if v is not None:
                integration.metric(span, "gauge", "ratelimit.tokens", int(v))
                span.set_metric("openai.organization.ratelimit.tokens.limit", int(v))
        # Gauge and set span info for remaining requests and tokens
        if headers.get("x-ratelimit-remaining-requests"):
            v = headers.get("x-ratelimit-remaining-requests")
            if v is not None:
                integration.metric(span, "gauge", "ratelimit.remaining.requests", int(v))
                span.set_metric("openai.organization.ratelimit.requests.remaining", int(v))
        if headers.get("x-ratelimit-remaining-tokens"):
            v = headers.get("x-ratelimit-remaining-tokens")
            if v is not None:
                integration.metric(span, "gauge", "ratelimit.remaining.tokens", int(v))
                span.set_metric("openai.organization.ratelimit.tokens.remaining", int(v))

        return func(*args, **kwargs)

    return patched_convert
