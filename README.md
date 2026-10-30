# Coral NPU development containers and emulators

Development environment and portable Linux executables for
[google-coral/coralnpu](https://github.com/google-coral/coralnpu).
The upstream source is pinned as the `coralnpu` submodule. Wrapper patches
apply only to the disposable `.cache/source` build tree.

## Download and run

CI artifacts and tagged releases contain two archives per host
architecture (`x86_64`, `aarch64`) and `SHA256SUMS`:

| Archive | Contents |
| --- | --- |
| `coralnpu-emulators-linux-<arch>.tar.gz` | MPACT V2/M3/M4 and seven standalone Verilator RTL simulators, each also as a `_fast` build |
| `coralnpu-subsystem-linux-<arch>.tar.gz` | Optional full-subsystem `chip_verilator` simulators and loader |

```sh
sha256sum -c SHA256SUMS
tar -xzf coralnpu-emulators-linux-x86_64.tar.gz
cd coralnpu-emulators-linux-x86_64
bin/coralnpu_v2_sim --semihost_htif --exit_on_ebreak examples/scalar.elf
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak examples/matrix.elf
bin/vme_core_mini_axi_sim --binary=examples/matrix.elf
bin/rvv_core_mini_axi_fast_sim --binary=examples/rvv_fp.elf
bin/core_mini_highmem_axi_sim --binary=examples/memory_tcm1m.elf --cycles=20000000
bin/rvv_core_mini_itcm512kb_dtcm512kb_axi_sim --binary=examples/rvv_tcm512k.elf
bash smoke.sh
```

Use the archive matching the **host** architecture; guest programs are RV32
Coral NPU ELFs on either host. Binaries require Linux with glibc 2.39 or newer
(Ubuntu 24.04, Debian 13). No Bazel, Python, Docker, repository checkout or
global library-path configuration is required, except that the subsystem
loader needs `python3`. Keep `bin/` and `lib/` together when relocating an
archive. Upstream command-line options remain available through `--helpfull`.

## Configurations

Every archive has `hardware-configurations.json` at its root, validated
against `hardware-configurations.schema.json` (JSON Schema Draft 2020-12,
`schema_version` `1.0`). It lists each simulated configuration with its ID,
upstream target, dependency pins, patch hashes, generated elaboration
parameters, ISA, memory regions and access rights, DMA and peripherals, and
every shipped simulator with its SHA-256, host and launch method:

```sh
jq -r '.configurations[] | [.id, .name, .simulation.backend] | @tsv' hardware-configurations.json
jq -r '.artifacts[] | [.configuration_id, .path, .host.architecture] | @tsv' hardware-configurations.json
```

IDs are `coralnpu:<name>:<digest>`, where the digest covers the whole record
except the ID (`id_rule` in the manifest gives the exact rule). They contain no
host values, so x86_64 and aarch64 builds share IDs; CI checks this. Any change
to the source pin, patches, parameters or memory map changes the ID. Units are
bytes, addresses are integers, `null` means unknown and `false` verified absent.
The manifest describes default invocations; `simulation.runtime_overrides`
marks flags that change the effective configuration (MPACT
`--allow_memory_region` and `--semihost_htif`), whose values must be recorded
alongside the base ID. Each CI run also publishes
`<archive>.fixture-results.json`, keyed by configuration ID and artifact hash.

| Executable | TCM (ITCM / DTCM at base) | Notes |
| --- | --- | --- |
| `coralnpu_v2_sim`, `coralnpu_m3_sim`, `coralnpu_m4_sim` | 8 KiB / 32 KiB at `0x10000` | MPACT functional; regions are flags |
| `core_mini_axi_sim`, `rvv_core_mini_axi_sim`, `vme_core_mini_axi_sim` | 8 KiB / 32 KiB at `0x10000` | Core CSR `0x30000` |
| `core_mini_itcm512kb_dtcm512kb_axi_sim`, `rvv_core_mini_itcm512kb_dtcm512kb_axi_sim` | 512 KiB / 512 KiB at `0x100000` | Core CSR `0x200000` |
| `core_mini_highmem_axi_sim`, `rvv_core_mini_highmem_axi_sim` | 1 MiB / 1 MiB at `0x100000` | Core CSR `0x200000` |

The self-checking `rvv_matmul_{fp32,int8,bf16}.elf` examples use the highmem
RVV binary and external weights/output at `0x20000000`.
`vme_external_matmul.elf` uses the default-TCM VME binary for external row/column
tile transfers and FP32 accumulation. See `examples/README.md` in the archive
(or [fixtures/README.md](fixtures/README.md)) for layouts and launch commands.

All standalone RTL simulators share the 4 MiB SystemC testbench RAM at
`0x20000000`; larger TCMs do not enlarge it and there is no DMA. RVV variants
use VLEN=128. The larger-TCM targets use the mini retirement buffer;
wrapper patch 0011 exposes their debug ports, so `--instr_trace` is available.
Mini-buffer traces report zero instruction and result fields. `linker/` holds
the generated linker layouts for 8/32 KiB,
512/512 KiB and 1/1 MiB, matching the examples; upstream's template is
`provenance/coralnpu_tcm.ld.tpl`.

Each standalone RTL simulator `<name>_sim` also ships as `<name>_fast_sim`:
the same hardware configuration (it shares the manifest record and ID),
verilated without trace code and without assertions (`--no-assert`, plus
`STOP_COND=0` and `ASSERT_VERBOSE_COND=0` for the firtool `$error`/`$fatal`
checks). It runs about 10-15% faster on the scalar cores and about twice as
fast on the RVV cores, at about half the size, but it does not report RTL
invariant violations, and `--trace`, `--trace_file`, `--trace_fd` and
`--trace_catalog` exit 126. Capture waveforms, or confirm a suspicious
result, with the plain simulator. `smoke.sh` runs the RTL fixture checks on both.

The subsystem archive packages `//fpga:build_chip_verilator_{vector,matrix}_{normal,highmem}`
as `bin/Vchip_<variant>`: 4 MiB SRAM, 32 KiB ROM, peripherals and the
`bus.DmaEngine`. Its 2 GiB DDR aperture is tied off and recorded as
unimplemented. `smoke.sh` shows the upstream launch protocol:
`--load_elf` backdoor loading, then `tools/loader.py --csr_only` over the SPI
DPI port; guest output is in the UART log files of the working directory.

MPACT provides functional V2, M3 and M4 emulation. M3 adds vector floating
point and BF16 conversion; M4 adds experimental Zvt matrix instructions.
Choose the MPACT generation by executable name. The emulator archive
describes the M4 Zvt encodings in `isa/zvt.jsonl`, exported by
`provenance/zvt_export.py` from the patched MPACT decoder: a provenance
line (MPACT commit, patch and input hashes), then one line per instruction
with mask/match, constrained fields, format field layout and disassembly
template. Verilator provides CoreMini
scalar, RvvCoreMini vector and VmeCoreMini matrix RTL simulation. Python
wheels, macOS and older Linux baselines are outside the archive scope.

The bundle also includes `examples/x0_load.elf` (and its larger-TCM variant)
to check discarded scalar loads, access-fault reporting and trap recovery.
Run `bin/core_mini_axi_sim --binary=examples/x0_load.elf --cycles=1000000`;
success prints `CORAL_X0_LOAD_PASS`.

RTL TCM bytes that no ELF segment loads start as zeros. Pass
`+verilator+rand+reset+1` for ones, or `+verilator+rand+reset+2` with
`+verilator+seed+N` for reproducible random contents (seed 0 or none picks
a fresh one); `examples/uninit_tcm.elf` prints them.

For MPACT batch jobs, pass `--max_instructions=N` to bound simulator
instruction steps. The default, 0, is unlimited. Exhaustion returns 124;
batch Ctrl-C returns 130. A guest halt on the last allowed instruction keeps
its guest status. Stderr reports the stop reason, count, budget and final PC.
The flag is incompatible with interactive mode. Retain an external `timeout`
for wall-clock deadlines and blocked host I/O; the budget does not bound those.

The emulator archive includes scalar, integer-vector, vector-FP/BF16, matrix
and memory guest ELFs, Coral's VME (Zvt) cocotb programs as standalone
`vme_*_test.elf`, larger-TCM builds of them, their sources under
`provenance/fixtures/`, and `smoke.sh`. See `examples/README.md` in the
archive, or the [example guide](https://github.com/TheCBaH/devcontainer.coralnpu/blob/main/fixtures/README.md),
for expected calculations, model compatibility, commands and test coverage.
The RTL simulators generate FST waveforms with `--trace`, or with
`--trace_file=path.fst` to choose an output path. See the example guide for
waveform commands.

The RTL simulators can record only chosen signals. `--trace_select=MANIFEST`
(with `--trace` or `--trace_file`) records the variables whose declaration
names are listed in the manifest, matched exactly (the names of the scopes and
of the variable, joined by single spaces, so a dot in a scope name stays part
of it), and fails before the run if a name matches no declaration. The
manifest is the text file `coralview plan` writes:

```text
hwfrp-verilator-select 1
producer core_mini_axi_sim fst
select VCoreMiniAxi.core CoreMiniAxi io_aclk
```

`--trace_catalog=path.fst` writes the declarations of every traceable signal,
with the values of one dump at time zero (a trace without a value block is not
a valid FST), and exits without running (`--binary` is not needed).
`catalogs/` in the emulator archive holds one per RTL simulator. Selection is
implemented by wrapper patch 0027, which adds an exact-name entry point to
Verilator's trace runtime and fixes two defects of its enable mask (a vector
read past its end for sparse selections, and SystemVerilog events that bypass
the mask); `make trace-tests` checks it on the runtime, under libstdc++ debug
containers.

`core_mini_axi_vcd_sim` is `core_mini_axi_sim` built for a live consumer. A
Verilated model has one trace format, so it has a model of its own, traced as
VCD: `--trace_file=path.vcd` writes a file, and `--trace_fd=N` writes the trace
to the open descriptor N, as the simulation runs, so that a pipe to a program
reading the waveform shows it while the run is in progress:

```sh
core_mini_axi_vcd_sim --binary=prog.elf --trace_fd=3 3>&1 1>&2 | consumer -
```

The writes block when the reader is slow; Verilator's own file output retries
them in a busy loop. If the reader closes the pipe the simulator ends with
status 141. `--trace_flush_interval=N` (default 4096) flushes the trace every N
timestamps, 1 for each, and applies to FST as well. A VCD stream ends at the
simulator's exit, so a reader that must know the run completed takes the
simulator's exit status (`set -o pipefail`), not the end of input.
`--trace_select` and `--trace_catalog` work as above, with a manifest whose
`producer` line says `vcd`, and the catalog is `catalogs/core_mini_axi_vcd_sim.catalog.vcd`.

## Development

Open `.devcontainer/devcontainer.json` in VS Code or Codespaces. When
creating a Codespace, select the **Coral NPU** configuration. The separate
Devcontainer CLI configuration is for building containers.

```sh
make fixtures       # x86_64: build the reusable guest ELFs and linker layouts
make dma-tests      # x86_64: Verilator DMA, TileLink and DDR-path tests
make package        # build native simulators and create all dist/ archives
make package ARCHIVES=emulators   # or subsystem
make python-bindings
```

CI caches are keyed by architecture and the `coralnpu` revision, saved once by
successful non-PR builds and left to GitHub's eviction; workflows have no
`actions: write`. To clear them by hand: `gh cache delete --all`.

On ARM64, copy `fixtures/*.elf` from the x86_64 fixture CI artifact before
packaging. The upstream guest compiler is x86_64
only. The ARM64 image builds pinned firtool 1.114.0 from source because
upstream publishes no Linux ARM64 firtool executable; the first build is slow.
Both architectures compile the host emulators natively. Cocotb at the upstream
pin has no Linux ARM64 wheel; its Python targets remain x86_64-only.

The [DMA and TileLink test guide](doc/dma-tilelink-tests.md) inventories both
DMA engines, their Verilator targets and the memory models they exercise.
`make dma-tests DMA_TEST_GROUPS=core` runs the 18 DMA/transpose unit cases;
omit the group to include TileLink and subsystem coverage. These cocotb
models are built from source and are separate from the downloadable emulator
executables. CI publishes their logs and JUnit results.

Use `make test` on a host with Docker to verify archives in fresh Ubuntu
24.04 and Debian 13 runtime containers (the subsystem archive in
`python:3.13-slim-trixie`, for the loader). Tests run without network, source,
build caches or Bazel runfiles and verify scalar/RVV, vector-FP/BF16, matrix,
larger-TCM and external-RAM transfers, subsystem
DMA between SRAM, DTCM and ITCM, and bad inputs. Packaging validates every
manifest against its schema, IDs, artifact hashes and coverage, and agreement
with the generated elaboration parameters.
`make ci` runs fixture build, packaging and external tests on an x86_64
Docker host with the development tools installed.

The devcontainer installs Bazel 9.1.0, the version in
`coralnpu/.bazelversion`, from its release binary; `make prepare` fails if
they differ.

CI runs on native Ubuntu x86_64 and ARM64 runners. `build.json` records
source revisions, patch hashes and tool versions; notices are under
`licenses/`. Development stays on `devel` until CI passes. Pushing a
`v*` tag triggers a release only after both architectures pass validation.
