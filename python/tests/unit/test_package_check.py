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


@pytest.fixture()
def preview(tmp_path: Path) -> Path:
    import hashlib
    import json

    hashes = {}
    for name in ("example.whl", "example.tar.gz", "example.tgz"):
        path = tmp_path / name
        path.write_bytes(b"synthetic package bytes")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "preview_only": True,
                "source_state": "working-tree",
                "git_head": "a" * 40,
                "dirty": False,
                "sha256": hashes,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8"
    )
    return tmp_path


def test_ci_exports_exact_audited_directory(
    packages: ModuleType,
    preview: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    output = tmp_path_factory.mktemp("ci-output") / "step-output"
    output.write_text("existing=value\n", encoding="utf-8")
    packages.emit_ci_path(preview, output)
    assert output.read_text(encoding="utf-8").splitlines() == [
        "existing=value",
        "artifact_dir=" + str(preview.resolve()),
    ]


@pytest.mark.parametrize("extra", [".env", "event.json", "node_modules"])
def test_preview_refuses_unexpected_files_or_directories(
    packages: ModuleType, preview: Path, extra: str
) -> None:
    path = preview / extra
    if extra == "node_modules":
        path.mkdir()
    else:
        path.write_text("PRIVATE_VALUE", encoding="utf-8")
    with pytest.raises(DoctorError) as caught:
        packages.validate_preview(preview)
    assert caught.value.code == "PACKAGE_PREVIEW_CONTENTS"
    assert "PRIVATE_VALUE" not in str(caught.value)


@pytest.mark.parametrize("name", ["example.whl", "SHA256SUMS", "manifest.json"])
def test_preview_refuses_modified_archive_or_metadata(
    packages: ModuleType, preview: Path, name: str
) -> None:
    (preview / name).write_text("modified", encoding="utf-8")
    with pytest.raises(DoctorError):
        packages.validate_preview(preview)


@pytest.mark.parametrize("dirty,mismatch", [(True, False), (False, True)])
def test_ci_source_must_be_clean_and_match_workflow(
    packages: ModuleType,
    preview: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
    dirty: bool,
    mismatch: bool,
) -> None:
    import json

    manifest = preview / "manifest.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["dirty"] = dirty
    manifest.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setenv("GITHUB_SHA", ("b" if mismatch else "a") * 40)
    output = tmp_path_factory.mktemp("ci-rejected") / "step-output"
    with pytest.raises(DoctorError) as caught:
        packages.emit_ci_path(preview, output)
    assert caught.value.code == "PACKAGE_CI_SOURCE"
    assert not output.exists()


def test_ci_metadata_cannot_modify_the_audited_bundle(
    packages: ModuleType, preview: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    original = (preview / "manifest.json").read_bytes()
    with pytest.raises(DoctorError) as caught:
        packages.emit_ci_path(preview, preview / "manifest.json")
    assert caught.value.code == "PACKAGE_CI_PATH"
    assert (preview / "manifest.json").read_bytes() == original


def test_ci_option_rejects_local_context_before_build(
    packages: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", ["package_check.py", "--github-output"])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(packages, "check_distributions", lambda: pytest.fail("No build outside CI"))
    with pytest.raises(DoctorError) as caught:
        packages.main()
    assert caught.value.code == "PACKAGE_CI_CONTEXT"
