#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
unset LD_LIBRARY_PATH PYTHONPATH RUNFILES_DIR RUNFILES_MANIFEST_FILE
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"

if [ "$#" -eq 0 ]; then set -- fp32 int8 bf16 vme; fi
for kind; do
  case "$kind" in
    fp32|int8|bf16|vme) ;;
    *) echo "Unknown matrix format: $kind" >&2; exit 2 ;;
  esac
  if [ "$kind" = vme ]; then
    sim=vme_core_mini_axi_sim
    elf=vme_external_matmul.elf
    marker=CORAL_VME_EXTERNAL_MATMUL
  else
    sim=rvv_core_mini_highmem_axi_sim
    elf=rvv_matmul_$kind.elf
    marker=CORAL_RVV_MATMUL_${kind^^}
  fi
  echo "Checking $elf on prebuilt layout $sim"
  status=0
  timeout --kill-after=5 300 "$root/bin/$sim" --cycles=100000000 \
    --binary="$root/examples/$elf" >output.log 2>&1 || status=$?
  cat output.log
  test "$status" -eq 0
  grep -q "${marker}_PASS" output.log
  echo "CORAL_RESULT bin/$sim $elf pass"

  cp "$root/examples/$elf" corrupt.elf
  chmod u+w corrupt.elf
  phoff=$(od -An -tu4 -j28 -N4 corrupt.elf)
  phsize=$(od -An -tu2 -j42 -N2 corrupt.elf)
  phnum=$(od -An -tu2 -j44 -N2 corrupt.elf)
  found=false
  for ((i=0; i<phnum; i++)); do
    offset=$((phoff + i*phsize))
    type=$(od -An -tu4 -j"$offset" -N4 corrupt.elf)
    address=$(od -An -tu4 -j"$((offset+12))" -N4 corrupt.elf)
    if [ "$type" -eq 1 ] && [ "$address" -eq 536870912 ]; then
      payload=$(od -An -tu4 -j"$((offset+4))" -N4 corrupt.elf)
      test "$(od -An -tu1 -j"$((payload))" -N1 corrupt.elf)" -ne 255
      printf '\377' | dd of=corrupt.elf bs=1 seek="$((payload))" conv=notrunc status=none
      found=true
      break
    fi
  done
  test "$found" = true
  status=0
  timeout --kill-after=5 300 "$root/bin/$sim" --cycles=100000000 \
    --binary="$scratch/corrupt.elf" >output.log 2>&1 || status=$?
  cat output.log
  test "$status" -eq 125
  grep -q "${marker}_FAIL" output.log
  if grep -q "${marker}_PASS" output.log; then
    echo "Corrupted input reported a pass" >&2
    exit 1
  fi
  echo "Corrupted external $kind input rejected"
done
