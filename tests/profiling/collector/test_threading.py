import os
import sys
import threading
import uuid

import pytest
from six.moves import _thread

from ddtrace.profiling import recorder
from ddtrace.profiling.collector import _lock
from ddtrace.profiling.collector import threading as collector_threading

from . import test_collector


TESTING_GEVENT = os.getenv("DD_PROFILE_TEST_GEVENT", False)


def test_repr():
    test_collector._test_repr(
        collector_threading.ThreadingLockCollector,
        "ThreadingLockCollector(status=<ServiceStatus.STOPPED: 'stopped'>, "
        "recorder=Recorder(default_max_events=16384, max_events={}), capture_pct=1.0, nframes=64, "
        "endpoint_collection_enabled=True, tracer=None)",
    )


def test_wrapper():
    r = recorder.Recorder()
    collector = collector_threading.ThreadingLockCollector(r)
    with collector:

        class Foobar(object):
            lock_class = threading.Lock

            def __init__(self):
                lock = self.lock_class()
                assert lock.acquire()
                lock.release()

        # Try to access the attribute
        lock = Foobar.lock_class()
        assert lock.acquire()
        lock.release()

        # Try this way too
        Foobar()


def test_patch():
    r = recorder.Recorder()
    lock = threading.Lock
    collector = collector_threading.ThreadingLockCollector(r)
    collector.start()
    assert lock == collector.original
    # wrapt makes this true
    assert lock == threading.Lock
    collector.stop()
    assert lock == threading.Lock
    assert collector.original == threading.Lock


def test_lock_acquire_events():
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, capture_pct=100):
        lock = threading.Lock()
        lock.acquire()
    assert len(r.events[collector_threading.ThreadingLockAcquireEvent]) == 1
    assert len(r.events[collector_threading.ThreadingLockReleaseEvent]) == 0
    event = r.events[collector_threading.ThreadingLockAcquireEvent][0]
    assert event.lock_name == "test_threading.py:66"
    assert event.thread_id == _thread.get_ident()
    assert event.wait_time_ns >= 0
    # It's called through pytest so I'm sure it's gonna be that long, right?
    assert len(event.frames) > 3
    assert event.nframes > 3
    assert event.frames[1] == (__file__.replace(".pyc", ".py"), 67, "test_lock_acquire_events", "")
    assert event.sampling_pct == 100


def test_lock_acquire_events_class():
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, capture_pct=100):

        class Foobar(object):
            def lockfunc(self):
                lock = threading.Lock()
                lock.acquire()

        Foobar().lockfunc()

    assert len(r.events[collector_threading.ThreadingLockAcquireEvent]) == 1
    assert len(r.events[collector_threading.ThreadingLockReleaseEvent]) == 0
    event = r.events[collector_threading.ThreadingLockAcquireEvent][0]
    assert event.lock_name == "test_threading.py:87"
    assert event.thread_id == _thread.get_ident()
    assert event.wait_time_ns >= 0
    # It's called through pytest so I'm sure it's gonna be that long, right?
    assert len(event.frames) > 3
    assert event.nframes > 3
    assert event.frames[1] == (__file__.replace(".pyc", ".py"), 88, "lockfunc", "Foobar")
    assert event.sampling_pct == 100


def test_lock_events_tracer(tracer):
    resource = str(uuid.uuid4())
    span_type = str(uuid.uuid4())
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, tracer=tracer, capture_pct=100):
        lock = threading.Lock()
        lock.acquire()
        with tracer.trace("test", resource=resource, span_type=span_type) as t:
            lock2 = threading.Lock()
            lock2.acquire()
            lock.release()
            trace_id = t.trace_id
            span_id = t.span_id
        lock2.release()
    events = r.reset()
    # The tracer might use locks, so we need to look into every event to assert we got ours
    for event_type in (collector_threading.ThreadingLockAcquireEvent, collector_threading.ThreadingLockReleaseEvent):
        assert {"test_threading.py:110", "test_threading.py:113"}.issubset({e.lock_name for e in events[event_type]})
        for event in events[event_type]:
            if event.name == "test_threading.py:110":
                assert event.trace_id is None
                assert event.span_id is None
                assert event.trace_resource_container is None
                assert event.trace_type is None
            elif event.name == "test_threading.py:113":
                assert event.trace_id == trace_id
                assert event.span_id == span_id
                assert event.trace_resource_container[0] == t.resource
                assert event.trace_type == t.span_type


def test_lock_events_tracer_late_finish(tracer):
    resource = str(uuid.uuid4())
    span_type = str(uuid.uuid4())
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, tracer=tracer, capture_pct=100):
        lock = threading.Lock()
        lock.acquire()
        span = tracer.start_span("test", span_type=span_type)
        lock2 = threading.Lock()
        lock2.acquire()
        lock.release()
        trace_id = span.trace_id
        span_id = span.span_id
        lock2.release()
    span.resource = resource
    span.finish()
    events = r.reset()
    # The tracer might use locks, so we need to look into every event to assert we got ours
    for event_type in (collector_threading.ThreadingLockAcquireEvent, collector_threading.ThreadingLockReleaseEvent):
        assert {"test_threading.py:141", "test_threading.py:144"}.issubset({e.lock_name for e in events[event_type]})
        for event in events[event_type]:
            if event.name == "test_threading.py:141":
                assert event.trace_id is None
                assert event.span_id is None
                assert event.trace_resource_container is None
                assert event.trace_type is None
            elif event.name == "test_threading.py:144":
                assert event.trace_id == trace_id
                assert event.span_id == span_id
                assert event.trace_resource_container[0] == span.resource
                assert event.trace_type == span.span_type


def test_resource_not_collected(monkeypatch, tracer):
    monkeypatch.setenv("DD_PROFILING_ENDPOINT_COLLECTION_ENABLED", "false")
    resource = str(uuid.uuid4())
    span_type = str(uuid.uuid4())
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, tracer=tracer, capture_pct=100):
        lock = threading.Lock()
        lock.acquire()
        with tracer.trace("test", resource=resource, span_type=span_type) as t:
            lock2 = threading.Lock()
            lock2.acquire()
            lock.release()
            trace_id = t.trace_id
            span_id = t.span_id
        lock2.release()
    events = r.reset()
    # The tracer might use locks, so we need to look into every event to assert we got ours
    for event_type in (collector_threading.ThreadingLockAcquireEvent, collector_threading.ThreadingLockReleaseEvent):
        assert {"test_threading.py:175", "test_threading.py:178"}.issubset({e.lock_name for e in events[event_type]})
        for event in events[event_type]:
            if event.name == "test_threading.py:175":
                assert event.trace_id is None
                assert event.span_id is None
                assert event.trace_resource_container is None
                assert event.trace_type is None
            elif event.name == "test_threading.py:178":
                assert event.trace_id == trace_id
                assert event.span_id == span_id
                assert event.trace_resource_container is None
                assert event.trace_type == t.span_type


def test_lock_release_events():
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, capture_pct=100):
        lock = threading.Lock()
        lock.acquire()
        lock.release()
    assert len(r.events[collector_threading.ThreadingLockAcquireEvent]) == 1
    assert len(r.events[collector_threading.ThreadingLockReleaseEvent]) == 1
    event = r.events[collector_threading.ThreadingLockReleaseEvent][0]
    assert event.lock_name == "test_threading.py:204"
    assert event.thread_id == _thread.get_ident()
    assert event.locked_for_ns >= 0
    # It's called through pytest so I'm sure it's gonna be that long, right?
    assert len(event.frames) > 3
    assert event.nframes > 3
    assert event.frames[1] == (__file__.replace(".pyc", ".py"), 206, "test_lock_release_events", "")
    assert event.sampling_pct == 100


@pytest.mark.skipif(not TESTING_GEVENT, reason="only works with gevent")
@pytest.mark.subprocess(ddtrace_run=True)
def test_lock_gevent_tasks():
    from gevent import monkey  # noqa:F401

    monkey.patch_all()

    import threading

    import pytest

    from ddtrace.profiling import recorder
    from ddtrace.profiling.collector import threading as collector_threading

    r = recorder.Recorder()

    def play_with_lock():
        lock = threading.Lock()
        lock.acquire()
        lock.release()

    with collector_threading.ThreadingLockCollector(r, capture_pct=100):
        t = threading.Thread(name="foobar", target=play_with_lock)
        t.start()
        t.join()

    assert len(r.events[collector_threading.ThreadingLockAcquireEvent]) >= 1
    assert len(r.events[collector_threading.ThreadingLockReleaseEvent]) >= 1

    for event in r.events[collector_threading.ThreadingLockAcquireEvent]:
        if event.lock_name == "test_threading.py:237":
            assert event.wait_time_ns >= 0
            assert event.task_id == t.ident
            assert event.task_name == "foobar"
            # It's called through pytest so I'm sure it's gonna be that long, right?
            assert len(event.frames) > 3
            assert event.nframes > 3
            assert event.frames[1] == ("tests/profiling/collector/test_threading.py", 238, "play_with_lock", "")
            assert event.sampling_pct == 100
            break
    else:
        pytest.fail("Lock event not found")

    for event in r.events[collector_threading.ThreadingLockReleaseEvent]:
        if event.lock_name == "test_threading.py:237":
            assert event.locked_for_ns >= 0
            assert event.task_id == t.ident
            assert event.task_name == "foobar"
            # It's called through pytest so I'm sure it's gonna be that long, right?
            assert len(event.frames) > 3
            assert event.nframes > 3
            assert event.frames[1] == ("tests/profiling/collector/test_threading.py", 239, "play_with_lock", "")
            assert event.sampling_pct == 100
            break
    else:
        pytest.fail("Lock event not found")


@pytest.mark.benchmark(
    group="threading-lock-create",
)
def test_lock_create_speed_patched(benchmark):
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r):
        benchmark(threading.Lock)


@pytest.mark.benchmark(
    group="threading-lock-create",
)
def test_lock_create_speed(benchmark):
    benchmark(threading.Lock)


def _lock_acquire_release(lock):
    lock.acquire()
    lock.release()


@pytest.mark.benchmark(
    group="threading-lock-acquire-release",
)
@pytest.mark.parametrize(
    "pct",
    range(5, 61, 5),
)
def test_lock_acquire_release_speed_patched(benchmark, pct):
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, capture_pct=pct):
        benchmark(_lock_acquire_release, threading.Lock())


@pytest.mark.benchmark(
    group="threading-lock-acquire-release",
)
def test_lock_acquire_release_speed(benchmark):
    benchmark(_lock_acquire_release, threading.Lock())


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="only works on linux")
@pytest.mark.subprocess(
    ddtrace_run=True,
    env=dict(DD_PROFILING_ENABLED="true"),
    err=None,
)
def test_user_threads_have_native_id():
    from os import getpid
    from threading import Thread
    from threading import _MainThread
    from threading import current_thread
    from time import sleep

    main = current_thread()
    assert isinstance(main, _MainThread)
    # We expect the main thread to have the same ID as the PID
    assert main.native_id == getpid(), (main.native_id, getpid())

    t = Thread(target=lambda: None)
    t.start()

    for _ in range(10):
        try:
            # The TID should be higher than the PID, but not too high
            assert 0 < t.native_id - getpid() < 100, (t.native_id, getpid())
        except AttributeError:
            # The native_id attribute is set by the thread so we might have to
            # wait a bit for it to be set.
            sleep(0.1)
        else:
            break
    else:
        raise AssertionError("Thread.native_id not set")

    t.join()


def test_lock_enter_exit_events():
    r = recorder.Recorder()
    with collector_threading.ThreadingLockCollector(r, capture_pct=100):
        lock = threading.Lock()
        with lock:
            pass
    assert len(r.events[collector_threading.ThreadingLockAcquireEvent]) == 1
    assert len(r.events[collector_threading.ThreadingLockReleaseEvent]) == 1
    acquire_event = r.events[collector_threading.ThreadingLockAcquireEvent][0]
    assert acquire_event.lock_name == "test_threading.py:359"
    assert acquire_event.thread_id == _thread.get_ident()
    assert acquire_event.wait_time_ns >= 0
    # We know that at least __enter__, this function, and pytest should be
    # in the stack.
    assert len(acquire_event.frames) >= 3
    assert acquire_event.nframes >= 3
    # To implement 'with lock:', _lock._ProfiledLock implements __enter__ and
    # __exit__. So frames[0] is __enter__ and __exit__ respectively.

    assert acquire_event.frames[0] == (
        _lock.__file__.replace(".pyc", ".py"),
        223,
        "__enter__",
        "_ProfiledThreadingLock",
    )
    assert acquire_event.frames[1] == (__file__.replace(".pyc", ".py"), 360, "test_lock_enter_exit_events", "")
    assert acquire_event.sampling_pct == 100

    release_event = r.events[collector_threading.ThreadingLockReleaseEvent][0]
    assert release_event.lock_name == "test_threading.py:359"
    assert release_event.thread_id == _thread.get_ident()
    assert release_event.locked_for_ns >= 0
    assert release_event.frames[0] == (_lock.__file__.replace(".pyc", ".py"), 226, "__exit__", "_ProfiledThreadingLock")
    release_lineno = 360 if sys.version_info >= (3, 10) else 361
    assert release_event.frames[1] == (
        __file__.replace(".pyc", ".py"),
        release_lineno,
        "test_lock_enter_exit_events",
        "",
    )
    assert release_event.sampling_pct == 100
