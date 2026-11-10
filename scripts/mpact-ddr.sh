#!/usr/bin/env bash
# MPACT with the simulated DDR: launchers/coralnpu_<v2|m3|m4>_ddr_sim runs bin/coralnpu_<v2|m3|m4>_sim
# with the default regions plus 1 GiB of read/write DDR at 0x80000000, after checking that every ELF
# PT_LOAD range lies in one of them. --semihost_htif would otherwise map any segment the ELF asks for.
# Same command line as the simulator, except that --allow_memory_region is fixed.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
name=${BASH_SOURCE[0]##*/}
sim=$here/../bin/${name/_ddr_sim/_sim}
ddr_base=$((0x80000000)) ddr_bytes=$((0x40000000))
# Instruction and data TCM of the 8/32 KiB and 1/1 MiB layouts; the 4 MiB external RAM; DDR.
ranges=("0 $((0x200000))" "$((0x20000000)) $((0x400000))" "$ddr_base $ddr_bytes")
regions=0x0:0x2000:rx,0x10000:0x8000:rw,0x20000000:0x400000:rw,0x80000000:0x40000000:rw

fail() { echo "$name: $*" >&2; exit 126; }
[ "$#" -gt 0 ] || exec "$sim" "$@"
for arg; do
  case "$arg" in --allow_memory_region|--allow_memory_region=*) fail "the regions of this profile are fixed" ;; esac
done
elf=${!#}
if [ -f "$elf" ] && [ "$(head -c 4 "$elf" | od -An -c | tr -d ' ')" = '177ELF' ]; then
  [ "$(od -An -tu1 -j4 -N1 "$elf")" -eq 1 ] || fail "only ELF32 files are supported: $elf"
  phoff=$(od -An -tu4 -j28 -N4 "$elf")
  phsize=$(od -An -tu2 -j42 -N2 "$elf")
  phnum=$(od -An -tu2 -j44 -N2 "$elf")
  for ((i = 0; i < phnum; i++)); do
    offset=$((phoff + i * phsize))
    [ "$(od -An -tu4 -j"$offset" -N4 "$elf")" -eq 1 ] || continue
    memsz=$(($(od -An -tu4 -j"$((offset + 20))" -N4 "$elf")))
    for field in 8 12; do
      address=$(($(od -An -tu4 -j"$((offset + field))" -N4 "$elf")))
      inside=false
      for range in "${ranges[@]}"; do
        read -r base size <<<"$range"
        if [ "$address" -ge "$base" ] && [ "$memsz" -le "$size" ] && [ "$((address - base))" -le "$((size - memsz))" ]; then
          inside=true
        fi
      done
      $inside || fail "segment $i at $(printf 0x%x "$address") size $memsz is outside the profile: $elf"
    done
  done
fi
exec "$sim" --allow_memory_region="$regions" "$@"
