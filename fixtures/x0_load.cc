#include <stdint.h>
#include <unistd.h>

extern "C" {
volatile uint32_t x0_trap[4];

__attribute__((naked, aligned(4))) void x0_trap_handler() {
  asm volatile(
      "addi sp, sp, -16\n"
      "sw t0, 0(sp)\n"
      "sw t1, 4(sp)\n"
      "la t0, x0_trap\n"
      "csrr t1, mcause\n"
      "sw t1, 0(t0)\n"
      "csrr t1, mepc\n"
      "sw t1, 4(t0)\n"
      "csrr t1, mtval\n"
      "sw t1, 8(t0)\n"
      "lw t1, 12(t0)\n"
      "addi t1, t1, 1\n"
      "sw t1, 12(t0)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "lw t0, 0(sp)\n"
      "lw t1, 4(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}

#define X0_LOAD(name, op) \
  __attribute__((naked, noinline, aligned(4))) void name(uint32_t) { \
    asm volatile(op " zero, 0(a0)\nret\n"); \
  }
X0_LOAD(x0_lb, "lb")
X0_LOAD(x0_lbu, "lbu")
X0_LOAD(x0_lh, "lh")
X0_LOAD(x0_lhu, "lhu")
X0_LOAD(x0_lw, "lw")
}

static int fail(int code) {
  char message[] = "CORAL_X0_LOAD_FAIL code=0\n";
  message[sizeof(message) - 3] += code;
  write(1, message, sizeof(message) - 1);
  for (uint32_t value : x0_trap) {
    char hex[9];
    for (int i = 0; i < 8; ++i) {
      hex[i] = "0123456789abcdef"[(value >> (28 - 4 * i)) & 15];
    }
    hex[8] = '\n';
    write(1, hex, sizeof(hex));
  }
  return code;
}

int main() {
  asm volatile("csrw mtvec, %0" : : "r"(x0_trap_handler));
  alignas(16) volatile uint32_t data[8] = {0x87654321u};
  const uint32_t dtcm = reinterpret_cast<uint32_t>(data);
  volatile uint32_t *external = reinterpret_cast<volatile uint32_t *>(0x20000000u);
  *external = 0x12345678u;
  using Load = void (*)(uint32_t);
  const Load loads[] = {x0_lb, x0_lbu, x0_lh, x0_lhu, x0_lw};
  uint32_t faults = 0;
  for (Load load : loads) {
    for (uint32_t offset = 0; offset < 16; ++offset) {
      load(dtcm + offset);
      load(0x20000000u + offset);
      load(reinterpret_cast<uint32_t>(x0_lw));
    }
    if (x0_trap[3] != faults) return fail(1);
    for (uint32_t offset = 0; offset < 4; ++offset) {
      const uint32_t address = 0x30000004u + 4 * offset;
      load(address);
      ++faults;
      if (x0_trap[0] != 5 || x0_trap[1] != reinterpret_cast<uint32_t>(load) ||
          x0_trap[2] != address || x0_trap[3] != faults) return fail(2);
      load(dtcm);
      if (x0_trap[3] != faults) return fail(3);
    }
  }
  uint32_t zero;
  asm volatile("addi %0, zero, 0" : "=r"(zero));
  if (zero != 0 || data[0] != 0x87654321u || *external != 0x12345678u) return fail(4);
  static const char message[] = "CORAL_X0_LOAD_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
