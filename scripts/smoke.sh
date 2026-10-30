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
# Runs an RTL check on a simulator and on its _fast twin, which must agree.
rtl() {
  check "$1" "$root/bin/$2" --cycles="${4:-1000000}" --binary="$root/examples/$3"
  if [ -x "$root/bin/${2%_sim}_fast_sim" ]; then
    check "$1" "$root/bin/${2%_sim}_fast_sim" --cycles="${4:-1000000}" --binary="$root/examples/$3"
  fi
}
mpact() {
  check "$1" "$root/bin/$2" --semihost_htif --exit_on_ebreak --max_instructions=100000000 "$root/examples/$3"
}
for sim in core_mini_axi_sim rvv_core_mini_axi_sim vme_core_mini_axi_sim; do
  check CORAL_SCALAR_PASS "$root/bin/$sim" --cycles=1000000 --trace --binary="$root/examples/scalar.elf"
  waveform=$(sed -n 's/.*for tracing: 1 ps (\(.*\.fst\)).*/\1/p' output.log)
  test -n "$waveform"
  test -s "$waveform"
  echo "FST waveform generated: $waveform ($(stat -c %s "$waveform") bytes)"
  custom_waveform="$PWD/$sim custom.fst"
  check CORAL_SCALAR_PASS "$root/bin/$sim" --cycles=1000000 --trace_file="$custom_waveform" --binary="$root/examples/scalar.elf"
  test -s "$custom_waveform"
  echo "Explicit FST waveform generated: $custom_waveform"
  case "$sim" in
    core_mini_axi_sim) top=CoreMiniAxi ;;
    rvv_core_mini_axi_sim) top=RvvCoreMiniAxi ;;
    vme_core_mini_axi_sim) top=VmeCoreMiniAxi ;;
  esac
  printf 'hwfrp-verilator-select 1\nproducer %s fst\nselect V%s.core %s io_aclk\n' "$sim" "$top" "$top" > select.txt
  selected_waveform="$PWD/$sim selected.fst"
  check CORAL_SCALAR_PASS "$root/bin/$sim" --cycles=1000000 --trace_file="$selected_waveform" \
    --trace_select=select.txt --binary="$root/examples/scalar.elf"
  test -s "$selected_waveform"
  test "$(stat -c %s "$selected_waveform")" -lt "$(stat -c %s "$custom_waveform")"
  echo "Selected FST waveform generated: $selected_waveform"
  printf 'hwfrp-verilator-select 1\nselect V%s.core %s io_aclk\nselect V%s.core %s no_such_signal\n' \
    "$top" "$top" "$top" "$top" > unknown.txt
  if "$root/bin/$sim" --cycles=1000000 --trace_file="$PWD/unknown.fst" --trace_select=unknown.txt \
      --binary="$root/examples/scalar.elf" > unknown.log 2>&1; then
    echo "An unknown selected name was accepted"
    exit 1
  fi
  cat unknown.log
  grep -q "no declaration named \"V$top.core $top no_such_signal\"" unknown.log
  if grep -q CORAL_SCALAR_PASS unknown.log; then
    echo "The simulator ran with an unknown selected name"
    exit 1
  fi
  catalog="$PWD/$sim catalog.fst"
  "$root/bin/$sim" --trace_catalog="$catalog" > catalog.log 2>&1
  test -s "$catalog"
  echo "FST catalog generated: $catalog ($(stat -c %s "$catalog") bytes)"
  rtl CORAL_X0_LOAD_PASS "$sim" x0_load.elf
  rtl CORAL_TRAP_ADDRESS_PASS "$sim" trap_address.elf
  rtl CORAL_MEMORY_PASS "$sim" memory.elf
done
for path in "$root"/bin/*_fast_sim; do
  for flag in --trace "--trace_catalog=$PWD/fast.fst"; do
    set +e
    "$path" --cycles=1000000 "$flag" --binary="$root/examples/scalar.elf" > fast-trace.log 2>&1
    status=$?
    set -e
    cat fast-trace.log
    test "$status" -eq 126
    grep -q 'built without trace code' fast-trace.log
  done
  echo "Tracing refused: ${path##*/}"
done
for sim in coralnpu_v2_sim coralnpu_m3_sim coralnpu_m4_sim; do
  mpact CORAL_SCALAR_PASS "$sim" scalar.elf
  mpact CORAL_RVV_PASS "$sim" rvv.elf
  mpact CORAL_X0_LOAD_PASS "$sim" x0_load.elf
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
mpact CORAL_VME_EXTERNAL_MATMUL_PASS coralnpu_m4_sim vme_external_matmul.elf
mpact CORAL_MATRIX_PASS coralnpu_m4_sim matrix.elf
rtl CORAL_MATRIX_PASS vme_core_mini_axi_sim matrix.elf
for example in "$root"/examples/vme_*_test.elf; do
  mpact CORAL_VME_TEST_PASS coralnpu_m4_sim "${example##*/}"
  rtl CORAL_VME_TEST_PASS vme_core_mini_axi_sim "${example##*/}" 20000000
done
for sim in core_mini_itcm512kb_dtcm512kb_axi_sim core_mini_highmem_axi_sim \
    rvv_core_mini_itcm512kb_dtcm512kb_axi_sim rvv_core_mini_highmem_axi_sim; do
  rtl CORAL_X0_LOAD_PASS "$sim" x0_load_tcm512k.elf
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
bash "$root/smoke-vcd.sh"
uninit() {
  timeout --kill-after=5 300 "$root/bin/$1" --cycles=1000000 "${@:3}" --binary="$root/examples/$2" >output.log 2>&1
  sed -n 's/^CORAL_UNINIT_TCM_PASS \([0-9a-f]\{32\}\)$/\1/p' output.log
}
zeros=00000000000000000000000000000000
for path in "$root"/bin/*; do
  sim=${path##*/}
  [[ "$sim" = coralnpu_* ]] && continue
  case "$sim" in
    *highmem*|*512kb*) elf=uninit_tcm_tcm512k.elf ;;
    *) elf=uninit_tcm.elf ;;
  esac
  check "CORAL_UNINIT_TCM_PASS $zeros" "$root/bin/$sim" --cycles=1000000 --binary="$root/examples/$elf"
  ones=$(uninit "$sim" "$elf" +verilator+rand+reset+1)
  seed7=$(uninit "$sim" "$elf" +verilator+rand+reset+2 +verilator+seed+7)
  again=$(uninit "$sim" "$elf" +verilator+rand+reset+2 +verilator+seed+7)
  seed8=$(uninit "$sim" "$elf" +verilator+rand+reset+2 +verilator+seed+8)
  if [ "$ones" != "${zeros//0/f}" ] || [ -z "$seed7" ] || [ "$seed7" != "$again" ] || [ "$seed7" = "$seed8" ]; then
    sed -n '1,200p' output.log
    echo "SRAM fill mismatch on $sim: ones=$ones seed7=$seed7,$again seed8=$seed8"
    exit 1
  fi
  echo "SRAM fill follows +verilator+rand+reset: $sim"
done
bash "$root/matrix-memory.sh"
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
bash "$root/mpact-limits.sh"
echo "External scalar, RVV, vector FP, matrix, memory and invalid-input checks passed"
