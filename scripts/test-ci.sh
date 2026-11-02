#!/usr/bin/env bash
# Archive tests by name; with no argument, all of them on one 4-CPU runner, each as a log group with its
# duration. Phase 1 gives the subsystem simulator (two Verilator threads) CPUs 0-1 and the libc checks
# CPUs 2-3; phase 2 runs the single-threaded groups four at a time.
#   libc       every simulator starts in the Ubuntu and Debian images (libc compatibility)
#   subsystem  the subsystem archive
#   <group>    a smoke.sh group of the emulators archive in the Ubuntu image
set -uo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
groups=(kernels-tcm kernels-highmem rtl matrix-fp32 matrix-int8 matrix-bf16 matrix-vme host uninit invalid limits)
emulators=coralnpu-emulators
run() { bash "$root/scripts/test-archives.sh" "$@"; }
one() {
  case $1 in
    libc) run $emulators ubuntu:24.04 libc && run $emulators debian:13-slim libc ;;
    subsystem) run coralnpu-subsystem python:3.13-slim-trixie ;;
    *) [[ " ${groups[*]} " == *" $1 "* ]] || { echo "Unknown test: $1" >&2; return 2; }
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
if [ "$#" -gt 0 ]; then
  for name in "$@"; do one "$name" || exit 1; done
  exit 0
fi
export -f logged one run
export root emulators
export groups_list="${groups[*]}"
failed=0
logged subsystem 0,1 & sub=$!
logged libc 2,3 || failed=1
wait "$sub" || failed=1
printf '%s\n' "${groups[@]}" | xargs -P4 -I{} bash -c 'groups=($groups_list); logged "$1" ""' _ {} || failed=1
exit "$failed"
