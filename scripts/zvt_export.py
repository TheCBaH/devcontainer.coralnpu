#!/usr/bin/env python3
"""Export the Zvt matrix instructions from the patched MPACT tree as JSONL.

The first line is a provenance record; each following line describes one
instruction: its encoding (mask/match and the constrained fields), the
operand fields of its format, and the MPACT disassembly template.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA_VERSION = 1
FORMATS = "riscv/riscv_format32.bin_fmt"
GROUP = "riscv/riscv_zvt.bin_fmt"
ISA = "riscv/riscv_zvt.isa"
REPOSITORY = "https://github.com/google/mpact-riscv"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strip_comments(text):
    # Blank out comments, keeping offsets so line numbers stay valid.
    return re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), text)


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def number(literal):
    return int(literal.replace("'", ""), 0)


def parse_formats(text):
    formats = {}
    for match in re.finditer(r"format\s+(\w+)\[(\d+)\]\s*(?::\s*(\w+))?\s*\{([^{}]*)\}", strip_comments(text), re.S):
        name, width, base, body = match.group(1), int(match.group(2)), match.group(3), match.group(4)
        fields, overlays = {}, {}
        section = None
        for statement in body.split(";"):
            statement = statement.strip()
            for heading in ("fields:", "overlays:"):
                if statement.startswith(heading):
                    section, statement = heading[:-1], statement[len(heading):].strip()
            if not statement:
                continue
            declaration = re.fullmatch(r"(?:signed|unsigned)\s+(\w+)\[(\d+)\](?:\s*=\s*(.+))?", statement, re.S)
            if not declaration:
                raise ValueError("Unsupported declaration in format " + name + ": " + statement)
            field, size, spec = declaration.group(1), int(declaration.group(2)), declaration.group(3)
            if section == "fields":
                fields[field] = size
            elif section == "overlays":
                overlays[field] = (size, spec)
        bits, position = {}, width
        for field, size in fields.items():
            position -= size
            bits[field] = list(range(position + size - 1, position - 1, -1))
        if fields and position != 0:
            raise ValueError("Format " + name + " fields do not cover its width")

        def resolve(field, seen=()):
            if field in bits:
                return bits[field]
            if field in seen or field not in overlays:
                raise ValueError("Unresolved field " + field + " in format " + name)
            size, spec = overlays[field]
            result = []
            for part in spec.split(","):
                part = part.strip()
                ref = re.fullmatch(r"(\w+)(?:\[(\d+)(?:\.\.(\d+))?\])?", part)
                if not ref:
                    raise ValueError("Unsupported overlay " + part + " in format " + name)
                source = resolve(ref.group(1), seen + (field,))
                if ref.group(2) is None:
                    result += source
                else:
                    high = int(ref.group(2))
                    low = int(ref.group(3)) if ref.group(3) is not None else high
                    result += [source[len(source) - 1 - i] for i in range(high, low - 1, -1)]
            if len(result) != size:
                raise ValueError("Overlay " + field + " in format " + name + " has the wrong width")
            bits[field] = result
            return result
        for field, (_, spec) in overlays.items():
            # Immediates with implicit literal bits (imm = ..., 0b0) have no single field layout.
            if not re.search(r"\b0[bx]", spec):
                resolve(field)
        formats[name] = {"width": width, "base": base, "bits": bits}
    return formats


def parse_group(text):
    clean = strip_comments(text)
    group = re.search(r"instruction\s+group\s+(\w+)\[(\d+)\]\s*:\s*(\w+)\s*\{(.*?)\};", clean, re.S)
    if not group:
        raise ValueError("No instruction group in " + GROUP)
    entries = []
    start = group.start(4)
    for match in re.finditer(r"(\w+)\s*:\s*(\w+)\s*:([^;]*);", group.group(4)):
        constraints = []
        for clause in match.group(3).split(","):
            field, value = (s.strip() for s in clause.split("=="))
            constraints.append((field, number(value)))
        entries.append({"name": match.group(1), "format": match.group(2), "constraints": constraints,
                        "line": line_of(clean, start + match.start())})
    return group.group(1), entries


def parse_isa(text):
    clean = strip_comments(text)
    slot = re.search(r"slot\s+(\w+)", clean).group(1)
    body = re.search(r"opcodes\s*\{", clean)
    opcodes = {}
    for match in re.finditer(r"(\w+)\s*\{([^}]*)\}((?:[^;\"]|\"[^\"]*\")*);", clean[body.end():]):
        predicate, sources, destinations = (match.group(2).split(":") + ["", ""])[:3]
        attributes = match.group(3)
        disasm = re.search(r"disasm:\s*((?:\"[^\"]*\"\s*,?\s*)+)", attributes)
        strings = re.findall(r"\"([^\"]*)\"", disasm.group(1)) if disasm else []
        if not strings:
            raise ValueError("No disassembly for " + match.group(1))
        template = ", ".join(strings[1:])
        opcodes[match.group(1)] = {
            "slot": slot,
            "mnemonic": strings[0],
            "disasm": template,
            "operands": re.findall(r"%(\w+)", template),
            "sources": [s.strip() for s in sources.split(",") if s.strip()],
            "destinations": [s.strip() for s in destinations.split(",") if s.strip()],
            "line": line_of(clean, body.end() + match.start()),
        }
    return opcodes


def overlaps(a, b):
    common = a["mask"] & b["mask"]
    return (a["match"] & common) == (b["match"] & common)


def instructions(root):
    formats = parse_formats((root / FORMATS).read_text())
    group, entries = parse_group((root / GROUP).read_text())
    opcodes = parse_isa((root / ISA).read_text())
    if {e["name"] for e in entries} != set(opcodes):
        raise ValueError("Decoder and ISA opcodes differ: " +
                         repr(sorted({e["name"] for e in entries} ^ set(opcodes))))
    records = []
    for entry in entries:
        layout = formats[entry["format"]]
        mask = match = 0
        constraints = []
        for field, value in entry["constraints"]:
            bits = layout["bits"][field]
            if value >> len(bits):
                raise ValueError(entry["name"] + ": " + field + " value does not fit")
            for i, bit in enumerate(bits):
                mask |= 1 << bit
                match |= ((value >> (len(bits) - 1 - i)) & 1) << bit
            constraints.append({"field": field, "bits": bits, "value": value})
        opcode = opcodes[entry["name"]]
        records.append({
            "record": "instruction",
            "name": entry["name"],
            "mnemonic": opcode["mnemonic"],
            "group": group,
            "slot": opcode["slot"],
            "format": entry["format"],
            "width": layout["width"],
            "mask": "0x%08x" % mask,
            "match": "0x%08x" % match,
            "constraints": constraints,
            "fields": layout["bits"],
            "disasm": opcode["disasm"],
            "operands": opcode["operands"],
            "sources": opcode["sources"],
            "destinations": opcode["destinations"],
            "locations": {"decoder": "%s:%d" % (GROUP, entry["line"]), "isa": "%s:%d" % (ISA, opcode["line"])},
        })
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if overlaps({"mask": int(a["mask"], 16), "match": int(a["match"], 16)},
                        {"mask": int(b["mask"], 16), "match": int(b["match"], 16)}):
                raise ValueError("Overlapping encodings: " + a["name"] + ", " + b["name"])
    return records


def patch_labels(source):
    # patches.bzl is plain Starlark data; evaluate it without its loads.
    text = (source / "third_party/patches/patches.bzl").read_text()
    scope = {}
    exec(compile(re.sub(r"(?m)^load\(.*\)$", "", text), "patches.bzl", "exec"), {}, scope)
    return scope["MPACT_RISCV_PATCHES"]


def label_path(source, label):
    match = re.fullmatch(r"@coralnpu_hw//([^:]*):(.+)", label)
    if not match:
        raise ValueError("Unsupported patch label " + label)
    return source / match.group(1) / match.group(2)


def provenance(root, source, coralnpu_revision=None):
    repo_defs = (source / "rules/repo_defs.bzl").read_text()
    commit = re.search(r'name = "com_google_mpact-riscv",.*?strip_prefix = "mpact-riscv-([0-9a-f]{40})"',
                       repo_defs, re.S).group(1)
    return {
        "record": "provenance",
        "schema_version": SCHEMA_VERSION,
        "description": "Zvt matrix instructions as decoded by MPACT for the CoralNPU M4 model",
        "coralnpu_revision": coralnpu_revision,
        "mpact_riscv": {"repository": REPOSITORY, "commit": commit},
        "patches": [{"label": label, "sha256": sha256(label_path(source, label))}
                    for label in patch_labels(source)],
        "inputs": [{"path": path, "sha256": sha256(root / path)} for path in (FORMATS, GROUP, ISA)],
    }


def export(root, source, output, coralnpu_revision=None):
    root, source = Path(root), Path(source)
    lines = [provenance(root, source, coralnpu_revision)] + instructions(root)
    Path(output).write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        raise SystemExit("usage: zvt_export.py MPACT_RISCV_DIR CORALNPU_SOURCE OUTPUT [CORALNPU_REVISION]")
    export(*sys.argv[1:])
