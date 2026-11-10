#include <stdint.h>
#include <unistd.h>
#ifdef CORAL_RVV
#include <riscv_vector.h>
#endif

#ifndef CORAL_DDR_BYTES
#error "CORAL_DDR_BYTES must be the size of the simulated DDR"
#endif

constexpr uintptr_t kDdrBase = 0x80000000u;
constexpr uint32_t kDdrBytes = CORAL_DDR_BYTES;
constexpr uintptr_t kRamBase = 0x20000000u;
constexpr uint32_t kPayloadBytes = 4608u * 1024;
constexpr uint32_t kPayloadWords = kPayloadBytes / 4;
constexpr uint32_t kScratchBytes = 6u * 1024 * 1024;
constexpr uint32_t kTileBytes = 256;
constexpr uint32_t kTailBytes = 512;

extern "C" const volatile uint32_t ddr_payload[kPayloadWords];
// No initial contents: zeroed by the loader, not by the guest.
alignas(16) volatile uint8_t ddr_scratch[kScratchBytes] __attribute__((section(".ddr_bss.scratch")));
alignas(16) static volatile uint32_t tile[kTileBytes / 4];
#ifdef CORAL_RVV
#define NAME "CORAL_DDR_RVV"
#else
#define NAME "CORAL_DDR_PAYLOAD"
#endif
volatile uint32_t trap_values[2];

// Initialized ELF bytes in DDR, more than the 4 MiB of the legacy external RAM.
asm(".pushsection .ddr_data.payload, \"a\", @progbits\n"
    ".balign 16\n"
    ".globl ddr_payload\n"
    ".type ddr_payload, @object\n"
    "ddr_payload:\n"
    ".set .Lword, 0\n"
    ".rept 1179648\n"
    ".long ((.Lword * 0x9e3779b9) ^ 0xa5a55a5a) & 0xffffffff\n"
    ".set .Lword, .Lword + 1\n"
    ".endr\n"
    ".size ddr_payload, . - ddr_payload\n"
    ".popsection\n");

extern "C" __attribute__((naked, aligned(4))) void capture_trap() {
  asm volatile(
      "addi sp, sp, -16\n"
      "sw t0, 0(sp)\n"
      "sw t1, 4(sp)\n"
      "la t0, trap_values\n"
      "csrr t1, mcause\n"
      "sw t1, 0(t0)\n"
      "csrr t1, mtval\n"
      "sw t1, 4(t0)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "lw t0, 0(sp)\n"
      "lw t1, 4(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}

static volatile uint32_t* word(uintptr_t address) { return reinterpret_cast<volatile uint32_t*>(address); }
static volatile uint8_t* byte(uintptr_t address) { return reinterpret_cast<volatile uint8_t*>(address); }
static uint32_t pattern(uint32_t i) { return (i * 0x9e3779b9u) ^ 0xa5a55a5au; }
static uint8_t pattern_byte(uint32_t offset) { return pattern(offset >> 2) >> (8 * (offset & 3)); }

static bool zero_words(uintptr_t address, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i)
    if (*word(address + 4 * i) != 0) return false;
  return true;
}

static bool write_read_words(uintptr_t address, uint32_t count, uint32_t seed) {
  for (uint32_t i = 0; i < count; ++i) *word(address + 4 * i) = pattern(seed + i);
  for (uint32_t i = 0; i < count; ++i)
    if (*word(address + 4 * i) != pattern(seed + i)) return false;
  return true;
}

// Copies through a bounded DTCM tile, in words when everything is aligned and in bytes otherwise.
static void copy(uintptr_t source, uintptr_t destination, uint32_t length) {
  volatile uint8_t* bytes = reinterpret_cast<volatile uint8_t*>(tile);
  const bool aligned = ((source | destination | length) & 3) == 0;
  for (uint32_t done = 0; done < length;) {
    const uint32_t n = length - done < kTileBytes ? length - done : kTileBytes;
    if (aligned) {
      for (uint32_t i = 0; i < n / 4; ++i) tile[i] = *word(source + done + 4 * i);
      for (uint32_t i = 0; i < n / 4; ++i) *word(destination + done + 4 * i) = tile[i];
    } else {
      for (uint32_t i = 0; i < n; ++i) bytes[i] = *byte(source + done + i);
      for (uint32_t i = 0; i < n; ++i) *byte(destination + done + i) = bytes[i];
    }
    done += n;
  }
}

#ifdef CORAL_RVV
// Copies with byte-element vector loads and stores, through the same DTCM tile.
static void copy_vector(uintptr_t source, uintptr_t destination, uint32_t length) {
  uint8_t* bytes = const_cast<uint8_t*>(reinterpret_cast<volatile uint8_t*>(tile));
  for (uint32_t done = 0; done < length;) {
    const uint32_t n = length - done < kTileBytes ? length - done : kTileBytes;
    for (uint32_t i = 0; i < n;) {
      size_t vl = __riscv_vsetvl_e8m1(n - i);
      __riscv_vse8_v_u8m1(bytes + i, __riscv_vle8_v_u8m1(reinterpret_cast<const uint8_t*>(source + done + i), vl), vl);
      i += vl;
    }
    for (uint32_t i = 0; i < n;) {
      size_t vl = __riscv_vsetvl_e8m1(n - i);
      __riscv_vse8_v_u8m1(reinterpret_cast<uint8_t*>(destination + done + i), __riscv_vle8_v_u8m1(bytes + i, vl), vl);
      i += vl;
    }
    done += n;
  }
}
#endif

struct Copy {
  uintptr_t source, destination;
  uint32_t length;
  uint32_t pattern_offset;  // The source holds pattern_byte(pattern_offset + i) at byte i.
  uint32_t leading;         // Bytes before the destination that must stay zero.
};

static int check_copy(const Copy& c, void (*copier)(uintptr_t, uintptr_t, uint32_t) = copy) {
  copier(c.source, c.destination, c.length);
  for (uint32_t i = 0; i < c.length; ++i)
    if (*byte(c.destination + i) != pattern_byte(c.pattern_offset + i)) return 1;
  for (uint32_t i = 1; i <= c.leading; ++i)
    if (*byte(c.destination - i) != 0) return 2;
  for (uint32_t i = 0; i < 8; ++i)
    if (*byte(c.destination + c.length + i) != 0) return 3;
  return 0;
}

static int fail(uint32_t step) {
  char text[] = NAME "_FAIL 00\n";
  text[sizeof(text) - 4] = '0' + step / 10;
  text[sizeof(text) - 3] = '0' + step % 10;
  write(1, text, sizeof(text) - 1);
  return 1;
}

#ifdef CORAL_RVV
// Wide loads over all of the initialized data; stores and loads at the last bytes of DDR.
static int check_vector() {
  alignas(16) static uint32_t chunk[32];
  for (uint32_t i = 0; i < kPayloadWords;) {
    size_t vl = __riscv_vsetvl_e32m8(kPayloadWords - i);
    __riscv_vse32_v_u32m8(chunk, __riscv_vle32_v_u32m8(reinterpret_cast<const uint32_t*>(kDdrBase + 4 * i), vl), vl);
    if (chunk[0] != pattern(i) || chunk[vl / 2] != pattern(i + vl / 2) || chunk[vl - 1] != pattern(i + vl - 1))
      return 40;
    i += vl;
  }
  uint32_t* last = reinterpret_cast<uint32_t*>(kDdrBase + kDdrBytes - 16);
  for (uint32_t i = 0; i < 4; ++i) chunk[i] = pattern(7000 + i);
  size_t vl = __riscv_vsetvl_e32m1(4);
  __riscv_vse32_v_u32m1(last, __riscv_vle32_v_u32m1(chunk, vl), vl);
  for (uint32_t i = 0; i < 4; ++i)
    if (last[i] != pattern(7000 + i)) return 41;
  __riscv_vse32_v_u32m1(chunk, __riscv_vle32_v_u32m1(last, vl), vl);
  for (uint32_t i = 0; i < 4; ++i)
    if (chunk[i] != pattern(7000 + i)) return 42;
  return 0;
}
#endif

static int load_fault(uintptr_t address) {
  trap_values[0] = 0;
  uint32_t value;
  asm volatile("lw %0, 0(%1)" : "=r"(value) : "r"(address) : "memory");
  return trap_values[0] == 5 && trap_values[1] == address ? 0 : 1;
}

int main() {
  const uintptr_t scratch = reinterpret_cast<uintptr_t>(ddr_scratch);
  const uintptr_t top = kDdrBase + kDdrBytes;
  if (reinterpret_cast<uintptr_t>(ddr_payload) != kDdrBase || scratch < kDdrBase + kPayloadBytes ||
      scratch + kScratchBytes > top) return fail(1);

  // Initialized ELF data, sampled every 64 bytes and at the end.
  uint32_t checksum = 0;
  for (uint32_t i = 0; i < kPayloadWords; i += i + 16 < kPayloadWords ? 16 : 1) {
    if (ddr_payload[i] != pattern(i)) return fail(2);
    checksum = ((checksum << 1) | (checksum >> 31)) ^ ddr_payload[i];
  }

  // Zero-filled ELF data, and untouched DDR.
  for (uint32_t offset = 0; offset < kScratchBytes; offset += 4096)
    if (*word(scratch + offset) != 0) return fail(3);
  if (!zero_words(scratch, 16) || !zero_words(scratch + kScratchBytes - 64, 16)) return fail(4);
  if (!zero_words(top - 64, 16) || !zero_words(kDdrBase + kDdrBytes / 2 + 0x1000, 16)) return fail(5);

  // The last bytes of DDR, and a sparse offset in the middle.
  if (!write_read_words(top - 64, 16, 1000) || !write_read_words(kDdrBase + kDdrBytes / 2 + 0x1000, 16, 2000))
    return fail(6);
  if (*word(top - 4) != pattern(1015) || *byte(top - 1) != (pattern(1015) >> 24)) return fail(7);

  // The same offsets in the legacy RAM and in DDR hold different data.
  const uint32_t offsets[] = {0x1000, 0x80000, 0x3ffff0};
  for (uint32_t k = 0; k < 3; ++k) {
    *word(kRamBase + offsets[k]) = 0x52414d00u + k;
    *word(scratch + offsets[k]) = 0x44445200u + k;
  }
  for (uint32_t k = 0; k < 3; ++k)
    if (*word(kRamBase + offsets[k]) != 0x52414d00u + k || *word(scratch + offsets[k]) != 0x44445200u + k)
      return fail(8);

  // DDR to DTCM to DDR at several offsets, with partial tiles and byte alignments.
  const uintptr_t tail = top - kTailBytes;
  for (uint32_t i = 0; i < kTailBytes; ++i) *byte(tail + i) = pattern_byte(i);
  const uintptr_t base = scratch + 0x100000;
  const Copy copies[] = {
      {kDdrBase, base, 256, 0, 0},
      {kDdrBase + 4, base + 0x20000 + 8, 256, 4, 8},
      {kDdrBase + 1, base + 0x40000 + 3, 100, 1, 3},
      {kDdrBase + 3, base + 0x60000 + 2, 255, 3, 2},
      {kDdrBase + 4093, base + 0x80000 + 5, 17, 4093, 5},
      {kDdrBase + kPayloadBytes - 1, base + 0xa0000 + 1, 1, kPayloadBytes - 1, 1},
      {kDdrBase + kPayloadBytes - 300, base + 0xc0000 + 7, 300, kPayloadBytes - 300, 7},
      {kDdrBase + 1000001, base + 0xe0000 + 9, 3000, 1000001, 9},
      {kDdrBase + 0x200000, base + 0x100000, 65536, 0x200000, 0},
      {tail + 3, base + 0x140000 + 6, kTailBytes - 3, 3, 6},
  };
  for (uint32_t i = 0; i < sizeof(copies) / sizeof(copies[0]); ++i)
    if (check_copy(copies[i])) return fail(10 + i);
#ifdef CORAL_RVV
  for (uint32_t i = 0; i < sizeof(copies) / sizeof(copies[0]); ++i) {
    Copy c = copies[i];
    c.destination += 0x180000;
    if (check_copy(c, copy_vector)) return fail(50 + i);
  }
  if (int status = check_vector()) return fail(status);
#endif
  // The last byte of DDR as a destination.
  copy(base + 0x140000 + 6, top - 100, 100);
  for (uint32_t i = 0; i < 100; ++i)
    if (*byte(top - 100 + i) != pattern_byte(3 + i)) return fail(30);

  // Loads just outside DDR fault with the bad address.
  asm volatile("csrw mtvec, %0" : : "r"(capture_trap));
  if (load_fault(kDdrBase - 4) || load_fault(top)) return fail(31);

  static const char marker[] = NAME "_PASS bytes=4718592 checksum=";
  char digits[9];
  for (uint32_t i = 0; i < 8; ++i) digits[i] = "0123456789abcdef"[(checksum >> (28 - 4 * i)) & 15];
  digits[8] = '\n';
  write(1, marker, sizeof(marker) - 1);
  write(1, digits, sizeof(digits));
  return 0;
}
