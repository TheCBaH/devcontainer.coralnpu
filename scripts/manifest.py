#!/usr/bin/env python3
"""Builds hardware-configurations.json records for the packaged simulators."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from build import ROOT, SOURCE

CORAL_REPOSITORY = "https://github.com/google-coral/coralnpu"
WRAPPER_REPOSITORY = "https://github.com/TheCBaH/devcontainer.coralnpu"
SCHEMA_VERSION = "1.0"
ID_RULE = (
    "id = 'coralnpu:' + name + ':' + the first 20 hex digits of SHA-256 over the "
    "configuration record without its id, serialized as JSON with sorted keys, "
    "separators (',', ':') and UTF-8. The record holds the upstream revision, "
    "dependency pins, applied patch hashes, effective build parameters, ISA, "
    "memory map and model behavior, and no host-specific values, so x86_64 and "
    "aarch64 builds of one configuration share an ID and any change to the "
    "simulated configuration yields a new ID. Host binaries are distinguished by "
    "artifacts[].sha256 and artifacts[].host.")
MINIMUM_GLIBC = "2.39"
KIB = 1024
MIB = 1024 * KIB

STANDALONE = {
    "core_mini_axi_sim": ("core-mini-axi", "scalar", "core_mini_axi_cc_library", "CoreMiniAxi"),
    "rvv_core_mini_axi_sim": ("rvv-core-mini-axi", "rvv", "rvv_core_mini_axi_cc_library", "RvvCoreMiniAxi"),
    "vme_core_mini_axi_sim": ("vme-core-mini-axi", "vme", "vme_core_mini_axi_cc_library", "VmeCoreMiniAxi"),
    "core_mini_highmem_axi_sim": (
        "core-mini-highmem-axi", "scalar", "core_mini_highmem_axi_cc_library", "CoreMiniHighmemAxi"),
    "rvv_core_mini_highmem_axi_sim": (
        "rvv-core-mini-highmem-axi", "rvv", "rvv_core_mini_highmem_axi_cc_library", "RvvCoreMiniHighmemAxi"),
    "core_mini_itcm512kb_dtcm512kb_axi_sim": (
        "core-mini-itcm512kb-dtcm512kb-axi", "scalar", "core_mini_itcm512kb_dtcm512kb_axi_cc_library",
        "CoreMini_ITCM512KB_DTCM512KBAxi"),
    "rvv_core_mini_itcm512kb_dtcm512kb_axi_sim": (
        "rvv-core-mini-itcm512kb-dtcm512kb-axi", "rvv", "rvv_core_mini_itcm512kb_dtcm512kb_axi_cc_library",
        "RvvCoreMini_ITCM512KB_DTCM512KBAxi"),
}
MPACT = {
    "coralnpu_v2_sim": ("mpact-v2", "v2"),
    "coralnpu_m3_sim": ("mpact-m3", "m3"),
    "coralnpu_m4_sim": ("mpact-m4", "m4"),
}
LIBRARIES = {
    "libcoralnpu_simulator.so": ("library-core-mini-axi", "scalar", "core_mini_axi_cc_library", "CoreMiniAxi"),
    "libcoralnpu_simulator_rvv.so": ("library-rvv-core-mini-axi", "rvv", "rvv_core_mini_axi_cc_library",
                                     "RvvCoreMiniAxi"),
    "libcoralnpu_simulator_vme.so": ("library-vme-core-mini-axi", "vme", "vme_core_mini_axi_cc_library",
                                     "VmeCoreMiniAxi"),
}
# fpga/BUILD _ALL_CONFIGS: core kind, TCM KiB, configured clock in MHz.
SUBSYSTEMS = {
    "chip_verilator_vector_normal": ("subsystem-vector-normal", "rvv", 8, 32, 50),
    "chip_verilator_vector_highmem": ("subsystem-vector-highmem", "rvv", 1024, 1024, 50),
    "chip_verilator_matrix_normal": ("subsystem-matrix-normal", "vme", 8, 32, 30),
    "chip_verilator_matrix_highmem": ("subsystem-matrix-highmem", "vme", 1024, 1024, 30),
}
DEPENDENCIES = ("coralnpu_mpact", "com_google_mpact-riscv", "com_google_mpact-sim", "toolchain_coralnpu_v2",
                "accellera_systemc", "verilator", "libsystemctlm_soc", "lowrisc_opentitan_gh")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration_id(record):
    body = {key: value for key, value in record.items() if key != "id"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "coralnpu:" + record["name"] + ":" + hashlib.sha256(text.encode()).hexdigest()[:20]


def generated_parameters(header):
    values = {}
    for name, value in re.findall(r"#define\s+KP_(\w+)\s+(.+)", Path(header).read_text()):
        value = value.strip().strip('"')
        if value in ("true", "false"):
            values[name] = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            values[name] = int(value)
        else:
            values[name] = value
    return values


def dependencies():
    found = {}
    text = "\n".join((SOURCE / path).read_text() for path in ("rules/repo_defs.bzl", "rules/repos.bzl"))
    for block in re.split(r"\n\s*\)\n", text):
        name = re.search(r'\bname\s*=\s*"([^"]+)"', block)
        url = re.search(r'https://[^"\s]+', block)
        if not name or not url or name.group(1) not in DEPENDENCIES or name.group(1) in found:
            continue
        digest = re.search(r'sha256\s*=\s*"([0-9a-f]{64})"', block)
        commit = re.search(r'commit\s*=\s*"([0-9a-f]{40})"', block)
        revision = commit.group(1) if commit else (re.search(r"[0-9a-f]{40}", url.group(0)) or
                                                   re.search(r"v?\d+(\.\d+)+", url.group(0)))
        found[name.group(1)] = {
            "name": name.group(1),
            "repository": url.group(0),
            "revision": revision if isinstance(revision, str) else (revision.group(0) if revision else url.group(0)),
            "sha256": digest.group(1) if digest else None,
        }
    # Bazel rewrites the working-tree lockfile with host-specific entries.
    lock = hashlib.sha256(subprocess.run(["git", "show", "HEAD:MODULE.bazel.lock"], cwd=ROOT / "coralnpu",
                                         check=True, capture_output=True).stdout).hexdigest()
    found["MODULE.bazel.lock"] = {"name": "MODULE.bazel.lock", "repository": CORAL_REPOSITORY,
                                  "revision": "sha256:" + lock, "sha256": lock}
    return [found[name] for name in sorted(found)]


def patches():
    entries = [{"file": "patches/" + p.name, "sha256": sha256(p), "applies_to": "coralnpu source tree"}
               for p in sorted((ROOT / "patches").glob("*.patch"))]
    entries += [{"file": "mpact-patches/" + p.name, "sha256": sha256(p), "applies_to": "coralnpu_mpact"}
                for p in sorted((ROOT / "mpact-patches").glob("*.patch"))]
    return entries


def provenance(target, build_parameters, revision):
    return {
        "repository": CORAL_REPOSITORY,
        "revision": revision,
        "target": target,
        "dependencies": dependencies(),
        "patches": patches(),
        "build_parameters": build_parameters,
    }


def access(load, store, fetch, host, dma):
    return {"guest_load": load, "guest_store": store, "instruction_fetch": fetch, "host_load": host, "dma": dma}


def region(name, kind, base, size, backing, interface, rights, timing, implemented=True, usable=True, notes=None):
    entry = {
        "name": name, "type": kind, "base_address": base, "size_bytes": size, "implemented": implemented,
        "usable": usable, "counts_toward_capacity": implemented and usable and kind not in ("mmio", "csr", "mailbox"),
        "backing_model": backing, "interface": interface, "timing": timing, "access": rights,
    }
    if notes:
        entry["notes"] = notes
    return entry


def tcm_layout(itcm, dtcm):
    default = itcm == 8 * KIB and dtcm == 32 * KIB
    return (0x10000, 0x30000) if default else (0x100000, 0x200000)


def rtl_isa(kind, parameters):
    extensions = ["i", "m", "zicsr", "zifencei", "zbb"]
    if parameters.get("enableFloat", True):
        extensions.append("f")
    if parameters.get("enableZfbfmin", True):
        extensions.append("zfbfmin")
    disabled = []
    vector = {"supported": False, "vlen_bits": None, "elen_bits": None, "floating_point": False}
    matrix = {"supported": False, "extension": None, "tile_registers": None, "element_formats": []}
    if kind in ("rvv", "vme"):
        extensions += ["zve32x", "zve32f"]
        vector = {"supported": True, "vlen_bits": parameters.get("rvvVlen", 128), "elen_bits": 32,
                  "floating_point": True}
        if parameters.get("enableVectorBf16", True):
            extensions.append("zvfbfmin")
    else:
        disabled += ["--enableRvv", "--enableVectorBf16"]
    if kind == "vme":
        extensions.append("zvt")
        matrix = {"supported": True, "extension": "zvt (experimental Coral NPU matrix engine)",
                  "tile_registers": parameters.get("vmeRegCount"), "element_formats": ["int8", "fp32", "bf16"]}
    else:
        disabled.append("--enableVme")
    if not parameters.get("enableVerification", False):
        disabled.append("--enableVerification")
    if not parameters.get("exposeDebugPorts", parameters.get("rawExposeDebugPorts", False)):
        disabled.append("--exposeDebugPorts")
    return {
        "xlen": 32,
        "extensions": sorted(set(extensions)),
        "compiler_march": None,
        "vector": vector,
        "matrix": matrix,
        "bf16": {"scalar_conversion": "zfbfmin" in extensions, "vector_conversion": "zvfbfmin" in extensions,
                 "matrix": kind == "vme"},
        "disabled_generator_options": disabled,
    }


def core_buses(parameters):
    return [
        {"name": "core-axi-master", "protocol": "AXI4", "data_width_bits": parameters.get("lsuDataBits"),
         "address_width_bits": 32, "note": "Width is not a bandwidth guarantee"},
        {"name": "core-axi-slave", "protocol": "AXI4", "data_width_bits": parameters.get("axi2DataBits",
                                                                                         parameters.get("lsuDataBits")),
         "address_width_bits": 32},
        {"name": "instruction-fetch", "protocol": "internal", "data_width_bits": parameters.get("fetchDataBits")},
    ]


def rtl_build_parameters(elaboration, header):
    parameters = generated_parameters(header)
    verification = parameters.get("enableVerification", False)
    return parameters, {
        "elaboration_target": "//hdl/chisel/src/coralnpu:" + elaboration["library"],
        "module": elaboration["module"],
        "generator_flags": elaboration["generator_flags"],
        "verilator_options": elaboration["verilator_options"],
        "defines": elaboration.get("defines", []),
        "enable_verification": verification,
        "rob_mode": "full" if verification else "mini",
        "expose_debug_ports": parameters.get("exposeDebugPorts", None),
        "generated_parameters": parameters,
    }


def check_tcm(parameters, itcm, dtcm, name):
    if parameters.get("itcmSizeKBytes") * KIB != itcm or parameters.get("dtcmSizeKBytes") * KIB != dtcm:
        raise RuntimeError("Generated TCM sizes disagree with the memory map of " + name)


def standalone(executable, elaboration, header, revision):
    name, kind, library, module = STANDALONE[executable]
    parameters, build_parameters = rtl_build_parameters(elaboration, header)
    itcm, dtcm = parameters["itcmSizeKBytes"] * KIB, parameters["dtcmSizeKBytes"] * KIB
    dtcm_base, csr_base = tcm_layout(itcm, dtcm)
    trace = parameters.get("exposeDebugPorts", False)
    rtl = "RTL SRAM, cycle-based"
    record = {
        "id": "",
        "name": name,
        "description": "Standalone " + module + " RTL core with the SystemC testbench, "
                       + str(itcm // KIB) + " KiB ITCM, " + str(dtcm // KIB) + " KiB DTCM and 4 MiB testbench RAM",
        "provenance": provenance("//tests/verilator_sim:" + executable, build_parameters, revision),
        "simulation": {
            "backend": "verilator",
            "interface": "standalone-cli",
            "top_level": module,
            "timing_scope": "cycle-rtl-core",
            "clock": {"configured_frequency_mhz": None,
                      "note": "Simulation time base only; not a measured FPGA or ASIC frequency"},
            "boot": {
                "loader": "ELF PT_LOAD segments written through the core AXI slave, read back and compared; "
                          "--backdoor_load writes TCM segments directly into the SRAM models",
                "entry": "ELF e_entry written to core CSR base + 4, then clock gate and reset released through "
                         "core CSR base",
                "steps": [executable + " --binary=<elf> [--cycles=N]"],
            },
            "termination": "Exits after an HTIF exit through the ELF tohost symbol or a core halt or fault; "
                           "status 0 only when the core did not fault and the HTIF exit code is 0. A missing or "
                           "unreadable ELF aborts with a nonzero status. Reaching --cycles stops the SystemC "
                           "kernel but the process keeps waiting for a halt, so callers need an external timeout. "
                           "HTIF detection snoops the core debug ports.",
            "runtime_overrides": [
                {"flag": "--binary", "default": "", "changes_configuration": False,
                 "description": "Guest ELF; its segments must lie in the regions marked host_load"},
                {"flag": "--cycles", "default": 100000000, "changes_configuration": False,
                 "description": "Simulation cycle limit"},
                {"flag": "--trace", "default": False, "changes_configuration": False,
                 "description": "Write an FST waveform under /tmp"},
                {"flag": "--debug_axi", "default": False, "changes_configuration": False,
                 "description": "Log AXI transactions"},
                {"flag": "--instr_trace", "default": False, "changes_configuration": False,
                 "description": "Log retired instructions; requires exposed debug ports"},
                {"flag": "--backdoor_load", "default": False, "changes_configuration": False,
                 "description": "Load TCM segments without AXI transactions"},
            ],
        },
        "isa": rtl_isa(kind, parameters),
        "memory_regions": [
            region("itcm", "itcm", 0, itcm, "rtl-sram", "core instruction TCM; host access through core AXI slave",
                   access(True, False, True, True, False), rtl,
                   notes="The LSU raises a store fault for guest stores to ITCM"),
            region("dtcm", "dtcm", dtcm_base, dtcm, "rtl-sram", "core data TCM; host access through core AXI slave",
                   access(True, True, None, True, False), rtl),
            region("core-csr", "csr", csr_base, 4 * KIB, "register-file", "core AXI slave",
                   access(None, None, False, True, False), rtl,
                   notes="Run control: +0 clock gate/reset, +4 start PC"),
            region("testbench-ram", "ram", 0x20000000, 4 * MIB, "systemc-array",
                   "core AXI master to SystemC Xbar", access(True, True, None, None, False),
                   "untimed SystemC TLM array behind the RTL AXI handshake",
                   notes="Xbar accepts accesses ending strictly before 0x20400000"),
            region("testbench-uart", "mmio", 0x54000000, 4, "register-file", "core AXI master to SystemC Xbar",
                   access(False, True, False, False, False), "untimed",
                   notes="Bytes written are printed to stdout at each newline"),
        ],
        "capabilities": {
            "dma": {"present": False, "type": None, "mmio_base_address": None, "reachable_regions": []},
            "mmio": [
                {"name": "core-csr", "base_address": csr_base, "size_bytes": 4 * KIB,
                 "description": "Core run control and status"},
                {"name": "testbench-uart", "base_address": 0x54000000, "size_bytes": 4,
                 "description": "Write-only character output"},
            ],
            "peripherals": ["htif-semihosting", "testbench-uart"],
            "external_instruction_fetch": None,
            "buses": core_buses(parameters),
            "memory_timing_model": "TCMs are cycle-based RTL SRAM; the testbench RAM is an untimed SystemC array; "
                                   "no cache or DRAM timing",
            "waveform_tracing": "fst",
            "instruction_trace": True if trace else False,
            "guest_output": "HTIF write/exit through the tohost and fromhost ELF symbols",
        },
        "limitations": [
            "Smoke fixtures do not establish complete ISA, rounding/NaN or RTL conformance",
            "Instruction fetch from DTCM and testbench RAM is not verified",
        ],
    }
    check_tcm(parameters, itcm, dtcm, name)
    return record


MPACT_ISA = {
    "v2": (["i", "m", "f", "zicsr", "zifencei", "zbb", "zve32x"], False, False, False),
    "m3": (["i", "m", "f", "zicsr", "zifencei", "zbb", "zve32x", "zve32f", "zvfbfmin"], True, True, False),
    "m4": (["i", "m", "f", "zicsr", "zifencei", "zbb", "zve32x", "zve32f", "zvfbfmin", "zvt"], True, True, True),
}


def mpact(executable, revision):
    name, generation = MPACT[executable]
    extensions, vector_fp, bf16, matrix = MPACT_ISA[generation]
    flat = "functional, untimed"
    record = {
        "id": "",
        "name": name,
        "description": "MPACT functional " + generation.upper() + " instruction-set simulator",
        "provenance": provenance("@coralnpu_mpact//sim:" + executable, {
            "elaboration_target": None,
            "module": None,
            "generator_flags": [],
            "verilator_options": [],
            "defines": [],
            "enable_verification": None,
            "rob_mode": "not-applicable",
            "expose_debug_ports": None,
            "generated_parameters": {"vector_byte_length": 16, "initial_misa_value": 0x40201120},
        }, revision),
        "simulation": {
            "backend": "mpact",
            "interface": "standalone-cli",
            "top_level": "CoralNPUSimulator (" + generation.upper() + ")",
            "timing_scope": "functional",
            "clock": {"configured_frequency_mhz": None, "note": "Cycle counts are instruction counts, not timing"},
            "boot": {"loader": "MPACT ELF loader writes PT_LOAD segments directly into functional memory",
                     "entry": "ELF e_entry unless --entry_point is given",
                     "steps": [executable + " --semihost_htif --exit_on_ebreak <elf>"]},
            "termination": "Runs until the guest halts, an HTIF exit with --semihost_htif, or ebreak with "
                           "--exit_on_ebreak; the process exits 0 after a completed run even when the guest exit "
                           "code is nonzero, and nonzero when the ELF cannot be loaded.",
            "runtime_overrides": [
                {"flag": "--allow_memory_region", "default": ["0x0:0x2000:rx", "0x10000:0x8000:rw",
                                                              "0x20000000:0x400000:rw"],
                 "changes_configuration": True,
                 "description": "Replaces the default guest-accessible regions; record the values with the base ID"},
                {"flag": "--semihost_htif", "default": False, "changes_configuration": True,
                 "description": "Enables HTIF and adds every ELF PT_LOAD segment as an extra region with the "
                                "segment's permissions; record the ELF hash with the base ID"},
                {"flag": "--initial_misa_value", "default": 0x40201120, "changes_configuration": True,
                 "description": "Initial misa CSR value; does not change the decoder generation"},
                {"flag": "--exit_on_ebreak", "default": False, "changes_configuration": True,
                 "description": "Stops the run at ebreak instead of trapping"},
                {"flag": "--entry_point", "default": None, "changes_configuration": False,
                 "description": "Overrides the ELF entry point"},
                {"flag": "--interactive", "default": False, "changes_configuration": False,
                 "description": "Interactive debugger"},
            ],
        },
        "isa": {
            "xlen": 32,
            "extensions": sorted(extensions),
            "compiler_march": None,
            "vector": {"supported": True, "vlen_bits": 128, "elen_bits": 32, "floating_point": vector_fp},
            "matrix": {"supported": matrix, "extension": "zvt (experimental)" if matrix else None,
                       "tile_registers": None, "element_formats": ["int8", "fp32", "bf16"] if matrix else []},
            "bf16": {"scalar_conversion": None, "vector_conversion": bf16, "matrix": matrix},
            "disabled_generator_options": [],
        },
        "memory_regions": [
            region("itcm", "itcm", 0, 8 * KIB, "mpact-flat", "functional memory region (rx)",
                   access(True, False, True, True, False), flat),
            region("dtcm", "dtcm", 0x10000, 32 * KIB, "mpact-flat", "functional memory region (rw)",
                   access(True, True, False, True, False), flat),
            region("extmem", "ram", 0x20000000, 4 * MIB, "mpact-flat", "functional memory region (rw)",
                   access(True, True, False, True, False), flat),
        ],
        "capabilities": {
            "dma": {"present": False, "type": None, "mmio_base_address": None, "reachable_regions": []},
            "mmio": [],
            "peripherals": ["htif-semihosting"],
            "external_instruction_fetch": False,
            "buses": [],
            "memory_timing_model": "Functional; regions are permission-checked memory, not cycle-modeled AXI devices",
            "waveform_tracing": False,
            "instruction_trace": None,
            "guest_output": "HTIF write/exit with --semihost_htif",
        },
        "limitations": [
            "V2 includes integer vectors, so it is not an ISA-exact model of the scalar-only CoreMini",
            "Generation is fixed by the executable; --initial_misa_value does not switch V2 to M3/M4",
        ],
    }
    return record


def library(filename, elaboration, header, revision):
    name, kind, library_target, module = LIBRARIES[filename]
    parameters, build_parameters = rtl_build_parameters(elaboration, header)
    build_parameters["defines"] = {"rvv": ["ENABLE_RVV"], "vme": ["ENABLE_VME"]}.get(kind, [])
    itcm, dtcm = parameters["itcmSizeKBytes"] * KIB, parameters["dtcmSizeKBytes"] * KIB
    rtl = "RTL SRAM, cycle-based"
    record = {
        "id": "",
        "name": name,
        "description": "Shared-library CoralNPUSimulator over the default-TCM " + module + " RTL core with the "
                       "library's 1 GiB functional DDR backing store",
        "provenance": provenance("//hw_sim:" + filename, build_parameters, revision),
        "simulation": {
            "backend": "verilator",
            "interface": "shared-library",
            "top_level": "CoralNPUSimulator over " + module,
            "timing_scope": "cycle-rtl-core",
            "clock": {"configured_frequency_mhz": None,
                      "note": "WaitForTermination timeouts are in simulated cycles"},
            "boot": {"loader": "Host WriteMem calls for each ELF segment (example uses tests/verilator_sim/elf.h)",
                     "entry": "Run(start_pc) writes core CSR 0x30004 and releases the core through 0x30000",
                     "steps": ["coralnpu_simulator_verilator_create()", "WriteMem(segments)", "Run(entry)",
                               "WaitForTermination(cycles)", "ReadMem/ReadMailbox/ReadCoreState"]},
            "termination": "WaitForTermination returns true when the core halts or waits in wfi, false after the "
                           "cycle timeout (default 10000 cycles when the timeout is not positive)",
            "runtime_overrides": [
                {"flag": "CoralNPUSimulatorOptions.cycle_callback", "default": None, "changes_configuration": False,
                 "description": "Host callback every cycle_callback_period cycles"},
            ],
        },
        "isa": rtl_isa(kind, parameters),
        "memory_regions": [
            region("itcm", "itcm", 0, itcm, "rtl-sram", "core instruction TCM; host WriteMem through core AXI slave",
                   access(True, False, True, True, False), rtl,
                   notes="The LSU raises a store fault for guest stores to ITCM"),
            region("dtcm", "dtcm", 0x10000, dtcm, "rtl-sram", "core data TCM; host WriteMem through core AXI slave",
                   access(True, True, None, True, False), rtl),
            region("core-csr", "csr", 0x30000, 4 * KIB, "register-file", "core AXI slave",
                   access(None, None, False, True, False), rtl),
            region("ddr", "ddr", 0x80000000, 1024 * MIB, "host-vector", "core AXI master callbacks; host "
                   "ReadMem/WriteMem copy directly", access(True, True, None, True, False),
                   "untimed host buffer; no physical DDR timing",
                   notes="Library-only functional backing store, absent from the CLI and subsystem simulators"),
            region("mailbox", "mailbox", 0x20000000, 16, "host-vector", "core AXI master callbacks; host "
                   "ReadMailbox/WriteMailbox", access(True, True, None, None, False), "untimed",
                   notes="Every external address outside DDR aliases this 16-byte mailbox by its low 4 bits"),
        ],
        "capabilities": {
            "dma": {"present": False, "type": None, "mmio_base_address": None, "reachable_regions": []},
            "mmio": [{"name": "core-csr", "base_address": 0x30000, "size_bytes": 4 * KIB,
                      "description": "Core run control and status"}],
            "peripherals": ["mailbox"],
            "external_instruction_fetch": None,
            "buses": core_buses(parameters),
            "memory_timing_model": "TCMs are cycle-based RTL SRAM; DDR and mailbox are untimed host callbacks",
            "waveform_tracing": False,
            "instruction_trace": False,
            "guest_output": "Mailbox words and memory read by the host",
        },
        "limitations": [
            "The 1 GiB DDR model belongs to this library interface only and is not a DDR timing model",
            "Default 8 KiB / 32 KiB TCM wrappers; a highmem linker script does not enlarge them",
        ],
    }
    check_tcm(parameters, itcm, dtcm, name)
    return record


def subsystem(variant, elaboration, revision):
    name, kind, itcm_kib, dtcm_kib, clock = SUBSYSTEMS[variant]
    itcm, dtcm = itcm_kib * KIB, dtcm_kib * KIB
    dtcm_base, csr_base = tcm_layout(itcm, dtcm)
    parameters = {"itcmSizeKBytes": itcm_kib, "dtcmSizeKBytes": dtcm_kib, "lsuDataBits": 128,
                  "fetchDataBits": 128, "enableRvv": True, "enableFloat": True, "enableZfbfmin": True,
                  "enableVectorBf16": True, "enableVme": kind == "vme", "enableAxiInstructionFetch": True,
                  "rvvVlen": 128, "enableVerification": False}
    rtl = "RTL, cycle-based"
    mmio = [
        ("uart0", 0x40000000), ("clk_table", 0x40001000), ("uart1", 0x40010000), ("spi_master", 0x40020000),
        ("gpio", 0x40030000), ("i2c_master", 0x40040000), ("dma", 0x40050000), ("spi_master_flash", 0x40070000),
    ]
    record = {
        "id": "",
        "name": name,
        "description": "Reference Coral NPU SoC subsystem (chip_verilator) with " + kind.upper() + " core, "
                       + str(itcm_kib) + " KiB ITCM, " + str(dtcm_kib) + " KiB DTCM, 4 MiB SRAM, 32 KiB ROM and DMA",
        "provenance": provenance("//fpga:build_" + variant, {
            "elaboration_target": elaboration["core"],
            "module": "chip_verilator",
            "generator_flags": elaboration["flags"],
            "verilator_options": elaboration["verilator_options"],
            "defines": [],
            "enable_verification": False,
            "rob_mode": "mini",
            "expose_debug_ports": None,
            "generated_parameters": parameters,
        }, revision),
        "simulation": {
            "backend": "verilator",
            "interface": "subsystem-cli",
            "top_level": "chip_verilator",
            "timing_scope": "cycle-rtl-subsystem",
            "clock": {"configured_frequency_mhz": clock,
                      "note": "--ClockFrequencyMhz build setting used by guest drivers; not a measured frequency"},
            "boot": {
                "loader": "Vchip_verilator --load_elf=<elf> backdoor-loads ITCM/DTCM/SRAM segments; the upstream "
                          "loader.py --csr_only then starts the core over the SPI-to-TL-UL bridge",
                "entry": "loader.py writes ELF e_entry to core CSR base + 4 and releases clock gate and reset",
                "steps": [
                    "SPI_DPI_PORT=<port> bin/Vchip_" + variant.split("chip_verilator_")[1] + " --load_elf=<elf>",
                    "wait for 'DPI: Server listening on port <port>'",
                    "SPI_DPI_PORT=<port> python3 tools/loader.py --csr_only --itcm_size_kbytes " + str(itcm_kib)
                    + " --dtcm_size_kbytes " + str(dtcm_kib) + " <elf>",
                ],
            },
            "termination": "The simulator runs until it is stopped or a Verilator simulation-control limit; guest "
                           "results are read from the UART logs written in the working directory",
            "runtime_overrides": [
                {"flag": "--load_elf", "default": "", "changes_configuration": False,
                 "description": "Backdoor ELF load into ITCM, DTCM and SRAM"},
                {"flag": "--trace", "default": None, "changes_configuration": False,
                 "description": "Write an FST waveform to the given path"},
                {"flag": "SPI_DPI_PORT", "default": None, "changes_configuration": False,
                 "description": "Environment variable: TCP port of the SPI DPI server used by loader.py"},
            ],
        },
        "isa": rtl_isa(kind, parameters),
        "memory_regions": [
            region("itcm", "itcm", 0, itcm, "rtl-sram", "core instruction TCM; core device port on the crossbar",
                   access(True, False, True, True, True), rtl,
                   notes="Guest stores fault in the LSU; DMA and host loading use the core device port"),
            region("dtcm", "dtcm", dtcm_base, dtcm, "rtl-sram", "core data TCM; core device port on the crossbar",
                   access(True, True, None, True, True), rtl),
            region("core-csr", "csr", csr_base, 4 * KIB, "register-file", "core device port on the crossbar",
                   access(None, None, False, True, None), rtl),
            region("rom", "rom", 0x10000000, 32 * KIB, "rtl-rom", "crossbar device", access(True, False, None, True, None),
                   rtl, notes="Read-only; built without a ROM image for ITCM boot"),
            region("sram", "ram", 0x20000000, 4 * MIB, "rtl-sram", "crossbar device, 128-bit",
                   access(True, True, None, True, True), rtl),
            region("ddr-control", "mmio", 0x70000000, 4 * KIB, "none", "crossbar device tied off in chip_verilator.sv",
                   access(False, False, False, False, False), "not simulated", implemented=False, usable=False),
            region("ddr", "ddr", 0x80000000, 2048 * MIB, "none", "crossbar aperture tied off in chip_verilator.sv",
                   access(False, False, False, False, False), "not simulated", implemented=False, usable=False,
                   notes="Address decode only; no DRAM backing store. Do not access."),
        ] + [region(peripheral, "mmio", base, 4 * KIB, "register-file", "crossbar device",
                    access(True, True, False, False, None), rtl) for peripheral, base in mmio],
        "capabilities": {
            "dma": {"present": True, "type": "bus.DmaEngine: descriptor chains, 128-bit, one outstanding transaction",
                    "mmio_base_address": 0x40050000, "reachable_regions": ["itcm", "dtcm", "core-csr", "rom", "sram"]},
            "mmio": [{"name": peripheral, "base_address": base, "size_bytes": 4 * KIB} for peripheral, base in mmio],
            "peripherals": ["uart0", "uart1", "clk_table", "spi_master", "spi_master_flash", "gpio", "i2c_master",
                            "dma", "clint", "plic", "ispyocto", "spi2tlul"],
            "external_instruction_fetch": None,
            "buses": [{"name": "crossbar", "protocol": "TL-UL/AXI4", "data_width_bits": 128,
                       "address_width_bits": 32, "note": "Width is not a bandwidth guarantee"}],
            "memory_timing_model": "Cycle-based RTL for TCM, SRAM, ROM, crossbar and DMA; no DDR",
            "waveform_tracing": "fst",
            "instruction_trace": None,
            "guest_output": "UART1 output written to a log file in the working directory",
        },
        "limitations": [
            "The 2 GiB DDR aperture and DDR control port are tied off and must not be accessed",
            "Requires python3 for the bundled loader",
        ],
    }
    return record


def finalize(record):
    record["id"] = configuration_id(record)
    return record
