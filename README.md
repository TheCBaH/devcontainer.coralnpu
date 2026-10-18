# Coral NPU development containers and emulators

Development environment and portable Linux executables for
[google-coral/coralnpu](https://github.com/google-coral/coralnpu).
The upstream source is pinned as the `coralnpu` submodule. Wrapper patches
apply only to the disposable `.cache/source` build tree.

## Download and run

CI artifacts and tagged releases contain three archives per host
architecture (`x86_64`, `aarch64`) and `SHA256SUMS`:

| Archive | Contents |
| --- | --- |
| `coralnpu-emulators-linux-<arch>.tar.gz` | MPACT V2/M3/M4 and seven standalone Verilator RTL simulators |
| `coralnpu-simulator-libraries-linux-<arch>.tar.gz` | Optional `libcoralnpu_simulator{,_rvv,_vme}.so` with headers and example |
| `coralnpu-subsystem-linux-<arch>.tar.gz` | Optional full-subsystem `chip_verilator` simulators and loader |

```sh
sha256sum -c SHA256SUMS
tar -xzf coralnpu-emulators-linux-x86_64.tar.gz
cd coralnpu-emulators-linux-x86_64
bin/coralnpu_v2_sim --semihost_htif --exit_on_ebreak examples/scalar.elf
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak examples/matrix.elf
bin/vme_core_mini_axi_sim --binary=examples/matrix.elf
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

All standalone RTL simulators share the 4 MiB SystemC testbench RAM at
`0x20000000`; larger TCMs do not enlarge it and there is no DMA. RVV variants
use VLEN=128. The larger-TCM targets keep upstream settings, including the
mini retirement buffer and no exposed debug ports, so `--instr_trace` is not
available on them. `linker/` holds the generated linker layouts for 8/32 KiB,
512/512 KiB and 1/1 MiB, matching the examples; upstream's template is
`provenance/coralnpu_tcm.ld.tpl`.

The library archive packages the upstream default-TCM `hw_sim` libraries,
with `include/hw_sim/coralnpu_simulator.h`, a 1 GiB functional DDR backing
store at `0x80000000` (library only, no timing model) and
`examples/library_example`, which loads a library with `dlopen`, runs
`examples/library.elf` and checks DDR, DTCM and mailbox results.

The subsystem archive packages `//fpga:build_chip_verilator_{vector,matrix}_{normal,highmem}`
as `bin/Vchip_<variant>`: 4 MiB SRAM, 32 KiB ROM, peripherals and the
`bus.DmaEngine`. Its 2 GiB DDR aperture is tied off and recorded as
unimplemented. `smoke.sh` shows the upstream launch protocol:
`--load_elf` backdoor loading, then `tools/loader.py --csr_only` over the SPI
DPI port; guest output is in the UART log files of the working directory.

MPACT provides functional V2, M3 and M4 emulation. M3 adds vector floating
point and BF16 conversion; M4 adds experimental Zvt matrix instructions.
Choose the MPACT generation by executable name. Verilator provides CoreMini
scalar, RvvCoreMini vector and VmeCoreMini matrix RTL simulation. Python
wheels, macOS and older Linux baselines are outside the archive scope.

For MPACT batch jobs, pass `--max_instructions=N` to bound simulator
instruction steps. The default, 0, is unlimited. Exhaustion returns 124;
batch Ctrl-C returns 130. A guest halt on the last allowed instruction keeps
its guest status. Stderr reports the stop reason, count, budget and final PC.
The flag is incompatible with interactive mode. Retain an external `timeout`
for wall-clock deadlines and blocked host I/O; the budget does not bound those.

The emulator archive includes scalar, integer-vector, vector-FP/BF16, matrix
and memory guest ELFs, larger-TCM builds of them, their sources under
`provenance/fixtures/`, and `smoke.sh`. See `examples/README.md` in the
archive, or the [example guide](https://github.com/TheCBaH/devcontainer.coralnpu/blob/main/fixtures/README.md),
for expected calculations, model compatibility, commands and test coverage.
The RTL simulators generate FST waveforms with `--trace`; the example guide
includes the output location and conversion to VCD with `fst2vcd`.

## Development

Open `.devcontainer/devcontainer.json` in VS Code or Codespaces. When
creating a Codespace, select the **Coral NPU** configuration. The separate
Devcontainer CLI configuration is for building containers.

```sh
make fixtures       # x86_64: build the reusable guest ELFs and linker layouts
make package        # build native simulators and create all dist/ archives
make package ARCHIVES=emulators   # or libraries, subsystem
make python-bindings
```

On ARM64, copy `fixtures/*.elf` from the x86_64 fixture CI artifact before
packaging. The upstream guest compiler is x86_64
only. The ARM64 image builds pinned firtool 1.114.0 from source because
upstream publishes no Linux ARM64 firtool executable; the first build is slow.
Both architectures compile the host emulators natively. Cocotb at the upstream
pin has no Linux ARM64 wheel; its Python targets remain x86_64-only.

Use `make test` on a host with Docker to verify archives in fresh Ubuntu
24.04 and Debian 13 runtime containers (the subsystem archive in
`python:3.13-slim-trixie`, for the loader). Tests run without network, source,
build caches or Bazel runfiles and verify scalar/RVV, vector-FP/BF16, matrix,
larger-TCM and external-RAM transfers, library DDR/mailbox results, subsystem
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
