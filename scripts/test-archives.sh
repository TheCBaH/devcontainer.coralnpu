#!/usr/bin/env bash
# Usage: [CORAL_CPUSET=0,1] test-archives.sh [archive-prefix image [smoke-groups]]
# Without arguments every archive runs in every image and the results are collected; CI shards by
# archive, image and smoke group, then collects with scripts/fixture_results.py.
set -euo pipefail
only_archive=${1:-} only_image=${2:-} only_groups=${3:-}
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/dist"
sha256sum -c SHA256SUMS
shopt -s nullglob
archives=(coralnpu-*-linux-*.tar.gz)
if [ "${#archives[@]}" -eq 0 ]; then
  echo "No archives were packaged"
  exit 1
fi
tag=${only_groups:-all}
results="$root/.cache/results/${tag// /+}"
mkdir -p "$results"
for archive in "${archives[@]}"; do
  [[ -z "$only_archive" || "$archive" == "$only_archive"-* ]] || continue
  case "$archive" in
    # The subsystem simulator is built for two threads; run it on two CPUs.
    coralnpu-subsystem-*) images=(python:3.13-slim-trixie) cpus=(--cpuset-cpus="${CORAL_CPUSET:-0,1}") ;;
    *) images=(ubuntu:24.04 debian:13-slim) cpus=(${CORAL_CPUSET:+--cpuset-cpus="$CORAL_CPUSET"}) ;;
  esac
  for image in "${images[@]}"; do
    [[ -z "$only_image" || "$image" == "$only_image" ]] || continue
    docker run --rm --network=none "${cpus[@]}" \
      --mount "type=bind,src=$root/dist,dst=/archives,readonly" \
      -e ARCHIVE="$archive" ${only_groups:+-e CORAL_SMOKE_GROUPS="$only_groups"} "$image" bash -euo pipefail -c '
        mkdir -p /tmp/relocated
        tar -xzf "/archives/$ARCHIVE" -C /tmp/relocated
        bundle=/tmp/relocated/${ARCHIVE%.tar.gz}
        for binary in "$bundle"/bin/*; do
          [ -e "$binary" ] || continue
          echo "Runtime dependencies: $binary"
          if output=$(ldd "$binary" 2>&1); then
            echo "$output"
          else
            echo "$output"
            exit 1
          fi
          if [[ "$output" = *"not found"* ]]; then echo "$output"; exit 1; fi
        done
        bash "$bundle/smoke.sh"
        if [ -e "$bundle/bin/coralnpu_v2_sim" ]; then
          printf invalid > "$bundle/lib/libstdc++.so.6"
          if timeout 10 "$bundle/bin/coralnpu_v2_sim" --semihost_htif "$bundle/examples/scalar.elf" > broken.log 2>&1; then
            echo "Corrupted runtime library was ignored"
            exit 1
          fi
          cat broken.log
          grep -Eq "file too short|invalid ELF header" broken.log
        fi
      ' | tee "$results/${archive%.tar.gz}-${image//[:\/]/_}.log"
  done
done
[ -n "$only_archive$only_image$only_groups" ] || python3 "$root/scripts/fixture_results.py" "$root/dist" "$root/.cache/results"
