#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
unset LD_LIBRARY_PATH
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"
for library in "$root"/lib/libcoralnpu_simulator*.so; do
  echo "Checking CORAL_LIBRARY_PASS with $library"
  timeout --kill-after=5 300 "$root/examples/library_example" "$library" "$root/examples/library.elf" | tee output.log
  grep -q CORAL_LIBRARY_PASS output.log
  echo "CORAL_RESULT lib/${library##*/} library.elf pass"
done
echo "Shared library API, DDR, DTCM and mailbox checks passed"
