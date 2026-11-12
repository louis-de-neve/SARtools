# Development foundation: milestone 0

**Status: complete (12 November 2026).** The [public repository](https://github.com/louis-de-neve/SARtools) contains the foundation commit. Its [first CI run](https://github.com/louis-de-neve/SARtools/actions/runs/43214348201) passed on Python 3.11 and 3.13. An [active ruleset](https://github.com/louis-de-neve/SARtools/rules/27116372) targets `main` and requires both `tests (3.11)` and `tests (3.13)`.

## Purpose

Establish a repeatable local and GitHub test gate before the first Sentinel-1 API adapter is built. This milestone is complete when the package installs in CI, the same tests run locally, and Git can track source without collecting research data or credentials.

## Work breakdown

1. **Repository and package:** initialize Git in this directory, use a `src/sartool` package, define package metadata in `pyproject.toml`, and ignore environments, caches, downloaded data, and local secrets. Keep the existing config and research plan under version control.
2. **Test baseline:** use `unittest` for the first provider-independent model. Add focused tests for valid and invalid AOI bounds and acquisition time intervals. Run tests through `PYTHONPATH=src python3 -m unittest discover -s tests -v` locally. Provider adapters will add response-fixture and error-path tests to the same suite.
3. **CI:** run GitHub Actions on pushes and pull requests. Test Python 3.11 and 3.13 on Ubuntu, install the package, then run `python -m unittest discover -s tests -v`. Require this workflow to pass before merging API work. Add Windows/macOS jobs when platform-specific processing or GUI dependencies arrive.
4. **GitHub repository:** choose the GitHub owner, repository name, visibility, and license. Create the remote repository, set `origin`, push the initial branch, and enable branch protection requiring the `tests` check. This last publishing step needs the chosen account/repository settings and GitHub access; it is not implied by creating the local Git repository.
5. **Next gate:** implement ASF search behind a provider adapter with saved official response fixtures, pagination/error tests, and a separately triggered live smoke test. The routine CI suite must not depend on a live external service or credentials.

## Commands

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
git status --short
```

At milestone 0 the package had no runtime third-party dependencies. Later milestones add provider and geometry dependencies; use the current commands in `README.md` for development.

## Done when

- Local unit tests and syntax compilation pass.
- The GitHub workflow installs the package and passes on a clean checkout for both declared Python versions.
- A remote repository exists and its branch protection requires the CI check (after GitHub details/access are available).
- The first provider pull request can use fixtures and tests without changing CI structure.
