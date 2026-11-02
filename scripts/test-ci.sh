#!/usr/bin/env bash
# Archive tests on one 4-CPU CI runner. The subsystem simulator runs two threads and gets two CPUs; the
# other checks are single-threaded. Phase 1: the subsystem on CPUs 0-1 beside the libc checks (every
# simulator in the Ubuntu and Debian images) on CPUs 2 and 3. Phase 2: the comprehensive groups, four at
# a time, in the Ubuntu image.
set -uo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
logs=$(mktemp -d)
run() { # name cpus archive image groups
  local name=$1 status=0
  CORAL_CPUSET=$2 bash "$root/scripts/test-archives.sh" "$3" "$4" "$5" >"$logs/$name.log" 2>&1 || status=$?
  echo "::group::$name (exit $status)"
  cat "$logs/$name.log"
  echo "::endgroup::"
  return "$status"
}
export -f run
export root logs
failed=0
pids=()
run subsystem 0,1 coralnpu-subsystem python:3.13-slim-trixie "" & pids+=($!)
run libc-ubuntu 2 coralnpu-emulators ubuntu:24.04 libc & pids+=($!)
run libc-debian 3 coralnpu-emulators debian:13-slim libc & pids+=($!)
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
[ "$failed" -eq 0 ] || exit 1
# Longest first.
printf '%s\n' kernels-tcm kernels-highmem rtl matrix-fp32 matrix-int8 matrix-bf16 matrix-vme host uninit invalid limits |
  xargs -P4 -I{} bash -c 'run "$1" "" coralnpu-emulators ubuntu:24.04 "$1"' _ {} || failed=1
exit "$failed"
