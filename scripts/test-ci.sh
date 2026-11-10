#!/usr/bin/env bash
# Archive tests by name. Several names run in parallel (one CI step each set, see .github/workflows/
# test.yml), their output grouped per test; no argument runs them all in turn.
#   libc       every simulator starts in the Ubuntu and Debian images (libc compatibility)
#   subsystem  the subsystem archive; its simulator runs two threads and gets CPUs 0-1
#   <group>    a smoke.sh group of the emulators archive in the Ubuntu image
set -uo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
tests=(libc subsystem rtl kernels-tcm kernels-highmem uninit matrix-fp32 matrix-int8 matrix-bf16 matrix-vme invalid host limits ddr-rtl ddr-mpact ddr-host)
emulators=coralnpu-emulators
run() { bash "$root/scripts/test-archives.sh" "$@"; }
one() {
  case $1 in
    libc) run $emulators ubuntu:24.04 libc && run $emulators debian:13-slim libc ;;
    subsystem) run coralnpu-subsystem python:3.13-slim-trixie ;;
    *) [[ " ${tests[*]} " == *" $1 "* ]] || { echo "Unknown test: $1" >&2; return 2; }
       run $emulators ubuntu:24.04 "$1" ;;
  esac
}
logged() { # name cpus
  local status=0 start=$SECONDS log
  log=$(mktemp)
  CORAL_CPUSET=$2 one "$1" >"$log" 2>&1 || status=$?
  echo "::group::$1: $([ "$status" -eq 0 ] && echo passed || echo FAILED) in $((SECONDS - start)) s"
  cat "$log"
  echo "::endgroup::"
  rm -f "$log"
  return "$status"
}
names=("$@")
[ "${#names[@]}" -gt 0 ] || names=("${tests[@]}")
if [ "${#names[@]}" -eq 1 ]; then
  CORAL_CPUSET=${CORAL_CPUSET:-} one "${names[0]}"
  exit
fi
# The subsystem simulator gets CPUs 0-1 and the rest share CPUs 2-3 when they run beside it.
others=""
[[ " ${names[*]} " == *" subsystem "* ]] && others=2,3
pids=()
for name in "${names[@]}"; do
  if [ "$name" = subsystem ]; then logged "$name" 0,1 & else logged "$name" "$others" & fi
  pids+=($!)
done
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
exit "$failed"
