#include <stdint.h>
#include <unistd.h>

// GAS lacks Zvt mnemonics. These encodings follow the pinned MPACT
// coralnpu_m4.bin_fmt and riscv_zvt.bin_fmt, referenced in examples/README.md.
static bool Configure(uint32_t widen, uint32_t k, uint32_t sew) {
  uint32_t mtype = (2u << 10) | (k << 5) | widen;
  // VME requires LMUL4 for FP32 and LMUL2 plus altfmt for BF16.
  uint32_t lmul = widen == 1 ? 2 : widen == 2 ? 1 : 0;
  uint32_t vtype = 0xc0 | (sew << 3) | lmul | (widen == 2 ? 0x100 : 0);
  asm volatile(".insn r 0x57, 7, 0x42, x0, %0, %1"
               : : "r"(mtype), "r"(vtype) : "memory");
  uint32_t tn, actual;
  asm volatile(".insn r 0x57, 7, 0x44, %0, %1, x0"
               : "=r"(tn) : "r"(2u) : "memory");
  asm volatile("csrr %0, 0xc23" : "=r"(actual));
  return tn == 2 && actual == mtype;
}

static void Zero() {
  asm volatile(".word 0x43e06057" : : : "memory");
}

template <uint32_t WORD>
static void Multiply() {
  asm volatile(".word %0" : : "i"(WORD) : "memory");
}

static void Store(void *output) {
  for (uint32_t row = 0; row < 2; ++row) {
    void *address = static_cast<uint8_t *>(output) + row * 8;
    asm volatile(".insn r 0x27, 7, 0x29, x0, %0, %1"
                 : : "r"(address), "r"(row) : "memory");
  }
}

static bool Int8() {
  static const int8_t a[2][2] = {{1, -2}, {-3, 4}};
  static const int8_t b[2][2] = {{5, 6}, {7, 8}};
  static const int32_t expected[4] = {-16, -18, 18, 20};
  int32_t output[4];
  if (!Configure(3, 2, 0)) return false;
  Zero();
  asm volatile("vle8.v v8, (%0)\nvle8.v v10, (%1)\n"
               "vle8.v v16, (%2)\nvle8.v v18, (%3)"
               : : "r"(a[0]), "r"(a[1]), "r"(b[0]), "r"(b[1])
               : "v8", "v10", "v16", "v18", "memory");
  for (int count = 1; count <= 2; ++count) {
    Multiply<0xf28800f7>();
    Store(output);
    for (int i = 0; i < 4; ++i) if (output[i] != count * expected[i]) return false;
  }
  Zero();
  Multiply<0xf28800f7>();
  Store(output);
  for (int i = 0; i < 4; ++i) if (output[i] != expected[i]) return false;
  return true;
}

static bool Fp32() {
  static const float a[2] = {-1.5f, 2.0f}, b[2] = {3.0f, -4.0f};
  static const float expected[4] = {-4.5f, 6.0f, 6.0f, -8.0f};
  float output[4];
  if (!Configure(1, 1, 2)) return false;
  Zero();
  asm volatile("vle32.v v8, (%0)\nvle32.v v16, (%1)"
               : : "r"(a), "r"(b)
               : "v8", "v9", "v10", "v11", "v16", "v17", "v18", "v19", "memory");
  Multiply<0xf2881077>();
  Store(output);
  for (int i = 0; i < 4; ++i) if (output[i] != expected[i]) return false;
  return true;
}

static bool Bf16() {
  static const uint16_t a[2][2] = {{0x3f80, 0xc000}, {0xc040, 0x4080}};
  static const uint16_t b[2][2] = {{0x40a0, 0x40c0}, {0x40e0, 0x4100}};
  static const float expected[4] = {-16.0f, -18.0f, 18.0f, 20.0f};
  float output[4];
  if (!Configure(2, 2, 1)) return false;
  Zero();
  asm volatile("vle16.v v8, (%0)\nvle16.v v12, (%1)\n"
               "vle16.v v16, (%2)\nvle16.v v20, (%3)"
               : : "r"(a[0]), "r"(a[1]), "r"(b[0]), "r"(b[1])
               : "v8", "v9", "v12", "v13", "v16", "v17", "v20", "v21", "memory");
  Multiply<0xf28810f7>();
  Store(output);
  for (int i = 0; i < 4; ++i) if (output[i] != expected[i]) return false;
  return true;
}

template <size_t N>
static int Fail(const char (&message)[N]) {
  write(1, message, N - 1);
  return 1;
}

int main() {
  asm volatile("csrs mstatus, %0" : : "r"(3u << 29) : "memory");
  if (!Int8()) return Fail("CORAL_MATRIX_INT8_FAIL\n");
  if (!Fp32()) return Fail("CORAL_MATRIX_FP32_FAIL\n");
  if (!Bf16()) return Fail("CORAL_MATRIX_BF16_FAIL\n");
  static const char message[] = "CORAL_MATRIX_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
