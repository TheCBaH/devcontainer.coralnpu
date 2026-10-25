#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile

from build import ROOT, SOURCE, VME_TESTS, RVV_MATMUL_TESTS, VCD_SIMULATORS, run
import manifest
import validate_manifest
import zvt_export

SYSTEM = re.compile(r"^(lib(c|m|pthread|dl|rt|resolv|util)\.so\.|ld-linux)")
ARCH = {"x86_64": "x86_64", "aarch64": "aarch64"}[platform.machine()]
ARCHIVES = {
    "emulators": "coralnpu-emulators-linux-",
    "libraries": "coralnpu-simulator-libraries-linux-",
    "subsystem": "coralnpu-subsystem-linux-",
}
# Example ELF: (success marker, configurations it runs on, linker layout).
EXAMPLES = {
    "emulators": {
        "batch_limits.elf": ("CORAL_MPACT_LIMITS_PASS", ["mpact-v2", "mpact-m3", "mpact-m4"],
                             "itcm8k_dtcm32k.ld"),
        "scalar.elf": ("CORAL_SCALAR_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                             "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "rvv.elf": ("CORAL_RVV_PASS", ["rvv-core-mini-axi", "vme-core-mini-axi", "mpact-v2", "mpact-m3",
                                       "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "rvv_fp.elf": ("CORAL_RVV_FP_PASS", ["rvv-core-mini-axi", "vme-core-mini-axi", "mpact-m3", "mpact-m4"],
                       "itcm8k_dtcm32k.ld"),
        "external_payload.elf": ("CORAL_EXTERNAL_PAYLOAD_PASS", ["core-mini-axi", "mpact-v2"],
                                 "itcm8k_dtcm32k.ld"),
        **{name + ".elf": ("CORAL_RVV_MATMUL_" + name.rsplit("_", 1)[1].upper() + "_PASS",
                           ["rvv-core-mini-highmem-axi"], "itcm1m_dtcm1m.ld") for name in RVV_MATMUL_TESTS},
        "vme_external_matmul.elf": ("CORAL_VME_EXTERNAL_MATMUL_PASS", ["vme-core-mini-axi", "mpact-m4"],
                                    "itcm8k_dtcm32k.ld"),
        "matrix.elf": ("CORAL_MATRIX_PASS", ["vme-core-mini-axi", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        **{name + ".elf": ("CORAL_VME_TEST_PASS", ["vme-core-mini-axi", "mpact-m4"], "itcm8k_dtcm32k.ld")
           for name in VME_TESTS},
        "host_io.elf": ("CORAL_HOST_IO_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                               "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "host_io_tcm512k.elf": ("CORAL_HOST_IO_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "host_ram.elf": ("CORAL_HOST_RAM_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                                 "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "host_ram_tcm512k.elf": ("CORAL_HOST_RAM_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "exit_status.elf": ("CORAL_EXIT_STATUS_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                                        "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "exit_status_tcm512k.elf": ("CORAL_EXIT_STATUS_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "uninit_tcm.elf": ("CORAL_UNINIT_TCM_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi"],
                           "itcm8k_dtcm32k.ld"),
        "uninit_tcm_tcm512k.elf": ("CORAL_UNINIT_TCM_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "x0_load.elf": ("CORAL_X0_LOAD_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                               "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "x0_load_tcm512k.elf": ("CORAL_X0_LOAD_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "trap_address.elf": ("CORAL_TRAP_ADDRESS_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                                        "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "trap_address_tcm512k.elf": ("CORAL_TRAP_ADDRESS_PASS", ["core-mini-itcm512kb-dtcm512kb-axi",
            "core-mini-highmem-axi", "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv-core-mini-highmem-axi"],
            "itcm512k_dtcm512k.ld"),
        "memory.elf": ("CORAL_MEMORY_PASS", ["core-mini-axi", "rvv-core-mini-axi", "vme-core-mini-axi",
                                             "mpact-v2", "mpact-m3", "mpact-m4"], "itcm8k_dtcm32k.ld"),
        "scalar_tcm512k.elf": ("CORAL_SCALAR_PASS", ["core-mini-itcm512kb-dtcm512kb-axi", "core-mini-highmem-axi",
                                                     "rvv-core-mini-itcm512kb-dtcm512kb-axi",
                                                     "rvv-core-mini-highmem-axi"], "itcm512k_dtcm512k.ld"),
        "rvv_tcm512k.elf": ("CORAL_RVV_PASS", ["rvv-core-mini-itcm512kb-dtcm512kb-axi",
                                               "rvv-core-mini-highmem-axi"], "itcm512k_dtcm512k.ld"),
        "rvv_fp_tcm512k.elf": ("CORAL_RVV_FP_PASS", ["rvv-core-mini-itcm512kb-dtcm512kb-axi",
                                                     "rvv-core-mini-highmem-axi"], "itcm512k_dtcm512k.ld"),
        "memory_tcm512k.elf": ("CORAL_MEMORY_PASS", ["core-mini-itcm512kb-dtcm512kb-axi", "core-mini-highmem-axi",
                                                     "rvv-core-mini-itcm512kb-dtcm512kb-axi",
                                                     "rvv-core-mini-highmem-axi"], "itcm512k_dtcm512k.ld"),
        "memory_tcm1m.elf": ("CORAL_MEMORY_PASS", ["core-mini-highmem-axi", "rvv-core-mini-highmem-axi"],
                             "itcm1m_dtcm1m.ld"),
    },
    "libraries": {
        "library.elf": ("CORAL_LIBRARY_PASS", ["library-core-mini-axi", "library-rvv-core-mini-axi",
                                               "library-vme-core-mini-axi"], "itcm8k_dtcm32k.ld"),
    },
    "subsystem": {
        "subsystem_dma.elf": ("CORAL_SUBSYSTEM_DMA_PASS", ["subsystem-vector-normal", "subsystem-matrix-normal"],
                              "itcm8k_dtcm32k.ld"),
        "subsystem_dma_tcm1m.elf": ("CORAL_SUBSYSTEM_DMA_PASS", ["subsystem-vector-highmem",
                                                                 "subsystem-matrix-highmem"], "itcm1m_dtcm1m.ld"),
    },
}
SUBSYSTEM_BINARY = "bin/Vchip_"


def dependencies(path):
    output = run("ldd", str(path), cwd=ROOT)
    if "not found" in output:
        raise RuntimeError(output)
    return re.findall(r"(\S+) => (/\S+)", output)


def bundle_libraries(bundle, sources, rpath):
    libraries = {}
    for path, source in sources:
        machine = run("readelf", "-h", str(path), cwd=ROOT)
        expected = "AArch64" if ARCH == "aarch64" else "Advanced Micro Devices X86-64"
        if expected not in machine:
            raise RuntimeError("Wrong architecture: " + machine)
        for soname, location in dependencies(Path(source)):
            if not SYSTEM.match(soname):
                if soname in libraries and Path(libraries[soname]).resolve() != Path(location).resolve():
                    raise RuntimeError("Conflicting libraries: " + soname)
                libraries[soname] = location
        run("patchelf", "--set-rpath", rpath, str(path), cwd=ROOT)
    pending = list(libraries)
    while pending:
        soname = pending.pop()
        path = bundle / "lib" / soname
        shutil.copy2(libraries[soname], path)
        path.chmod(0o755)
        for dep, location in dependencies(Path(libraries[soname])):
            if not SYSTEM.match(dep) and dep not in libraries:
                libraries[dep] = location
                pending.append(dep)
        run("patchelf", "--set-rpath", "$ORIGIN", str(path), cwd=ROOT)
    return libraries


def copy_licenses(bundle):
    shutil.copy2(ROOT / "LICENSE", bundle / "licenses/wrapper-MIT")
    shutil.copy2(ROOT / "coralnpu/LICENSE", bundle / "licenses/coralnpu-Apache-2.0")
    for notice in (ROOT / "licenses").glob("*"):
        shutil.copy2(notice, bundle / "licenses" / notice.name)
    output_root = Path(run("bazel", "--output_user_root=" + str(ROOT / ".cache/bazel"),
                           "info", "output_base")) / "external"
    for repo in output_root.iterdir():
        if repo.is_dir():
            for license_path in repo.glob("*"):
                if license_path.is_file() and re.match(r"(?i)(license|copying|notice|artistic)", license_path.name):
                    shutil.copy2(license_path, bundle / "licenses" / (repo.name + "-" + license_path.name))
    for pattern in ("libstdc++*", "gcc-*-base", "libgcc-s*"):
        for path in Path("/usr/share/doc").glob(pattern + "/copyright"):
            shutil.copy2(path, bundle / "licenses" / (path.parent.name + "-copyright"))
    return output_root


def copy_provenance(bundle):
    for filename in ("MODULE.bazel", "MODULE.bazel.lock", "rules/repo_defs.bzl", "rules/repos.bzl",
                     "toolchain/coralnpu_tcm.ld.tpl"):
        shutil.copy2(SOURCE / filename, bundle / "provenance" / Path(filename).name)
    for patch in (ROOT / "patches").glob("*.patch"):
        shutil.copy2(patch, bundle / "provenance" / patch.name)
    shutil.copytree(ROOT / "fixtures", bundle / "provenance/fixtures",
                    ignore=shutil.ignore_patterns("*.elf", "*.ld"))
    shutil.copytree(ROOT / "mpact-patches", bundle / "provenance/mpact-patches")
    shutil.copytree(SOURCE / "tests/cocotb/vme_test", bundle / "provenance/fixtures/vme_test")
    for kernel in ("rvv_matmul.cc", "rvv_int8_matmul.cc", "rvv_bf16_matmul.cc"):
        destination = bundle / "provenance/fixtures/gemma_kernels" / kernel
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(SOURCE / "tests/cocotb/rvv/ml_ops/gemma_kernels" / kernel, destination)
    shutil.copytree(ROOT / "manifest", bundle / "provenance/manifest")
    for script in ("manifest.py", "validate_manifest.py", "zvt_export.py"):
        shutil.copy2(ROOT / "scripts" / script, bundle / "provenance" / script)


def host():
    return {"architecture": ARCH, "os": "linux", "libc": "glibc", "minimum_glibc": manifest.MINIMUM_GLIBC}


def build_tools():
    tools = {
        "bazel": run("bazel", "--version"),
        "clang": run("clang", "--version").splitlines()[0],
        "java": subprocess.check_output(["java", "--version"], text=True).splitlines()[0],
        "glibc": run("getconf", "GNU_LIBC_VERSION"),
    }
    firtool = shutil.which("firtool")
    if firtool:
        tools["firtool"] = run(firtool, "--version").splitlines()[0]
    return tools


def configurations(kind, outputs, revision):
    records = {}
    for name, path in outputs["files"].items():
        model = outputs["elaboration"].get(name)
        if name in VCD_SIMULATORS:
            continue
        if kind == "emulators" and name in manifest.MPACT:
            record = manifest.mpact(name, revision)
        elif kind == "emulators":
            record = manifest.standalone(name, model, model["parameters_header"], revision)
        elif kind == "libraries":
            record = manifest.library(name, model, model["parameters_header"], revision)
        else:
            record = manifest.subsystem(name, model, revision)
        records[name] = manifest.finalize(record)
    for name, base in VCD_SIMULATORS.items():
        if name in outputs["files"]:
            records[name] = records[base]
    return records


def artifact(bundle, relative, record, kind, runtime_files):
    path = bundle / relative
    entry = {
        "path": relative,
        "configuration_id": record["id"],
        "kind": "shared-library" if kind == "libraries" else "executable",
        "sha256": manifest.sha256(path),
        "host": host(),
        "abi": None,
        "launch": {"method": "command-line", "command": [relative] + (
            ["--semihost_htif", "--exit_on_ebreak", "--max_instructions=100000000", "<elf>"] if record["simulation"]["backend"] == "mpact" else
            ["--load_elf=<elf>"] if kind == "subsystem" else ["--binary=<elf>"])},
        "runtime_files": runtime_files,
    }
    if kind == "libraries":
        entry["abi"] = ("C++17 Itanium ABI against libstdc++ (_GLIBCXX_USE_CXX11_ABI=1); "
                        "extern \"C\" CoralNPUSimulator* coralnpu_simulator_verilator_create(void)")
        entry["launch"] = {"method": "dlopen-or-link",
                           "entry_points": ["coralnpu_simulator_verilator_create",
                                            "coralnpu_simulator_verilator_create_with_options"],
                           "headers": ["include/hw_sim/coralnpu_simulator.h", "include/hw_sim/mailbox.h"]}
    return entry


def package(kind):
    outputs = json.loads((ROOT / ".cache" / ("outputs-" + kind + ".json")).read_text())
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    name = ARCHIVES[kind] + ARCH
    bundle = ROOT / ".cache" / name
    if bundle.exists():
        shutil.rmtree(bundle)
    for directory in ("bin", "lib", "examples", "licenses", "provenance", "linker"):
        (bundle / directory).mkdir(parents=True, exist_ok=True)
    revision = run("git", "rev-parse", "HEAD", cwd=ROOT / "coralnpu")
    records = configurations(kind, outputs, revision)
    placed = []
    for filename, source in outputs["files"].items():
        if kind == "libraries":
            relative = "lib/" + filename
        elif kind == "subsystem":
            relative = SUBSYSTEM_BINARY + filename.split("chip_verilator_")[1]
        else:
            relative = "bin/" + filename
        shutil.copy2(source, bundle / relative)
        (bundle / relative).chmod(0o755)
        placed.append((bundle / relative, source, filename, relative))
    libraries = bundle_libraries(bundle, [(p, s) for p, s, _, _ in placed],
                                 "$ORIGIN" if kind == "libraries" else "$ORIGIN/../lib")
    output_root = copy_licenses(bundle)
    copy_provenance(bundle)
    for example in EXAMPLES[kind]:
        shutil.copy2(ROOT / "fixtures" / example, bundle / "examples" / example)
    for layout in {layout for _, _, layout in EXAMPLES[kind].values()}:
        shutil.copy2(ROOT / "fixtures" / layout, bundle / "linker" / layout)
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    shutil.copy2(ROOT / "fixtures/README.md", bundle / "examples/README.md")
    runtime = []
    isa = []
    catalogs = []
    if kind == "emulators":
        (bundle / "catalogs").mkdir()
        for _, _, filename, relative in placed:
            if filename in manifest.MPACT:
                continue
            catalog = "catalogs/" + filename + (".catalog.vcd" if filename in VCD_SIMULATORS else ".catalog.fst")
            run(str(bundle / relative), "--trace_catalog=" + str(bundle / catalog), cwd=ROOT)
            size = (bundle / catalog).stat().st_size
            if size == 0:
                raise RuntimeError("Empty trace catalog: " + catalog)
            print("catalog", catalog, size, flush=True)
            catalogs.append(catalog)
        mpact_riscv, = output_root.glob("*com_google_mpact-riscv")
        (bundle / "isa").mkdir()
        zvt_export.export(mpact_riscv, SOURCE, bundle / "isa/zvt.jsonl", revision)
        isa.append("isa/zvt.jsonl")
        shutil.copy2(ROOT / "scripts/smoke.sh", bundle / "smoke.sh")
        shutil.copy2(ROOT / "scripts/host-contract.sh", bundle / "host-contract.sh")
        shutil.copy2(ROOT / "scripts/smoke-vcd.sh", bundle / "smoke-vcd.sh")
        shutil.copy2(ROOT / "scripts/matrix-memory.sh", bundle / "matrix-memory.sh")
        shutil.copy2(ROOT / "scripts/mpact-limits.sh", bundle / "mpact-limits.sh")
    elif kind == "libraries":
        include = bundle / "include/hw_sim"
        include.mkdir(parents=True)
        for header in ("coralnpu_simulator.h", "mailbox.h"):
            shutil.copy2(SOURCE / "hw_sim" / header, include / header)
        helpers = bundle / "examples/tests/verilator_sim"
        helpers.mkdir(parents=True)
        for source in ("elf.h", "elf.cc"):
            shutil.copy2(SOURCE / "tests/verilator_sim" / source, helpers / source)
        shutil.copy2(ROOT / "examples/library_example.cc", bundle / "examples/library_example.cc")
        run("clang++", "-std=c++17", "-O2", "-I", str(bundle / "include"), "-I", str(bundle / "examples"),
            "-o", str(bundle / "examples/library_example"), str(bundle / "examples/library_example.cc"),
            str(helpers / "elf.cc"), "-ldl", cwd=ROOT)
        run("patchelf", "--set-rpath", "$ORIGIN/../lib", str(bundle / "examples/library_example"), cwd=ROOT)
        shutil.copy2(ROOT / "scripts/smoke-libraries.sh", bundle / "smoke.sh")
    else:
        tools = bundle / "tools"
        tools.mkdir()
        for script in ("utils/coralnpu_soc_loader/loader.py", "utils/coralnpu_soc_loader/spi_driver.py"):
            shutil.copy2(SOURCE / script, tools / Path(script).name)
        elftools = Path(outputs["runtime"]["elftools"])
        shutil.copytree(elftools, tools / "elftools", ignore=shutil.ignore_patterns("__pycache__"))
        for license_path in elftools.parent.glob("pyelftools-*.dist-info/*LICENSE*"):
            shutil.copy2(license_path, bundle / "licenses" / ("pyelftools-" + license_path.name))
        (bundle / "share").mkdir()
        shutil.copy2(outputs["runtime"]["grey_bars_320x240.raw"], bundle / "share/grey_bars_320x240.raw")
        shutil.copy2(ROOT / "scripts/smoke-subsystem.sh", bundle / "smoke.sh")
        runtime = ["tools/loader.py", "tools/spi_driver.py", "tools/elftools", "share/grey_bars_320x240.raw"]
    for path in [*bundle.glob("bin/*"), *bundle.glob("lib/*"), *bundle.glob("examples/library_example")]:
        symbols = run("readelf", "--version-info", str(path), cwd=ROOT)
        for major, minor in re.findall(r"GLIBC_(\d+)\.(\d+)", symbols):
            if (int(major), int(minor)) > tuple(map(int, manifest.MINIMUM_GLIBC.split("."))):
                raise RuntimeError("Newer glibc needed by " + str(path))
    lib_files = sorted("lib/" + soname for soname in libraries)
    document = {
        "schema_version": manifest.SCHEMA_VERSION,
        "archive": {
            "name": name,
            "kind": kind,
            "wrapper_repository": manifest.WRAPPER_REPOSITORY,
            "wrapper_revision": run("git", "rev-parse", "HEAD", cwd=ROOT),
            "host": host(),
            "build_tools": build_tools(),
        },
        "id_rule": manifest.ID_RULE,
        "configurations": sorted({record["id"]: record for record in records.values()}.values(),
                                 key=lambda record: record["name"]),
        "artifacts": [artifact(bundle, relative, records[filename], kind, lib_files + runtime)
                      for _, _, filename, relative in sorted(placed, key=lambda item: item[3])],
        "fixtures": [{"path": "examples/" + example, "sha256": manifest.sha256(bundle / "examples" / example),
                      "marker": marker, "linker_layout": "linker/" + layout,
                      "configurations": sorted({record["id"] for record in records.values()
                                                if record["name"] in names})}
                     for example, (marker, names, layout) in sorted(EXAMPLES[kind].items())],
    }
    (bundle / "hardware-configurations.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "manifest/hardware-configurations.schema.json", bundle / "hardware-configurations.schema.json")
    validate_manifest.validate(bundle)
    (bundle / "build.json").write_text(json.dumps({
        "architecture": ARCH,
        "wrapper_commit": document["archive"]["wrapper_revision"],
        "upstream_commit": revision,
        "configuration_manifest": "hardware-configurations.json",
        "files": sorted(relative for _, _, _, relative in placed),
        "examples": sorted(EXAMPLES[kind]),
        "isa": isa,
        "catalogs": sorted(catalogs),
        "runtime_libraries": sorted(libraries),
        "runtime_packages": run("dpkg-query", "-W", "-f=${Package} ${Version}\n",
                                "libstdc++6", "libgcc-s1", cwd=ROOT).splitlines(),
        "build_tools": document["archive"]["build_tools"],
        "minimum_glibc": manifest.MINIMUM_GLIBC,
    }, indent=2) + "\n")
    timestamp = int(run("git", "show", "-s", "--format=%ct", "HEAD", cwd=ROOT))

    def normalize(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = timestamp
        return info
    archive = dist / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bundle, arcname=name, filter=normalize)
    shutil.copy2(bundle / "hardware-configurations.json", dist / (name + ".hardware-configurations.json"))
    print(archive)


def main():
    for kind in sys.argv[1:] or ["emulators"]:
        package(kind)
    archives = sorted((ROOT / "dist").glob("*.tar.gz"))
    (ROOT / "dist/SHA256SUMS").write_text("".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in archives))


if __name__ == "__main__":
    main()
