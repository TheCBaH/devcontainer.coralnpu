#include <fcntl.h>
#include <stdint.h>
#include <unistd.h>

#ifndef CORAL_DDR_BYTES
#error "CORAL_DDR_BYTES must be the size of the simulated DDR"
#endif

constexpr uintptr_t kDdrBase = 0x80000000u;
constexpr uintptr_t kDdrTop = kDdrBase + CORAL_DDR_BYTES;
constexpr uint32_t kFileBytes = 4096;

extern "C" {
extern volatile uint64_t tohost, tohost_ready, fromhost, fromhost_ready;
}

// Everything the host reads or writes lives in DDR: the HTIF packet, buffers and the file name.
__attribute__((section(".ddr_data.htif"), aligned(64))) volatile uint64_t packet[8] = {};
__attribute__((section(".ddr_data.htif"), aligned(16))) char text[] = "DDR_INITIALIZED";
__attribute__((section(".ddr_data.htif"), aligned(16))) char name[] = "coral-ddr-io.tmp";
alignas(16) volatile char input[16] __attribute__((section(".ddr_bss.htif")));
alignas(16) volatile uint8_t file_out[kFileBytes] __attribute__((section(".ddr_bss.htif")));
alignas(16) volatile uint8_t file_in[kFileBytes] __attribute__((section(".ddr_bss.htif")));

long call(long number, long fd, uint64_t address, uint64_t size) {
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

static int fail(int step) {
  char message[] = "\nCORAL_DDR_HTIF_FAIL 00\n";
  message[sizeof(message) - 4] = '0' + step / 10;
  message[sizeof(message) - 3] = '0' + step % 10;
  write(1, message, sizeof(message) - 1);
  return 1;
}

int main() {
  if (reinterpret_cast<uintptr_t>(packet) < kDdrBase || reinterpret_cast<uintptr_t>(file_in) + kFileBytes > kDdrTop)
    return fail(1);

  // Output from, and input into, DDR buffers; the last word of DDR as an output buffer.
  if (call(64, 1, reinterpret_cast<uintptr_t>(text), 15) != 15) return fail(2);
  if (call(63, 0, reinterpret_cast<uintptr_t>(input), 16) != 16) return fail(3);
  for (int i = 0; i < 16; ++i)
    if (input[i] != "0123456789abcdef"[i]) return fail(4);
  *reinterpret_cast<volatile uint32_t*>(kDdrTop - 4) = 0x44434241;
  if (call(64, 1, kDdrTop - 4, 4) != 4) return fail(5);

  // File operations with the name and the buffers in DDR.
  for (uint32_t i = 0; i < kFileBytes; ++i) file_out[i] = (i * 7) ^ (i >> 5);
  int fd = open(name, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0 || write(fd, const_cast<const uint8_t*>(file_out), kFileBytes) != kFileBytes || close(fd) != 0)
    return fail(6);
  fd = open(name, O_RDONLY);
  if (fd < 0 || read(fd, const_cast<uint8_t*>(file_in), kFileBytes) != kFileBytes) return fail(7);
  for (uint32_t i = 0; i < kFileBytes; ++i)
    if (file_in[i] != file_out[i]) return fail(8);
  if (lseek(fd, 100, SEEK_SET) != 100 || read(fd, const_cast<uint8_t*>(file_in), 16) != 16) return fail(9);
  for (uint32_t i = 0; i < 16; ++i)
    if (file_in[i] != file_out[100 + i]) return fail(10);
  if (close(fd) != 0) return fail(11);

  // A trailing 'B' on stdin asks for the bounds checks: buffers that cross the end of DDR, wrap around
  // the address space, or start outside DDR are refused. Only the RTL testbench validates buffer ranges.
  char mode = 0;
  const bool bounds = read(0, &mode, 1) == 1 && mode == 'B';
  if (bounds) {
    if (call(64, 1, kDdrTop - 16, 32) != -1) return fail(12);
    if (call(63, 0, kDdrTop - 16, 32) != -1) return fail(13);
    if (call(64, 1, 0xfffffffffffffff0ull, 32) != -1) return fail(14);
    if (call(64, 1, kDdrTop, 4) != -1) return fail(15);
    if (call(64, 1, kDdrBase - 1, 2) != -1) return fail(16);
  }

  static const char marker[] = "\nCORAL_DDR_HTIF_PASS bounds=";
  write(1, marker, sizeof(marker) - 1);
  write(1, bounds ? "1\n" : "0\n", 2);
  return 0;
}
