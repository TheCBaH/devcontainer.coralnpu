# Corrections to the emulator reports

Source review of release v0.0.2, wrapper `4708669`, Coral `9f31e14e`,
and MPACT `7670ee4c`. These corrections concern
`coralnpu_emulator_issues.md` and coralview's `doc/emulator-improvements.md`.
They describe that release, before the host-contract fixes in this repository.

## Highmem examples already exist

Observability suggestion 7 says that highmem configurations lack suitable
examples. `scripts/package.py` already maps `scalar_tcm512k.elf`,
`rvv_tcm512k.elf`, `rvv_fp_tcm512k.elf`, and the larger memory fixtures to
the applicable highmem configurations. `scripts/smoke.sh` runs these mappings
in both architecture jobs. `memory_tcm1m.elf` exercises the 1 MiB layouts.

The base `scalar.elf` and `rvv.elf` use DTCM at `0x10000`. Larger-TCM
configurations place it at `0x100000`; select compatible fixtures through
`hardware-configurations.json`, rather than assuming every ELF fits every
configuration. For example:

```sh
bin/rvv_core_mini_highmem_axi_sim --trace \
  --binary=examples/rvv_tcm512k.elf --cycles=1000000
```

The reported timeouts are evidence of unsuitable invocations, not absent
fixtures. Repeat coralview's trace validation with the compatible examples.

## The shipped MPACT already retains opened descriptors

The last bullet of host-contract item 8 describes a real omission in the
unpatched mpact-riscv source. Coral already applies
`third_party/mpact-riscv-openat.patch`, which inserts a successful `openat`
result into `fd_map_`. `third_party/patches/patches.bzl` lists that patch for
the dependency used by the shipped V2/M3/M4 drivers.

The initial plausibility review missed this applied dependency patch and
incorrectly ranked the descriptor omission as a release defect. It needs
regression coverage, not another descriptor-map patch.

The flag mismatch also needs a corrected diagnosis. The shipped guest runtime,
`toolchain/crt/coralnpu_htif_gloss.cc::_open`, already translates newlib flags
to Linux HTIF flags. MPACT's direct forwarding matches that runtime. RTL's
second newlib-to-host translation misinterprets this packet. Keep the mismatch
open, but repair RTL to accept the runtime's HTIF ABI rather than adding a
second translation to MPACT.

## Verification builds require more than extra trace fields

Observability suggestion 1 correctly identifies fields masked or omitted
without verification. Its proposed build variants need functional validation:
`Parameters.scala` couples `enableVerification` to the full retirement buffer
and explicitly documents bugs/hangs with Float enabled and RVV disabled.
Existing verification library targets do not establish that every requested
configuration can execute correctly in this mode.

Treat verification variants as an RTL validation task. Do not promise complete
commit results for every configuration from a build-flag change alone.

## Trace closing already exists on orderly stops

Suggestion 5's fixed-filename problem is real. However, `Sysc_tb::start()`
already closes the FST after `sc_start()` returns, and its destructor also
contains cleanup. Reaching the cycle limit stops the kernel and reaches this
cleanup even though the standalone driver's other thread keeps waiting.

Explicit filenames and graceful SIGTERM/SIGINT handling remain useful work.
No cleanup can be guaranteed after SIGKILL. A missing logged path after an
external timeout does not establish that normal cleanup is absent.

## The 105 MB FST measurement predates the shipped fix

Suggestion 4 mentions the large trace without patch 0010. The release includes
that patch: it changes flushing from every edge to every 4096 dumps. The
documented small VME example is approximately 1.15 MB with this fix.
Trace windows and scope filtering are still reasonable enhancements, but the
105 MB example should not be presented as current release behavior.

## Correction to the earlier MPACT trace verdict

The initial plausibility review pointed to `sim/coralnpu_top.cc`, which has
protobuf tracing, and called suggestion 12 partly contradicted. The shipped
V2/M3/M4 drivers use `CoralNPUSimulator`, which constructs mpact-riscv's
`RiscVTop`; they do not use that `CoralNPUTop` implementation. Their Bazel
dependency lists confirm this distinction.

The existence of another engine's trace code therefore does not contradict
the report about the shipped drivers. Keep the documented architectural
commit-trace request open; verify CLI capabilities against the actual linked
engine before claiming support.

## Timing variation needs a narrower diagnosis

Suggestion 13 is plausible, but distinguishes two questions: whether
host-thread scheduling shifts loading/reset in the waveform, and whether
instruction intervals vary after aligning traces at reset release or first
retirement. The original asynchronous setup supports the first explanation;
it does not alone establish the second. Fixed input and aligned repeated
runs are needed before calling kernel timing nondeterministic.

Further runtime findings from the new regressions are recorded in
[emulator-runtime-findings.md](emulator-runtime-findings.md).
