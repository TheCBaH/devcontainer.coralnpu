#include <stdint.h>
#include <unistd.h>

extern "C" long htif_syscall_6args(long, long, long, long, long, long, long);

int main() {
  char mode = 0;
  if (read(0, &mode, 1) != 1) return 99;
  switch (mode) {
    case '0': {
      static const char marker[] = "CORAL_EXIT_STATUS_PASS\n";
      write(1, marker, sizeof(marker) - 1);
      return 0;
    }
    case '5': return 5;
    case '7': return 77;
    case 'x':
      htif_syscall_6args(93, 5, 0, 0, 0, 0, 0);
      break;
    case 'b': asm volatile("ebreak"); break;
    case 'p': asm volatile(".word 0x08000073"); break;
    case 'l': while (true) asm volatile("nop");
    default: return 98;
  }
  while (true) asm volatile("nop");
}
