#include <stdint.h>
#include <unistd.h>

extern "C" long htif_syscall_6args(long, long, long, long, long, long, long);
extern "C" volatile uint64_t tohost, tohost_ready;

extern "C" __attribute__((noreturn)) void host_exit(uint32_t status) {
  asm volatile("fence rw, w" ::: "memory");
  tohost = (static_cast<uint64_t>(status) << 1) | 1;
  asm volatile("fence rw, w" ::: "memory");
  tohost_ready = 1;
  while (true) asm volatile("nop");
}

__attribute__((naked, aligned(4))) void exit_trap() {
  asm volatile("li a0, 77\ntail host_exit");
}

int main() {
  char mode = 0;
  if (read(0, &mode, 1) != 1) return 99;
  switch (mode) {
    case '0': {
      static const char marker[] = "CORAL_EXIT_STATUS_PASS\n";
      write(1, marker, sizeof(marker) - 1);
      host_exit(0);
    }
    case '5': host_exit(5);
    case '7': host_exit(77);
    case 'x':
      htif_syscall_6args(93, 5, 0, 0, 0, 0, 0);
      break;
    case 'w': return write(1, reinterpret_cast<const void*>(0x30000004u), 4) == -1 ? 0 : 1;
    case 'r': return read(0, reinterpret_cast<void*>(0x30000004u), 1) == -1 ? 0 : 1;
    case 'o': return write(1, reinterpret_cast<const void*>(0xfffffffcu), 8) == -1 ? 0 : 1;
    case 'h': return htif_syscall_6args(64, 1, 0x10000, 0x7fffffff, 0, 0, 0) == -1 ? 0 : 1;
    case 't':
      asm volatile("csrw mtvec, %0\n.word 0xffffffff" : : "r"(exit_trap) : "memory");
      break;
    case 'b': asm volatile("ebreak"); break;
    case 'p': asm volatile(".word 0x08000073"); break;
    case 'l': while (true) asm volatile("nop");
    default: return 98;
  }
  while (true) asm volatile("nop");
}
