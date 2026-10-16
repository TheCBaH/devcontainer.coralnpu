// Loads a CoralNPUSimulator shared library, runs examples/library.elf and
// checks DDR, DTCM and mailbox results.
#include <dlfcn.h>

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>

#include "hw_sim/coralnpu_simulator.h"
#include "tests/verilator_sim/elf.h"

namespace {

constexpr uint32_t kDdrLow = 0x80000000u;
constexpr uint32_t kDdrHigh = 0xbfffff00u;

int Fail(const char* message) {
  std::printf("CORAL_LIBRARY_FAIL %s\n", message);
  return 1;
}

uint32_t ReadWord(CoralNPUSimulator* simulator, uint32_t address) {
  uint32_t value = 0;
  simulator->ReadMem(address, sizeof(value), reinterpret_cast<char*>(&value));
  return value;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s lib/libcoralnpu_simulator*.so examples/library.elf\n", argv[0]);
    return 2;
  }
  void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!library) return Fail(dlerror());
  auto create = reinterpret_cast<CoralNPUSimulator* (*)()>(dlsym(library, "coralnpu_simulator_verilator_create"));
  if (!create) return Fail("coralnpu_simulator_verilator_create not found");
  std::ifstream file(argv[2], std::ios::binary);
  std::vector<uint8_t> elf((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
  if (elf.size() < 4) return Fail("cannot read ELF");

  CoralNPUSimulator* simulator = create();
  const uint32_t entry = LoadElf(elf.data(), [simulator](void* dest, const void* src, size_t count) {
    simulator->WriteMem(static_cast<uint32_t>(reinterpret_cast<uintptr_t>(dest)), count,
                        static_cast<const char*>(src));
    return dest;
  });
  uint64_t result_address = 0;
  if (!LookupSymbol(elf.data(), "dtcm_result", &result_address)) return Fail("dtcm_result not found");

  const uint32_t low[4] = {1, 2, 3, 4};
  const uint32_t high[4] = {10, 20, 30, 40};
  simulator->WriteMem(kDdrLow, sizeof(low), reinterpret_cast<const char*>(low));
  simulator->WriteMem(kDdrHigh, sizeof(high), reinterpret_cast<const char*>(high));
  simulator->Run(entry);
  if (!simulator->WaitForTermination(1000000)) return Fail("timeout");
  CoralNPUCoreState state;
  if (simulator->ReadCoreState(&state) && state.fault) return Fail("core fault");

  const CoralNPUMailbox& mailbox = simulator->ReadMailbox();
  if (mailbox.message[0] != 0xc0da11b0u || mailbox.message[1] != 10 || mailbox.message[2] != 100 ||
      mailbox.message[3] != (0xau ^ 0x64u))
    return Fail("mailbox");
  if (ReadWord(simulator, kDdrLow + 16) != 10 || ReadWord(simulator, kDdrHigh + 16) != 100) return Fail("ddr");
  if (ReadWord(simulator, static_cast<uint32_t>(result_address)) != (0xau ^ 0x64u)) return Fail("dtcm");
  std::printf("CORAL_LIBRARY_PASS cycles=%llu\n", static_cast<unsigned long long>(simulator->GetCycleCount()));
  delete simulator;
  return 0;
}
