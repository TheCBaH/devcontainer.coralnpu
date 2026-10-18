# MPACT batch execution limits

Implementation and native validation: 2026-10-17. All three MPACT
binaries now accept `--max_instructions=N`. This addresses the confirmed,
high-priority batch automation gap in ranking entry 13. That rank measures
confidence rather than severity. The default remains unlimited for existing
callers; unattended jobs should pass a positive budget and retain a process
timeout for blocked host I/O.

```sh
timeout --signal=TERM --kill-after=5s 60s \
  bin/coralnpu_v2_sim --semihost_htif --exit_on_ebreak \
  --max_instructions=100000000 examples/external_payload.elf
```

The flag works identically in `coralnpu_v2_sim`, `coralnpu_m3_sim` and
`coralnpu_m4_sim`. It counts simulator instruction steps, including trap
instructions and handler execution. A vector or matrix instruction counts
as one step despite its greater host cost. This is not an RTL cycle budget
or a claim about architecturally successful retirement.

## Behavior

| Condition | Result |
| --- | --- |
| Flag absent or `N=0` | Unlimited batch execution. |
| Positive budget exhausted without guest halt | Stop reason `instruction_limit`, status 124. |
| Guest HTIF exit at or before the boundary | Stop reason `guest_exit`, normalized low-eight-bit guest status. |
| Normal mpause | Stop reason `mpause`, status 0. |
| Configured ebreak stop | Stop reason `ebreak`, status 125. |
| Other abnormal halt | Stop reason `halted`, status 125. |
| Loader, stepping or execution API error | Status 126 with an error diagnostic. |
| Batch SIGINT / Ctrl-C | Stop reason `interrupted`, status 130. |
| Negative, overflowing or malformed budget | Flag parsing rejects it before execution. |
| Interactive mode with a nonzero budget | Reject before loading or execution. |

Stderr reports `Stop reason`, executed instructions, configured budget and
final PC. Guest stdout remains program output. A guest halt on the final
permitted instruction takes precedence over exhaustion or a pending signal.
A second step call never resumes a completed guest. Status 124 can also be a
guest exit code; use the stop diagnostic to distinguish those outcomes.
There is no JSON result format in this change.

## Implementation

The examined dependency revisions are Coral MPACT `7670ee4c`, mpact-riscv
`e4f1e9c` and mpact-sim `9c43949f`, together with this wrapper's patches.
The original three drivers called `Run()` and `Wait()` without a budget.
They use **RiscVTop**, rather than the separate CoralNPUTop engine.

The shared `CoralNPUSimulator::RunBatch()` method uses synchronous `Step()`
calls in chunks of at most 65,536 instructions, with a `uint64_t` total.
It uses a smaller final chunk to avoid overshooting the requested budget.
Accounting uses the actual step return value, independently of guest CSRs
and optional statistics, and rejects invalid counts or overflow. Because
chunks fit in `int`, budgets larger than INT_MAX do not narrow into the
upstream step argument. Explicit results carry the stop reason, exit status,
executed steps and final PC.

All batch jobs, including unlimited jobs, use this path. No detached run
thread or watchdog thread is added. The batch SIGINT handler only writes a
`volatile sig_atomic_t` flag, which the helper observes between chunks.
Interactive execution retains the existing debugger path and its existing
halt handler. Budgeted debug action points are outside this contract: the
upstream step-over path can execute extra instructions, so future support
requires enforcement inside the engine or an audit of that path.

The wrapper maintains the change in
[execution-limits.patch](../mpact-patches/execution-limits.patch), registered
by [0018](../patches/0018-mpact-execution-limits.patch). The original
[host-contract patch](../mpact-patches/host-contract.patch) still provides
HTIF status propagation. No upstream dependency revision was advanced.
The manifest records the option, default and termination behavior. Packaged
smoke/host-contract scripts pass a finite budget; the examples and launch
recipes use 100,000,000 steps. Workloads can choose a larger budget.

## Why the process deadline remains necessary

[HTIF semihosting](https://github.com/google/mpact-riscv/blob/e4f1e9c1b243954ff8388fd39019248b2ae7341a/riscv/riscv32_htif_semihost.cc#L160)
performs host `read`, `write` and `openat` calls synchronously. Waiting for
stdin, opening a FIFO, or writing to a full pipe can block inside a single
instruction. Neither the next budget check nor cooperative cancellation can
run until the operation returns. A simulator bug can have the same effect.
WFI itself is a no-op unless a callback is installed in this pinned engine;
it is not an established blocking case for these drivers.

A thread that sleeps then calls `Halt()` would not provide a hard deadline.
The pinned [control fields](https://github.com/google/mpact-riscv/blob/e4f1e9c1b243954ff8388fd39019248b2ae7341a/riscv/riscv_top.h#L183)
are non-atomic, `Halt()` rejects single-step mode, and `Wait()` has no timeout.
An instruction-counter listener is also not an exact drop-in limit: the
[current loop](https://github.com/google/mpact-riscv/blob/e4f1e9c1b243954ff8388fd39019248b2ae7341a/riscv/riscv_top.cc#L292)
snapshots its halt flag before incrementing the instruction counter, so a
listener's halt can allow another instruction. Statistics can be disabled.

The external supervisor must cover loading as well as guest execution and
escalate to termination after a grace period. In the example above, ordinary
`timeout` expiration returns 124; forced KILL can return 137. Those numeric
statuses can collide with guest exits. The packaged host-contract wrapper
uses `--preserve-status`, which has different timeout status semantics.
A future built-in hard timeout should supervise a child process. Library
embeddings need equivalent isolation for that stronger guarantee.

## Regression coverage

[mpact-limits.sh](../scripts/mpact-limits.sh) ships beside `smoke.sh` and uses
the [batch_limits fixture](../fixtures/batch_limits.cc). Fixed entry points bypass
CRT startup for exact instruction counts. An outer wall-clock timeout guards
every potentially looping check. The suite covers each MPACT binary:

- Loop budgets 1, 65,535, 65,536, 65,537 and 131,073, checking the final PC.
- mpause/ebreak and guest exits 0/77/124, with the budget one instruction
  below, exactly at, and above the halt boundary; explicit zero and absent
  budgets; 64-bit budget values through UINT64_MAX.
- A trap loop with a handler-PC check, and a loop repeatedly writing
  minstret/minstreth, both exhausting their independent host budgets.
- Invalid arguments, interactive conflicts and SIGINT during a looping job.
- HTIF input blocked on a live pipe, terminated by the external supervisor.

The 64-bit cases verify argument acceptance and early halt preservation;
these tests do not execute billions of steps. Existing status 0/5/77,
stdout/stderr, file-I/O, vector/matrix and large external-payload regressions
also run with finite budgets.

[Actions run 39053331060](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39053331060)
passed all nine jobs for executable/fixture revision `0f61faa`. Each of V2,
M3 and M4 passed the complete budget suite on native x86_64 and ARM64 in
Ubuntu 24.04 and Debian 13. The existing emulator, library and subsystem
regressions and cross-host manifest comparison also passed. The 1 MiB
external-payload case passed with the finite MPACT budget.

Verified emulator bundles, including `examples/batch_limits.elf` and
`mpact-limits.sh`:
[x86_64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39053331060/artifacts/12109800058),
[ARM64](https://github.com/TheCBaH/devcontainer.coralnpu/actions/runs/39053331060/artifacts/12110790152).
These artifacts contain the new flag at `0f61faa`; this follow-up did not
create a release tag. Later changes to the reports are documentation only.
