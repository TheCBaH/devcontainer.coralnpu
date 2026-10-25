#!/usr/bin/env bash
# Exact-name trace selection on the Verilator trace runtime, built with libstdc++ debug containers.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/.cache/source"
bazel --output_user_root="$root/.cache/bazel" test -c opt --config=glibcxx-debug \
  --repository_cache="$root/.cache/repos" --disk_cache="$root/.cache/actions" \
  --jobs="${BUILD_JOBS:-2}" --verbose_failures --test_output=all \
  //tests/trace_selection:trace_selection_test //tests/verilator_sim:fd_vcd_file_test \
  //tests/verilator_sim:sysc_tb_trace_test
