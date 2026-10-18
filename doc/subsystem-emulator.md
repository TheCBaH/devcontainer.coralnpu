# Using the subsystem emulator

`bin/Vchip_<variant>` in `coralnpu-subsystem-linux-<arch>.tar.gz` is a
cycle-accurate Verilator model of the whole Coral NPU SoC (`chip_verilator`),
not just a core. It is the only emulator with the `bus.DmaEngine` copy
engine, the 4 MiB SRAM, the peripherals and the crossbar between them. The
standalone `*_core_mini_axi_sim` models and MPACT have a bare core and a
testbench RAM, and no DMA.

It behaves differently from the standalone simulators: it only loads a
program, then waits for the host to start the core over a socket, and it
never exits on its own.

## Variants

| Binary | Core | ITCM | DTCM | DTCM base | Core CSR base | Linker script |
| --- | --- | --- | --- | --- | --- | --- |
| `Vchip_vector_normal` | RVV | 8 KiB | 32 KiB | `0x10000` | `0x30000` | `itcm8k_dtcm32k.ld` |
| `Vchip_matrix_normal` | RVV + Zvt | 8 KiB | 32 KiB | `0x10000` | `0x30000` | `itcm8k_dtcm32k.ld` |
| `Vchip_vector_highmem` | RVV | 1 MiB | 1 MiB | `0x100000` | `0x200000` | `itcm1m_dtcm1m.ld` |
| `Vchip_matrix_highmem` | RVV + Zvt | 1 MiB | 1 MiB | `0x100000` | `0x200000` | `itcm1m_dtcm1m.ld` |

All variants have a 30 MHz configured clock (a build setting for guest
drivers, not a measured frequency). The guest programs and linker scripts
are in `examples/` and `linker/` of the archive. The full machine-readable
description (memory regions, ISA, build flags) is in the manifest under
`provenance/`.

## Memory map

| Region | Address | Notes |
| --- | --- | --- |
| ITCM | `0x0` | Guest stores fault (`mcause` 7). Only the DMA and the host can write it. |
| DTCM | see table above | |
| Core CSRs | see table above | Entry point at base + 4; reset and clock gate at base |
| ROM | `0x1000_0000` | 32 KiB, no image built in (ITCM boot) |
| SRAM | `0x2000_0000` | 4 MiB, 128-bit |
| UART0 / clock table / UART1 | `0x4000_0000` / `0x4000_1000` / `0x4001_0000` | |
| SPI master / GPIO / I2C | `0x4002_0000` / `0x4003_0000` / `0x4004_0000` | |
| DMA | `0x4005_0000` | `bus.DmaEngine` |
| SPI master flash | `0x4007_0000` | |
| DDR control, DDR | `0x7000_0000`, `0x8000_0000` | Tied off. Do not access. |

## Running a program

Starting needs three steps and a free TCP port. `python3` is the only
extra requirement (`tools/loader.py` and `tools/elftools` are in the
archive).

```sh
export SPI_DPI_PORT=5556
bin/Vchip_matrix_normal --load_elf=examples/subsystem_dma.elf >sim.out 2>&1 &
sim=$!
timeout 120 bash -c 'until grep -q "DPI: Server listening on port $SPI_DPI_PORT" sim.out; do sleep 0.2; done'
python3 tools/loader.py --csr_only --itcm_size_kbytes 8 --dtcm_size_kbytes 32 \
    examples/subsystem_dma.elf
```

1. `--load_elf=<elf>` is a backdoor load: the simulator writes the ELF's
   segments into ITCM, DTCM and SRAM before simulation starts. Nothing runs
   yet.
2. The simulator opens a SPI-to-TL-UL bridge on `SPI_DPI_PORT` and prints
   `DPI: Server listening on port <port>`. Wait for that line.
3. `loader.py --csr_only` connects to the bridge, writes the ELF entry point
   to the core CSR base + 4, then releases clock gate and reset. Pass the
   `--itcm_size_kbytes` and `--dtcm_size_kbytes` of the variant; the
   defaults are 8 and 32. Use a different port for each simultaneous
   simulator.

Then wait for the guest to finish and stop the simulator yourself. The
simulator runs until killed, so kill its process group (`kill "$sim"`
stops it if you started it directly, as above).
`smoke.sh` in the archive does all of this for the four variants and
checks the `CORAL_SUBSYSTEM_DMA_PASS` marker.

### Guest output

The guest prints through UART1 (`uart_puts` from `fpga/sw/uart.h`). The
simulator writes it to log files in its **working directory**, so run each
simulator in its own empty directory. Wait for the marker with, for example,
`grep -qs CORAL_SUBSYSTEM_DMA ./*.log`. There is no exit code, no semihosting
and no HTIF.

### Waveforms

`--trace <path>` writes an FST waveform to `<path>`.

## Writing a guest program

Guests are bare-metal RV32 ELFs built with Coral's toolchain and the
archive's `linker/` scripts. Use the headers from the upstream
`fpga/sw/` directory: `uart.h` (UART1 at `0x4001_0000`, 115200 baud derived
from the clock table) and `dma.h`.

### DMA

The DMA engine is programmed by the guest through three registers at
`0x4005_0000`: control (+0x0), status (+0x4) and descriptor address (+0x8).
It runs descriptor chains of 32-byte, 32-byte-aligned descriptors:

```c
struct dma_descriptor {
  uint32_t src_addr, dst_addr;
  uint32_t len_flags;           // dma_make_len_flags(len, width_log2, src_fixed, dst_fixed, poll_en)
  uint32_t next_desc;           // 0 ends the chain
  uint32_t poll_addr, poll_mask, poll_value;
  uint32_t reserved;
};
```

```c
desc->src_addr  = src;
desc->dst_addr  = dst;
desc->len_flags = dma_make_len_flags(64, 2, 0, 0, 0);   // 64 bytes, 4-byte beats
desc->next_desc = 0;
dma_start((uint32_t)desc);
int rc = dma_wait_done();                                // 0 ok, -1 error, -2 timeout
```

`fixtures/subsystem_dma.cc` (built as `examples/subsystem_dma.elf`) copies
SRAM to DTCM, DTCM to SRAM, and SRAM to ITCM (the DMA is the only way to
write the ITCM from the guest). Only
16-byte beats are efficient: a narrower beat costs as long as a full one.
The engine has one transaction outstanding. Measured rates (from the
investigation notes): about 1.14 B/cycle between SRAM and DTCM, about 1.77
for SRAM to SRAM, about 0.84 for DTCM to DTCM, about 57 cycles to start and
about 8 per further descriptor.

## Getting results out

| Path | Use |
| --- | --- |
| UART1 log | text and completion markers; also a one-byte "done" signal |
| Memory over SPI | the host can read and write any mapped address through the bridge (`tools/spi_driver.py`) |

Reading memory over the bridge is slow (about 1 KiB/s, one 16-byte beat
per read). Read one beat at a time: a multi-beat read inserts a stray
framing byte between beats.

Do not touch the bus from the host during a timed region. Each bridge read
takes the DTCM device port that the DMA also uses, at a wall-clock moment
that cannot be repeated, and perturbs DMA timing by about one beat per
read. Poll the UART log for a done marker instead, then read memory. With
no host bus traffic during the run, cycle counts repeat exactly.

## Speed and limits

- About 20 000 simulated cycles a second for one run; about 4 100 each with
  two Zvt runs at once (each uses about 4 host cores).
- No timing model for DDR; the aperture is unimplemented.
- Only the matrix variants have Zvt. BF16 tile multiplies (`vtfmm.alt`)
  need the `-DZVTBF16FMM_ON` build define, added by
  `patches/0026-subsystem-matrix-bf16.patch`; releases built without it
  give wrong BF16 results.
- 8 KiB ITCM on the normal variants limits unrolled kernels. Use the
  highmem variants (1 MiB ITCM) for large code.

## Choosing between the simulators

| Need | Use |
| --- | --- |
| DMA, SRAM, peripherals, bus behaviour | `Vchip_*` |
| Core cycle counts, no DMA, run-to-completion with exit code | `*_core_mini_axi_sim --binary=<elf> --cycles=N` |
| Fast functional runs | `coralnpu_{v2,m3,m4}_sim --semihost_htif --exit_on_ebreak <elf>` |
