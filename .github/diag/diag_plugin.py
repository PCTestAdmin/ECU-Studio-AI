"""DIAGNOSE only (branch diag/rc1-exit-code, never merged): pytest result vs. process exit code."""
import atexit
import sys
import pytest

_failed = []
_state = {'exitstatus': None}


def pytest_runtest_logreport(report):
    if report.outcome not in ('passed', 'skipped'):
        _failed.append(f'{report.nodeid} [{report.when}] {report.outcome}')


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _state['exitstatus'] = int(session.exitstatus)
    print(f'\nDIAG sessionfinish session.exitstatus={int(session.exitstatus)} testsfailed={session.testsfailed} '
          f'failed_reports={_failed!r}', flush=True)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    print(f'DIAG unconfigure reached (exitstatus {_state["exitstatus"]})', flush=True)
    try:
        import gc
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
        threads = [o for o in gc.get_objects() if isinstance(o, QThread)]
        for t in threads:
            try:
                print(f'DIAG live QThread {type(t).__module__}.{type(t).__qualname__} running={t.isRunning()} '
                      f'finished={t.isFinished()}', flush=True)
            except RuntimeError as exc:
                print(f'DIAG live QThread {type(t).__qualname__} (C++ object gone: {exc})', flush=True)
        app = QApplication.instance()
        tops = app.topLevelWidgets() if app else []
        names = {}
        for w in tops:
            names[type(w).__qualname__] = names.get(type(w).__qualname__, 0) + 1
        print(f'DIAG QApplication={app is not None} top-level widgets={len(tops)} {names}', flush=True)
        import threading
        print(f'DIAG python threads={[(t.name, t.daemon) for t in threading.enumerate()]}', flush=True)
    except Exception as exc:
        print(f'DIAG thread listing failed: {exc!r}', flush=True)


def _bye():
    try:
        sys.stdout.write(f'DIAG atexit reached (exitstatus {_state["exitstatus"]})\n')
        sys.stdout.flush()
    except Exception:
        pass


atexit.register(_bye)
