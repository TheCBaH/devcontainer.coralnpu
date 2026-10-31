#!/usr/bin/env python3
"""Check kernels/kernels.json against the built programs and render doc/kernels.md."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load():
    return json.loads((ROOT / "kernels/kernels.json").read_text())


def check(examples):
    """Every program exists and contains its marker and entry symbol."""
    problems = []
    for kernel in load()["kernels"]:
        for variant in kernel["variants"]:
            program = examples / Path(variant["program"]).name
            if not program.is_file():
                problems.append("missing " + str(program))
                continue
            data = program.read_bytes()
            if variant["marker"].encode() + b"_PASS" not in data:
                problems.append(program.name + ": no pass marker " + variant["marker"])
            for entry in variant["entry"].split(" (")[0].split(", "):
                if entry.split(" ")[0].encode() not in data:
                    problems.append(program.name + ": no symbol " + entry)
    return problems


def render():
    data = load()
    lines = ["# Gemma kernels", "", data["description"], ""]
    conventions = data["conventions"]
    labels = {"isa": "ISA", "bf16": "BF16", "layout": "Layout", "cycles": "Cycles", "pass_marker": "Pass marker"}
    lines += ["## Conventions", ""] + ["- **%s.** %s" % (labels[key], text.replace("<marker>", "`<marker>`"))
                                       for key, text in conventions.items()]
    lines += ["", "Upstream sources: `%s`, `%s`." % (data["upstream"]["repository"], data["upstream"]["directory"]),
              "The program sources are in `provenance/fixtures/`.", ""]
    lines += ["| Kernel | Programs | Computes |", "| --- | --- | --- |"]
    for kernel in data["kernels"]:
        programs = ", ".join("`%s`" % Path(v["program"]).name for v in kernel["variants"])
        lines.append("| `%s` | %s | %s |" % (kernel["id"], programs, kernel["summary"]))
    for kernel in data["kernels"]:
        lines += ["", "## `%s`" % kernel["id"], "", kernel["summary"], "", "`" + kernel["operation"] + "`", ""]
        for variant in kernel["variants"]:
            lines.append("- **%s**: `%s`" % (variant["dtype"], variant["signature"]))
            lines.append("  - program `%s`, marker `%s_PASS`" % (Path(variant["program"]).name, variant["marker"]))
            tolerance = variant["tolerance"]
            lines.append("  - check: " + ("exact" if tolerance.get("exact") else
                                          "rtol %g, atol %g" % (tolerance["rtol"], tolerance["atol"])))
        lines += ["", "Shapes checked: " + "; ".join(kernel["shapes_checked"]) + ".",
                  "Reference: " + kernel["reference"] + "."]
        if "notes" in kernel:
            lines += ["", kernel["notes"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if sys.argv[1:2] == ["check"]:
        found = check(Path(sys.argv[2]))
        print("\n".join(found) or "kernels.json matches the programs")
        sys.exit(1 if found else 0)
    sys.stdout.write(render())
