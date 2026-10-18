#include <riscv_vector.h>
#include <stdint.h>
#include <stdio.h>

#if defined(CORAL_MATMUL_INT8)
using Input = int8_t;
using Output = int32_t;
constexpr int kMaxM = 128, kMaxN = 512;
#define FORMAT "INT8"
#define EMIT_RHS ".byte ((1 << (.Lhash & 3)) * (1 - ((.Lhash >> 2) * 2)))\n"
extern "C" void rvv_gemv_int8(const Input*, const Input*, Output*, size_t, size_t);
extern "C" void rvv_matmul_int8(const Input*, const Input*, Output*, size_t, size_t, size_t);
#elif defined(CORAL_MATMUL_BF16)
using Input = __bf16;
using Output = __bf16;
constexpr int kMaxM = 256, kMaxN = 1024;
#define FORMAT "BF16"
#define EMIT_RHS ".short (0x3f80 + ((.Lhash & 3) << 7)) | ((.Lhash >> 2) << 15)\n"
extern "C" void rvv_gemv_1d_bf16(const Input*, const Input*, Output*, int, int);
extern "C" void rvv_tiled_matmul_2d_bf16(const Input*, const Input*, Output*, int, int, int);
#else
using Input = float;
using Output = float;
constexpr int kMaxM = 256, kMaxN = 1024;
#define FORMAT "FP32"
#define EMIT_RHS ".long (0x3f800000 + ((.Lhash & 3) << 23)) | ((.Lhash >> 2) << 31)\n"
extern "C" void rvv_gemv_1d_f32(const Input*, const Input*, Output*, int, int);
extern "C" void rvv_tiled_matmul_2d_f32(const Input*, const Input*, Output*, int, int, int);
#endif

constexpr int kMaxK = 640, kGuard = 64;
constexpr int kRhsElements = kMaxK * kMaxN;
extern "C" const Input rhs_input[kRhsElements];
#if defined(CORAL_MATMUL_BF16)
alignas(16) Input lhs_input[kMaxM * kMaxK] __attribute__((section(".extbss")));
#else
alignas(16) Input lhs_input[kMaxM * kMaxK] __attribute__((section(".noinit")));
#endif
alignas(16) Output result_output[kMaxM * kMaxN + kGuard] __attribute__((section(".extbss")));

// Initialized external ELF data, rather than a guest-generated TCM copy.
asm(".pushsection .extdata.rvv_matmul, \"a\", @progbits\n"
    ".balign 16\n"
    ".globl rhs_input\n"
    ".type rhs_input, @object\n"
    "rhs_input:\n"
    ".set .Lrhs_index, 0\n"
#if defined(CORAL_MATMUL_INT8)
    ".rept 327680\n"
#else
    ".rept 655360\n"
#endif
    ".set .Lhash, ((.Lrhs_index * 13) ^ (.Lrhs_index >> 3) ^ (.Lrhs_index >> 9)) & 7\n"
    EMIT_RHS
    ".set .Lrhs_index, .Lrhs_index + 1\n"
    ".endr\n"
    ".size rhs_input, . - rhs_input\n"
    ".popsection\n");

static int lhs_value(int row, int k) { return ((row * 3 + k * 5 + (k >> 3)) % 7) - 3; }

static int rhs_value(int index) {
  const int hash = ((index * 13) ^ (index >> 3) ^ (index >> 9)) & 7;
  return (1 << (hash & 3)) * (1 - ((hash >> 2) * 2));
}

static bool matches(Output actual, int expected) {
#if defined(CORAL_MATMUL_BF16)
  union { float value; uint32_t bits; } reference = {static_cast<float>(expected)};
  union { __bf16 value; uint16_t bits; } result = {actual};
  const uint16_t rounded = (reference.bits + 0x7fffu + ((reference.bits >> 16) & 1)) >> 16;
  return result.bits == rounded;
#else
  return actual == static_cast<Output>(expected);
#endif
}

struct Shape { int m, k, n, offset; };
static const Shape cases[] = {
    {1, 4, 64, 0},
    {1, 5, 65, 16},
    {1, 7, 33, 32},
    {2, 8, 32, 0},
    {3, 7, 35, 48},
    {3, 4, 96, kRhsElements - 384},
    {1, kMaxK, 65, kRhsElements - kMaxK * 65},
    {2, 4, kMaxN, 0},
    {1, 1, 1, kRhsElements - 1},
};

static bool in_region(const void* pointer, size_t bytes, uintptr_t base, size_t size) {
  const uintptr_t address = reinterpret_cast<uintptr_t>(pointer);
  return address >= base && bytes <= size && address - base <= size - bytes;
}

int main() {
  if (__riscv_vsetvlmax_e8m1() != 16 ||
      reinterpret_cast<uintptr_t>(rhs_input) != 0x20000000u ||
      !in_region(rhs_input, sizeof(rhs_input), 0x20000000, 4 * 1024 * 1024) ||
      !in_region(result_output, sizeof(result_output), 0x20000000, 4 * 1024 * 1024) ||
#if defined(CORAL_MATMUL_BF16)
      !in_region(lhs_input, sizeof(lhs_input), 0x20000000, 4 * 1024 * 1024)) {
#else
      !in_region(lhs_input, sizeof(lhs_input), 0x100000, 1024 * 1024)) {
#endif
    printf("CORAL_RVV_MATMUL_" FORMAT "_FAIL layout\n");
    return 1;
  }
  for (const Shape& s : cases) {
    printf("CORAL_RVV_MATMUL_" FORMAT "_CASE %dx%dx%d offset=%d\n", s.m, s.k, s.n, s.offset);
    for (int m = 0; m < s.m; ++m)
      for (int k = 0; k < s.k; ++k) lhs_input[m * s.k + k] = static_cast<Input>(lhs_value(m, k));
    for (int i = 0; i < s.m * s.n + kGuard; ++i) result_output[i] = static_cast<Output>(123);
    const Input* rhs = rhs_input + s.offset;
#if defined(CORAL_MATMUL_INT8)
    if (s.m == 1) rvv_gemv_int8(lhs_input, rhs, result_output, s.k, s.n);
    else rvv_matmul_int8(lhs_input, rhs, result_output, s.m, s.k, s.n);
#elif defined(CORAL_MATMUL_BF16)
    if (s.m == 1) rvv_gemv_1d_bf16(lhs_input, rhs, result_output, s.k, s.n);
    else rvv_tiled_matmul_2d_bf16(lhs_input, rhs, result_output, s.m, s.k, s.n);
#else
    if (s.m == 1) rvv_gemv_1d_f32(lhs_input, rhs, result_output, s.k, s.n);
    else rvv_tiled_matmul_2d_f32(lhs_input, rhs, result_output, s.m, s.k, s.n);
#endif
    for (int m = 0; m < s.m; ++m) {
      for (int n = 0; n < s.n; ++n) {
        int expected = 0;
        for (int k = 0; k < s.k; ++k)
          expected += lhs_value(m, k) * rhs_value(s.offset + k * s.n + n);
        if (!matches(result_output[m * s.n + n], expected)) {
          printf("CORAL_RVV_MATMUL_" FORMAT "_FAIL row=%d col=%d expected=%d actual=%d\n",
                 m, n, expected, int(result_output[m * s.n + n]));
          return 1;
        }
      }
    }
    for (int i = s.m * s.n; i < s.m * s.n + kGuard; ++i) {
      if (!matches(result_output[i], 123)) {
        printf("CORAL_RVV_MATMUL_" FORMAT "_FAIL output guard=%d\n", i);
        return 1;
      }
    }
  }
  printf("CORAL_RVV_MATMUL_" FORMAT "_PASS cases=%u\n", unsigned(sizeof(cases) / sizeof(cases[0])));
  return 0;
}
