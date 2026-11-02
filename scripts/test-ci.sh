#!/usr/bin/env bash
# Archive tests by name, one CI job each (see .github/workflows/test.yml); no argument runs them all.
#   libc       every simulator starts in the Ubuntu and Debian images (libc compatibility)
#   subsystem  the subsystem archive on two CPUs (its simulator runs two threads)
#   <group>    a smoke.sh group of the emulators archive in the Ubuntu image
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
tests=(libc subsystem rtl kernels-tcm kernels-highmem uninit matrix-fp32 matrix-int8 matrix-bf16 matrix-vme invalid host limits)
emulators=coralnpu-emulators
run() { bash "$root/scripts/test-archives.sh" "$@"; }
one() {
  case $1 in
    libc) run $emulators ubuntu:24.04 libc; run $emulators debian:13-slim libc ;;
    subsystem) CORAL_CPUSET=0,1 run coralnpu-subsystem python:3.13-slim-trixie ;;
    *) [[ " ${tests[*]} " == *" $1 "* ]] || { echo "Unknown test: $1" >&2; exit 2; }
       run $emulators ubuntu:24.04 "$1" ;;
  esac
}
for name in "${@:-${tests[@]}}"; do one "$name"; done
