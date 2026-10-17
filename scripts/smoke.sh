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
  if timeout --kill-after=5 300 "$@" >output.log 2>&1; then
    status=0
  else
    status=$?
  fi
  sed -n '1,200p' output.log
  if [ "$status" -ne 0 ]; then
    echo "Simulator exited with status $status"
    return "$status"
  fi
  grep -q "$marker" output.log
  binary=${1#"$root/"}
  example=${*: -1}
  echo "CORAL_RESULT $binary ${example##*/} pass"
}
rtl() {
  check "$1" "$root/bin/$2" --cycles="${4:-1000000}" --binary="$root/examples/$3"
}
mpact() {
  check "$1" "$root/bin/$2" --semihost_htif --exit_on_ebreak "$root/examples/$3"
}
for sim in core_mini_axi_sim rvv_core_mini_axi_sim vme_core_mini_axi_sim; do
  check CORAL_SCALAR_PASS "$root/bin/$sim" --cycles=1000000 --trace --binary="$root/examples/scalar.elf"
  waveform=$(sed -n 's/.*for tracing: 1 ps (\(.*\.fst\)).*/\1/p' output.log)
  test -n "$waveform"
  test -s "$waveform"
  echo "FST waveform generated: $waveform ($(stat -c %s "$waveform") bytes)"
  rtl CORAL_TRAP_ADDRESS_PASS "$sim" trap_address.elf
  rtl CORAL_MEMORY_PASS "$sim" memory.elf
done
for sim in coralnpu_v2_sim coralnpu_m3_sim coralnpu_m4_sim; do
  mpact CORAL_SCALAR_PASS "$sim" scalar.elf
  mpact CORAL_RVV_PASS "$sim" rvv.elf
  mpact CORAL_TRAP_ADDRESS_PASS "$sim" trap_address.elf
  mpact CORAL_MEMORY_PASS "$sim" memory.elf
done
for sim in rvv_core_mini_axi_sim vme_core_mini_axi_sim; do
  rtl CORAL_RVV_PASS "$sim" rvv.elf
  rtl CORAL_RVV_FP_PASS "$sim" rvv_fp.elf
done
for sim in coralnpu_m3_sim coralnpu_m4_sim; do
  mpact CORAL_RVV_FP_PASS "$sim" rvv_fp.elf
done
mpact CORAL_MATRIX_PASS coralnpu_m4_sim matrix.elf
rtl CORAL_MATRIX_PASS vme_core_mini_axi_sim matrix.elf
for sim in core_mini_itcm512kb_dtcm512kb_axi_sim core_mini_highmem_axi_sim \
    rvv_core_mini_itcm512kb_dtcm512kb_axi_sim rvv_core_mini_highmem_axi_sim; do
  rtl CORAL_TRAP_ADDRESS_PASS "$sim" trap_address_tcm512k.elf
  rtl CORAL_SCALAR_PASS "$sim" scalar_tcm512k.elf
  rtl CORAL_MEMORY_PASS "$sim" memory_tcm512k.elf 20000000
done
for sim in core_mini_highmem_axi_sim rvv_core_mini_highmem_axi_sim; do
  rtl CORAL_MEMORY_PASS "$sim" memory_tcm1m.elf 20000000
done
for sim in rvv_core_mini_itcm512kb_dtcm512kb_axi_sim rvv_core_mini_highmem_axi_sim; do
  rtl CORAL_RVV_PASS "$sim" rvv_tcm512k.elf
  rtl CORAL_RVV_FP_PASS "$sim" rvv_fp_tcm512k.elf
done
for sim in "$root"/bin/*; do
  sim=${sim##*/}
  set +e
  if [[ "$sim" = coralnpu_* ]]; then
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
bash "$root/host-contract.sh"
echo "External scalar, RVV, vector FP, matrix, memory and invalid-input checks passed"
