# Emulator examples and smoke tests

These guest programs are RV32 bare-metal ELF files. The same files run on
x86_64 and ARM64 hosts; select the archive matching the host architecture.
Run commands from the extracted archive root. Linux with glibc 2.39 or newer,
Bash and the standard `timeout` utility are required for the smoke script.

```sh
bash smoke.sh
```

The script requires successful exits and the expected markers, checks missing
ELF rejection for all six simulators, and fails on timeouts. Success finishes
with `External scalar, RVV, vector FP, matrix and invalid-input checks passed`.
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

## Run examples individually

```sh
bin/core_mini_axi_sim --binary=examples/scalar.elf --cycles=1000000
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak examples/matrix.elf
bin/vme_core_mini_axi_sim --binary=examples/matrix.elf --cycles=1000000
bin/rvv_core_mini_axi_sim --binary=examples/rvv_fp.elf --cycles=1000000
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
