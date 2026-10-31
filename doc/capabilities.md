# Which simulator can do what

Pick the simulator by the question you are asking. MPACT is fast and
functional; the Verilator RTL models are cycle-accurate; only the subsystem
model has a DMA engine and the SoC SRAM.

## Features

| | MPACT V2 | MPACT M3 | MPACT M4 | `core_mini*` RTL | `rvv_core_mini*` RTL | `vme_core_mini*` RTL | `Vchip_*` subsystem |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Fidelity | functional | functional | functional | cycle-accurate | cycle-accurate | cycle-accurate | cycle-accurate |
| Scalar RV32 (incl. FP32) | yes | yes | yes | yes | yes | yes | yes |
| RVV integer | yes | yes | yes | no | yes | yes | yes |
| RVV FP32, FP32 to BF16 conversion | no | yes | yes | no | yes | yes | yes |
| Zvt matrix (VME) | no | no | yes (experimental) | no | no | yes | `Vchip_matrix_*` only |
| Timing (`mcycle`, `--cycles`) | no timing | no timing | no timing | yes | yes | yes | yes |
| Instruction budget | `--max_instructions` | same | same | `--cycles` | `--cycles` | `--cycles` | none (run until killed) |
| Waveforms | no | no | no | FST (`--trace`); `core_mini_axi_vcd_sim` can stream VCD | FST | FST | `--trace` FST |
| Program exit | HTIF semihosting, `ebreak` | same | same | HTIF semihosting, `ebreak`, `mpause` | same | same | none; poll the UART log |
| DMA engine | **no** | **no** | **no** | **no** | **no** | **no** | yes (`0x4005_0000`) |
| Peripherals (UART, SPI, GPIO, I2C) | no | no | no | no | no | no | yes |
| DDR | no | no | no | no | no | no | tied off, do not access |
| External RAM at `0x20000000` | flat 4 MiB region | same | same | 4 MiB testbench RAM | same | same | 4 MiB SoC SRAM |

`mcycle` on MPACT is not meaningful; use an RTL simulator for any cycle
count. RVV variants use VLEN=128. The `_fast_sim` RTL builds have the same
configuration without trace code and assertions (see the README).

## Memory defaults

| Simulator | ITCM | DTCM | Notes |
| --- | --- | --- | --- |
| MPACT | `0x0`, 8 KiB, rx | `0x10000`, 32 KiB, rw | plus 4 MiB rw at `0x20000000`; regions are `--allow_memory_region=start:length:rwx` flags |
| RTL default | 8 KiB | 32 KiB at `0x10000` | |
| RTL 512 KiB | 512 KiB | 512 KiB at `0x100000` | |
| RTL highmem | 1 MiB | 1 MiB at `0x100000` | |
| Subsystem | 8 KiB or 1 MiB | 32 KiB or 1 MiB | see `subsystem-emulator.md` |

Upstream's Python test wrapper (the `npusim` backend) runs MPACT with a
highmem layout (1 MiB ITCM at `0x0`, 1 MiB DTCM at `0x100000`, 4 MiB at
`0x20000000`, 128 MiB at `0x80000000`, `misa` `0x40801120`). The shipped MPACT
binaries default to the small layout instead. The TCM-large example ELFs are
smoke-tested on RTL only; to run one on MPACT, pass regions that match its
linker layout and check the result, since that combination is not covered by
`smoke.sh`.

## Which ELF runs where

`examples/README.md` lists every example with the models that `smoke.sh`
exercises. Short version: the scalar, integer-vector and host-I/O examples run
everywhere they apply; `rvv_fp.elf` needs M3 or later; `matrix.elf` and the
`vme_*` programs need M4 or the VME RTL; the `rvv_matmul_*` kernels are
checked on the highmem RVV RTL only. BF16 conversion is verified on M3, M4
and the RVV RTL (`rvv_fp.elf`); BF16 matrix multiplication is verified on M4
and the VME RTL (`matrix.elf`).
