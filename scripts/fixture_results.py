#!/usr/bin/env python3
"""Writes dist/<archive>.fixture-results.json keyed by configuration ID and artifact hash."""
import json
from pathlib import Path
import re
import sys


def main(dist, logs):
    dist, logs = Path(dist), Path(logs)
    for manifest_path in sorted(dist.glob("*.hardware-configurations.json")):
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        archive = document["archive"]["name"]
        results = {}
        artifacts = {artifact["path"]: artifact for artifact in document["artifacts"]}
        fixtures = {Path(fixture["path"]).name: fixture for fixture in document.get("fixtures", [])}
        for log in sorted(logs.glob(archive + "-*.log")):
            image = log.stem[len(archive) + 1:]
            for path, example in re.findall(r"^CORAL_RESULT (\S+) (\S+) pass$", log.read_text(), re.MULTILINE):
                artifact = artifacts[path]
                fixture = fixtures[example]
                if artifact["configuration_id"] not in fixture["configurations"]:
                    raise SystemExit(example + " ran on unlisted configuration " + path)
                key = (artifact["configuration_id"], artifact["sha256"], example)
                entry = results.setdefault(key, {
                    "configuration_id": artifact["configuration_id"],
                    "artifact_path": path,
                    "artifact_sha256": artifact["sha256"],
                    "host_architecture": artifact["host"]["architecture"],
                    "fixture": fixture["path"],
                    "fixture_sha256": fixture["sha256"],
                    "marker": fixture["marker"],
                    "result": "pass",
                    "runtime_images": [],
                })
                entry["runtime_images"].append(image)
        for fixture in document.get("fixtures", []):
            for configuration in fixture["configurations"]:
                if not any(key[0] == configuration and key[2] == Path(fixture["path"]).name for key in results):
                    raise SystemExit("No result for " + fixture["path"] + " on " + configuration)
        output = dist / (archive + ".fixture-results.json")
        output.write_text(json.dumps({"archive": archive, "results": sorted(results.values(), key=lambda entry: (
            entry["configuration_id"], entry["fixture"]))}, indent=2) + "\n")
        print(output)


if __name__ == "__main__":
    main(*sys.argv[1:])
