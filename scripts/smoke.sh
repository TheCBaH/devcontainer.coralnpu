#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
unset LD_LIBRARY_PATH PYTHONPATH RUNFILES_DIR RUNFILES_MANIFEST_FILE
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"
check() {
  marker=$1
  shift
  echo "Checking $marker with $*"
  if timeout 120 "$@" >output.log 2>&1; then
    status=0
  else
    status=$?
  fi
  cat output.log
  if [ "$status" -ne 0 ]; then
    echo "Simulator exited with status $status"
    return "$status"
  fi
  grep -q "$marker" output.log
}
for sim in core_mini_axi_sim rvv_core_mini_axi_sim; do
  check CORAL_SCALAR_PASS "$root/bin/$sim" --binary="$root/examples/scalar.elf" --cycles=1000000
done
check CORAL_SCALAR_PASS "$root/bin/coralnpu_v2_sim" --semihost_htif "$root/examples/scalar.elf"
check CORAL_RVV_PASS "$root/bin/coralnpu_v2_sim" --semihost_htif "$root/examples/rvv.elf"
check CORAL_RVV_PASS "$root/bin/rvv_core_mini_axi_sim" --binary="$root/examples/rvv.elf" --cycles=1000000
for sim in core_mini_axi_sim rvv_core_mini_axi_sim coralnpu_v2_sim; do
  set +e
  if [ "$sim" = coralnpu_v2_sim ]; then
    timeout 10 "$root/bin/$sim" "$scratch/missing.elf" >invalid.log 2>&1
  else
    timeout 10 "$root/bin/$sim" --binary="$scratch/missing.elf" >invalid.log 2>&1
  fi
  status=$?
  set -e
  test "$status" -ne 0
  test "$status" -ne 124
  test "$status" -ne 127
done
echo "External scalar, RVV and invalid-input checks passed"
