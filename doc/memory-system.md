# Memory system and data movement

What backs each address range, how the memories compare, and how a program
moves data between them. Structure comes from the RTL; nothing here is a
measured latency or bandwidth.

## The memories

| Memory | Address | What it is |
| --- | --- | --- |
| ITCM | `0x0` | Banked instruction SRAM inside the core. Reads only; guest stores fault (`mcause` 7). The host or DMA can write it. |
| DTCM | `0x10000` or `0x100000` | Banked data SRAM inside the core: 4 banks of 32 bits behind a local crossbar. The scalar and vector LSUs, the matrix engine and the host/DMA port reach it. |
| Core CSRs | `0x30000` or `0x200000` | Core control registers. |
| External SRAM | `0x20000000`, 4 MiB | In the SoC: `soc.TlulSram`, a 128-bit-wide SRAM behind the TileLink-UL crossbar (`TlulToSram` into `Sram_Nx128`, built from foundry macros for synthesis and a behavioural or DPI memory in simulation). In the standalone RTL simulators it is a 4 MiB SystemC testbench RAM answering the core's AXI master. In MPACT it is a flat region. |
| DDR | `0x8000_0000` and up (control at `0x7000_0000`) | Off-chip, in the SoC only: a separate asynchronous clock domain, a small FIFO per path, a 128 to 256-bit width bridge and a 256-bit AXI master port. The packaged simulators tie it off. |

The core reaches external memory through its 128-bit AXI master (`ebus`). It
also fetches instructions from there if the PC is outside the ITCM.

## How they compare

- **DTCM** is the fast one. The LSU has a point-to-point 16-byte interface to
  it and the design documents zero wait-state, pipelined responses.
- **External SRAM** is the same macro technology but behind the AXI and
  TileLink bridges and crossbar arbitration, shared with the DMA and the
  host. One 16-byte beat per access, with a longer request path.
- **DDR** is slower again and exists only in the full SoC.

Treat this as an ordering. For numbers, measure with `mcycle` on an RTL
simulator.

## Moving data

| Method | Where | Notes |
| --- | --- | --- |
| Scalar load/store loop | everywhere | At most 4 bytes per instruction. |
| Vector `vle`/`vse` loop | where RVV exists | The efficient CPU copy: 16 bytes per beat, LMUL up to 8. |
| DMA engine (`bus.DmaEngine`) | subsystem simulator only | Descriptor-driven copy between SRAM, DDR, ITCM, DTCM and peripherals. One outstanding transaction. Poll `STATUS.done`; no interrupt. See `subsystem-emulator.md`. |
| Host backdoor | all simulators | `--load_elf` or the simulator API writes memory before or outside the program. The guest cannot call it. |
| SPI/TL-UL bridge | subsystem simulator | Host reads and writes any mapped address; slow (about 1 KiB/s). |

MPACT and the standalone RTL simulators have no DMA, so the only guest-side
option there is a CPU copy.

## Overlapping a copy with computation

The LSU is a decoupled, in-order unit with its own reservation station, so
the vector ALU keeps issuing while earlier loads and stores are in flight.
External reads can be outstanding (the AXI transaction ID count is
`lsuSlotTxidEntries`). There is no cache and no prefetch instruction, so the
overlap is software pipelining with explicit double buffering:

1. Load tile *n+1* into one vector register group.
2. Compute on tile *n* in a different group.
3. Store the finished tile *n-1*.
4. Swap the groups.

Place the load far enough ahead that the compute covers the external latency.
At LMUL=8 there are four register groups, so staging costs registers. A
compute that streams its operands from the same memory as the copy competes
for the one LSU execution slot; the matrix engine, which computes from tile
registers, overlaps better. MPACT runs this code correctly but has no timing,
so use an RTL simulator to see whether the overlap pays off.
