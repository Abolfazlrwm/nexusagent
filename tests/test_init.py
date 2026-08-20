import importlib

import nexusagent
from nexusagent import Runtime, create_runtime
from nexusagent.runtime import Runtime as RuntimeFromModule
from nexusagent.runtime import create_runtime as create_runtime_from_module


def test_runtime_importable_from_package_root():
    assert Runtime is RuntimeFromModule


def test_create_runtime_importable_from_package_root():
    assert create_runtime is create_runtime_from_module


def test_version_unchanged():
    assert nexusagent.__version__ == "0.1.0"


def test_all_contains_exactly_the_public_runtime_api():
    assert set(nexusagent.__all__) == {"Runtime", "create_runtime"}


def test_import_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("importing nexusagent must not open network connections")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    importlib.reload(nexusagent)
