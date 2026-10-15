# Coral NPU development containers and emulators

Development environment and portable Linux executables for
[google-coral/coralnpu](https://github.com/google-coral/coralnpu).
The upstream source is pinned as the `coralnpu` submodule. Wrapper patches
apply only to the disposable `.cache/source` build tree.

## Download and run

CI artifacts contain `coralnpu-emulators-linux-x86_64.tar.gz` or
`coralnpu-emulators-linux-aarch64.tar.gz` and `SHA256SUMS`. Tagged releases
publish the same assets. An initial release has not been published.

```sh
sha256sum -c SHA256SUMS
tar -xzf coralnpu-emulators-linux-x86_64.tar.gz
cd coralnpu-emulators-linux-x86_64
bin/coralnpu_v2_sim --semihost_htif --exit_on_ebreak examples/scalar.elf
bin/coralnpu_m3_sim --semihost_htif --exit_on_ebreak examples/rvv_fp.elf
bin/coralnpu_m4_sim --semihost_htif --exit_on_ebreak examples/matrix.elf
bin/vme_core_mini_axi_sim --binary=examples/matrix.elf
bin/core_mini_axi_sim --binary=examples/scalar.elf
bin/rvv_core_mini_axi_sim --binary=examples/rvv.elf
bash smoke.sh
```

Use the archive matching the **host** architecture; guest programs are RV32
Coral NPU ELFs on either host. Binaries require Linux with glibc 2.39 or newer
(Ubuntu 24.04, Debian 13). No Bazel, Python, Docker, repository checkout or
global library-path configuration is required. Keep `bin/` and `lib/`
together when relocating the archive. Upstream command-line options remain
available through `--helpfull`.

MPACT provides functional V2, M3 and M4 emulation. M3 adds vector floating
point and BF16 conversion; M4 adds experimental Zvt matrix instructions.
Choose the MPACT generation by executable name. Verilator provides CoreMini
scalar, RvvCoreMini vector and VmeCoreMini matrix RTL simulation. High-memory
variants, Python wheels, macOS and older Linux baselines are outside the archive
scope.

Every archive includes scalar, integer-vector, vector-FP/BF16 and matrix guest
ELFs, their sources under `provenance/fixtures/`, and `smoke.sh`. See
`examples/README.md` in the archive, or the [example guide](https://github.com/TheCBaH/devcontainer.coralnpu/blob/main/fixtures/README.md),
for expected calculations, model compatibility, commands and test coverage.
The RTL simulators generate FST waveforms with `--trace`; the example guide
includes the output location and conversion to VCD with `fst2vcd`.

## Development

Open `.devcontainer/devcontainer.json` in VS Code or Codespaces. When
creating a Codespace, select the **Coral NPU** configuration. The separate
Devcontainer CLI configuration is for building containers.

```sh
make fixtures       # x86_64: build all four reusable guest ELFs
make package        # build native simulators and create dist/ archives
make python-bindings
```

On ARM64, copy `fixtures/*.elf` from the x86_64 fixture CI artifact before
packaging. The upstream guest compiler is x86_64
only. The ARM64 image builds pinned firtool 1.114.0 from source because
upstream publishes no Linux ARM64 firtool executable; the first build is slow.
Both architectures compile the host emulators natively. Cocotb at the upstream
pin has no Linux ARM64 wheel; its Python targets remain x86_64-only.

Use `make test` on a host with Docker to verify archives in fresh Ubuntu
24.04 and Debian 13 runtime containers. Tests run without network, source,
build caches or Bazel runfiles and verify scalar/RVV, vector-FP/BF16, matrix
results and bad inputs.
`make ci` runs fixture build, packaging and external tests on an x86_64
Docker host with the development tools installed.

The devcontainer installs Bazel 9.1.0, the version in
`coralnpu/.bazelversion`, from its release binary; `make prepare` fails if
they differ.

CI runs on native Ubuntu x86_64 and ARM64 runners. `build.json` records
source revisions, patch hashes and tool versions; notices are under
`licenses/`. Development stays on `devel` until CI passes. Pushing a
`v*` tag triggers a release only after both architectures pass validation.
