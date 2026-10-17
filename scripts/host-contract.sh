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
  for mode in 0 5 7 x b p t; do
    case "$mode" in
      0|p) expected=0 ;;
      5|x) expected=5 ;;
      7|t) expected=77 ;;
      b) expected=125 ;;
    esac
    expect_status "$expected" "$mode" "${args[@]}"
    if [ "$mode" = 0 ]; then grep -q CORAL_EXIT_STATUS_PASS stdout; fi
  done
  if [[ "$sim" != coralnpu_* ]]; then
    expect_status 0 w "${args[@]}"
    expect_status 0 rZ "${args[@]}"
    expect_status 0 o "${args[@]}"
    expect_status 0 h "${args[@]}"
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

for path in "$root"/bin/*; do
  sim=${path##*/}
  case "$sim" in
    *highmem*|*512kb*) elf=host_ram_tcm512k.elf ;;
    *) elf=host_ram.elf ;;
  esac
  if [[ "$sim" = coralnpu_* ]]; then
    args=("$path" --semihost_htif --exit_on_ebreak "$root/examples/$elf")
  else
    args=("$path" --cycles=100000 --binary="$root/examples/$elf")
  fi
  expect_status 0 0123456789abcdef "${args[@]}"
  grep -q RAM_INITIALIZED stdout
  grep -q CORAL_HOST_RAM_PASS stdout
  if [[ "$sim" != coralnpu_* ]]; then
    expect_status 0 0123456789abcdef "${args[@]}" --backdoor_load
    grep -q CORAL_HOST_RAM_PASS stdout
    cp "$root/examples/$elf" bad.elf
    phoff=$(od -An -tu4 -j28 -N4 bad.elf)
    phnum=$(od -An -tu2 -j44 -N2 bad.elf)
    found=false
    for ((i=0; i<phnum; i++)); do
      offset=$((phoff + i*32 + 12))
      address=$(od -An -tu4 -j"$offset" -N4 bad.elf)
      if [ "$address" -eq 536870912 ]; then
        printf '\000\000\000\060' | dd of=bad.elf bs=1 seek="$offset" conv=notrunc status=none
        found=true
        break
      fi
    done
    test "$found" = true
    expect_status 126 '' "$path" --binary="$scratch/bad.elf"
    expect_status 126 '' "$path" --backdoor_load --binary="$scratch/bad.elf"
    head -c 32 "$root/examples/$elf" >short.elf
    expect_status 126 '' "$path" --binary="$scratch/short.elf"
  fi
  echo "CORAL_RESULT bin/$sim $elf pass"
done

for path in "$root"/bin/*; do
  sim=${path##*/}
  case "$sim" in
    *highmem*|*512kb*) elf=host_io_tcm512k.elf ;;
    *) elf=host_io.elf ;;
  esac
  if [[ "$sim" = coralnpu_* ]]; then
    args=("$path" --semihost_htif --exit_on_ebreak "$root/examples/$elf")
  else
    args=("$path" --cycles=100000 --binary="$root/examples/$elf")
  fi
  expect_status 0 '' "${args[@]}"
  grep -q CORAL_STDOUT_ONLY stdout
  grep -q CORAL_STDERR_ONLY stderr
  ! grep -q CORAL_STDERR_ONLY stdout
  ! grep -q CORAL_STDOUT_ONLY stderr
  grep -q CORAL_HOST_IO_PASS stdout
  test "$(cat coral-host-io.tmp)" = ok
  if [[ "$sim" = coralnpu_* ]]; then
    test "$(cat stdout)" = $'CORAL_STDOUT_ONLY\nCORAL_HOST_IO_PASS'
  fi
  echo "CORAL_RESULT bin/$sim $elf pass"
done
