"""DIAGNOSE only (branch diag/rc1-exit-code, never merged): why does pytest exit 1 with all tests passed?"""
import sys
import pytest

_failed = []


def pytest_runtest_logreport(report):
    if report.outcome not in ('passed', 'skipped'):
        _failed.append(f'{report.nodeid} [{report.when}] {report.outcome}')


def pytest_collectreport(report):
    if report.failed:
        _failed.append(f'COLLECT {report.nodeid} failed')


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    mods = {n: getattr(m, '_registry', None) for n, m in list(sys.modules.items()) if n.endswith('conftest')}
    print(f'\nDIAG sessionfinish exitstatus={exitstatus!r} session.exitstatus={session.exitstatus!r} '
          f'testsfailed={session.testsfailed} failed_reports={_failed!r}', flush=True)
    for n, reg in mods.items():
        if reg is not None:
            print(f'DIAG {n}: registry changes={reg.get("changes")!r}', flush=True)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_logfinish(nodeid, location):
    import conftest
    before = len(conftest._registry['changes'])
    res = yield
    if len(conftest._registry['changes']) != before:
        print(f'\nDIAG registry change recorded after {nodeid}: {conftest._registry["changes"][-1]!r}', flush=True)
    return res
