# Contributing

Thanks for your interest in `ws-wire-audit`.

## Licensing of contributions (inbound = MIT)

By submitting a pull request, issue patch, or any other contribution to this
repository, you agree that:

1. You are the author of the contribution, or you otherwise have the right to
   submit it; and
2. You license the contribution to this project under the repository's existing
   license (MIT), inbound, with no additional terms; and
3. You have not copied code from a source whose license is incompatible with MIT.

You retain copyright in your contribution. No CLA is required; a one-line
confirmation in the pull request ("I confirm the above") is sufficient.

## How to submit a pull request

1. Fork the repository and work on a branch.
2. Keep changes scoped: one concern per PR, with a clear description of *what*
   changed and *why*.
3. Do not include measurement outputs, credentials, private hostnames, or raw
   wire captures in the diff.

## Requirements for review

- **Keep the tool single-file and stdlib-only.** `measure_ws.py` must stay one
  file with no runtime dependencies; do not add import lines that require a
  package outside the standard library.
- **`python3 measure_ws.py --selftest` must pass**, and if your change touches a
  documented number, that number must be reproducible with the exact command
  shown wherever it is documented.
- **Tests are welcome and must be offline.** If you add tests, place them under
  `tests/` and make sure no test opens a real network connection; prefer a fake
  transport and assert the recorded output rather than connecting out.
- **Do not weaken the honesty wording.** Caliber notes, "not validated" and
  not-determined caveats, `n=1` / `n≥3` sample-size limits, and sentences that
  disclaim venue-level claims are part of the measurement contract. Propose changes to them in a separate PR with a
  justification, rather than relaxing them inside an unrelated change.

## Review outcome

Maintainers may **accept**, **request changes**, or **decline** a contribution
at their discretion. Opening a pull request does not create an obligation to
merge it, and the maintainers may apply smaller edits themselves rather than
sending the PR back.
