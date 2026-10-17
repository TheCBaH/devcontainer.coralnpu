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

This is a separate RTL retirement/fault-handling issue, still open. The
store-address regression uses an ordinary destination register for its
load-fault control so that this independent issue does not mask the store
checks. Keep an x0 load-fault reproducer when investigating retirement.

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
