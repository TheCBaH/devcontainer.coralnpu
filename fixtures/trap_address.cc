#include <stdint.h>
#include <unistd.h>

extern "C" {
volatile uint32_t trap_values[3];

__attribute__((naked, aligned(4))) void capture_trap() {
  asm volatile(
      "addi sp, sp, -16\n"
      "sw t0, 0(sp)\n"
      "sw t1, 4(sp)\n"
      "la t0, trap_values\n"
      "csrr t1, mcause\n"
      "sw t1, 0(t0)\n"
      "csrr t1, mepc\n"
      "sw t1, 4(t0)\n"
      "csrr t1, mtval\n"
      "sw t1, 8(t0)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "lw t0, 0(sp)\n"
      "lw t1, 4(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}
}

int main() {
  asm volatile("csrw mtvec, %0" : : "r"(capture_trap));
  const uint32_t addresses[] = {0x100u, 0x104u, 0x1238u};
  for (uint32_t addr : addresses) {
    trap_values[0] = 0;
    asm volatile("sw zero, 0(%0)" : : "r"(addr) : "memory");
    if (trap_values[0] != 7 || trap_values[2] != addr) return 1;
  }
  asm volatile("lw zero, 0(%0)" : : "r"(0x30000004u) : "memory");
  if (trap_values[0] != 5 || trap_values[2] != 0x30000004u) return 2;
  static const char message[] = "CORAL_TRAP_ADDRESS_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
