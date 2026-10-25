# Releases

**English** · [Русский](releases.ru.md)

A GitHub release is a published snapshot tied to a Git tag. It does not publish packages to npm or PyPI. This guide prepares that workflow; no release or tag has been created by this documentation change.

## The first release

Suggested first preview: **v0.1.0-alpha.1**, marked as a pre-release. This is a proposed name, not an existing release. Use **v0.1.0** only after the full MVP gates are met. An alpha can be a source-only snapshot with clearly documented limitations; it must not be described as production-ready or a verified complete MVP.

The repository currently contains package version `0.1.0` as development metadata. Before producing alpha package artifacts, align versions deliberately:

| Location | Alpha metadata | Stable metadata |
| --- | --- | --- |
| Root package.json and SDK package.json | 0.1.0-alpha.1 | 0.1.0 |
| Python pyproject.toml and __version__ | 0.1.0a1 | 0.1.0 |
| Git tag | v0.1.0-alpha.1 | v0.1.0 |

Update lockfiles, examples and displayed versions together. The Python and JavaScript spellings differ. Do not rename an old `0.1.0` wheel to make it look like an alpha build. This documentation has not changed application versions.

## Before a stable release

- Push the reviewed implementation branch, open a PR and merge to main after review/checks. The public README follows the branch being viewed; the default landing page needs the README on main.
- Run the commands in [development](development.md), including a wheel installation smoke test.
- Run the actual Docker/Supabase E2E in [getting started](getting-started.md). A mocked HTTP test does not satisfy this gate.
- Observe successful GitHub Actions for the exact commit to be tagged.
- Obtain independent review across the TypeScript and Python workstreams. No fabricated review or contributor identities.
- Update CHANGELOG.md and the dated verification record. Keep unverified compatibility explicit.

## Create a draft on GitHub

1. Open **Releases → Draft a new release**.
2. Choose the version tag and the reviewed target commit/branch.
3. Add a title, notes and any tested build assets.
4. For an alpha, select **This is a pre-release**.
5. Choose **Save draft**; publish only after reviewing the exact target and contents.

Use the [English notes template](releases/v0.1.0-alpha.1.md) or [Russian notes template](releases/v0.1.0-alpha.1.ru.md). Drafts and templates are not release announcements. [GitHub's official release instructions](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository?tool=webui) describe the current controls.

## Release contents

For a source preview, GitHub's tag archives can be sufficient. If attaching installable packages, build fresh artifacts from the exact tagged source, verify installation and checksums, then attach only the intended files. Do not upload credentials, captures, local configs, database dumps, dependency directories or raw logs. The SDK is currently a private workspace package; npm publication requires a separate packaging decision.

Use CHANGELOG.md for version history, Releases for downloadable snapshots and Issues/PRs for implementation discussion. Each later release should say what changed, what was tested, known limits and how to upgrade. Preserve existing published tags; release corrections should use a new version.

## Source references

- [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository?tool=webui).
- [Repository README behavior](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes).


## Local installable-artifact validation

`uv run --project python python scripts/package_check.py` builds and audits a wheel,
sdist and SDK tarball, installs both components separately, and checks installed
SDK/file-sink behavior, public declarations, version metadata and the shared event
contract. It writes SHA256SUMS and manifest.json beside the intended archives.

This is a working-tree preview, not publication. The manifest records the source
commit and dirty state. Rebuild from the reviewed release commit before attaching
artifacts; do not upload the whole consumer/venv/capture directory. Versions are
not bumped automatically and the SDK's private flag is preserved.
