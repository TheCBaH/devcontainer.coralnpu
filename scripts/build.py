#!/usr/bin/env python3
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/source"
FIXTURES = ("scalar", "rvv", "rvv_fp", "matrix", "memory", "memory_tcm512k", "memory_tcm1m",
            "scalar_tcm512k", "rvv_tcm512k", "rvv_fp_tcm512k", "library", "subsystem_dma",
            "subsystem_dma_tcm1m", "trap_address", "trap_address_tcm512k", "exit_status", "exit_status_tcm512k", "host_ram", "host_ram_tcm512k", "host_io", "host_io_tcm512k")
# Linker layouts shipped with the archives, taken from these fixtures.
LINKER_LAYOUTS = {
    "itcm8k_dtcm32k.ld": "memory_ITCM8KB_DTCM32KB_STACK2048_HEAPDTCM.ld",
    "itcm512k_dtcm512k.ld": "memory_tcm512k_ITCM512KB_DTCM512KB_STACK2048_HEAPDTCM.ld",
    "itcm1m_dtcm1m.ld": "memory_tcm1m_ITCM1024KB_DTCM1024KB_STACK2048_HEAPDTCM.ld",
}
CORE = "//hdl/chisel/src/coralnpu:"
# Executable: (Bazel target, elaborated Chisel library, module).
EMULATORS = {
    "coralnpu_v2_sim": ("@coralnpu_mpact//sim:coralnpu_v2_sim", None, None),
    "coralnpu_m3_sim": ("@coralnpu_mpact//sim:coralnpu_m3_sim", None, None),
    "coralnpu_m4_sim": ("@coralnpu_mpact//sim:coralnpu_m4_sim", None, None),
    "core_mini_axi_sim": ("//tests/verilator_sim:core_mini_axi_sim", "core_mini_axi_cc_library", "CoreMiniAxi"),
    "rvv_core_mini_axi_sim": ("//tests/verilator_sim:rvv_core_mini_axi_sim", "rvv_core_mini_axi_cc_library",
                              "RvvCoreMiniAxi"),
    "vme_core_mini_axi_sim": ("//tests/verilator_sim:vme_core_mini_axi_sim", "vme_core_mini_axi_cc_library",
                              "VmeCoreMiniAxi"),
    "core_mini_highmem_axi_sim": ("//tests/verilator_sim:core_mini_highmem_axi_sim",
                                  "core_mini_highmem_axi_cc_library", "CoreMiniHighmemAxi"),
    "rvv_core_mini_highmem_axi_sim": ("//tests/verilator_sim:rvv_core_mini_highmem_axi_sim",
                                      "rvv_core_mini_highmem_axi_cc_library", "RvvCoreMiniHighmemAxi"),
    "core_mini_itcm512kb_dtcm512kb_axi_sim": ("//tests/verilator_sim:core_mini_itcm512kb_dtcm512kb_axi_sim",
                                              "core_mini_itcm512kb_dtcm512kb_axi_cc_library",
                                              "CoreMini_ITCM512KB_DTCM512KBAxi"),
    "rvv_core_mini_itcm512kb_dtcm512kb_axi_sim": ("//tests/verilator_sim:rvv_core_mini_itcm512kb_dtcm512kb_axi_sim",
                                                  "rvv_core_mini_itcm512kb_dtcm512kb_axi_cc_library",
                                                  "RvvCoreMini_ITCM512KB_DTCM512KBAxi"),
}
LIBRARIES = {
    "libcoralnpu_simulator.so": ("//hw_sim:libcoralnpu_simulator.so", "core_mini_axi_cc_library", "CoreMiniAxi"),
    "libcoralnpu_simulator_rvv.so": ("//hw_sim:libcoralnpu_simulator_rvv.so", "rvv_core_mini_axi_cc_library",
                                     "RvvCoreMiniAxi"),
    "libcoralnpu_simulator_vme.so": ("//hw_sim:libcoralnpu_simulator_vme.so", "vme_core_mini_axi_cc_library",
                                     "VmeCoreMiniAxi"),
}
SUBSYSTEMS = {
    "chip_verilator_" + variant: ("//fpga:build_chip_verilator_" + variant, variant)
    for variant in ("vector_normal", "vector_highmem", "matrix_normal", "matrix_highmem")
}
MPACT_PLATFORM = "--platforms=//toolchain/host_clang:host_clang_platform"


def run(*args, cwd=SOURCE):
    try:
        return subprocess.check_output(args, cwd=cwd, text=True).strip()
    except subprocess.CalledProcessError as error:
        if error.output:
            print(error.output, file=sys.stderr, flush=True)
        raise


def bazel(*args):
    cache = ROOT / ".cache"
    return run("bazel", "--output_user_root=" + str(cache / "bazel"), *args,
               "--repository_cache=" + str(cache / "repos"),
               "--disk_cache=" + str(cache / "actions"),
               "--jobs=" + os.environ.get("BUILD_JOBS", "2"),
               "--verbose_failures")


def attributes(label):
    output = run("bazel", "--output_user_root=" + str(ROOT / ".cache/bazel"), "query",
                 "--output=streamed_jsonproto", label)
    rule = json.loads(output.splitlines()[0])["rule"]
    values = {}
    for attribute in rule.get("attribute", []):
        for key in ("stringValue", "stringListValue"):
            if key in attribute:
                values[attribute["name"]] = attribute[key]
    return values


def elaboration(library, module):
    command = attributes(CORE + library + "_emit_verilog")["cmd"]
    return {
        "library": library,
        "module": module,
        "generator_flags": command.split("--target-dir=$(RULEDIR)", 1)[1].split(),
        "verilator_options": attributes(CORE + library).get("vopts", []),
    }


def copy_output(source, destination):
    destination.unlink(missing_ok=True)
    shutil.copy2(source, destination)


def output(target, *flags):
    files = bazel("cquery", "-c", "opt", *flags, target, "--output=files")
    return str(SOURCE / files.splitlines()[-1])


def build_cores(targets):
    files, models = {}, {}
    for name, (target, library, module) in targets.items():
        print("Building", target, flush=True)
        flags = [MPACT_PLATFORM] if target.startswith("@coralnpu_mpact//") else []
        bazel("build", "-c", "opt", *flags, target)
        files[name] = output(target, *flags)
        if library:
            header = CORE + "V" + module + "_parameters.h"
            bazel("build", "-c", "opt", header)
            models[name] = dict(elaboration(library, module), parameters_header=output(header))
    return {"files": files, "elaboration": models}


def build_subsystems():
    files, models = {}, {}
    for name, (target, variant) in SUBSYSTEMS.items():
        print("Building", target, flush=True)
        bazel("build", "-c", "opt", "--output_groups=+binary", target)
        binary, = (SOURCE / "bazel-bin/fpga").glob(
            "*build_chip_verilator_" + variant + "/**/sim-verilator/Vchip_verilator")
        files[name] = str(binary.resolve())
        rule = attributes(target)
        options = attributes("//fpga:verilator_options_" + variant)
        models[name] = {
            "core": next(core for core in rule.get("cores", []) if "chisel_subsystem" in core),
            "flags": rule.get("flags", []),
            "verilator_options": options.get("build_setting_default", []),
        }
    image = "//fpga/ip/ispyocto:grey_bars_320x240.raw"
    bazel("build", "-c", "opt", "//utils/coralnpu_soc_loader:loader", image)
    elftools, = (SOURCE / "bazel-bin/utils/coralnpu_soc_loader/loader.runfiles").glob(
        "*pyelftools/elftools")
    runtime = {"elftools": str(elftools), "grey_bars_320x240.raw": output(image)}
    return {"files": files, "elaboration": models, "runtime": runtime}


def main():
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "fixtures":
        if platform.machine() != "x86_64":
            raise SystemExit("Build guest fixtures on x86_64, then copy fixtures/*.elf to ARM64")
        bazel("build", "-c", "opt", *("//portable_fixtures:" + name + ".elf" for name in FIXTURES))
        for name in FIXTURES:
            output_file = bazel("cquery", "//portable_fixtures:" + name + ".elf", "-c", "opt", "--output=files")
            copy_output(SOURCE / output_file.splitlines()[-1], ROOT / "fixtures" / (name + ".elf"))
        for layout, script in LINKER_LAYOUTS.items():
            label = "//portable_fixtures:" + script
            bazel("build", "-c", "opt", label)
            copy_output(output(label), ROOT / "fixtures" / layout)
        output_base = Path(run("bazel", "--output_user_root=" + str(ROOT / ".cache/bazel"),
                               "info", "output_base"))
        objdump, = (output_base / "external").glob("*toolchain_coralnpu_v2/bin/riscv64-unknown-elf-objdump")
        for name in ("scalar", "scalar_tcm512k", "memory", "memory_tcm512k", "memory_tcm1m", "library"):
            disassembly = run(str(objdump), "-d", str(ROOT / "fixtures" / (name + ".elf")))
            vector = re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(v\S+)", disassembly, re.MULTILINE)
            if vector:
                raise RuntimeError("Vector instruction in scalar fixture " + name + ": " + vector.group(0))
    elif command == "build":
        kinds = sys.argv[2:] or ["emulators"]
        for kind in kinds:
            if kind == "emulators":
                outputs = build_cores(EMULATORS)
            elif kind == "libraries":
                outputs = build_cores(LIBRARIES)
            elif kind == "subsystem":
                outputs = build_subsystems()
            else:
                raise SystemExit("Unknown archive kind: " + kind)
            (ROOT / ".cache" / ("outputs-" + kind + ".json")).write_text(json.dumps(outputs, indent=2))
    elif command == "python-bindings":
        bazel("build", "-c", "opt", "//sw/coralnpu_sim:coralnpu_v2_sim")
    else:
        raise SystemExit("Unknown command: " + command)


def prepare():
    expected = (ROOT / "coralnpu/.bazelversion").read_text().strip()
    actual = run("bazel", "--version", cwd=ROOT).split()[-1]
    if actual != expected:
        raise SystemExit("bazel " + actual + " installed, coralnpu requires " + expected)
    SOURCE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "--delete", "--exclude=.git", "--exclude=bazel-*",
                    str(ROOT / "coralnpu") + "/", str(SOURCE) + "/"], check=True)
    # Keep Git from interpreting patch paths relative to the wrapper repository.
    patch_env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(SOURCE.parent))
    for patch in sorted((ROOT / "patches").glob("*.patch")):
        subprocess.run(["git", "apply", "--verbose", str(patch)], cwd=SOURCE, env=patch_env, check=True)
    (SOURCE / "internal/netlist_test").mkdir(parents=True, exist_ok=True)
    (SOURCE / "internal/netlist_test/BUILD.bazel").write_text("")
    shutil.copytree(ROOT / "fixtures", SOURCE / "portable_fixtures", dirs_exist_ok=True)
    shutil.copytree(ROOT / "mpact-patches", SOURCE / "portable_patches", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
