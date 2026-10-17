# Emulator examples and smoke tests

These guest programs are RV32 bare-metal ELF files. The same files run on
x86_64 and ARM64 hosts; select the archive matching the host architecture.
Run commands from the extracted archive root. Linux with glibc 2.39 or newer,
Bash and the standard `timeout` utility are required for the smoke script.

```sh
bash smoke.sh
```

The script requires successful exits and the expected markers, checks missing
ELF rejection for all simulators, and fails on timeouts. Each pass prints a
`CORAL_RESULT <simulator> <example> pass` line, which CI collects into the
fixture results. Success finishes
with `External scalar, RVV, vector FP, matrix, memory and invalid-input checks passed`.
Each RTL simulator also runs the scalar example with tracing enabled and must
produce a nonempty FST waveform.
MPACT runs use `--exit_on_ebreak`, so the startup trap handler stops a failing
program promptly. The script still requires its success marker and bounds
timeouts and printed diagnostic output.

| Example | Checks | Success marker | Models exercised by smoke.sh |
| --- | --- | --- | --- |
| `scalar.elf` | Scalar FP32 addition, output and exit | `CORAL_SCALAR_PASS` | V2, M3, M4, scalar/RVV/VME RTL |
| `rvv.elf` | Sixteen signed int32 vector additions with loads/stores | `CORAL_RVV_PASS` | V2, M3, M4, RVV/VME RTL |
| `rvv_fp.elf` | Sixteen FP32 vector additions and FP32-to-BF16 conversion | `CORAL_RVV_FP_PASS` | M3, M4, RVV/VME RTL |
| `matrix.elf` | Zvt configuration, tile zeroing, signed INT8/FP32/BF16 multiplication and integer accumulation | `CORAL_MATRIX_PASS` | M4, VME RTL |
| `exit_status.elf`, `exit_status_tcm512k.elf` | Guest status 0/5/77, raw syscall 93, ebreak, mpause, cycle limit | `CORAL_EXIT_STATUS_PASS` | All standalone simulators |
| `trap_address.elf`, `trap_address_tcm512k.elf` | ITCM store-fault byte addresses at three offsets, plus an unmapped-load control | `CORAL_TRAP_ADDRESS_PASS` | All applicable standalone RTL and MPACT |
| `memory.elf` | Copies a 16 KiB DTCM buffer to testbench RAM at `0x20000000` and back | `CORAL_MEMORY_PASS` | V2, M3, M4, default-TCM RTL |
| `memory_tcm512k.elf` | Fetches code at 448 KiB in ITCM; copies a 448 KiB DTCM buffer through testbench RAM | `CORAL_MEMORY_PASS` | 512 KiB and 1 MiB TCM RTL |
| `memory_tcm1m.elf` | Same with code at 960 KiB and a 960 KiB DTCM buffer | `CORAL_MEMORY_PASS` | 1 MiB TCM RTL |
| `scalar_tcm512k.elf`, `rvv_tcm512k.elf`, `rvv_fp_tcm512k.elf` | The scalar/RVV/vector-FP examples linked for DTCM at `0x100000` | as above | 512 KiB and 1 MiB TCM RTL |

The memory examples check the addresses of the far function and of the last
buffer word, so they fail if linked for a smaller layout. Buffers are sampled
every 16 words plus the last word. They are linked with `linker/*.ld`, the
upstream `coralnpu_v2_binary` layouts for 8/32 KiB, 512/512 KiB and 1/1 MiB;
any non-default size moves DTCM to `0x100000`. An ELF linked for a larger
layout does not fit a smaller simulator.

The library archive has `library.elf`: the host writes four words at the start
and end of the library's 1 GiB DDR model, the guest sums them, writes the sums
to DDR, DTCM and the mailbox, and waits in `wfi`; `examples/library_example`
checks all three (`CORAL_LIBRARY_PASS`). The subsystem archive has
`subsystem_dma.elf` and `subsystem_dma_tcm1m.elf`: the guest programs the DMA
engine at `0x40050000` to copy SRAM to DTCM, DTCM to SRAM and SRAM to ITCM,
and prints `CORAL_SUBSYSTEM_DMA_PASS` on UART1.

## Run examples individually

```sh
bin/core_mini_axi_sim --binary=examples/scalar.elf --cycles=1000000
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak examples/matrix.elf
bin/vme_core_mini_axi_sim --binary=examples/matrix.elf --cycles=1000000
bin/rvv_core_mini_axi_sim --binary=examples/rvv_fp.elf --cycles=1000000
bin/core_mini_highmem_axi_sim --binary=examples/memory_tcm1m.elf --cycles=20000000
```

The MPACT generation is selected by the executable name. Loading an ELF or
setting `--initial_misa_value` does not switch V2 into M3/M4. The scalar RTL
simulator runs scalar programs; the RVV RTL simulator adds vector execution.
The VME RTL simulator adds the experimental matrix engine. M3/M4 are MPACT
functional models; RVV/VME RTL are separate implementations whose complete
instruction subsets are not established as equivalent by these smoke tests.

## Expected calculations

`scalar.elf` checks `1.25 + 2.5 == 3.75`. `rvv.elf` checks every element of
`(i - 7) + 3*i == 4*i - 7`, for `i=0..15`. `rvv_fp.elf` checks every element
of `(0.5*i - 2) + (2*i + 1.25) == 2.5*i - 0.75` and the BF16 encoding
`0x3fc0` of `1.5`. These FP inputs and expected results are exactly representable.

`matrix.elf` uses tile 0 and checks configuration readback, then:

- Signed INT8: `A=[[1,-2],[-3,4]]`, `B=[[5,6],[7,8]]`, and
  `A^T * B=[[-16,-18],[18,20]]`. A second multiply doubles the accumulator;
  zeroing and multiplying again restores the original result.
- FP32: outer product `[-1.5,2]^T * [3,-4]=[[-4.5,6],[6,-8]]`.
- BF16: the same 2x2 inputs as the INT8 case, with FP32 tile outputs.

Each result is read back with `vtse32` and checked element by element.
FP32 uses LMUL4; BF16 uses LMUL2 and the alternate-format bit in `vtype`, as
required by VME RTL. INT8 uses LMUL1. A failed calculation prints the relevant
`CORAL_MATRIX_INT8_FAIL`, `CORAL_MATRIX_FP32_FAIL` or `CORAL_MATRIX_BF16_FAIL`
marker when execution reaches the check.

Matrix instructions use `.insn`/`.word` because the guest GNU assembler lacks Zvt
mnemonics. Encodings follow the pinned
[M4 decoder](https://github.com/google-coral/coralnpu-mpact/blob/7670ee4c3df4cbc0ea06220c39a19b5d14338ed6/sim/coralnpu_m4.bin_fmt)
and [Zvt format](https://github.com/google/mpact-riscv/blob/e4f1e9c1b243954ff8388fd39019248b2ae7341a/riscv/riscv_zvt.bin_fmt).
The upstream [matrix operation tests](https://github.com/google-coral/coralnpu-mpact/blob/7670ee4c3df4cbc0ea06220c39a19b5d14338ed6/sim/test/coralnpu_m4_ops_test.cc)
provide independent scalar expected results for these operations.
The pinned M4 binary decoder omits M3's BF16-conversion instruction group;
the wrapper applies `provenance/mpact-patches/m4-bf16-decoder.patch` to restore
that inherited instruction. The FP/BF16 example tests this path on both models.
`provenance/mpact-patches/matrix-altfmt.patch` also permits the matrix-specific
alternate-format bit during MPACT matrix configuration and guards invalid
element widths. The BF16 matrix case exercises configuration and arithmetic.
`provenance/0009-vme-retirement-interlock.patch` prevents tile-store
completions from colliding with staggered matrix-result retirement in VME.
The accumulation, configuration-readback and program-exit checks cover this
sequence, which otherwise leaves the matrix engine busy indefinitely.

## RTL waveforms

All three Verilator simulators include FST waveform tracing. Add `--trace`:

```sh
bin/rvv_core_mini_axi_sim --binary=examples/rvv.elf --cycles=1000000 --trace
```

The simulator prints the waveform path under `/tmp`, typically
`/tmp/VRvvCoreMiniAxi.core.fst` for this command. It overwrites that model's
previous trace, so copy the file after a run if you need to preserve it.
Upstream flushes the trace after every dump, which repeats every signal's value
in each FST block; `provenance/0010-fst-periodic-flush.patch` flushes every
4096 dumps instead, so a run killed before it ends loses at most those.
MPACT V2/M3/M4 do not produce RTL waveforms.

For VCD output, convert the FST using a separately installed
[`fst2vcd`](https://gtkwave.github.io/gtkwave/man/fst2vcd.1.html):

```sh
fst2vcd -f /tmp/VRvvCoreMiniAxi.core.fst -o rvv.vcd
```

The conversion tool and waveform viewer are not bundled. The smoke tests
verify FST generation; they do not run the optional converter or inspect every
signal in the resulting waveform.

## Sources and rebuilding

Source code and Bazel rules are included under `provenance/fixtures/`.
To rebuild, clone the wrapper revision recorded in `build.json`, open its
development container on x86_64 and run `make fixtures`. The source fixtures
live in `fixtures/`; Bazel builds them against the pinned guest toolchain and
startup/linker files. ARM64 hosts use the same guest ELFs from the fixture CI
artifact because upstream's guest compiler executable is x86_64-only.

CI additionally verifies the archive checksum and library resolution after
relocation in clean, network-disabled Ubuntu 24.04 and Debian 13 containers on
both native host architectures. It corrupts the bundled C++ library and checks
that the loader rejects it. These are functional smoke tests; they do not
establish exhaustive ISA, rounding/NaN, matrix-shape or RTL conformance coverage.

## Host exit status

Standalone simulators return the low eight bits of a guest HTIF exit status.
A normal halt (`mpause`) returns 0. RTL returns 124 at its cycle limit; core
faults and MPACT `--exit_on_ebreak` stops return 125. Load/simulator errors
return 126. These conventional codes can also be returned by a guest; they
are not a separate namespace. Traps handled by guest software are ordinary
guest execution. MPACT currently still needs an external timeout for loops.

`host-contract.sh` checks these outcomes, including an RTL cycle limit during
startup. It uses `timeout --preserve-status` so an external kill cannot pass
the cycle-limit exit test.
