#!/usr/bin/env bash
# Simulated DDR tests: ddr-tests.sh rtl|mpact|host. Each passing run prints
# "CORAL_RESULT <path> <fixture> pass" for scripts/fixture_results.py.
#   rtl    guest programs on the DDR Verilator simulators (the 4.5 MiB product on the _fast ones)
#   mpact  the same programs through launchers/coralnpu_*_ddr_sim
#   host   payload corruption, invalid ELF segments and cycle limits on the DDR Verilator simulators
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
unset LD_LIBRARY_PATH PYTHONPATH RUNFILES_DIR RUNFILES_MANIFEST_FILE
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"
payload_marker='bytes=4718592 checksum=d0429f10'
rtl_sims=(rvv_core_mini_highmem_axi_ddr_sim rvv_core_mini_highmem_axi_ddr_fast_sim
          vme_core_mini_axi_ddr_sim vme_core_mini_axi_ddr_fast_sim)

# run <expected status> <stdin> <command...>: stdout, stderr and the input are kept in the scratch directory.
run() {
  local expected=$1 input=$2 status
  shift 2
  printf '%s' "$input" >stdin
  if timeout --preserve-status --kill-after=5 "${CORAL_DDR_TIMEOUT:-1200}" "$@" <stdin >stdout 2>stderr; then
    status=0
  else
    status=$?
  fi
  if [ "$status" -ne "$expected" ]; then
    sed -n '1,100p' stdout stderr
    echo "Expected status $expected, got $status: $*" >&2
    exit 1
  fi
}
result() { echo "CORAL_RESULT $1 $2 pass"; }
absent() { if grep -q "$1" stdout; then sed -n '1,100p' stdout; echo "Unexpected output: $1" >&2; exit 1; fi; }

# Small-TCM simulators take the 8/32 KiB layouts, the others the 1 MiB ones.
layout() { case $1 in vme_*) echo "" ;; *) echo _tcm1m ;; esac; }

rtl() {
  for sim in "${rtl_sims[@]}"; do
    local suffix elf
    suffix=$(layout "$sim")
    local bin="$root/bin/$sim" cycles=--cycles=200000000
    elf=ddr_payload$suffix.elf
    run 0 '' "$bin" $cycles --binary="$root/examples/$elf"
    grep -q "CORAL_DDR_PAYLOAD_PASS $payload_marker" stdout
    result "bin/$sim" "$elf"
    run 0 '' "$bin" $cycles --backdoor_load --binary="$root/examples/$elf"
    grep -q "CORAL_DDR_PAYLOAD_PASS $payload_marker" stdout
    elf=ddr_htif$suffix.elf
    run 0 0123456789abcdefB "$bin" $cycles --binary="$root/examples/$elf"
    grep -q DDR_INITIALIZED stdout
    grep -q ABCD stdout
    grep -q 'CORAL_DDR_HTIF_PASS bounds=1' stdout
    test "$(stat -c %s coral-ddr-io.tmp)" -eq 4096
    rm -f coral-ddr-io.tmp
    result "bin/$sim" "$elf"
    case $sim in
      rvv_*)
        elf=ddr_rvv_tcm1m.elf
        run 0 '' "$bin" $cycles --binary="$root/examples/$elf"
        grep -q "CORAL_DDR_RVV_PASS $payload_marker" stdout
        result "bin/$sim" "$elf"
        ;;
    esac
    case $sim in
      rvv_*_fast_sim)
        elf=rvv_matmul_ddr_int8.elf
        run 0 '' "$bin" --cycles=2000000000 --binary="$root/examples/$elf"
        grep -q CORAL_RVV_MATMUL_DDR_INT8_PASS stdout
        result "bin/$sim" "$elf"
        ;;
    esac
    echo "DDR passed: $sim"
  done
}

mpact() {
  for gen in v2 m3 m4; do
    local launcher="$root/launchers/coralnpu_${gen}_ddr_sim"
    local flags=(--semihost_htif --exit_on_ebreak --max_instructions=2000000000)
    local elves=(ddr_payload ddr_htif)
    [ "$gen" = v2 ] || elves+=(ddr_payload_tcm1m ddr_htif_tcm1m ddr_rvv_tcm1m rvv_matmul_ddr_int8)
    for name in "${elves[@]}"; do
      local elf=$name.elf
      case $name in
        ddr_payload*) marker="CORAL_DDR_PAYLOAD_PASS $payload_marker" ;;
        ddr_htif*) marker='CORAL_DDR_HTIF_PASS bounds=0' ;;
        ddr_rvv*) marker="CORAL_DDR_RVV_PASS $payload_marker" ;;
        rvv_matmul*) marker=CORAL_RVV_MATMUL_DDR_INT8_PASS ;;
      esac
      run 0 0123456789abcdef "$launcher" "${flags[@]}" "$root/examples/$elf"
      grep -q "$marker" stdout
      test "$(grep -c "$marker" stdout)" -eq 1
      if [ "$name" = ddr_htif ] || [ "$name" = ddr_htif_tcm1m ]; then
        grep -q DDR_INITIALIZED stdout
        grep -q ABCD stdout
        test "$(stat -c %s coral-ddr-io.tmp)" -eq 4096
        rm -f coral-ddr-io.tmp
      fi
      result "launchers/coralnpu_${gen}_ddr_sim" "$elf"
    done
    # An ELF outside the profile is refused before the simulator starts.
    cp "$root/examples/ddr_payload.elf" outside.elf
    chmod u+w outside.elf
    poke32 outside.elf "$(ddr_segment outside.elf) + 12" $((0xbffffff0))
    run 126 '' "$launcher" "${flags[@]}" outside.elf
    grep -q 'outside the profile' stderr
    run 126 '' "$launcher" "${flags[@]}" --allow_memory_region=0x0:0x2000:rx outside.elf
    echo "MPACT DDR passed: $gen"
  done
}

peek32() { echo $(($(od -An -tu4 -j"$2" -N4 "$1"))); }
poke32() { # file offset-expression value
  local value=$3
  printf "$(printf '\\%03o\\%03o\\%03o\\%03o' $((value & 255)) $(((value >> 8) & 255)) \
    $(((value >> 16) & 255)) $(((value >> 24) & 255)))" | dd of="$1" bs=1 seek="$(($2))" conv=notrunc status=none
}
# The offset of the program header of the first initialized PT_LOAD at the start of DDR.
ddr_segment() {
  local phoff phsize phnum offset
  phoff=$(peek32 "$1" 28)
  phsize=$(($(od -An -tu2 -j42 -N2 "$1")))
  phnum=$(($(od -An -tu2 -j44 -N2 "$1")))
  for ((i = 0; i < phnum; i++)); do
    offset=$((phoff + i * phsize))
    if [ "$(peek32 "$1" "$offset")" -eq 1 ] && [ "$(peek32 "$1" "$((offset + 12))")" -eq $((0x80000000)) ] &&
        [ "$(peek32 "$1" "$((offset + 16))")" -gt 0 ]; then
      echo "$offset"
      return
    fi
  done
  echo "No initialized DDR segment in $1" >&2
  return 1
}

host() {
  for sim in "${rtl_sims[@]}"; do
    local suffix bin="$root/bin/$sim" elf segment position original
    suffix=$(layout "$sim")
    elf=ddr_payload$suffix.elf
    # The last byte of the initialized payload is changed: the guest must notice and fail.
    cp "$root/examples/$elf" corrupt.elf
    chmod u+w corrupt.elf
    segment=$(ddr_segment corrupt.elf)
    test "$(peek32 corrupt.elf "$((segment + 16))")" -eq 4718592
    position=$(($(peek32 corrupt.elf "$((segment + 4))") + 4718592 - 1))
    original=$(($(od -An -tu1 -j"$position" -N1 corrupt.elf)))
    printf "$(printf '\\%03o' $((original ^ 255)))" | dd of=corrupt.elf bs=1 seek="$position" conv=notrunc status=none
    run 125 '' "$bin" --cycles=200000000 --binary="$scratch/corrupt.elf"
    grep -q CORAL_DDR_PAYLOAD_FAIL stdout
    absent CORAL_DDR_PAYLOAD_PASS
    # Segments that cross the end of DDR, start outside it or are larger than it are refused by the loader.
    for change in "12 $((0xbffffff0))" "12 $((0xc0000000))" "12 $((0x7ffffff0))" "20 $((0x40000001))"; do
      set -- $change
      cp "$root/examples/$elf" bad.elf
      chmod u+w bad.elf
      segment=$(ddr_segment bad.elf)
      poke32 bad.elf "$segment + $1" "$2"
      run 126 '' "$bin" --binary="$scratch/bad.elf"
      run 126 '' "$bin" --backdoor_load --binary="$scratch/bad.elf"
      absent CORAL_DDR_PAYLOAD_PASS
    done
    run 124 '' "$bin" --cycles=1000 --binary="$root/examples/$elf"
    absent CORAL_DDR_PAYLOAD_PASS
    echo "DDR failures observable: $sim"
  done
}

case ${1:-} in
  rtl) rtl ;;
  mpact) mpact ;;
  host) host ;;
  *) echo "Usage: ddr-tests.sh rtl|mpact|host" >&2; exit 2 ;;
esac
