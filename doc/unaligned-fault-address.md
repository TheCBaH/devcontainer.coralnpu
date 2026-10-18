# Unaligned scalar access faults can report a bus-block address

Status: open, source-supported finding, 2026-10-18. Discovered while
validating the separate [x0 retirement fix](emulator-runtime-findings.md).
It is not one of the original 27 ranked reports.

## Evidence

A stress variant of `fixtures/x0_load.cc` uses fault addresses
`0x30000004 + offset` instead of the shipped `0x30000004 + 4 * offset`.
After the byte-load tests, the halfword load at PC `0x1a4` faults on the
second iteration, which requests bytes `0x30000005` and `0x30000006`.

The saved scalar RTL retirement trace ends that check with:

```text
0x000002dc ... trap=no
0x000002e0 ... trap=no
0x000002e4 ... trap=no
0x00000370 ... trap=no
```

The matching disassembly identifies `0x2dc` as the successful `mepc`
comparison, `0x2e0` as the load of the captured `mtval`, and `0x2e4` as
`bne a5,s0,0x370`: the address comparison branches to the failure path.
The trap-count comparison at `0x2ec` is not reached. A diagnostic build
prints cause 5, its halfword-load PC, `mtval=0x30000004`, and trap count 10.
Thus the saved trace supplies evidence that the CSR values alone did not:
the failed check is the address check, rather than the trap-count check.
MPACT V2 passes the original stress program.

An attempted variant changing the five destinations to t0 fails its checks
earlier on baseline RTL. That is not a successful isolated control and does
not establish equivalent ordinary-register behavior. No patched A/B test
of an address-reporting fix has been performed.

## Source-backed explanation

The relevant address path is unchanged by patch 0019. In pinned Coral
`9f31e14e`, `LsuSuperSlot.computeScalarTxPlan` widens same-row unaligned
loads into aligned bus transactions. For a halfword at row offset 5:

```text
tx1Size = 2 << PriorityEncoder(~5) = 4
txOffset = 5 & ~(4 - 1) = 4
```

`LsuV3` sends that aligned offset on `ebus.dbus.addr`.
`DBus2AxiV2` copies `io.dbus.addr` directly into the fault address, and
`FaultManager` copies it into `mtval`. This explains the observed block
address. The scalar retirement fix changes completion accounting and tags;
it does not change these transaction-size or address calculations.

See the pinned [LSU](https://github.com/google-coral/coralnpu/blob/9f31e14e7d105b99b8c99b3a3f4bd569a8e835f9/hdl/chisel/src/coralnpu/scalar/Lsu.scala)
and [AXI adapter](https://github.com/google-coral/coralnpu/blob/9f31e14e7d105b99b8c99b3a3f4bd569a8e835f9/hdl/chisel/src/coralnpu/DBus2Axi.scala).

The privileged ISA requires a nonzero `mtval` for a misaligned access fault
to identify the faulting portion of the access. `0x30000004` lies outside
the requested two bytes, so this appears inconsistent with that rule.
This is an inference from the trace and address path, not an exhaustive
conformance result. [RISC-V machine-level ISA, Machine Trap Value](https://docs.riscv.org/reference/isa/priv/machine.html).

## Proposed follow-up

Carry the requested byte address separately from the aligned bus address.
Preserve it through transaction holding and response/fault latency. For
split accesses, report the first requested byte in the portion that faults;
returning the original instruction address unconditionally would also be
wrong if only the second portion fails. Keep the fault PC paired with that
transaction. Review masked stores and vector accesses separately.

Add isolated x0 and ordinary-register load tests, then unaligned store and
cross-row cases with only the second portion unmapped. Check cause, PC,
address, exactly one trap, recovery, and successful adjacent accesses on
scalar/RVV/VME and both TCM layouts. Compare MPACT, baseline RTL and repaired
RTL without conflating these checks with retirement progress.

The shipped x0 regression checks successful unaligned/cross-row reads and
twenty naturally aligned access faults. It does not claim to fix this
address-reporting issue.
