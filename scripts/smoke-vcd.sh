#!/usr/bin/env bash
# The VCD simulator: a VCD file, the same bytes on a pipe whether the reader is quick or slow, a slow
# reader costing the simulator no CPU, a selection, and a catalog. Run by smoke.sh, or alone on an
# extracted emulator archive.
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"
check() {
  marker=$1
  shift
  echo "Checking $marker with $*"
  if timeout --kill-after=5 300 "$@" >output.log 2>&1; then status=0; else status=$?; fi
  sed -n '1,200p' output.log
  if [ "$status" -ne 0 ]; then
    echo "Simulator exited with status $status"
    return "$status"
  fi
  grep -q "$marker" output.log
  example=${*: -1}
  echo "CORAL_RESULT ${1#"$root/"} ${example##*/} pass"
}
# The design traces heap addresses, which differ from run to run. noise A B lists the signals whose
# values differ between two runs of the same simulator; mask FILE NOISE replaces their values.
noise() {
  awk 'NR == FNR { a[FNR] = $0; next }
       a[FNR] != $0 && $0 !~ /^[#$ ]/ { n = split($0, f, " "); print (n == 2 && $0 ~ /^b/) ? f[2] : substr($0, 2) }' \
    "$1" "$2" | sort -u
}
mask() {
  awk 'NR == FNR { noisy[$0] = 1; next }
       $0 ~ /^[#$ ]/ { print; next }
       { n = split($0, f, " "); id = (n == 2 && $0 ~ /^b/) ? f[2] : substr($0, 2); print (id in noisy) ? "masked " id : $0 }' \
    "$2" "$1"
}
# same A B: the files are equal, but for the signals in noise.txt, or say how they differ.
same() {
  mask "$1" noise.txt > a.masked
  mask "$2" noise.txt > b.masked
  if cmp a.masked b.masked; then return; fi
  cmp -l a.masked b.masked | head -5 || true
  diff a.masked b.masked | head -12 | cut -c1-120 || true
  exit 1
}
# The VCD simulator: a VCD file, the same bytes on a pipe whether the reader is quick or slow,
# a slow reader costing the simulator no CPU, a selection, and a catalog.
vcd_sim=core_mini_axi_vcd_sim
vcd_file="$PWD/$vcd_sim.vcd"
check CORAL_SCALAR_PASS "$root/bin/$vcd_sim" --cycles=1000000 --trace_file="$vcd_file" --binary="$root/examples/scalar.elf"
grep -q '^\$enddefinitions \$end$' "$vcd_file"
test "$(tail -c 1 "$vcd_file" | od -An -tx1 | tr -d ' ')" = 0a
echo "VCD waveform generated: $vcd_file ($(stat -c %s "$vcd_file") bytes)"
check CORAL_SCALAR_PASS "$root/bin/$vcd_sim" --cycles=1000000 --trace_file="$PWD/again.vcd" --binary="$root/examples/scalar.elf"
noise "$vcd_file" again.vcd > noise.txt
echo "Signals with values that differ between two runs: $(wc -l < noise.txt)"
same again.vcd "$vcd_file"
cpu_seconds() { awk '{ print $2 + $3 }' "$1"; }
stream() {
  local delay=$1 output=$2 fifo=$PWD/stream.fifo
  rm -f "$fifo"
  mkfifo "$fifo"
  { sleep "$delay"; cat > "$output"; } < "$fifo" &
  local reader=$!
  TIMEFORMAT='%R %U %S'
  { time timeout --kill-after=5 300 "$root/bin/$vcd_sim" --cycles=1000000 --trace_fd=3 \
      --binary="$root/examples/scalar.elf" ${3:-} 3>"$fifo" > stream.log 2>&1; } 2> "$output.time"
  wait "$reader"
  grep -q CORAL_SCALAR_PASS stream.log
}
stream 0 fast.vcd
stream 4 slow.vcd
same fast.vcd "$vcd_file"
same slow.vcd "$vcd_file"
fast_cpu=$(cpu_seconds fast.vcd.time)
slow_cpu=$(cpu_seconds slow.vcd.time)
echo "Trace on a pipe: $(cat fast.vcd.time) s with a quick reader, $(cat slow.vcd.time) s with a slow one"
awk -v fast="$fast_cpu" -v slow="$slow_cpu" 'BEGIN { exit !(slow < fast + 1.5) }'
stream 0 every-edge.vcd --trace_flush_interval=1
# A flush can repeat a timestamp line; the value changes are the same.
grep -v '^#' every-edge.vcd > every-edge.changes
grep -v '^#' "$vcd_file" > file.changes
same every-edge.changes file.changes
printf 'hwfrp-verilator-select 1\nproducer %s vcd\nselect VCoreMiniAxi.core CoreMiniAxi io_aclk\n' "$vcd_sim" > select-vcd.txt
check CORAL_SCALAR_PASS "$root/bin/$vcd_sim" --cycles=1000000 --trace_file="$PWD/selected.vcd" \
  --trace_select=select-vcd.txt --binary="$root/examples/scalar.elf"
test "$(grep -c '^ *\$var ' selected.vcd)" -eq 1
test "$(stat -c %s selected.vcd)" -lt "$(stat -c %s "$vcd_file")"
if "$root/bin/core_mini_axi_sim" --cycles=1000000 --trace_file="$PWD/wrong.fst" --trace_select=select-vcd.txt \
    --binary="$root/examples/scalar.elf" > wrong.log 2>&1; then
  echo "A VCD manifest was accepted by an FST simulator"
  exit 1
fi
grep -q "made for a vcd simulator" wrong.log
"$root/bin/$vcd_sim" --trace_catalog="$PWD/vcd catalog.vcd" > vcd-catalog.log 2>&1
grep -q '^\$enddefinitions \$end$' "vcd catalog.vcd"
test "$(grep -c '^ *\$var ' "vcd catalog.vcd")" -gt 1000
echo "VCD catalog generated: $(stat -c %s "vcd catalog.vcd") bytes"
if "$root/bin/core_mini_axi_sim" --cycles=1000000 --trace_fd=1 --binary="$root/examples/scalar.elf" > fd.log 2>&1; then
  echo "An FST simulator accepted --trace_fd"
  exit 1
fi
grep -q "only the VCD simulators" fd.log
