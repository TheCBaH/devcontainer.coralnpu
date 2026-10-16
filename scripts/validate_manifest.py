#!/usr/bin/env python3
"""Validates hardware-configurations.json in an extracted archive root."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration_id(record):
    body = {key: value for key, value in record.items() if key != "id"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "coralnpu:" + record["name"] + ":" + hashlib.sha256(text.encode()).hexdigest()[:20]


def check(condition, message):
    if not condition:
        raise SystemExit("Manifest error: " + message)


def overlaps(a, b):
    return a["base_address"] < b["base_address"] + b["size_bytes"] and \
        b["base_address"] < a["base_address"] + a["size_bytes"]


def validate_configuration(record):
    name = record["name"]
    check(configuration_id(record) == record["id"], "ID of " + name + " does not match its record")
    regions = record["memory_regions"]
    names = [region["name"] for region in regions]
    check(len(names) == len(set(names)), "duplicate region names in " + name)
    for index, region in enumerate(regions):
        check(region["base_address"] + region["size_bytes"] <= 1 << 32, region["name"] + " exceeds 32 bits")
        if not region["implemented"]:
            check(not region["usable"] and not region.get("counts_toward_capacity", False),
                  "unimplemented region " + region["name"] + " is usable in " + name)
            check(not any(region["access"].values()), "unimplemented region " + region["name"] + " grants access")
            check(region["backing_model"] == "none", "unimplemented region " + region["name"] + " has a backing")
        for other in regions[index + 1:]:
            check(not overlaps(region, other), region["name"] + " overlaps " + other["name"] + " in " + name)
        if region["type"] == "itcm":
            check(region["access"]["guest_store"] is False, "ITCM guest stores must be forbidden in " + name)
        if region["type"] == "rom":
            check(region["access"]["guest_store"] is False, "ROM must be read-only in " + name)
    capabilities = record["capabilities"]
    if not capabilities["dma"]["present"]:
        check(not any(region["access"]["dma"] for region in regions), "DMA access without DMA in " + name)
        check(capabilities["dma"]["mmio_base_address"] is None, "DMA MMIO without DMA in " + name)
    else:
        reachable = set(capabilities["dma"]["reachable_regions"])
        check(reachable <= set(names), "DMA reaches unknown regions in " + name)
        for region in regions:
            if region["name"] not in reachable:
                check(region["access"]["dma"] is not True, "DMA access to unreachable " + region["name"])
    isa = record["isa"]
    if not isa["vector"]["supported"]:
        check(isa["vector"]["vlen_bits"] is None, "VLEN without vectors in " + name)
        check(not any(ext.startswith("zve") or ext.startswith("zvf") for ext in isa["extensions"]),
              "vector extensions listed without vector support in " + name)
        check(isa["bf16"]["vector_conversion"] is not True, "vector BF16 without vectors in " + name)
    if not isa["matrix"]["supported"]:
        check("zvt" not in isa["extensions"] and isa["bf16"]["matrix"] is not True,
              "matrix features listed without matrix support in " + name)
    else:
        check(isa["vector"]["supported"], "matrix support requires vectors in " + name)
    parameters = record["provenance"]["build_parameters"].get("generated_parameters", {})
    for kind, key in (("itcm", "itcmSizeKBytes"), ("dtcm", "dtcmSizeKBytes")):
        if key in parameters:
            sizes = [region["size_bytes"] for region in regions if region["type"] == kind]
            check(sizes == [parameters[key] * 1024], kind + " size disagrees with generated parameters in " + name)
    if "enableRvv" in parameters:
        check(isa["vector"]["supported"] == parameters["enableRvv"], "vector support disagrees in " + name)
    if "enableVme" in parameters:
        check(isa["matrix"]["supported"] == parameters["enableVme"], "matrix support disagrees in " + name)


def validate(root):
    import jsonschema

    root = Path(root)
    document = json.loads((root / "hardware-configurations.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "hardware-configurations.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(document)
    ids = [record["id"] for record in document["configurations"]]
    check(len(ids) == len(set(ids)), "duplicate configuration IDs")
    names = [record["name"] for record in document["configurations"]]
    check(len(names) == len(set(names)), "duplicate configuration names")
    for record in document["configurations"]:
        validate_configuration(record)
    paths = set()
    host = document["archive"]["host"]
    for artifact in document["artifacts"]:
        check(artifact["configuration_id"] in ids, "unresolved configuration of " + artifact["path"])
        check(artifact["path"] not in paths, "duplicate artifact " + artifact["path"])
        paths.add(artifact["path"])
        check((root / artifact["path"]).is_file(), "missing artifact " + artifact["path"])
        check(sha256(root / artifact["path"]) == artifact["sha256"], "hash mismatch for " + artifact["path"])
        check(artifact["host"] == host, "host mismatch for " + artifact["path"])
        for runtime in artifact["runtime_files"]:
            check((root / runtime).exists(), "missing runtime file " + runtime)
    shipped = {str(path.relative_to(root)) for path in root.glob("bin/*")}
    shipped |= {str(path.relative_to(root)) for path in root.glob("lib/libcoralnpu_simulator*.so")}
    check(shipped == paths, "artifacts do not cover the shipped simulators: " + str(sorted(shipped ^ paths)))
    check({artifact["configuration_id"] for artifact in document["artifacts"]} == set(ids),
          "configuration without an artifact")
    for fixture in document.get("fixtures", []):
        check(sha256(root / fixture["path"]) == fixture["sha256"], "hash mismatch for " + fixture["path"])
        check(set(fixture["configurations"]) <= set(ids), "fixture references unknown configuration")
        if fixture["linker_layout"]:
            check((root / fixture["linker_layout"]).is_file(), "missing " + fixture["linker_layout"])
    for query in ('.configurations[] | [.id, .name, .simulation.backend] | @tsv',
                  '.artifacts[] | [.configuration_id, .path, .host.architecture] | @tsv'):
        lines = subprocess.check_output(["jq", "-r", query, str(root / "hardware-configurations.json")],
                                        text=True).splitlines()
        check(len(lines) == len(ids if query.startswith(".configurations") else paths), "jq discovery failed")


def compare(manifests):
    """Checks that host variants of one configuration share an ID and record."""
    by_kind = {}
    for path in manifests:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        records = {record["id"]: record for record in document["configurations"]}
        kind = document["archive"]["kind"]
        if kind in by_kind:
            check(by_kind[kind] == records, "configurations differ between hosts for " + kind)
        by_kind[kind] = records


if __name__ == "__main__":
    if sys.argv[1] == "--compare":
        compare(sys.argv[2:])
    else:
        for root in sys.argv[1:]:
            validate(root)
    print("Manifest validation passed")
