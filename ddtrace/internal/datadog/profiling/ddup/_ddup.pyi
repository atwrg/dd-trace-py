from typing import Dict
from typing import Optional
from typing import Union
from .._types import StringType
from ddtrace._trace.span import Span

def config(
    env: StringType,
    service: StringType,
    version: StringType,
    tags: Optional[Dict[Union[str, bytes], Union[str, bytes]]],
    max_nframes: Optional[int],
    url: Optional[str],
    timeline_enabled: Optional[bool],
    sample_pool_capacity: Optional[int],
) -> None: ...
def start() -> None: ...
def upload() -> None: ...

class SampleHandle:
    def push_cputime(self, value: int, count: int) -> None: ...
    def push_walltime(self, value: int, count: int) -> None: ...
    def push_acquire(self, value: int, count: int) -> None: ...
    def push_release(self, value: int, count: int) -> None: ...
    def push_alloc(self, value: int, count: int) -> None: ...
    def push_heap(self, value: int) -> None: ...
    def push_lock_name(self, lock_name: StringType) -> None: ...
    def push_frame(self, name: StringType, filename: StringType, address: int, line: int) -> None: ...
    def push_threadinfo(self, thread_id: int, thread_native_id: int, thread_name: StringType) -> None: ...
    def push_task_id(self, task_id: Optional[int]) -> None: ...
    def push_task_name(self, task_name: StringType) -> None: ...
    def push_exceptioninfo(self, exc_type: Union[None, bytes, str, type], count: int) -> None: ...
    def push_class_name(self, class_name: StringType) -> None: ...
    def push_span(self, span: Optional[Span]) -> None: ...
    def push_monotonic_ns(self, monotonic_ns: int) -> None: ...
    def flush_sample(self) -> None: ...
