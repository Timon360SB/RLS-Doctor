"""Distribution checks reject runtime state, traversal and incomplete packages."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from rls_doctor.core.errors import DoctorError


@pytest.fixture()
def packages() -> ModuleType:
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "package_check_test", root / "scripts/package_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "name",
    [
        "../private.txt",
        "/absolute/file",
        "package/.env",
        "package/.ENV",
        "C:/unexpected.txt",
        "package/node_modules/lib.js",
        "package/fixture.log",
        "package/.rls-doctor/report.json",
    ],
)
def test_local_state_and_unsafe_paths_are_rejected(packages: ModuleType, name: str) -> None:
    with pytest.raises(DoctorError):
        packages.check_members(["package/LICENSE", name], kind="sdk")


def test_license_and_schema_are_required(packages: ModuleType) -> None:
    with pytest.raises(DoctorError) as caught:
        packages.check_members(["rls_doctor/__init__.py"], kind="wheel")
    assert caught.value.code == "PACKAGE_LICENSE"
    with pytest.raises(DoctorError) as caught:
        packages.check_members(["rls_doctor-0.1.0.dist-info/licenses/LICENSE"], kind="wheel")
    assert caught.value.code == "PACKAGE_SCHEMA"


def test_built_wheel_shape_is_accepted(packages: ModuleType) -> None:
    packages.check_members(
        [
            "rls_doctor/__init__.py",
            "rls_doctor/schemas/diagnostic-event-v1.schema.json",
            "rls_doctor-0.1.0.dist-info/licenses/LICENSE",
            "rls_doctor-0.1.0.dist-info/METADATA",
        ],
        kind="wheel",
    )
