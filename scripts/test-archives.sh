#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/dist"
sha256sum -c SHA256SUMS
for archive in coralnpu-emulators-linux-*.tar.gz; do
  for image in ubuntu:24.04 debian:13-slim; do
    docker run --rm --network=none \
      --mount "type=bind,src=$root/dist,dst=/archives,readonly" \
      -e ARCHIVE="$archive" "$image" bash -euo pipefail -c '
        mkdir -p /tmp/relocated
        tar -xzf "/archives/$ARCHIVE" -C /tmp/relocated
        bundle=/tmp/relocated/${ARCHIVE%.tar.gz}
        for binary in "$bundle"/bin/*; do
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
        printf invalid > "$bundle/lib/libstdc++.so.6"
        if timeout 10 "$bundle/bin/coralnpu_v2_sim" --semihost_htif "$bundle/examples/scalar.elf" > broken.log 2>&1; then
          echo "Corrupted runtime library was ignored"
          exit 1
        fi
        cat broken.log
        grep -Eq "file too short|invalid ELF header" broken.log
      '
  done
done
