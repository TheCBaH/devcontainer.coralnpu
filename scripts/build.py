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
FIXTURES = ("scalar", "rvv", "rvv_fp", "matrix")
TARGETS = {
    "coralnpu_v2_sim": "@coralnpu_mpact//sim:coralnpu_v2_sim",
    "coralnpu_m3_sim": "@coralnpu_mpact//sim:coralnpu_m3_sim",
    "coralnpu_m4_sim": "@coralnpu_mpact//sim:coralnpu_m4_sim",
    "core_mini_axi_sim": "//tests/verilator_sim:core_mini_axi_sim",
    "rvv_core_mini_axi_sim": "//tests/verilator_sim:rvv_core_mini_axi_sim",
    "vme_core_mini_axi_sim": "//tests/verilator_sim:vme_core_mini_axi_sim",
}


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


def prepare():
    SOURCE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "--delete", "--exclude=.git", "--exclude=bazel-*",
                    str(ROOT / "coralnpu") + "/", str(SOURCE) + "/"], check=True)
    for patch in sorted((ROOT / "patches").glob("*.patch")):
        subprocess.run(["git", "apply", str(patch)], cwd=SOURCE, check=True)
    (SOURCE / "internal/netlist_test").mkdir(parents=True, exist_ok=True)
    (SOURCE / "internal/netlist_test/BUILD.bazel").write_text("")
    shutil.copytree(ROOT / "fixtures", SOURCE / "portable_fixtures", dirs_exist_ok=True)
    shutil.copytree(ROOT / "mpact-patches", SOURCE / "portable_patches", dirs_exist_ok=True)


def main():
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "fixtures":
        if platform.machine() != "x86_64":
            raise SystemExit("Build guest fixtures on x86_64, then copy fixtures/*.elf to ARM64")
        bazel("build", "-c", "opt", *("//portable_fixtures:" + name + ".elf" for name in FIXTURES))
        for name in FIXTURES:
            output = bazel("cquery", "//portable_fixtures:" + name + ".elf", "-c", "opt", "--output=files")
            shutil.copy2(SOURCE / output.splitlines()[-1], ROOT / "fixtures" / (name + ".elf"))
        output_base = Path(run("bazel", "--output_user_root=" + str(ROOT / ".cache/bazel"),
                               "info", "output_base"))
        objdump, = (output_base / "external").glob("*toolchain_coralnpu_v2/bin/riscv64-unknown-elf-objdump")
        disassembly = run(str(objdump), "-d", str(ROOT / "fixtures/scalar.elf"))
        vector = re.search(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(v\S+)", disassembly, re.MULTILINE)
        if vector:
            raise RuntimeError("Vector instruction in scalar fixture: " + vector.group(0))
    elif command == "build":
        outputs = {}
        for name, target in TARGETS.items():
            print("Building", target, flush=True)
            flags = ["--platforms=//toolchain/host_clang:host_clang_platform"] if target.startswith("@coralnpu_mpact//") else []
            bazel("build", "-c", "opt", *flags, target)
            output = bazel("cquery", "-c", "opt", *flags, target, "--output=files")
            outputs[name] = str(SOURCE / output.splitlines()[-1])
        (ROOT / ".cache/outputs.json").write_text(json.dumps(outputs, indent=2))
    elif command == "python-bindings":
        bazel("build", "-c", "opt", "//sw/coralnpu_sim:coralnpu_v2_sim")
    else:
        raise SystemExit("Unknown command: " + command)


if __name__ == "__main__":
    main()
