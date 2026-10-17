# Corrections to the emulator reports

For the complete ranking, implementation status and validation results, see
[the final improvement report](emulator-improvements-final.md).

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

### Small local memory with a large external payload

The follow-up `examples/external_payload.elf` uses the base scalar
configuration: **8 KiB ITCM, 32 KiB DTCM, and a 1 MiB initialized external
ELF payload at 0x20000000**. It processes every word through a 256-byte
working tile and checks the result, without staging the whole payload in
DTCM. This is the small-local-memory use case; it does not require a
highmem core configuration.

```sh
bin/core_mini_axi_sim --cycles=20000000 \
  --binary=examples/external_payload.elf
```

Expected: status 0 and
`CORAL_EXTERNAL_PAYLOAD_PASS bytes=1048576 tile=256 checksum=2287547e`.
See the packaged [example README](../fixtures/README.md) for both loading
modes, the MPACT V2 command, ELF layout checks and corruption coverage.
This new fixture demonstrates the repaired external-loading path; the
existing highmem examples below establish the earlier release's coverage.

### Concrete payload examples in the emulator binary bundle

The emulator archive includes these ELF files under `examples/`, alongside
its `bin/` simulators and `examples/README.md`:

| ELF | Memory exercised | Expected output |
| --- | --- | --- |
| `memory_tcm1m.elf` | Code above 960 KiB in ITCM; a 960 KiB DTCM buffer copied through external RAM at `0x20000000` and back | `CORAL_MEMORY_PASS` |
| `host_ram_tcm512k.elf` | An initialized external ELF segment at `0x20000000`, containing a data payload and HTIF packet/buffer; host input round trip and the final RAM word at `0x203ffffc` | `RAM_INITIALIZED`, then `CORAL_HOST_RAM_PASS` |

`memory_tcm1m.elf` is already present in release v0.0.2. Its
[published fixture results](https://github.com/TheCBaH/devcontainer.coralnpu/releases/download/v0.0.2/coralnpu-emulators-linux-x86_64.fixture-results.json)
record successful runs on both scalar and RVV highmem simulators, in Debian
13 and Ubuntu 24.04. This is the concrete counterexample to missing highmem
examples. Its buffers are checked every 16 words and at the final word.

`host_ram_tcm512k.elf` is added by the host-memory fixes and ships in the
updated emulator bundle. Its external segment has nonzero file size: the
loader supplies the initial `RAM_INITIALIZED` bytes from the ELF. The guest
then reads and writes that payload in external RAM and uses an external HTIF
packet. This separately demonstrates the repaired external ELF-loading path;
it is not evidence that release v0.0.2 already supported that path.

Run from the extracted **updated emulator archive** root:

```sh
bin/core_mini_highmem_axi_sim --cycles=20000000 \
  --binary=examples/memory_tcm1m.elf

printf '0123456789abcdef' | bin/core_mini_highmem_axi_sim --cycles=100000 \
  --binary=examples/host_ram_tcm512k.elf
```

Both commands should exit 0 and print their success markers. Replace the
simulator with `bin/rvv_core_mini_highmem_axi_sim` to test the RVV highmem
configuration with the same scalar guest ELFs. The manifest lists each
ELF's compatible configurations. The archive includes their sources under
`provenance/fixtures/` and linker layouts under `linker/`.

Here, **highmem** selects 1 MiB ITCM and 1 MiB DTCM; DTCM starts at
`0x100000`. The standalone emulator's external region is a 4 MiB SystemC RAM
model at `0x20000000`–`0x203fffff`. The far function executes from ITCM;
the external payload is data. The separate simulator-library archive models
1 GiB DDR at `0x80000000`–`0xbfffffff`; its `examples/library.elf` and
`examples/library_example` exercise payloads near both ends. That library
example requires its host harness and shared library. These models establish
functional memory access, rather than physical DRAM timing.

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
