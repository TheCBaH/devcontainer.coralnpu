#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'find "$scratch" -delete' EXIT
cd "$scratch"
trap 'status=$?; echo "MPACT limit check failed at line $LINENO" >&2; cat stdout stderr >&2; exit "$status"' ERR

expect() {
  local expected=$1 reason=$2 count=$3 status
  shift 3
  if timeout --preserve-status --kill-after=2 20 "$@" </dev/null >stdout 2>stderr; then
    status=0
  else
    status=$?
  fi
  if [ "$status" -ne "$expected" ] ||
     ! grep -q "Stop reason: $reason; instructions=$count;" stderr; then
    cat stdout stderr
    echo "Expected status=$expected reason=$reason instructions=$count: $*" >&2
    exit 1
  fi
  test ! -s stdout
}

for sim in coralnpu_v2_sim coralnpu_m3_sim coralnpu_m4_sim; do
  args=("$root/bin/$sim" --semihost_htif --exit_on_ebreak "$root/examples/batch_limits.elf")
  for limit in 1 65535 65536 65537 131073; do
    expect 124 instruction_limit "$limit" "${args[@]}" --entry_point=0x1000 --max_instructions="$limit"
    grep -q 'pc=0x00001000' stderr
  done
  for spec in '0x1004 mpause 0 2' '0x100c ebreak 125 2' \
              '0x1040 guest_exit 0 10' '0x1080 guest_exit 77 10' \
              '0x10c0 guest_exit 124 10'; do
    read -r entry reason status boundary <<<"$spec"
    expect 124 instruction_limit "$((boundary-1))" "${args[@]}" \
      --entry_point="$entry" --max_instructions="$((boundary-1))"
    for limit in "$boundary" "$((boundary+1))" 4294967297 18446744073709551615 0; do
      expect "$status" "$reason" "$boundary" "${args[@]}" \
        --entry_point="$entry" --max_instructions="$limit"
    done
    expect "$status" "$reason" "$boundary" "${args[@]}" --entry_point="$entry"
  done
  for entry in 0x1100 0x1140; do
    expect 124 instruction_limit 65537 "${args[@]}" --entry_point="$entry" --max_instructions=65537
    if [ "$entry" = 0x1100 ]; then grep -q 'pc=0x00001110' stderr; fi
  done
  grep -q 'pc=0x00001148' stderr
  for invalid in -1 18446744073709551616 invalid; do
    if timeout 10 "${args[@]}" --max_instructions="$invalid" >stdout 2>stderr; then
      echo "Accepted invalid budget $invalid" >&2
      exit 1
    fi
    ! grep -q 'Starting simulation' stderr
    grep -q 'max_instructions' stderr
  done
  for flag in --interactive -i; do
    if timeout 10 "${args[@]}" "$flag" --max_instructions=1 >stdout 2>stderr; then
      echo "Accepted interactive budget" >&2
      exit 1
    fi
    grep -q 'requires batch mode' stderr
  done

  # An outer supervisor prevents a cancellation regression from hanging CI.
  timeout --kill-after=2 10 bash -c '
    "$@" </dev/null >stdout 2>stderr &
    child=$!
    for ((i=0; i<500; i++)); do
      if grep -q "Starting simulation" stderr; then break; fi
      sleep 0.01
    done
    kill -INT "$child"
    if wait "$child"; then status=0; else status=$?; fi
    cat stderr
    test "$status" -eq 130 || exit 1
    grep -q "Stop reason: interrupted;" stderr
  ' bash "${args[@]}" --entry_point=0x1000 --max_instructions=18446744073709551615

  # Keep a pipe writer open without supplying data: HTIF read must block.
  mkfifo input
  exec 3<>input
  if timeout --kill-after=2 1 "$root/bin/$sim" --semihost_htif \
       --max_instructions=1000000 "$root/examples/exit_status.elf" \
       <input >stdout 2>stderr; then
    status=0
  else
    status=$?
  fi
  exec 3>&-
  rm input
  test "$status" -eq 124
  grep -q 'Starting simulation' stderr
  ! grep -q 'Stop reason:' stderr
  echo "CORAL_MPACT_LIMITS_PASS $sim"
  echo "CORAL_RESULT bin/$sim batch_limits.elf pass"
done
