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
    case 'w': return write(1, reinterpret_cast<const void*>(0x30000004u), 4) == -1 ? 0 : 1;
    case 'r': return read(0, reinterpret_cast<void*>(0x30000004u), 1) == -1 ? 0 : 1;
    case 'o': return write(1, reinterpret_cast<const void*>(0xfffffffcu), 8) == -1 ? 0 : 1;
    case 'h': return htif_syscall_6args(64, 1, 0x10000, 0x7fffffff, 0, 0, 0) == -1 ? 0 : 1;
    case 'b': asm volatile("ebreak"); break;
    case 'p': asm volatile(".word 0x08000073"); break;
    case 'l': while (true) asm volatile("nop");
    default: return 98;
  }
  while (true) asm volatile("nop");
}
