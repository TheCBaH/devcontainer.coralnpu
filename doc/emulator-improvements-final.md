# Emulator suggestions: final ranking and implementation report

Final assessment: 2026-10-17. **The confirmed automation, fault-address,
external-memory and host-I/O defects were fixed. Most waveform observability
suggestions remain open.** Missing highmem examples and missing MPACT file
descriptor tracking were contradicted for the shipped release.

Implementation baseline: main/devel `272565e`; executable changes were tested
at `339330f`. Changes between those revisions are Markdown only. This report
records that implementation rather than promising that all proposals below
have been completed.

## Sources and ranking method

Two reports were reviewed:

- `coralnpu_emulator_issues.md`: host-contract defects, referenced as **H1–H9**.
- Coralview's [emulator-improvements.md](https://github.com/TheCBaH/coralview/blob/b2c5aba8ec4e48f8ebba892e4d9a7e19dc4ea2ee/doc/emulator-improvements.md): observability suggestions, referenced as **O1–O13**.

The review used release v0.0.2, wrapper `4708669`, Coral `9f31e14e`, MPACT
`7670ee4c`, and the wrapper's applied dependency patches. Reading unpatched
upstream source alone was insufficient to establish shipped behavior.

**Plausibility measures confidence in the finding and its explanation.** It
is separate from severity, implementation cost, and usefulness. Source-backed
faults ranked highest; useful enhancements followed; contradicted claims or
unproven explanations ranked lowest. Ranks within a tier are approximate,
not numerical probabilities. H8 contains several independent claims, and
O6 duplicates H1; the resulting assessment has 27 entries.

The original report's linked reproducer directory was absent. Its exact
original runs were not rerun. New fixtures, CI archives and waveform analysis
provided independent validation during implementation.

## Ranking and final disposition

### Source-supported findings

| Rank | Report | Finding and reason for ranking | Final disposition |
| --- | --- | --- | --- |
| 1 | H9 | ITCM store-fault `mtval` used a row address, losing byte-address bits. Direct LSU assignment confirmed the cause. | **Fixed:** retain row and byte offset; tested faults at 0x100, 0x104 and 0x1238. |
| 2 | H1 / O6 | RTL cycle-limit stop left the driver waiting for a separate halt callback. | **Fixed:** run SystemC on the calling thread and return at the cycle limit, including during initial reset. |
| 3 | H2 | MPACT discarded guest HTIF status and returned success after completed runs. | **Fixed:** retain the exit payload and propagate normalized guest status through all three drivers. A guest trap can still continue executing. |
| 4 | H3 | RTL reduced guest exits to a Boolean. | **Fixed:** preserve encoded HTIF exits and raw syscall-93 exits with their distinct encodings. |
| 5 | H8 | RTL routed guest fd 2 through stdout. | **Fixed:** guest fd 2 uses stderr. |
| 6 | H8 | RTL and MPACT interpreted open flags differently. | **Fixed with corrected diagnosis:** the CRT already translates newlib flags to Linux values; remove RTL's second translation. |
| 7 | H8 | MPACT banners and halt messages contaminated stdout. | **Fixed:** simulator diagnostics use stderr; regression checks exact guest stdout. |
| 8 | H4 | RTL ELF loading routed external segments through the core AXI slave, which cannot reach testbench RAM. | **Fixed:** load external segments directly into the memory model; validate malformed and unsupported segments. |
| 9 | H5 | HTIF writes could not read buffers in external RAM through the existing host route. | **Fixed:** shared host transport reaches testbench RAM and rejects invalid ranges before AXI transactions. |
| 10 | H6 | HTIF reads could not write buffers in external RAM through that route. | **Fixed:** the same route handles packets, buffers, filenames and responses. |
| 11 | H7 | The manifest did not accurately describe external host loading. | **Resolved by implementing support:** `host_load` is now true for testbench RAM. Setting it false would only describe the old limitation. |
| 12 | H8 | RTL `ebreak` uses the custom halt/fault path rather than a standard breakpoint trap. | **Documented, behavior retained:** fault stops return 125. Changing the architecture remains a separate decision. |
| 13 | H8 | Shipped MPACT drivers lack a batch execution-limit flag. | **Open:** a real CLI gap; callers still need an external timeout for loops. |

### Strong enhancement cases, with qualifications

| Rank | Report | Finding and reason for ranking | Final disposition |
| --- | --- | --- | --- |
| 14 | O5 | Fixed trace filenames can collide; explicit paths and graceful signal handling are useful. | **Open.** Orderly trace closing already existed, including after kernel cycle stops. |
| 15 | O3 | Trace timestamps and sampling phase lack a sufficient consumer contract. | **Open:** no timebase or dump-phase redesign was implemented. |
| 16 | O10 | Consumers need build-specific packed-struct layouts and fields. | **Open:** layouts cannot restore fields omitted from the RTL build. |
| 17 | O2 | Waveform roots, lane counts, sampling phase and debug capabilities need metadata. | **Open:** the existing top-level-name metadata is insufficient for that contract. |
| 18 | O4 | Trace windows and hierarchy selection would reduce recording work. | **Open:** periodic flushing was already fixed by patch 0010; the 105 MB example predates that fix. |
| 19 | O11 | Public stall-reason bits would avoid consumers duplicating dispatch logic. | **Open:** simultaneous blockers and attribution semantics still need design. |
| 20 | O12, RTL | Instruction text traces lack cycle numbers. | **Open:** mini-mode retirement fields also limit the available instruction/result data. |
| 21 | O12, ISS | Shipped MPACT drivers lack a documented architectural commit trace. | **Open; initial review corrected:** protobuf tracing in another engine does not establish support in the shipped RiscVTop-based drivers. |
| 22 | O8 | Dependence on internal waveform wires is fragile. | **Open, moderate-to-high confidence:** the specific optimization stage responsible for missing wires was not established. |
| 23 | O9 | VME tile reads need a stable valid/consume interface. | **Open, moderate-to-high confidence:** internal valid/ready controls already exist, but a public interface would make reconstruction more reliable. |
| 24 | O13 | Host-thread scheduling can shift startup; broader kernel timing nondeterminism was not established. | **Startup reworked, broader claim unverified:** single-thread startup removes the identified host-thread interaction; repeated aligned timing comparisons remain necessary. |

### Lowest plausibility as written

| Rank | Report | Claim and reason for ranking | Final disposition |
| --- | --- | --- | --- |
| 25 | O1 | Verification variants straightforwardly provide complete commit results. Missing fields are real, but full ROB mode has documented Float/no-RVV hangs. | **Investigate before rollout:** no verification variants were added. This is an RTL validation task, beyond packaging flags. |
| 26 | O7 | Highmem simulators have no suitable example ELFs. Existing packaging and positive fixture results contradict this. | **Contradicted:** use compatible larger-TCM examples; added explicit payload commands and a new initialized external-RAM fixture. |
| 27 | H8 | Shipped MPACT does not retain opened descriptors. Coral already applies the upstream descriptor-map fix. | **Contradicted:** added file-I/O regression coverage rather than another descriptor-map patch. |

See [emulator-report-corrections.md](emulator-report-corrections.md) for the
supporting corrections, including mistakes corrected in the initial review.

## What was implemented

The wrapper retains changes as patches applied to pinned source; the upstream
submodule revisions were not advanced for these fixes.

| Change | Implementation | Regression evidence |
| --- | --- | --- |
| Correct store-fault addresses | [0012](../patches/0012-itcm-store-fault-address.patch); commit `021158a` | `trap_address.elf` and its larger-TCM variant check distinct byte offsets. |
| Preserve exits and terminate RTL at limits | [0013](../patches/0013-emulator-termination.patch), MPACT host-contract/HTIF patches; commits `84feef1`, `899f7a2` | Guest codes 0/5/77, raw syscall 93, trap-to-exit, ebreak, mpause, loops, startup cycle limit and missing ELF. |
| Support host access to external RAM | [0014](../patches/0014-host-testbench-ram.patch); commit `b9adbe8` | Initialized external segment, external HTIF packet/buffers, input round trip, last RAM word, both loading modes, invalid/truncated ELF. |
| Fix file flags and output streams | [0015](../patches/0015-htif-host-io.patch), MPACT host-contract patch; commit `180753e` | Create, append after seek, truncate, exclusive open, read/close, descriptor reuse and separate stdout/stderr. |
| Reject invalid buffers before allocation | [0016](../patches/0016-validate-htif-buffer-ranges.patch); commit `97ba648` | Unmapped/overflowing buffers and a rejected 2 GiB request. |
| Keep shared guest runtime scalar-compatible | [0017](../patches/0017-scalar-semihosting-runtime.patch); commit `339330f` | File-I/O fixture runs on scalar RTL without trapping on vectorized `strlen`. |
| Ensure source patches actually apply | `scripts/build.py`; commit `03396d7` | Reproduced nested-cache Git discovery; verified patch application in the actual directory layout, then compiled in CI. |

Standalone status codes now preserve the low eight bits of a guest HTIF
exit. Normal `mpause` returns 0; RTL cycle limits return 124, fault/abnormal
halts return 125, and loader/simulator failures return 126. Guest codes can
have those same numeric values: these are conventional statuses, not a
collision-free namespace. Handled traps remain guest execution.

The source changes do not implement the open waveform enhancements above.
The startup redesign is a termination fix and a narrower response to O13;
it is not proof of deterministic kernel timing.

## Bundled highmem and external-payload examples

Both host-architecture emulator bundles include these ELF files and their
compatibility entries in `hardware-configurations.json`:

| File in archive | Demonstration | Availability |
| --- | --- | --- |
| `examples/memory_tcm1m.elf` | Executes code above 960 KiB in ITCM and copies a 960 KiB DTCM buffer through external RAM and back, checking every 16 words plus the final word. | Already shipped in v0.0.2. |
| `examples/host_ram_tcm512k.elf` | Loads initialized payload bytes from an external ELF segment, uses external HTIF packets/buffers, reads 16 input bytes and checks the final RAM word. | Added with these fixes. |

From the extracted updated emulator bundle:

```sh
bin/core_mini_highmem_axi_sim --cycles=20000000 \
  --binary=examples/memory_tcm1m.elf
printf '0123456789abcdef' | bin/core_mini_highmem_axi_sim --cycles=100000 \
  --binary=examples/host_ram_tcm512k.elf
```

Expect status 0 and `CORAL_MEMORY_PASS` / `CORAL_HOST_RAM_PASS` respectively.
Both also run with `rvv_core_mini_highmem_axi_sim`. Sources and linker layouts
ship under `provenance/fixtures/` and `linker/`; the packaged
[example README](../fixtures/README.md) describes the checks.

Highmem selects 1 MiB ITCM and 1 MiB DTCM, with DTCM at `0x100000`.
Standalone external memory is a 4 MiB SystemC RAM model at `0x20000000`.
The separate simulator-library bundle provides a 1 GiB DDR model at
`0x80000000`, exercised by its `library.elf` and host harness. These examples
establish functional memory access, without establishing physical DRAM timing.
The new initialized-payload test demonstrates the repaired loader; it does
not imply that external ELF preloading already worked in v0.0.2.

## Validation and limits

[Actions run 39039228043](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39039228043)
passed all nine jobs: guest fixtures, the ARM tool image, emulator/library/
subsystem archives on x86_64 and ARM64, and manifest aggregation. Archive
checks ran in Ubuntu 24.04 and Debian 13. The standalone regressions cover
all ten configurations with compatible guest layouts. Both payload ELFs
passed on scalar and RVV highmem in both host architectures and both
runtime containers.

Verified CI emulator bundles:
[x86_64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39039228043/artifacts/12103951180),
[ARM64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39039228043/artifacts/12103896946).
These artifacts were built at `339330f`; later documentation is available in
the repository. No new release tag was published for this work.

Coralview `24a55dc` was also built in a Codespace. Its `check`, `commits`,
`stalls` and `memory` commands completed on both diagnostic traces. This
validated existing consumer capabilities; no coralview source improvements
were implemented in this task. No target build or emulator execution ran
on the local host, and both task Codespaces were deleted.

These are functional regressions, not exhaustive ISA or RTL conformance
checks. In particular, they do not establish verification-mode correctness,
full trace-result reconstruction, or deterministic instruction intervals.

## New findings and remaining work

The regressions uncovered an additional **open RTL x0 load-fault retirement
stall**. A load to x0 retires before its fault arrives; trap CSRs update and
handler stores issue, but no handler instruction retires. MPACT completes
the original fixture. Using an ordinary destination register isolates the
store-address regression; it does not repair the x0 issue. The shared CRT's
unintended RVV instructions, also discovered during testing, were fixed.
See [emulator-runtime-findings.md](emulator-runtime-findings.md).

Recommended next work, separate from this delivered implementation:

1. Investigate the confirmed x0 load-fault retirement stall and retain a
   focused reproducer.
2. Add explicit trace paths and graceful signal handling, then document
   sample phase/timebase and publish waveform capability metadata.
3. Add cycle-tagged traces, build-specific struct layouts and trace windows;
   design stable stall/tile-read debug interfaces.
4. Investigate full-ROB verification hangs and compare aligned repeated
   traces before claiming broader timing determinism.

Consumer-side suggestions from this investigation are bounded signal queries,
trap/CSR timelines, PC/cycle filters, trap-instruction reconstruction, and
separate memory request/completion/fault reporting. They are proposals, not
implemented features; their detailed evidence is in the workspace document
`coralview-emulator-debugging-improvements.md`.
