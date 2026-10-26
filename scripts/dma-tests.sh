#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/.cache/source"
targets=()
groups=("$@")
if [ "${#groups[@]}" -eq 0 ]; then
  groups=(core tilelink subsystem engine)
fi
for group in "${groups[@]}"; do
  case "$group" in
    core)
      targets+=(//tests/cocotb/dma:dma_core_cocotb_test
                //tests/cocotb/dma:transpose_buffer_cocotb_test)
      ;;
    tilelink)
      for suite in tlul2axi_cocotb_test axi2tlul_cocotb_test \
                   tlul_to_sram_cocotb_test tlul_local_xbar_cocotb_test \
                   coralnpu_xbar_cocotb; do
        targets+=("//tests/cocotb/tlul:$suite")
      done
      ;;
    subsystem)
      targets+=(//tests/cocotb/tlul:dma_integration_cocotb)
      for testcase in test_ddr_access test_ddr_burst_pattern_repro \
                      test_tlul_width_bridge_bug_reproduction; do
        targets+=("//tests/cocotb/tlul:coralnpu_chisel_subsystem_cocotb_$testcase")
      done
      ;;
    engine)
      targets+=(//hdl/chisel/src/bus:dma_engine_test)
      ;;
    *) echo "Unknown DMA test group: $group" >&2; exit 2 ;;
  esac
done
bazel --output_user_root="$root/.cache/bazel" test -c opt \
  --repository_cache="$root/.cache/repos" --disk_cache="$root/.cache/actions" \
  ${BUILD_JOBS:+--jobs="$BUILD_JOBS"} --verbose_failures --test_output=errors \
  --keep_going --test_timeout=900 --test_env=COCOTB_RANDOM_SEED=42 \
  --test_env=PYTHONHASHSEED=42 "${targets[@]}"
