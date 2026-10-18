# CoralNPU upstream update, October 2026

The CoralNPU submodule advances from `9f31e14e7d105b99b8c99b3a3f4bd569a8e835f9`
to `08eadd1caede64ac4ee99dbbfc9cc70b74c2c5ca`, the upstream `main` tip checked
on 2026-10-18. Development starts from wrapper `d1c4202`, preserving its
emulator fixes and documentation.

## Patch integration

- Remove patch 0005: upstream now describes FST tracing correctly.
- Retain upstream's `--trace_file` option while keeping the wrapper's
  synchronous simulator startup, guest exit codes and cycle-limit handling.
  Compatibility manifests describe the option; smoke tests check an explicit
  path containing spaces without also setting `--trace`.
- Rebase patch 0019 around upstream's physical-slot tile accumulation and
  vector-store completion logic. Preserve tagged x0 load completion and its
  mini/full retirement regressions.
- Extend upstream's matrix retirement interlock to cover the initial PE
  retirement pulse as well as the staggered block pulses.
- Rebase the MPACT BF16 `altfmt` patch over upstream's revised matrix
  configuration and LMUL calculation. Preserve `altfmt` after validating the
  ordinary vector type; keep upstream's illegal-configuration checks.
- Correct the new upstream MPACT alignment patch's hunk length (85 to 80).
  All dependency patches apply in order using ordinary patch application.
- Make only scratch corruption copies of fixture ELFs writable. Bazel outputs
  are read-only; the integration harness must also work as the Codespace's
  ordinary user.

The upstream MPACT revision pins are unchanged; their applied alignment
patches change. Existing historical reports describe their original source
revisions and remain as historical records.

## Verification

A four-core x86_64 Codespace built all 25 guest fixtures, both mini/full
retirement regressions, MPACT V2/M3/M4, scalar RTL and VME RTL. The 25 ELFs
and three linker scripts exactly match the CI fixture artifact. All 23
modified upstream source files match the independently reconciled patch tree.

Focused runtime verification passed:

- 29 model/fixture combinations: scalar, x0 loads, trap addresses, memory,
  RVV, vector floating point and matrix INT8/FP32/BF16 where supported.
- Explicit FST output paths containing spaces on scalar and VME RTL.
- Guest exit codes, cycle limits, invalid ELF rejection, external RAM,
  file flags, separate output streams and descriptor reuse on all five models.
- A 1 MiB payload with small TCMs, ordinary/backdoor RTL loading, MPACT V2
  execution and rejection of corruption in the last payload byte.
- V2/M3/M4 instruction-limit boundaries, 64-bit limits, guest-exit precedence,
  SIGINT, and supervised blocking input.

The initial corruption check exposed read-only scratch copies; after fixing
that harness issue, the complete focused run ended with
`CORAL_FOCUSED_INTEGRATION_PASS` and status 0. No simulator source change was
needed for that failure.

The Codespace was deleted after saving evidence on 2026-10-18 at 05:34 UTC;
no task Codespaces remain. No target builds ran on the local editing host.

The [native CI run](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39097481615)
passed fixtures and retirement tests; full archive verification is in progress.
The [container images](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39097481620)
passed on both architectures. Promotion to `main` awaits native archive CI.
