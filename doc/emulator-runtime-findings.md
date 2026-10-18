# Findings from the host-contract regressions

Tested the archives from devel `03396d7` (Actions run 39005667493).
Both host architectures compiled successfully. Interactive diagnosis used
that run's x86_64 archive in a Codespace.

## Access fault from a load into x0 stalls scalar RTL

The trap-address fixture successfully handles stores to `0x100`, `0x104`,
and `0x1238`, recording cause 7 and the complete byte address. It then
executes `lw zero, 0(a4)` with `a4 = 0x30000004`.

The waveform shows the load retiring at PC `0x214` before the memory fault
arrives. The fault updates `mepc = 0x214`, `mcause = 5`, and
`mtval = 0x30000004`. Coralview shows two handler stores issuing
(PCs 0x148 and 0x14c), but no handler instruction retires after the load;
the run reaches the cycle limit. Replacing only the instruction's destination with
t0 allows the same ELF to complete. MPACT completes the original ELF.

This is a separate RTL retirement/fault-handling issue. The
store-address regression uses an ordinary destination register for its
load-fault control so that this independent issue does not mask the store
checks. Keep an x0 load-fault reproducer when investigating retirement.

### Completion fix and regression

The current pre-fix bundle (source `0f61faa`, Actions run 39053331060)
reproduces the same pair: x0 reaches 10,000 cycles and returns 124, while
the otherwise identical t0 ELF prints `CORAL_TRAP_ADDRESS_PASS` and returns
0. MPACT V2 passes the original x0 ELF within 321 instruction steps.

The retirement buffer excluded scalar register zero from its writeback
index, then treated the instruction as complete through `nonWritingInstr`.
An access fault can arrive after that entry has retired, leaving no entry
to retire the trap and flush the pipeline's fault state.

Patch `0019-x0-load-retirement.patch` recognizes scalar loads to x0 and
keeps them pending until the LSU reports completion or the registered fault
marks the instruction as trapping. Dispatch attaches a retirement tag to
each LSU command; the reservation queue and active LSU slot retain it.
Completion matches that tag, including on scalar configurations; completions
from a transaction that outlives a trap flush are suppressed. This
avoids confusing simultaneous instances of a load at the same PC or an
unrelated ALU operation that also discards its result. The existing trap
retirement and pipeline flush paths handle fault recovery.

The earlier [PR #91 comparison](https://github.com/google-coral/coralnpu/pull/91)
used head `6a963421f9caad10dde325a2a6f20daabec7db4c`, whose changes address
zero-work RVV decoding. This repair addresses scalar loads and applies
with RVV disabled; its implementation changes scalar Chisel decode, LSU,
core wiring and retirement handling.

`RetirementBufferTest.scala` checks both mini and full buffer modes: two
loads at the same PC remain pending, an unrelated x0 write completes neither,
one tagged completion releases only its load, and a fault retires the
remaining trap. A fresh load also completes after the trap flush, and repeated
completions exercise tag wraparound.
`make rtl-tests` runs these checks in the fixture CI job.

The emulator bundle includes `examples/x0_load.elf` and its larger-TCM
variant. It exercises all five RV32 integer load forms (`lb`, `lbu`, `lh`,
`lhu`, `lw`) into x0, successful ITCM/DTCM/external-memory reads, unaligned
and cross-row reads, twenty naturally aligned access faults with exact
`mepc`/`mcause`/`mtval` checks, and a successful load after each trap. Smoke tests require status 0
and `CORAL_X0_LOAD_PASS` on every applicable standalone RTL and MPACT model.

The rebuilt scalar RTL passes both original x0/t0 ELFs and the new guest
fixture. Mini/full retirement unit tests pass. MPACT V2/M3/M4 pass the new
fixture (2,352 instruction steps). Native archive validation passed on
x86_64 and ARM64 in Ubuntu 24.04 and Debian 13 at source `24c22f5`:
[build run 39086935102](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39086935102).
All ten standalone models passed the new fixture; existing library,
subsystem, payload, host-contract and MPACT budget suites also passed.
The later history reorder preserves the tested executable files.

The CI bundles include both new ELF layouts:
[x86_64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39086935102/artifacts/12124413652),
[ARM64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39086935102/artifacts/12124141591).

An extra stress variant with unaligned *faulting* addresses fails the
`mtval` address comparison. The saved retirement trace identifies the
failed branch; source inspection explains how an aligned bus-block address
reaches `mtval`. This is a separate open finding, described with evidence,
limits and a proposed fix in [unaligned-fault-address.md](unaligned-fault-address.md).
The shipped regression uses aligned fault addresses and still tests
successful unaligned and cross-row reads.

## The shared semihosting runtime can contain RVV instructions

The file-I/O fixture is compiled for the scalar ISA, but its shared
`crt_semihosting` dependency originally inherits the vector toolchain's
architecture. `_open`'s `strlen` is compiled into `vsetvli`, `vle8ff.v`,
and vector mask operations. The scalar RTL traps at the first `vsetvli`
(PC `0x510`, instruction `0x0c007857`) before issuing `openat`.

Compile the shared runtime for the scalar ISA used by these RV32 archives.
The rebuilt guest fixture passes against the CI-built scalar RTL binary.
The file-I/O fixture checks the actual host ABI on scalar, RVV, VME,
and MPACT configurations rather than failing in guest runtime setup.

## Coralview cross-check

Coralview devel `24a55dc` binds both failing scalar traces successfully.
Its commits model shows the x0 load retiring at cycle 605, six instructions
in flight at the end, and no later retirements. Its memory model shows the
handler stores at cycles 619 and 621. The illegal RVV instruction is a trap
row at PC 0x510 with no dispatch word (`????????`); the next retired PC is
the default handler at 0x410. These observations refine the initial raw
waveform diagnosis: handler issue and handler retirement are distinct.
