"""Build and install local preview artifacts; never publish or include credentials."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from rls_doctor.core.errors import DoctorError

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = {
    ".env",
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".rls-doctor",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def check_members(names: list[str], *, kind: str) -> None:
    if not names or len(names) > 1000:
        raise DoctorError("PACKAGE_CONTENTS", "Archive member count is invalid.")
    for name in names:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or any(
                part.lower() in BLOCKED or part.lower().startswith(".env.") or ":" in part
                for part in path.parts
            )
        ):
            raise DoctorError("PACKAGE_CONTENTS", "Unsafe or local-only archive path was blocked.")
        if name.endswith((".pyc", ".log", ".tmp")):
            raise DoctorError(
                "PACKAGE_CONTENTS", "Generated runtime files must not be distributed."
            )
        if kind in {"wheel", "sdk"} and any(part in {"test", "tests"} for part in path.parts):
            raise DoctorError(
                "PACKAGE_CONTENTS", "Runtime packages must not contain test directories."
            )
    if not any(PurePosixPath(name).name.upper() in {"LICENSE", "LICENSE.TXT"} for name in names):
        raise DoctorError("PACKAGE_LICENSE", "Archive does not include the license text.")
    if kind == "wheel" and "rls_doctor/schemas/diagnostic-event-v1.schema.json" not in names:
        raise DoctorError("PACKAGE_SCHEMA", "Python wheel is missing the canonical event schema.")
    if kind == "sdk" and not {
        "package/dist/index.js",
        "package/dist/index.d.ts",
        "package/package.json",
    } <= set(names):
        raise DoctorError(
            "PACKAGE_SDK_ENTRY", "SDK archive is missing its runtime or declaration entry point."
        )


def command(
    args: list[str], *, cwd: Path = ROOT, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def require_command(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    child = command(args, cwd=cwd)
    if child.returncode:
        raise DoctorError(
            "PACKAGE_COMMAND", "A distribution build/install command failed; raw logs suppressed."
        )
    return child


def validate_preview(artifacts: Path) -> None:
    """Only the three audited packages and two provenance files may leave CI."""
    try:
        if artifacts.is_symlink() or any(
            path.is_symlink() or not path.is_file() for path in artifacts.iterdir()
        ):
            raise ValueError
        manifest_path = artifacts / "manifest.json"
        if manifest_path.stat().st_size > 65536:
            raise ValueError
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hashes = manifest["sha256"]
        if (
            manifest["preview_only"] is not True
            or manifest["source_state"] != "working-tree"
            or not isinstance(hashes, dict)
            or len(hashes) != 3
        ):
            raise ValueError
        names = set(hashes)
        if any(
            not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for name, digest in hashes.items()
        ):
            raise ValueError
        if (
            sum(name.endswith(".whl") for name in names) != 1
            or sum(name.endswith(".tar.gz") for name in names) != 1
            or sum(name.endswith(".tgz") for name in names) != 1
            or {path.name for path in artifacts.iterdir()}
            != names | {"manifest.json", "SHA256SUMS"}
        ):
            raise ValueError
        for name in names | {"manifest.json", "SHA256SUMS"}:
            path = artifacts / name
            if path.is_symlink() or not path.is_file():
                raise ValueError
        for name, digest in hashes.items():
            if hashlib.sha256((artifacts / name).read_bytes()).hexdigest() != digest:
                raise ValueError
        checksums = (artifacts / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        if len(checksums) != 3 or set(checksums) != {
            f"{digest}  {name}" for name, digest in hashes.items()
        }:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise DoctorError(
            "PACKAGE_PREVIEW_CONTENTS",
            "Preview package contents/checksums differ; no CI artifact path was exported.",
        ) from None


def emit_ci_path(artifacts: Path, output_file: Path) -> None:
    """Explicit CI-only metadata handoff; never glob local runs or capture folders."""
    validate_preview(artifacts)
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    expected_sha = os.environ.get("GITHUB_SHA", "")
    if (
        not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected_sha)
        or manifest.get("git_head") != expected_sha
        or manifest.get("dirty") is not False
    ):
        raise DoctorError(
            "PACKAGE_CI_SOURCE", "CI artifacts require a clean matching source commit."
        )
    directory = str(artifacts.resolve())
    if output_file.resolve().is_relative_to(artifacts.resolve()):
        raise DoctorError("PACKAGE_CI_PATH", "CI metadata must stay outside the package directory.")
    if any(char in directory for char in "\r\n\x00"):
        raise DoctorError(
            "PACKAGE_CI_PATH", "Invalid artifact directory; no CI output was written."
        )
    with output_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("artifact_dir=" + directory + "\n")


def check_distributions() -> Path:
    """Return audited preview artifacts after installed-package checks; never publish."""
    uv = shutil.which("uv")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    node = shutil.which("node")
    if not all((uv, npm, pnpm, node)):
        raise DoctorError(
            "PACKAGE_TOOLS", "Install uv, Node.js/npm and pnpm before checking distributions."
        )
    assert uv and npm and pnpm and node
    base = ROOT / ".rls-doctor"
    base.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="distribution-check-", dir=base))
    artifacts = run / "artifacts"
    artifacts.mkdir()
    print("Building Python and SDK preview packages...", flush=True)
    require_command([pnpm, "build"])
    python_build = run / "python-build"
    require_command([uv, "build", "--project", "python", "--out-dir", str(python_build)])
    # uv may add build metadata such as .gitignore. Export only explicit packages.
    for pattern in ("*.whl", "*.tar.gz"):
        built = list(python_build.glob(pattern))
        if len(built) != 1 or not built[0].is_file() or built[0].is_symlink():
            raise DoctorError("PACKAGE_FILENAME", "Expected one wheel and one source archive.")
        shutil.copyfile(built[0], artifacts / built[0].name)
    require_command(
        [npm, "pack", "--ignore-scripts", "--json", "--pack-destination", str(artifacts)],
        cwd=ROOT / "packages/capture-sdk",
    )
    # npm JSON metadata shapes differ across versions; inspect the owned output
    # directory and the installed package instead of depending on that shape.
    candidates = list(artifacts.glob("*.tgz"))
    if len(candidates) != 1 or not re.fullmatch(r"[a-zA-Z0-9_.-]+\.tgz", candidates[0].name):
        raise DoctorError(
            "PACKAGE_FILENAME", "Expected exactly one SDK archive in the owned output directory."
        )
    sdk = candidates[0]
    wheel = next(artifacts.glob("*.whl"))
    sdist = next(artifacts.glob("*.tar.gz"))
    with ZipFile(wheel) as archive:
        check_members(archive.namelist(), kind="wheel")
    for path, kind in ((sdk, "sdk"), (sdist, "sdist")):
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if any(member.issym() or member.islnk() for member in members):
                raise DoctorError(
                    "PACKAGE_CONTENTS", "Links are not expected in these distributions."
                )
            check_members([member.name for member in members if member.isfile()], kind=kind)
    print("PASS archive contents, license texts and packaged schema", flush=True)
    venv = run / "python-env"
    require_command([uv, "venv", "--python", sys.executable, str(venv)])
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    require_command([uv, "pip", "install", "--python", str(python), str(wheel)])
    consumer = run / "node-consumer"
    consumer.mkdir()
    (consumer / "package.json").write_text(
        json.dumps({"name": "rls-doctor-package-smoke", "private": True, "type": "module"}),
        encoding="utf-8",
    )
    require_command(
        [npm, "install", "--offline", "--ignore-scripts", "--no-audit", "--no-fund", str(sdk)],
        cwd=consumer,
    )
    (consumer / "check.mjs").write_text(
        """
import { createCaptureFetch, createJsonFileSink } from '@rls-doctor/capture-sdk';
import { readdir, readFile } from 'node:fs/promises';
const sentinel = 'SYNTHETIC_PACKAGE_VALUE';
const response = new Response('[]', {status: 200, headers: {'Content-Range': '*/0'}});
const events = [];
const fileSink = createJsonFileSink({directory: './captures'});
let stored;
const wrapped = createCaptureFetch(async () => response, {
  enabled: true, allowedOrigin: 'http://127.0.0.1:54321', resources: ['documents'],
  sink: event => { events.push(event); stored = fileSink(event); return stored; }, maxEvents: 1,
});
const result = await wrapped('http://127.0.0.1:54321/rest/v1/documents?owner_id=eq.' + sentinel,
  {headers: {Authorization: 'Bearer ' + sentinel}});
await new Promise(resolve => setImmediate(resolve));
if (stored) await stored;
const files = await readdir('./captures');
if (files.length !== 1) throw new Error('Packed file sink count failed');
const saved = JSON.parse(await readFile('./captures/' + files[0], 'utf8'));
if (JSON.stringify(saved) !== JSON.stringify(events[0]))
  throw new Error('Packed file sink check failed');
if (result !== response || response.bodyUsed || events.length !== 1 ||
    JSON.stringify(events).includes(sentinel)) throw new Error('Packed SDK behavior check failed');
process.stdout.write(JSON.stringify(events[0]));
""",
        encoding="utf-8",
    )
    captured = require_command([node, "check.mjs"], cwd=consumer).stdout
    if len(captured) > 65536 or "SYNTHETIC_PACKAGE_VALUE" in captured:
        raise DoctorError("PACKAGE_CAPTURE", "Packed SDK event violated privacy or size bounds.")
    json.loads(captured)
    event = run / "event.json"
    event.write_text(captured, encoding="utf-8")
    validation = require_command(
        [str(python), "-m", "rls_doctor.cli.main", "validate", str(event), "--format", "json"],
        cwd=consumer,
    )
    if json.loads(validation.stdout).get("result") != "PASS":
        raise DoctorError(
            "PACKAGE_CONTRACT", "Installed Python package did not accept the packed SDK event."
        )
    analyzed = command(
        [str(python), "-m", "rls_doctor.cli.main", "analyze", str(event), "--format", "json"],
        cwd=consumer,
    )
    if analyzed.returncode != 2 or json.loads(analyzed.stdout).get("result") != "UNKNOWN":
        raise DoctorError(
            "PACKAGE_ANALYSIS", "Installed offline analysis did not preserve uncertainty."
        )
    source_version = tomllib.loads((ROOT / "python/pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    installed_version = require_command(
        [str(python), "-m", "rls_doctor.cli.main", "--version"], cwd=consumer
    ).stdout.strip()
    if installed_version != "RLS Doctor " + source_version:
        raise DoctorError(
            "PACKAGE_VERSION", "Installed CLI version does not match project metadata."
        )
    diagnosis_help = require_command(
        [str(python), "-m", "rls_doctor.cli.main", "diagnose", "--help"], cwd=consumer
    ).stdout
    if not all(
        option in diagnosis_help
        for option in ("--host", "--approve-read-only", "--connection-env", "--event")
    ):
        raise DoctorError(
            "PACKAGE_DIAGNOSE", "Installed CLI is missing existing-database diagnosis."
        )
    source_sdk = json.loads(
        (ROOT / "packages/capture-sdk/package.json").read_text(encoding="utf-8")
    )
    installed_sdk = json.loads(
        (consumer / "node_modules/@rls-doctor/capture-sdk/package.json").read_text(encoding="utf-8")
    )
    if (
        installed_sdk["name"] != source_sdk["name"]
        or installed_sdk["version"] != source_sdk["version"]
    ):
        raise DoctorError(
            "PACKAGE_VERSION", "Installed SDK metadata differs from the built source."
        )
    (consumer / "check.ts").write_text(
        """
import {
  createCaptureFetch, createJsonFileSink, type DiagnosticEvent,
} from '@rls-doctor/capture-sdk';
const sink = createJsonFileSink({directory: './type-check'});
const wrapped = createCaptureFetch(fetch, {
  enabled: true, allowedOrigin: 'http://127.0.0.1:54321', resources: ['documents'], sink,
});
const response: Promise<Response> = wrapped('http://127.0.0.1:54321/rest/v1/documents');
const acceptEvent = (event: DiagnosticEvent): void => { void sink(event); };
void response; void acceptEvent; wrapped.stop();
""",
        encoding="utf-8",
    )
    (consumer / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": True,
                    "noEmit": True,
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                    "target": "ES2022",
                    "lib": ["ES2022", "DOM"],
                    "types": [],
                },
                "files": ["check.ts"],
            }
        ),
        encoding="utf-8",
    )
    require_command(
        [
            node,
            str(ROOT / "node_modules/typescript/bin/tsc"),
            "--project",
            str(consumer / "tsconfig.json"),
        ],
        cwd=consumer,
    )
    print("PASS installed SDK types, versions and packaged Python contract", flush=True)

    git = shutil.which("git")
    head = command([git, "rev-parse", "HEAD"]) if git else None
    dirty = command([git, "status", "--porcelain"]) if git else None
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (wheel, sdist, sdk)
    }
    (artifacts / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8"
    )
    manifest = {
        "preview_only": True,
        "source_state": "working-tree",
        "git_head": head.stdout.strip() if head is not None and head.returncode == 0 else None,
        "dirty": bool(dirty.stdout.strip())
        if dirty is not None and dirty.returncode == 0
        else None,
        "versions": {"python": source_version, "sdk": source_sdk["version"]},
        "sha256": hashes,
        "checks": [
            "archive-contents",
            "license-texts",
            "sdk-install",
            "wheel-install",
            "installed-sdk-types",
            "installed-versions",
            "installed-diagnose-help",
            "installed-file-sink",
            "installed-event-contract",
            "offline-unknown",
        ],
    }
    (artifacts / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validate_preview(artifacts)
    print("Local preview artifacts and checksums: " + str(artifacts))
    print("No publication performed. Use only the files listed in manifest.json.")
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Explicitly export the audited directory to the CI step output.",
    )
    args = parser.parse_args()
    output = os.environ.get("GITHUB_OUTPUT") if args.github_output else None
    if args.github_output and (os.environ.get("GITHUB_ACTIONS") != "true" or not output):
        raise DoctorError("PACKAGE_CI_CONTEXT", "--github-output requires a GitHub Actions step.")
    artifacts = check_distributions()
    if output is not None:
        emit_ci_path(artifacts, Path(output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DoctorError as error:
        print("ERROR " + error.code)
        raise SystemExit(3) from None
    except Exception:
        print("ERROR distribution check failed; unsafe details suppressed.")
        raise SystemExit(3) from None
