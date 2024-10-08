from typing import Any
from typing import Callable
from typing import List

from ddtrace.internal.flare.flare import Flare
from ddtrace.internal.flare.flare import FlareSendRequest
from ddtrace.internal.logger import get_logger


log = get_logger(__name__)


def _tracerFlarePubSub():
    from ddtrace.internal.flare._subscribers import TracerFlareSubscriber
    from ddtrace.internal.remoteconfig._connectors import PublisherSubscriberConnector
    from ddtrace.internal.remoteconfig._publishers import RemoteConfigPublisher
    from ddtrace.internal.remoteconfig._pubsub import PubSub

    class _TracerFlarePubSub(PubSub):
        __publisher_class__ = RemoteConfigPublisher
        __subscriber_class__ = TracerFlareSubscriber
        __shared_data__ = PublisherSubscriberConnector()

        def __init__(self, callback: Callable, flare: Flare):
            self._publisher = self.__publisher_class__(self.__shared_data__, None)
            self._subscriber = self.__subscriber_class__(self.__shared_data__, callback, flare)

    return _TracerFlarePubSub


def _handle_tracer_flare(flare: Flare, data: dict, cleanup: bool = False):
    if cleanup:
        log.info("Cleaning up")
        flare.revert_configs()
        flare.clean_up_files()
        return

    log.info("data in handle_tracer_flare")
    log.info(data)
    log.info("")
    if "config" not in data:
        log.warning("Unexpected tracer flare RC payload %r", data)
        return
    if len(data["config"]) == 0:
        log.warning("Unexpected number of tracer flare RC payloads %r", data)
        return

    product_type = data.get("metadata", [{}])[0].get("product_name")
    configs = data.get("config", [{}])
    log.info("configs in handle_tracer")
    log.info(configs)
    if product_type == "AGENT_CONFIG":
        log.info("found AGENT CONFIG")
        _prepare_tracer_flare(flare, configs)
    elif product_type == "AGENT_TASK":
        log.info("found AGENT TASK")
        _generate_tracer_flare(flare, configs)
    else:
        log.warning("Received unexpected tracer flare product type: %s", product_type)


def _prepare_tracer_flare(flare: Flare, configs: List[dict]) -> bool:
    """
    Update configurations to start sending tracer logs to a file
    to be sent in a flare later.
    """
    log.info("prepare_config")
    log.info(configs)
    log.info("")
    for c in configs:
        # AGENT_CONFIG is currently being used for multiple purposes
        # We only want to prepare for a tracer flare if the config name
        # starts with 'flare-log-level'
        if not isinstance(c, dict):
            log.info("c is not type dict: %s", str(type(c)))
            continue
        if not c.get("name", "").startswith("flare-log-level"):
            log.info("c task is not tracer flare")
            continue

        flare_log_level = c.get("config", {}).get("log_level").upper()
        flare.prepare(flare_log_level)
        return True
    return False


def _generate_tracer_flare(flare: Flare, configs: List[Any]) -> bool:
    """
    Revert tracer flare configurations back to original state
    before sending the flare.
    """
    log.info("generate_config:")
    log.info(configs)
    log.info("")
    for c in configs:
        # AGENT_TASK is currently being used for multiple purposes
        # We only want to generate the tracer flare if the task_type is
        # 'tracer_flare'
        if not isinstance(c, dict):
            continue
        if c.get("task_type") != "tracer_flare":
            continue
        args = c.get("args", {})
        flare_request = FlareSendRequest(
            case_id=args.get("case_id"), hostname=args.get("hostname"), email=args.get("user_handle")
        )

        flare.revert_configs()

        flare.send(flare_request)
        return True
    return False
