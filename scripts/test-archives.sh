#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/dist"
sha256sum -c SHA256SUMS
shopt -s nullglob
archives=(coralnpu-*-linux-*.tar.gz)
if [ "${#archives[@]}" -eq 0 ]; then
  echo "No archives were packaged"
  exit 1
fi
mkdir -p "$root/.cache/results"
for archive in "${archives[@]}"; do
  case "$archive" in
    coralnpu-subsystem-*) images=(python:3.13-slim-trixie) ;;
    *) images=(ubuntu:24.04 debian:13-slim) ;;
  esac
  for image in "${images[@]}"; do
    docker run --rm --network=none \
      --mount "type=bind,src=$root/dist,dst=/archives,readonly" \
      -e ARCHIVE="$archive" "$image" bash -euo pipefail -c '
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
      ' | tee "$root/.cache/results/${archive%.tar.gz}-${image//[:\/]/_}.log"
  done
done
python3 "$root/scripts/fixture_results.py" "$root/dist" "$root/.cache/results"
