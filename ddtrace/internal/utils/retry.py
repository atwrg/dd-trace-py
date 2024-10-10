from __future__ import absolute_import

from functools import wraps
from itertools import repeat
import random
from time import sleep
import typing as t

from ddtrace.internal.http_client import DEBUG

class RetryError(Exception):
    pass


def retry(
    after: t.Union[int, float, t.Iterable[t.Union[int, float]]],
    until: t.Callable[[t.Any], bool] = lambda result: result is None,
    initial_wait: float = 0,
) -> t.Callable:
    def retry_decorator(f):
        @wraps(f)
        def retry_wrapped(*args, **kwargs):
            sleep(initial_wait)
            after_iter = repeat(after) if isinstance(after, (int, float)) else after
            exception = None

            for s in after_iter:
                try:
                    result = f(*args, **kwargs)
                except Exception as e:
                    DEBUG(f"Retry failed with exception: {e}")
                    exception = e
                    result = e

                if until(result):
                    DEBUG("Retry function succeeded")
                    return result

                DEBUG(f"Retry failed because result doesn't match condition: {result}")

                sleep(s)

            # Last chance to succeed
            try:
                result = f(*args, **kwargs)
            except Exception as e:
                DEBUG(f"Retry failed with exception (last attempt): {e}")
                exception = e
                result = e

            if until(result):
                DEBUG("Retry function succeeded (last attempt)")
                return result

            DEBUG(f"Retry failed because result doesn't match condition (last attempt): {result}")

            if exception is not None:
                raise exception

            raise RetryError(result)

        return retry_wrapped

    return retry_decorator


def fibonacci_backoff_with_jitter(attempts, initial_wait=1.0, until=lambda result: result is None):
    # type: (int, float, t.Callable[[t.Any], bool]) -> t.Callable
    return retry(
        after=[random.uniform(0, initial_wait * (1.618**i)) for i in range(attempts - 1)],  # nosec
        until=until,
    )
