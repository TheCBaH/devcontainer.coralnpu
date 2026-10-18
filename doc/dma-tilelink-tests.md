# DMA and TileLink tests

The pinned source has two independent DMA engines. The RGB/plane engine is
`hdl/chisel/src/dma/DmaCore.scala`: independent fill and drain engines,
a transpose buffer and a TL-UL arbiter. The integrated peripheral is
`hdl/chisel/src/bus/DmaEngine.scala`: a descriptor-driven copy engine with
chaining, fixed addresses, polling and abort. Their register maps differ.
The subsystem instantiates `bus.DmaEngine`, not `dma.DmaCore`.

## Run the tests

In the x86_64 development container or a Codespace:

```sh
make dma-tests
make dma-tests DMA_TEST_GROUPS=core
make dma-tests DMA_TEST_GROUPS='tilelink subsystem engine'
```

The default runs 52 cocotb cases plus the Scala descriptor-engine test.
`scripts/dma-tests.sh` selects Verilator targets explicitly; no commercial
simulator is needed. Bazel builds and caches the required models. Randomized
cocotb tests use seed 42. The `DMA and TileLink` job in the `build`
workflow runs the same command and uploads test logs and JUnit XML;
local results are under `.cache/source/bazel-testlogs/`.
Wrapper patch 0024 adds data assertions to the DDR access and burst tests;
upstream's burst case otherwise only logs mismatches.

| Group | Source/suite in `tests/cocotb/` | Cases | Coverage |
| --- | --- | ---: | --- |
| `core` | `dma/test_dma_core.py`, `dma_core_cocotb_test` | 15 | Copy, single/multiple chunks, partial tails, back-to-back transfers, alignment/configuration errors, sticky-error gating, source preservation, strided de-interleave and randomized traffic |
| `core` | `dma/test_transpose_buffer.py`, `transpose_buffer_cocotb_test` | 3 | Random element types/strides, input reordering, output backpressure and memcopy |
| `tilelink` | `tlul/tlul2axi_cocotb_test.py`, `tlul2axi_cocotb_test` | 4 | Get, Put, backpressure and write/read sequences |
| `tilelink` | `tlul/axi2tlul_cocotb_test.py`, `axi2tlul_cocotb_test` | 5 | Reads, writes, bursts and read errors |
| `tilelink` | `tlul/test_tlul_to_sram.py`, `tlul_to_sram_cocotb_test` | 5 | Random backpressure, read/write, byte masks and pipelining |
| `tilelink` | `tlul/test_tlul_local_xbar.py`, `tlul_local_xbar_cocotb_test` | 3 | Concurrent banks, arbitration and random backpressure |
| `tilelink` | `tlul/coralnpu_xbar_test.py`, `coralnpu_xbar_cocotb` | 11 | Routing, invalid addresses, host/device paths, width conversion/integrity, halfword masks, interleaved hosts and pipelined requests sharing a source ID |
| `subsystem` | `tlul/test_dma_integration.py`, `dma_integration_cocotb` | 3 | Descriptor-engine CSR access, SRAM copy and descriptor chaining through the SoC interconnect |
| `subsystem` | Selected `tlul/test_subsystem.py` cases | 3 | DDR access, CPU DDR burst pattern and a width-bridge regression |
| `engine` | `hdl/chisel/src/bus/DmaEngineTest.scala` | 1 Scala test | CSR access/errors, memory copy, descriptor chaining, fixed destination and abort |

The selected subsystem case names are `test_ddr_access`,
`test_ddr_burst_pattern_repro` and
`test_tlul_width_bridge_bug_reproduction` under
`//tests/cocotb/tlul:coralnpu_chisel_subsystem_cocotb_<case>`.

## Verilator builds

These are upstream Bazel models, independent of the standalone ELF runners:

| Test hardware | Build target |
| --- | --- |
| 128-bit TL-UL RGB/de-interleave DMA | `//hdl/chisel/src/dma:dma_core_model` |
| Transpose buffer | `//hdl/chisel/src/dma:transpose_buffer_model` |
| TL-UL to AXI | `//hdl/chisel/src/bus:tlul2axi_model` |
| AXI to TL-UL | `//hdl/chisel/src/bus:axi2tlul_model` |
| TL-UL SRAM adapter | `//hdl/chisel/src/bus:tlul_to_sram_model` |
| Local bank crossbar | `//hdl/chisel/src/bus:tlul_local_xbar_model` |
| SoC crossbar harness | `//hdl/chisel/src/soc:coralnpu_xbar_testharness_model` |
| Subsystem with exposed DDR AXI ports | `//hdl/chisel/src/soc:coralnpu_chisel_subsystem_testharness_model` |

From `.cache/source`, use `bazel build -c opt <target>` to build a model,
or `bazel test -c opt //tests/cocotb/dma:dma_core_cocotb_test` to run all
15 DMA cases. The test rule supplies cocotb, NumPy, the Python runtime and
the VPI library. A raw model executable needs those dependencies and its
Python testbench; it does not accept the standalone simulators' ELF CLI.
Once built, changing Python test inputs reuses the model. Changing bus
widths, hardware parameters or SoC integration requires elaborating and
compiling a new model.

Additional upstream Verilator suites are available under
`//tests/cocotb/tlul:<suite>`. They are outside the default `make dma-tests`
selection:

| Suite | Cases | Coverage |
| --- | ---: | --- |
| `tlul_fifo_async_128_cocotb_test` | 1 | Asynchronous clock crossing |
| `tlul_fifo_sync_cocotb_test` | 1 | Synchronous FIFO and spare signals |
| `tlul_socket_1n_128_cocotb_test` | 3 | Device steering/locking, errors and backpressure |
| `tlul_socket_m1_2_128_cocotb_test` | 3 | Host arbitration/ordering and directed/random backpressure |
| `tlul_integrity_cocotb_test` | 4 | Request/response integrity generation and checking |
| `secded_encoder_cocotb_test`, `secded_encoder_32_cocotb_test`, `secded_encoder_57_cocotb_test` | 1 each | SECDED reference comparisons at three widths |
| `banked_dtcm_cocotb_test` | 4 | Read/write, bank isolation, concurrency and bounds |
| `axi_addr_gen_cocotb_test` | 1 | AXI address generation |

`//hdl/chisel/src/bus:tlul_to_sram_test` also exercises the SRAM adapter
through ChiselSim. Other subsystem cases cover SPI, interrupts, boot/fetch
paths and GPIO; `test_ddr_access_via_spi` provides a separate SPI-to-DDR path.

## External memory and prebuilt compatibility

`DmaCore` unit tests serve a sparse byte-addressed memory over its TL-UL
host port. Source starts at `0x80000000`, destination at `0x20000000`.
Randomized runs use 4–40-cycle responses, out-of-order completion and
70% request readiness. They check de-interleave results and destination
tail guards. This exercises external-memory transactions without a CPU,
a SoC address decoder or a physical DRAM controller. The existing error
cases concern configuration/alignment; they do not inject TL bus errors.

The subsystem DMA integration cases use SRAM at `0x20000000` and the
descriptor peripheral at `0x40050000`. The separate DDR cases drive
the subsystem's actual TL-UL/AXI bridge path with Python AXI responders at
`0x70000000` (control) and `0x80000000` (memory). These are functional
memory models, not DRAM timing tests. They do not combine DMA, DDR and
matrix computation into one test.

The existing prebuilt standalone core executables contain no DMA. The
prebuilt `chip_verilator` variants contain the descriptor engine, so the
bundled `subsystem_dma.elf` can run without rebuilding, but their DDR clock
and response inputs are tied off in `fpga/rtl/chip_verilator.sv`.
They cannot run the new DMA/transpose unit tests or DDR-path cocotb tests.
The shared-library DDR backing store also has no DMA peripheral.

Use the dedicated upstream cocotb builds for this coverage. Making a
downloadable test bundle would additionally require packaging these VPI
models and their Python runtime/dependencies; the current archives do not
include them. An end-to-end DDR-to-DMA-to-matrix test would require a new
integrated harness: either connect DDR responses to the descriptor-engine
subsystem, or integrate `dma.DmaCore` explicitly for de-interleave.
