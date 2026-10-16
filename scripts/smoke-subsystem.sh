#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
unset LD_LIBRARY_PATH PYTHONPATH
scratch=$(mktemp -d)
cleanup() {
  [ -z "${sim:-}" ] || kill "$sim" 2>/dev/null || true
  find "$scratch" -delete
}
trap cleanup EXIT
cd "$scratch"
ln -s "$root/share/grey_bars_320x240.raw" .
port=5555
run() {
  variant=$1 elf=$2 itcm=$3 dtcm=$4
  port=$((port + 1))
  rm -f ./*.log
  echo "Checking CORAL_SUBSYSTEM_DMA_PASS with Vchip_$variant and $elf"
  SPI_DPI_PORT=$port "$root/bin/Vchip_$variant" --load_elf="$root/examples/$elf" >sim.out 2>&1 &
  sim=$!
  timeout 120 bash -c "until grep -q 'DPI: Server listening on port $port' sim.out; do sleep 0.2; done"
  SPI_DPI_PORT=$port timeout 120 python3 "$root/tools/loader.py" --csr_only \
    --itcm_size_kbytes "$itcm" --dtcm_size_kbytes "$dtcm" "$root/examples/$elf"
  if ! timeout 600 bash -c 'until grep -qs CORAL_SUBSYSTEM_DMA "$0"/*.log; do sleep 0.5; done' "$PWD"; then
    tail -50 sim.out
    return 1
  fi
  kill "$sim"
  wait "$sim" || true
  sim=
  cat ./*.log
  grep -qs CORAL_SUBSYSTEM_DMA_PASS ./*.log
  echo "CORAL_RESULT bin/Vchip_$variant $elf pass"
}
run vector_normal subsystem_dma.elf 8 32
run matrix_normal subsystem_dma.elf 8 32
run vector_highmem subsystem_dma_tcm1m.elf 1024 1024
run matrix_highmem subsystem_dma_tcm1m.elf 1024 1024
echo "Subsystem SRAM, TCM and DMA checks passed"
