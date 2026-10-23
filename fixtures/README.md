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
MPACT runs use `--max_instructions=100000000` and `--exit_on_ebreak`, so the startup trap handler stops a failing
program promptly. The script still requires its success marker and bounds
timeouts and printed diagnostic output.

| Example | Checks | Success marker | Models exercised by smoke.sh |
| --- | --- | --- | --- |
| `batch_limits.elf` | Exact instruction budgets, boundary guest exits, trap/CSR loops and cancellation; run through `bash mpact-limits.sh` | `CORAL_MPACT_LIMITS_PASS` (harness) | V2, M3, M4 |
| `scalar.elf` | Scalar FP32 addition, output and exit | `CORAL_SCALAR_PASS` | V2, M3, M4, scalar/RVV/VME RTL |
| `rvv.elf` | Sixteen signed int32 vector additions with loads/stores | `CORAL_RVV_PASS` | V2, M3, M4, RVV/VME RTL |
| `rvv_fp.elf` | Sixteen FP32 vector additions and FP32-to-BF16 conversion | `CORAL_RVV_FP_PASS` | M3, M4, RVV/VME RTL |
| `rvv_matmul_fp32.elf`, `rvv_matmul_int8.elf`, `rvv_matmul_bf16.elf` | Upstream RVV matrix kernels, external weights/output, scalar numerical checks and output guards | `CORAL_RVV_MATMUL_<format>_PASS` | Highmem RVV RTL |
| `vme_external_matmul.elf` | FP32 tiled matrix accumulation with external row/column tile loads/stores, partial tiles and output guards | `CORAL_VME_EXTERNAL_MATMUL_PASS` | M4, VME RTL |
| `matrix.elf` | Zvt configuration, tile zeroing, signed INT8/FP32/BF16 multiplication and integer accumulation | `CORAL_MATRIX_PASS` | M4, VME RTL |
| `vme_*_test.elf` | Coral's VME cocotb programs run standalone: every Zvt form except the 64-bit tile loads/stores, on several tiles, plus illegal encodings that must trap | `CORAL_VME_TEST_PASS` (exit 0) | M4, VME RTL |
| `host_io.elf`, `host_io_tcm512k.elf` | File create/append/truncate/exclusive-open/read/close and separated stdout/stderr | `CORAL_HOST_IO_PASS` | All standalone simulators |
| `external_payload.elf` | 1 MiB initialized external payload processed through a 256-byte tile with 8 KiB ITCM / 32 KiB DTCM; checksum and corruption checks | `CORAL_EXTERNAL_PAYLOAD_PASS` | Scalar base RTL and MPACT V2 |
| `host_ram.elf`, `host_ram_tcm512k.elf` | Initialized external PT_LOAD, external HTIF packet/buffers, stdin round trip and the last RAM word | `CORAL_HOST_RAM_PASS` | All standalone simulators; RTL frontdoor and backdoor loading |
| `exit_status.elf`, `exit_status_tcm512k.elf` | Guest status 0/5/77, raw syscall 93, ebreak, mpause, cycle limit | `CORAL_EXIT_STATUS_PASS` | All standalone simulators |
| `uninit_tcm.elf`, `uninit_tcm_tcm512k.elf` | Prints 16 DTCM bytes no PT_LOAD covers: zeros by default, ones with `+verilator+rand+reset+1`, seeded random with `+verilator+rand+reset+2 +verilator+seed+N` | `CORAL_UNINIT_TCM_PASS` | All standalone RTL |
| `x0_load.elf`, `x0_load_tcm512k.elf` | Discarded scalar loads from ITCM, DTCM and external RAM, successful unaligned reads, and aligned access-fault recovery | `CORAL_X0_LOAD_PASS` | All applicable standalone RTL and MPACT |
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
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak --max_instructions=100000000 examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak --max_instructions=100000000 examples/matrix.elf
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

## Matrix kernels with external memory

The matrix memory fixtures run on the packaged simulators without rebuilding
an emulator. `bash matrix-memory.sh` checks all four fixtures and verifies
that corrupting an initialized external input makes each one fail.

`rvv_matmul_{fp32,int8,bf16}.elf` calls the pinned upstream Gemma GeMV and
2D matrix kernels. Its standalone driver supplies deterministic signed inputs,
checks every output against an integer scalar dot product (including BF16
round-to-nearest-even), and checks output guards. Cases cover full vectors,
K/N tails, odd row counts, 640-element reduction depths, up to 1024 output
columns (512 for INT8), and weights near the end of the large payload.
The scalar driver disables automatic vectorization; the kernels retain their explicit RVV instructions.
Patch 0023 expresses the INT8 column tail with RVV intrinsics and active
lengths; the upstream tail otherwise overwrites the output guard. The
full-vector fast path is retained.

These ELFs use the prebuilt `rvv_core_mini_highmem_axi_sim`: 1 MiB ITCM,
1 MiB DTCM at `0x100000`, VLEN=128, and the existing 4 MiB external RAM at
`0x20000000`. Initialized external weights occupy 2,621,440 bytes for FP32,
327,680 for INT8, or 1,310,720 for BF16. Output is also external; BF16 keeps
its LHS external too. The ELF build checks every loadable segment against
this layout. Upstream's cocotb layout at `0x80000000` is not used.

`vme_external_matmul.elf` uses the default-TCM `vme_core_mini_axi_sim` and
computes `C += A*B` for M=19, N=23, K=5 across four 16-by-16 tiles. Inputs
are initialized external ELF data. One pass loads accumulator rows with
`vtle32`, accumulates five FP32 outer products with `vtfmm`, and writes
columns with `vtse32`. The other loads columns and writes rows. A/B vector
loads also come directly from external RAM. Results and guards sit near the
end of RAM at `0x203ff800`, and every result is checked. This exercises both
slice orientations, non-square matrix strides, and partial tiles with small
TCMs. It also runs on MPACT M4.

```sh
bin/rvv_core_mini_highmem_axi_sim --cycles=100000000 \
  --binary=examples/rvv_matmul_fp32.elf
bin/vme_core_mini_axi_sim --cycles=100000000 \
  --binary=examples/vme_external_matmul.elf
```

External RAM remains a functional memory model. These tests exercise core
memory transactions and numerical results, without DRAM timing or DMA.

## Small TCM with a large external payload

`examples/external_payload.elf` keeps its code in 8 KiB ITCM and its working
storage in 32 KiB DTCM. The ELF contains **1 MiB of initialized data** in a
separate `PT_LOAD` at `0x20000000`–`0x200fffff`, loaded directly into the
standalone simulator's 4 MiB external RAM model. The payload is 32 times
the entire DTCM capacity. It is not generated by the guest or staged there
in full: the guest processes it in 256-byte tiles, checks every word and
computes a rolling checksum.

The CI-built ELF has these loadable segments (sizes in bytes):

| Address | File size | Memory size | Contents |
| --- | ---: | ---: | --- |
| `0x00000000` | 1,504 | 1,504 | ITCM code and read-only constants |
| `0x00010000` | 304 | 32,768 | DTCM data, reserved heap and stack |
| `0x20000000` | 1,048,576 | 1,048,576 | Initialized external payload |

From the extracted emulator binary bundle:

```sh
bin/core_mini_axi_sim --cycles=20000000 \
  --binary=examples/external_payload.elf
# Optional TCM backdoor loading; external payload loading is direct in both modes:
bin/core_mini_axi_sim --cycles=20000000 --backdoor_load \
  --binary=examples/external_payload.elf
bin/coralnpu_v2_sim --semihost_htif --exit_on_ebreak --max_instructions=100000000 \
  examples/external_payload.elf
```

Expected status 0 and output:

```text
CORAL_EXTERNAL_PAYLOAD_PASS bytes=1048576 tile=256 checksum=2287547e
```

The build checks the actual ELF program headers: code/data segments fit the
small TCM layout, and the external segment has file size and memory size
exactly 1 MiB. Archive tests check both RTL loading modes and corrupt the
last payload byte in an ELF copy; the guest must reject it with
`CORAL_EXTERNAL_PAYLOAD_FAIL`. The compatibility manifest lists this ELF
for the base scalar RTL and MPACT V2. Its source is included under
`provenance/fixtures/external_payload.cc`.

This demonstrates a large **data** payload with small local memories. Code
executes from ITCM. External RAM is a functional SystemC memory model;
the library bundle's separate DDR model is described below.

## Highmem and initialized external payloads

The emulator binary bundle includes both of these ELF files; run from its
extracted root:

```sh
bin/core_mini_highmem_axi_sim --cycles=20000000 \
  --binary=examples/memory_tcm1m.elf
printf '0123456789abcdef' | bin/core_mini_highmem_axi_sim --cycles=100000 \
  --binary=examples/host_ram_tcm512k.elf
```

The first prints `CORAL_MEMORY_PASS`: it executes code above 960 KiB in
ITCM and checks a 960 KiB DTCM buffer copied through external RAM and back,
sampling every 16 words plus the final word. The second loads initialized
`RAM_INITIALIZED` bytes from an external ELF segment at `0x20000000`, uses
external HTIF packet/buffers, reads the supplied 16 input bytes, checks the
last external RAM word, and prints `CORAL_HOST_RAM_PASS`. Both exit 0.
Use `rvv_core_mini_highmem_axi_sim` for the same checks on RVV highmem RTL.

Highmem provides 1 MiB ITCM and 1 MiB DTCM, with DTCM at `0x100000`.
Standalone external memory is a 4 MiB SystemC RAM model at `0x20000000`.
The separate simulator-library bundle provides the 1 GiB DDR model at
`0x80000000`; run its `examples/library_example` harness with
`examples/library.elf` as described above. These are functional memory
models. The highmem example fetches code from ITCM and uses external RAM
for data.

## Expected calculations

`scalar.elf` checks `1.25 + 2.5 == 3.75`. `rvv.elf` checks every element of
`(i - 7) + 3*i == 4*i - 7`, for `i=0..15`. `rvv_fp.elf` checks every element
of `(0.5*i - 2) + (2*i + 1.25) == 2.5*i - 0.75` and the BF16 encoding
`0x3fc0` of `1.5`. These FP inputs and expected results are exactly representable.

The `vme_*_test.elf` programs are upstream's `tests/cocotb/vme_test` sources
at the pinned revision (copied to `provenance/fixtures/vme_test/`), built
unmodified with the semihosting runtime. Under cocotb the harness picks one
subtest and checks the result tables it writes; with no harness each program
runs all of its subtests. `vme_test_main.cc` wraps `main` to print
`CORAL_VME_TEST_PASS` when it returns 0. The marker therefore shows that
every subtest ran to completion with the expected traps handled, not that
the results match: the result checks live in upstream's cocotb bench. They
cover `msetmtype`, `msettn/m/k` (with clamping), `msetmtypei`, `vtzero`,
`vtdiscard`, `vtmv.v.t`, `vtmv.t.v`, `vtle8/16/32`, `vtse8/16/32`,
`vtmmu`/`vtmms`/`vtfmm` on tiles 0, 4 and 8, `mstatus.MS` transitions, and
encodings the RTL must reject (`vtle64`/`vtse64`, reserved `nf`, `vm=0`,
non-zero `vd`/`mop`). `vme_mset_vtmmu_sequence_test` is left out: it halts
with `mpause` instead of returning.

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

All standalone Verilator simulators include FST waveform tracing. Add `--trace`:

```sh
bin/rvv_core_mini_axi_sim --binary=examples/rvv.elf --cycles=1000000 --trace
```

The simulator prints the waveform path under `/tmp`, typically
`/tmp/VRvvCoreMiniAxi.core.fst` for this command. It overwrites that model's
previous trace, so copy the file after a run if you need to preserve it.
Use `--trace_file=rvv.fst` to select a path; this also enables tracing without
`--trace`.

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
guest execution. MPACT returns 124 when `--max_instructions=N` is exhausted,
and 130 on batch Ctrl-C. The default budget, 0, is unlimited; the flag is
incompatible with interactive mode. Guest exit or mpause exactly at the
boundary takes precedence over the limit. Stderr reports the stop reason,
instruction count, budget and final PC. Steps include trap instructions and
handler execution; vector/matrix instructions each count as one step.

Retain an external wall-clock timeout: an instruction budget cannot interrupt
blocked HTIF host I/O or a simulator bug. `bash mpact-limits.sh` checks exact
boundaries, chunk transitions, trap/CSR loops, large 64-bit budget arguments,
cancellation and external termination of a blocked input operation on all
three MPACT binaries. Its `batch_limits.elf` uses fixed entry points beginning
at `0x1000` to bypass CRT startup for exact counts.

`host-contract.sh` checks these outcomes, including an RTL cycle limit during
startup. It uses `timeout --preserve-status` so an external kill cannot pass
the cycle-limit exit test.

`host_ram.elf` has an initialized `.host_ram` section linked at `0x20000000`.
Its HTIF packet and I/O buffer also reside there. `host-contract.sh` supplies
16 input bytes and checks the initialized output and successful round trip.
The RTL host path rejects HTIF accesses outside TCM and testbench RAM without
issuing a transaction through the AXI checker.

`host_io.elf` calls the shipped newlib runtime's `open`, which translates flags
to Linux values before constructing the HTIF packet. Both backends accept that
packet ABI. The regression checks append after seeking, truncation, exclusive
creation, descriptor reuse, and separate output streams. MPACT simulator
banners go to stderr, leaving stdout for guest output.
