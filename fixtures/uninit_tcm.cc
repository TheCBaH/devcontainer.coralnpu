#include <stdint.h>
#include <unistd.h>

// No PT_LOAD covers .noinit and the startup code leaves it alone, so this
// prints the simulator's initial DTCM contents.
__attribute__((section(".noinit"))) volatile uint32_t uninit[4];

int main() {
  char line[] = "CORAL_UNINIT_TCM_PASS 00000000000000000000000000000000\n";
  char *hex = line + sizeof("CORAL_UNINIT_TCM_PASS");
  for (uint32_t value : uninit) {
    for (int i = 0; i < 8; ++i) {
      *hex++ = "0123456789abcdef"[(value >> (28 - 4 * i)) & 15];
    }
  }
  write(1, line, sizeof(line) - 1);
  return 0;
}
