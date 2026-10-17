#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
root=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"

expect_status() {
  local expected=$1 input=$2 status
  shift 2
  printf '%s' "$input" >stdin
  if timeout --preserve-status --kill-after=5 60 "$@" <stdin >stdout 2>stderr; then
    status=0
  else
    status=$?
  fi
  if [ "$status" -ne "$expected" ]; then
    cat stdout stderr
    echo "Expected status $expected, got $status: $*" >&2
    exit 1
  fi
}

for path in "$root"/bin/*; do
  sim=${path##*/}
  if [[ "$sim" = coralnpu_* ]]; then
    elf=exit_status.elf
    args=("$path" --semihost_htif --exit_on_ebreak "$root/examples/exit_status.elf")
  else
    case "$sim" in
      *highmem*|*512kb*) elf=exit_status_tcm512k.elf ;;
      *) elf=exit_status.elf ;;
    esac
    args=("$path" --cycles=100000 --binary="$root/examples/$elf")
  fi
  for mode in 0 5 7 x b p; do
    case "$mode" in
      0|p) expected=0 ;;
      5|x) expected=5 ;;
      7) expected=77 ;;
      b) expected=125 ;;
    esac
    expect_status "$expected" "$mode" "${args[@]}"
  done
  if [[ "$sim" != coralnpu_* ]]; then
    expect_status 124 l "${args[@]}"
    expect_status 124 '' "$path" --cycles=1 --binary="$root/examples/$elf"
    expect_status 126 '' "$path" --binary="$scratch/missing.elf"
  else
    expect_status 126 '' "$path" "$scratch/missing.elf"
    test ! -s stdout
  fi
  echo "Host exit contract passed: $sim"
  echo "CORAL_RESULT bin/$sim $elf pass"
done
