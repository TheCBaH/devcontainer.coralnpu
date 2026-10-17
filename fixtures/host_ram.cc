#include <stdint.h>
#include <unistd.h>

extern "C" {
extern volatile uint64_t tohost, tohost_ready, fromhost, fromhost_ready;
}

__attribute__((section(".host_ram"), aligned(64)))
volatile uint64_t packet[8] = {};
__attribute__((section(".host_ram"), aligned(16)))
char buffer[16] = "RAM_INITIALIZED";

long call(long number, long fd, uintptr_t address, long size) {
  packet[0] = number;
  packet[1] = fd;
  packet[2] = address;
  packet[3] = size;
  for (int i = 4; i < 8; ++i) packet[i] = 0;
  asm volatile("fence rw, w" ::: "memory");
  tohost = reinterpret_cast<uintptr_t>(packet);
  asm volatile("fence rw, w" ::: "memory");
  tohost_ready = 1;
  while (fromhost == 0 && fromhost_ready == 0) {}
  fromhost = 0;
  fromhost_ready = 0;
  asm volatile("fence r, rw" ::: "memory");
  return packet[0];
}

int main() {
  static const char initial[] = "RAM_INITIALIZED";
  for (unsigned i = 0; i < sizeof(buffer); ++i) {
    if (buffer[i] != initial[i]) return 1;
  }
  if (call(64, 1, reinterpret_cast<uintptr_t>(buffer), 15) != 15) return 2;
  if (call(63, 0, reinterpret_cast<uintptr_t>(buffer), 16) != 16) return 3;
  for (int i = 0; i < 16; ++i) {
    if (buffer[i] != "0123456789abcdef"[i]) return 4;
  }
  auto* last = reinterpret_cast<volatile uint32_t*>(0x203ffffc);
  *last = 0x44434241;
  if (call(64, 1, 0x203ffffc, 4) != 4) return 5;
  static const char marker[] = "\nCORAL_HOST_RAM_PASS\n";
  write(1, marker, sizeof(marker) - 1);
  return 0;
}
