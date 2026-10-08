# Publishing to PyPI

Status: **package builds cleanly; upload not performed (no PyPI credentials on
the build machine).** This document records how to build and what is required to
upload. It makes no claim that a release has happened.

The distribution is a single stdlib-only module (`measure_ws.py`) exposed through
the console script `ws-wire-audit`. Packaging metadata lives in `pyproject.toml`
(name `ws-wire-audit`, version `1.4.0`, `requires-python >=3.8`, no runtime
dependencies).

---

## 1. Build the distributions

Standard command (network available):

```console
python3 -m build          # produces dist/ws_wire_audit-1.4.0.tar.gz and dist/ws_wire_audit-1.4.0-py3-none-any.whl
```

`python3 -m build` requires the `build` package (`python3 -m pip install build`).
If that package (or its `setuptools>=61` build requirement) is not installed and
the machine has no package-index access, build with an already-present backend
instead:

```console
python3 -c "import setuptools.build_meta as bm; bm.build_sdist('dist'); bm.build_wheel('dist')"
```

Both routes are equivalent: they run the PEP 517 backend declared in
`pyproject.toml` (`setuptools.build_meta`).

## 2. Verify the artifacts before upload

```console
# wheel installs and the offline self-test passes
python3 -m venv /tmp/v && /tmp/v/bin/pip install dist/*.whl
/tmp/v/bin/python -m measure_ws --selftest        # expect: all self-tests pass, exit 0
/tmp/v/bin/ws-wire-audit --help                   # console-script entry point

# the wheel must contain no third-party code and no local files
python3 -m zipfile -l dist/ws_wire_audit-1.4.0-py3-none-any.whl
```

Confirm the wheel carries only `measure_ws.py` plus the `*.dist-info` metadata
(no `tests/`, no `examples/`, no local paths).

## 3. Upload

Uploading requires an account and a credential, neither of which exists on the
build machine used here:

- a **PyPI account** (`pypi.org`), and
- a **project-scoped API token** (preferred) or username/password, with
  **two-factor authentication** enabled on the account (PyPI requires 2FA for
  uploads; tokens are the supported non-interactive credential).

Once the token exists, either uploader works:

```console
# Option A - twine (needs: python3 -m pip install twine)
TWINE_USERNAME=__token__ TWINE_PASSWORD=<token> python3 -m twine upload dist/*

# Option B - uv
UV_PUBLISH_TOKEN=<token> uv publish dist/*
```

Preferred credential storage on the uploading machine, in order:

1. `~/.pypirc` with `[pypi]` and `password = pypi-<...>` (scope it to the
   project, not the whole account), or
2. an environment variable supplied only to the upload command, or
3. a secret manager that injects the token for the command only.

Do not paste a token into a shell that records history, a commit, or a CI log.
`TestPyPI` (`test.pypi.org`) is the recommended dry run before the real index.

## 4. Pre-release checklist

- [ ] `ws-wire-audit --selftest` passes in a clean venv (Section 2).
- [ ] `pyproject.toml` version matches the intended release, and the matching
      `CHANGELOG.md` entry exists.
- [ ] `LICENSE` and the author metadata match the intended public identity.
- [ ] The sdist and wheel contain no local paths, no credentials, no session
      dumps beyond the curated `examples/`.
- [ ] A `TestPyPI` upload succeeds and `pip install -i https://test.pypi.org/simple/ ws-wire-audit`
      works before the real upload.

## 5. What is still required from the maintainer

- A PyPI account with 2FA.
- A project-scoped API token.

Neither is present on the machine that produced this document, so the upload has
**not** been attempted.
