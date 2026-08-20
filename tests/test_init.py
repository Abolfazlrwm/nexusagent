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
