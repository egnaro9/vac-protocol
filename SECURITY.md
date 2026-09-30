# Security policy

This project exists to refuse false claims, so a way to make it accept one is
the only bug class that really matters here. Reports of that kind are welcome
and get published rather than buried.

## Threat model: the issuer is the adversary

A VAC bundle is written by the party whose claim it makes. The verifier's job
is to hold that party to their own artifacts. So the attacker to reason about
is not a stranger in the network path, it is the issuer, who controls every
declared number, every filename, every prose field, and the order in which
they are written.

A bundle is trustworthy only to the extent that a stranger running
`python -m vac.verify` offline gets the same answer the issuer got, and that
answer is false whenever the declared numbers do not recompute from the hashed
artifacts.

## In scope

Report it if you can do any of these.

- **Make a bundle verify clean while a declared number does not recompute from
  its artifacts.** This is the core class. It is what the first external audit
  found five separate ways, including a 4-byte substitution.
- **Make verdicts depend on the host.** Same bytes, different answer on another
  OS, filesystem, locale or Python version. A protocol whose premise is that a
  stranger gets the same answer offline has no tolerance for this.
- **Escape the bundle directory during verification.** Path traversal, absolute
  or drive-anchored paths, tar member escape, symlink escape. `vac/verify.py:74`
  and `vac/verify.py:325` are the current defenses; getting past them is a
  finding.
- **Make the verifier hang, exhaust memory, or crash instead of naming a
  reason.** A verifier that dies is a verifier that did not refuse. Quadratic
  behaviour on a clean bundle counts.
- **Paint a false verdict in the output.** Terminal escapes, bidi overrides, or
  any control sequence in issuer-controlled text that makes a failing run read
  as PASS.
- **Get a bundle into the registry that the verifier would refuse.** Including
  by exploiting the gap between the verifier the registry runs and the one a
  stranger runs.
- **Make a permanent tamper fixture pass**, or make one pass for a reason other
  than the hole it was written to measure. There are 23 of them under
  `fixtures/`; a fixture that silently stops testing its hole is a real defect.

## Out of scope, and why

These are known and documented, not oversights. Saying so here so a report is
not wasted work.

- **`vac_version` 0.1 semantics.** 0.1 keeps its behaviour indefinitely and by
  design, with no cutoff. The loose summary tier that 0.2 replaced still
  accepts what 0.2 refuses in 0.1 bundles. That is deliberate: there is no
  window in which the verifier knowingly accepts what it has called unsound
  under a version that claims otherwise. New findings should target 0.2.
- **Structural verification not proving the semantic claim.** A clean
  structural PASS binds numbers to hashed artifacts. It does not prove the
  artifact is what its filename says it is. That is replay's job and SPEC §3.4
  says so. A report that structural verification "does not prove the claim" is
  describing the design.
- **`protocol.grading` not being machine-checked.** SPEC §5 rule 3 states
  outright that it is not, names the two non-structural gates that carry it,
  and the published registry repeats it on every entry. A keyword screen for
  "LLM" would be theatre.
- **Free-text pool keys being non-authoritative.** SPEC §3.1 already says a
  registry must not treat a number admitted only by issuer free text as
  recomputed.

## How to report

Private first, for anything in the in-scope list:

- **GitHub private advisory**, preferred:
  <https://github.com/egnaro9/vac-protocol/security/advisories/new>
- **Email**: erik@erikhill.dev

Include the commit you tested against and the smallest bundle that shows it. A
fixture directory is ideal. If you would rather just open a public issue,
that is fine too: nothing here handles anyone's data or credentials, so there
is no user population at risk while a hole is open, and a public issue has
historically produced a better discussion.

## What you get back

- An acknowledgement within 3 days, and a real answer within 14.
- Credit by name and handle in the fix commit and in the release note, unless
  you ask otherwise.
- **Your finding becomes a permanent fixture.** Every accepted report is turned
  into a tamper fixture under `fixtures/`, confirmed to verify clean against
  the pre-fix verifier first, so it measures your hole and not some unrelated
  refusal. That is how the hole stays closed.
- If the finding does not hold, you get the reasoning, in the spec where it
  belongs rather than only in a thread.

## Prior art: this has been done before, successfully

In August 2026 Giulio D'Erme (`GiulioDER`) ran an unsolicited deep audit and
broke it. A bundle declaring 9999 verdicts while holding 3 exited 0 and printed
`structural verification: PASS`, with `evidence/bundle.json` replaced by the
four bytes `null` and its sha256 re-pinned honestly. Four more forgery paths,
plus path traversal and a host-dependent verdict. Four of his pull requests are
merged. His four SPEC-level issues (#4 to #7) are answered in the spec.

Two of his four proposed fixes did not close their holes, and working out why
is what produced protocol v0.2. That exchange is the best available description
of what a useful report here looks like:

- Audit PRs: [#1](https://github.com/egnaro9/vac-protocol/pull/1),
  [#2](https://github.com/egnaro9/vac-protocol/pull/2),
  [#8](https://github.com/egnaro9/vac-protocol/pull/8),
  [#9](https://github.com/egnaro9/vac-protocol/pull/9)
- SPEC issues: [#4](https://github.com/egnaro9/vac-protocol/issues/4),
  [#5](https://github.com/egnaro9/vac-protocol/issues/5),
  [#6](https://github.com/egnaro9/vac-protocol/issues/6),
  [#7](https://github.com/egnaro9/vac-protocol/issues/7)
- The standing invitation, with a ten-minute path: [REPLAY_REQUEST.md](REPLAY_REQUEST.md)

## Supported versions

`main` is the supported version. The protocol version a bundle declares
(`vac_version`) determines the semantics it is held to; both 0.1 and 0.2 are
verified by the current tool.
