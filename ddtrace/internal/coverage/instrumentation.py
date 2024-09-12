import sys
import os
from ddtrace.internal.utils.formats import asbool


# Import are noqa'd otherwise some formatters will helpfully remove them
if sys.version_info >= (3, 12):
    from ddtrace.internal.coverage.instrumentation_py3_12 import instrument_all_lines  # noqa
elif sys.version_info >= (3, 11):
    from ddtrace.internal.coverage.instrumentation_py3_11 import instrument_all_lines  # noqa
elif sys.version_info >= (3, 10):
    if asbool(os.environ.get("DD_HACKED_INSTRUMENTATION", "false")):
        from ddtrace.internal.coverage.instrumentation_py3_10_new import instrument_all_lines  # noqa
    else:
        from ddtrace.internal.coverage.instrumentation_py3_10 import instrument_all_lines  # noqa
elif sys.version_info >= (3, 8):
    # Python 3.8 and 3.9 use the same instrumentation
    from ddtrace.internal.coverage.instrumentation_py3_8 import instrument_all_lines  # noqa
else:
    from ddtrace.internal.coverage.instrumentation_py3_7 import instrument_all_lines  # noqa
