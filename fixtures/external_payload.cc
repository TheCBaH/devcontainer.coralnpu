#include <stdint.h>
#include <unistd.h>

constexpr uint32_t kPayloadWords = 1024 * 1024 / sizeof(uint32_t);
constexpr uint32_t kTileWords = 64;

extern "C" const volatile uint32_t external_payload[kPayloadWords];

// Emit initialized ELF bytes directly in external memory, without a TCM copy.
asm(".pushsection .extdata.payload, \"a\", @progbits\n"
    ".balign 16\n"
    ".globl external_payload\n"
    ".type external_payload, @object\n"
    "external_payload:\n"
    ".set .Lpayload_word, 0\n"
    ".rept 262144\n"
    ".long ((.Lpayload_word * 0x9e3779b9) ^ 0xa5a55a5a) & 0xffffffff\n"
    ".set .Lpayload_word, .Lpayload_word + 1\n"
    ".endr\n"
    ".size external_payload, . - external_payload\n"
    ".popsection\n");

int main() {
  if (reinterpret_cast<uintptr_t>(external_payload) != 0x20000000u) return 1;
  uint32_t tile[kTileWords];
  uint32_t checksum = 0;
  for (uint32_t base = 0; base < kPayloadWords; base += kTileWords) {
    for (uint32_t i = 0; i < kTileWords; ++i) tile[i] = external_payload[base + i];
    for (uint32_t i = 0; i < kTileWords; ++i) {
      if (tile[i] != (((base + i) * 0x9e3779b9u) ^ 0xa5a55a5au)) {
        static const char failure[] = "CORAL_EXTERNAL_PAYLOAD_FAIL\n";
        write(1, failure, sizeof(failure) - 1);
        return 1;
      }
      checksum = ((checksum << 1) | (checksum >> 31)) ^ tile[i];
    }
  }
  static const char marker[] =
      "CORAL_EXTERNAL_PAYLOAD_PASS bytes=1048576 tile=256 checksum=";
  char digits[9];
  for (uint32_t i = 0; i < 8; ++i)
    digits[i] = "0123456789abcdef"[(checksum >> (28 - 4 * i)) & 15];
  digits[8] = '\n';
  write(1, marker, sizeof(marker) - 1);
  write(1, digits, sizeof(digits));
  return 0;
}
