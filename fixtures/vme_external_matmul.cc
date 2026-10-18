#include <stdint.h>
#include <unistd.h>

#include "tests/cocotb/vme_test/vme_test_utils.h"

constexpr int kM = 19, kN = 23, kK = 5, kTile = 16, kGuard = 16;
static constexpr int a_value(int m, int k) { return (m * 3 + k * 2) % 7 - 3; }
static constexpr int b_value(int k, int n) { return (k * 5 + n * 3) % 9 - 4; }
static constexpr int c_value(int m, int n) { return (m * 7 + n) % 13 - 6; }

struct Inputs {
  float a[kK * kM + kTile];
  float b[kK * kN + kTile];
  float c_rows[kM * kN];
  float c_cols[kM * kN];
};

static constexpr Inputs make_inputs() {
  Inputs data = {};
  for (int k = 0; k < kK; ++k) {
    for (int m = 0; m < kM; ++m) data.a[k * kM + m] = a_value(m, k);
    for (int n = 0; n < kN; ++n) data.b[k * kN + n] = b_value(k, n);
  }
  for (int m = 0; m < kM; ++m) {
    for (int n = 0; n < kN; ++n) {
      data.c_rows[m * kN + n] = c_value(m, n);
      data.c_cols[n * kM + m] = c_value(m, n);
    }
  }
  return data;
}

__attribute__((section(".extdata"), aligned(16))) const Inputs inputs = make_inputs();
__attribute__((section(".extbss"), aligned(16))) float output[kM * kN + 2 * kGuard];

static void configure(int m, int n) {
  vme_msetmtype(MtypeValue(m, 1, 1), 0xd2);
  (void)vme_msettn(n);
}

static void load_slice(const float* source, uint32_t slice) {
  asm volatile(".insn r 0x07, 7, 0x29, x0, %0, %1" : : "r"(source), "r"(slice) : "memory");
}

static void store_slice(float* destination, uint32_t slice) {
  asm volatile(".insn r 0x27, 7, 0x29, x0, %0, %1" : : "r"(destination), "r"(slice) : "memory");
}

static bool run(bool column_loads) {
  for (float& value : output) value = 123;
  for (int bm = 0; bm < kM; bm += kTile) {
    const int tm = kM - bm < kTile ? kM - bm : kTile;
    for (int bn = 0; bn < kN; bn += kTile) {
      const int tn = kN - bn < kTile ? kN - bn : kTile;
      configure(tm, tn);
      asm volatile(".word %0" : : "i"(ZvtVtzeroWord(0)) : "memory");
      if (column_loads) {
        (void)vme_msettn(tm);
        for (int n = 0; n < tn; ++n)
          load_slice(inputs.c_cols + (bn + n) * kM + bm, (1u << 24) | n);
      } else {
        for (int m = 0; m < tm; ++m)
          load_slice(inputs.c_rows + (bm + m) * kN + bn, m);
      }
      for (int k = 0; k < kK; ++k) {
        (void)vme_msettn(kTile);
        asm volatile("vle32.v v8, (%0)\nvle32.v v16, (%1)"
                     : : "r"(inputs.a + k * kM + bm), "r"(inputs.b + k * kN + bn)
                     : "v8", "v9", "v10", "v11", "v16", "v17", "v18", "v19", "memory");
        (void)vme_msettn(tn);
        asm volatile(".word %0" : : "i"(ZvtMatmulFpWord(0)) : "memory");
      }
      if (column_loads) {
        for (int m = 0; m < tm; ++m)
          store_slice(output + kGuard + (bm + m) * kN + bn, m);
      } else {
        (void)vme_msettn(tm);
        for (int n = 0; n < tn; ++n)
          store_slice(output + kGuard + (bn + n) * kM + bm, (1u << 24) | n);
      }
    }
  }
  for (int m = 0; m < kM; ++m) {
    for (int n = 0; n < kN; ++n) {
      int expected = c_value(m, n);
      for (int k = 0; k < kK; ++k) expected += a_value(m, k) * b_value(k, n);
      const int index = column_loads ? m * kN + n : n * kM + m;
      if (output[kGuard + index] != static_cast<float>(expected)) return false;
    }
  }
  for (int i = 0; i < kGuard; ++i)
    if (output[i] != 123 || output[kGuard + kM * kN + i] != 123) return false;
  return true;
}

int main() {
  asm volatile("csrs mstatus, %0" : : "r"(3u << 29) : "memory");
  if (reinterpret_cast<uintptr_t>(&inputs) != 0x20000000 ||
      reinterpret_cast<uintptr_t>(output) != 0x203ff800 || !run(false) || !run(true)) {
    static const char message[] = "CORAL_VME_EXTERNAL_MATMUL_FAIL\n";
    write(1, message, sizeof(message) - 1);
    return 1;
  }
  static const char message[] = "CORAL_VME_EXTERNAL_MATMUL_PASS cases=2 m=19 n=23 k=5\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
