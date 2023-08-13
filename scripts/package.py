#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile

from build import ROOT, SOURCE, run

SYSTEM = re.compile(r"^(lib(c|m|pthread|dl|rt|resolv|util)\.so\.|ld-linux)")
ARCH = {"x86_64": "x86_64", "aarch64": "aarch64"}[platform.machine()]


def dependencies(path):
    output = run("ldd", str(path), cwd=ROOT)
    if "not found" in output:
        raise RuntimeError(output)
    return re.findall(r"(\S+) => (/\S+)", output)


def main():
    outputs = json.loads((ROOT / ".cache/outputs.json").read_text())
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    name = "coralnpu-emulators-linux-" + ARCH
    bundle = ROOT / ".cache" / name
    if bundle.exists():
        shutil.rmtree(bundle)
    for directory in ("bin", "lib", "examples", "licenses", "provenance"):
        (bundle / directory).mkdir(parents=True, exist_ok=True)
    libraries = {}
    for executable, source in outputs.items():
        path = bundle / "bin" / executable
        shutil.copy2(source, path)
        path.chmod(0o755)
        machine = run("readelf", "-h", str(path), cwd=ROOT)
        expected = "AArch64" if ARCH == "aarch64" else "Advanced Micro Devices X86-64"
        if expected not in machine:
            raise RuntimeError("Wrong architecture: " + machine)
        for soname, location in dependencies(Path(source)):
            if not SYSTEM.match(soname):
                if soname in libraries and Path(libraries[soname]).resolve() != Path(location).resolve():
                    raise RuntimeError("Conflicting libraries: " + soname)
                libraries[soname] = location
        run("patchelf", "--set-rpath", "$ORIGIN/../lib", str(path), cwd=ROOT)
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
    for filename in ("scalar.elf", "rvv.elf"):
        shutil.copy2(ROOT / "fixtures" / filename, bundle / "examples" / filename)
    shutil.copy2(ROOT / "scripts/smoke.sh", bundle / "smoke.sh")
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    shutil.copy2(ROOT / "LICENSE", bundle / "licenses/wrapper-MIT")
    shutil.copy2(ROOT / "coralnpu/LICENSE", bundle / "licenses/coralnpu-Apache-2.0")
    for notice in (ROOT / "licenses").glob("*"):
        shutil.copy2(notice, bundle / "licenses" / notice.name)
    for filename in ("MODULE.bazel", "MODULE.bazel.lock", "rules/repo_defs.bzl", "rules/repos.bzl"):
        shutil.copy2(SOURCE / filename, bundle / "provenance" / Path(filename).name)
    for patch in (ROOT / "patches").glob("*.patch"):
        shutil.copy2(patch, bundle / "provenance" / patch.name)
    shutil.copytree(ROOT / "fixtures", bundle / "provenance/fixtures",
                    ignore=shutil.ignore_patterns("*.elf"))
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
    metadata = {
        "architecture": ARCH,
        "wrapper_commit": run("git", "rev-parse", "HEAD", cwd=ROOT),
        "upstream_commit": run("git", "rev-parse", "HEAD", cwd=ROOT / "coralnpu"),
        "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "patches").glob("*.patch")},
        "bazel": run("bazel", "--version"),
        "clang": run("clang", "--version").splitlines()[0],
        "java": subprocess.check_output(["java", "--version"], text=True).splitlines()[0],
        "glibc": run("getconf", "GNU_LIBC_VERSION"),
        "minimum_glibc": "2.39",
        "runtime_libraries": sorted(libraries),
        "runtime_packages": run("dpkg-query", "-W", "-f=${Package} ${Version}\n",
                                "libstdc++6", "libgcc-s1", cwd=ROOT).splitlines(),
        "sources": {
            "coralnpu": "https://github.com/google-coral/coralnpu",
            "libstdc++": "https://gcc.gnu.org/git/",
            "dependency_pins": "coralnpu/MODULE.bazel, MODULE.bazel.lock and rules/repo_defs.bzl",
        },
    }
    (bundle / "build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    for path in [*bundle.glob("bin/*"), *bundle.glob("lib/*")]:
        symbols = run("readelf", "--version-info", str(path), cwd=ROOT)
        for major, minor in re.findall(r"GLIBC_(\d+)\.(\d+)", symbols):
            if (int(major), int(minor)) > (2, 39):
                raise RuntimeError("Newer glibc needed by " + str(path))
    timestamp = int(run("git", "show", "-s", "--format=%ct", "HEAD", cwd=ROOT))
    def normalize(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = timestamp
        return info
    archive = dist / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bundle, arcname=name, filter=normalize)
    archives = sorted(dist.glob("*.tar.gz"))
    (dist / "SHA256SUMS").write_text("".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in archives))
    print(archive)


if __name__ == "__main__":
    main()
