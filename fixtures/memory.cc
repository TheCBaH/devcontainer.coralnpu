#include <stdint.h>
#include <unistd.h>

#define STRINGIFY(x) #x
#define EXPAND(x) STRINGIFY(x)

// Padding places far_add near the top of ITCM, past the default 8 KiB.
asm(".section .text.far, \"ax\", @progbits\n"
    ".p2align 4\n"
    ".skip " EXPAND(CORAL_FAR_CODE_OFFSET) "\n"
    ".globl far_add\n"
    "far_add:\n"
    "  add a0, a0, a1\n"
    "  ret\n"
    ".text\n");
extern "C" uint32_t far_add(uint32_t, uint32_t);

constexpr uint32_t kWords = CORAL_DATA_BYTES / 4;
constexpr uint32_t kStride = 16;
__attribute__((section(".noinit"))) volatile uint32_t dtcm_buffer[kWords];
__attribute__((section(".extbss"))) volatile uint32_t ext_buffer[kWords];

static uint32_t pattern(uint32_t i) { return 0x9e3779b9u * (i + 1); }

static int fail(const char* message, size_t length) {
  write(1, message, length);
  return 1;
}
#define FAIL(text) fail(text "\n", sizeof(text))

int main() {
  const uint32_t code = reinterpret_cast<uintptr_t>(&far_add);
  const uint32_t top = reinterpret_cast<uintptr_t>(&dtcm_buffer[kWords - 1]);
  const uint32_t ext = reinterpret_cast<uintptr_t>(&ext_buffer[0]);
  if (code < CORAL_MIN_CODE_ADDRESS) return FAIL("CORAL_MEMORY_ITCM_FAIL");
  if (top < CORAL_MIN_DATA_ADDRESS) return FAIL("CORAL_MEMORY_DTCM_FAIL");
  if (ext < 0x20000000u || ext + CORAL_DATA_BYTES > 0x20400000u) return FAIL("CORAL_MEMORY_EXT_FAIL");
  if (far_add(40, 2) != 42) return FAIL("CORAL_MEMORY_FETCH_FAIL");
  for (uint32_t i = 0; i < kWords; i += kStride) dtcm_buffer[i] = pattern(i);
  dtcm_buffer[kWords - 1] = pattern(kWords - 1);
  for (uint32_t i = 0; i < kWords; i += kStride) ext_buffer[i] = dtcm_buffer[i];
  ext_buffer[kWords - 1] = dtcm_buffer[kWords - 1];
  for (uint32_t i = 0; i < kWords; i += kStride) dtcm_buffer[i] = 0;
  dtcm_buffer[kWords - 1] = 0;
  for (uint32_t i = 0; i < kWords; i += kStride) dtcm_buffer[i] = ext_buffer[i];
  dtcm_buffer[kWords - 1] = ext_buffer[kWords - 1];
  for (uint32_t i = 0; i < kWords; i += kStride)
    if (dtcm_buffer[i] != pattern(i)) return FAIL("CORAL_MEMORY_COPY_FAIL");
  if (dtcm_buffer[kWords - 1] != pattern(kWords - 1)) return FAIL("CORAL_MEMORY_COPY_FAIL");
  static const char message[] = "CORAL_MEMORY_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
