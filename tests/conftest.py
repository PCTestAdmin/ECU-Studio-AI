"""Every test runs with temporary home and app-data folders.

The main window opens the project database and the fingerprint library in the
user's folders; without this, a test run would read and change the real ones.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_user_folders(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp('home')
    for name in ('USERPROFILE', 'HOME', 'LOCALAPPDATA', 'APPDATA'):
        monkeypatch.setenv(name, str(home))
