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


def _bye():
    try:
        sys.stdout.write(f'DIAG atexit reached (exitstatus {_state["exitstatus"]})\n')
        sys.stdout.flush()
    except Exception:
        pass


atexit.register(_bye)
