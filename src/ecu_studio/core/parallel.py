"""Process pool for CPU-bound scan stages (the GIL keeps threads on one core).

Tasks must be module-level functions with picklable arguments. Results come
back in submission order, so a parallel run returns exactly what the
sequential run returns. The pool is created on first use and reused; small
jobs stay in-process because starting workers costs about a second on Windows.

Off by default: on Windows every worker re-imports the calling script, which
re-runs any top-level code not guarded by ``if __name__ == "__main__"``. Programs
with a guarded entry point switch it on with ``enable()`` (the app, the CLI and
the benchmark tools do). ``ECU_STUDIO_WORKERS`` overrides the worker count
(``1`` = always sequential).
"""
from __future__ import annotations
import atexit
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

MAX_WORKERS = 8
_enabled = False
_pool: ProcessPoolExecutor | None = None
_pool_size = 0


def enable(on: bool = True) -> None:
    """Allow worker processes; call only from a guarded entry point."""
    global _enabled
    _enabled = on
    if not on:
        shutdown()


def worker_count() -> int:
    if not _enabled or multiprocessing.parent_process() is not None:
        return 1
    try:
        forced = int(os.environ.get('ECU_STUDIO_WORKERS', ''))
    except ValueError:
        forced = 0
    if forced > 0:
        return forced
    return max(1, min(MAX_WORKERS, (os.cpu_count() or 1) - 1))


def _get_pool(n: int) -> ProcessPoolExecutor:
    global _pool, _pool_size
    if _pool is None or _pool_size != n:
        shutdown()
        _pool = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context('spawn'))
        _pool_size = n
    return _pool


def shutdown() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


atexit.register(shutdown)


def ordered_map(fn, tasks: list, *, parallel: bool, cancelled=None) -> list | None:
    """[fn(*t) for t in tasks], in order; None if cancelled.

    Falls back to in-process work when parallel is False, only one worker is
    available, or the pool cannot start (e.g. restricted environment).
    """
    n = worker_count()
    if not parallel or n <= 1 or len(tasks) <= 1:
        out = []
        for t in tasks:
            if cancelled and cancelled():
                return None
            out.append(fn(*t))
        return out
    try:
        pool = _get_pool(n)
        futures = [pool.submit(fn, *t) for t in tasks]
    except (OSError, RuntimeError):
        return ordered_map(fn, tasks, parallel=False, cancelled=cancelled)
    out = []
    for f in futures:
        while True:
            if cancelled and cancelled():
                for g in futures:
                    g.cancel()
                return None
            try:
                out.append(f.result(timeout=.2))
                break
            except TimeoutError:
                continue
            except BrokenProcessPool:
                shutdown()
                return ordered_map(fn, tasks, parallel=False, cancelled=cancelled)
    return out


class Deferred:
    """Result of fn(*args): already running in a worker, or computed on demand."""

    def __init__(self, fn, args, future=None):
        self.fn, self.args, self.future = fn, args, future

    def result(self, cancelled=None):
        if self.future is None:
            return self.fn(*self.args)
        while True:
            if cancelled and cancelled():
                self.future.cancel()
                return None
            try:
                return self.future.result(timeout=.2)
            except TimeoutError:
                continue
            except BrokenProcessPool:
                shutdown()
                return self.fn(*self.args)


def defer(fn, *args, parallel: bool) -> Deferred:
    """Start fn(*args) in a worker now (if allowed) and collect it later."""
    if parallel and worker_count() > 1:
        try:
            return Deferred(fn, args, _get_pool(worker_count()).submit(fn, *args))
        except (OSError, RuntimeError):
            pass
    return Deferred(fn, args)
