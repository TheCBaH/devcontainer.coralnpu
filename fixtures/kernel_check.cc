// Self-checking harness for Coral's Gemma RVV kernels (see kernels/kernels.json).
// One source; the kernel is chosen with -DKERNEL_<NAME> and the data type with
// -DKERNEL_BF16. The kernel sources are Coral's, unmodified. Inputs are
// generated in the guest, the kernel runs on them, and the output is compared
// with a double-precision reference using the tolerance the upstream cocotb
// test uses. Words after the output must stay untouched.
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(KERNEL_RESIDUAL_ADD)
#define KERNEL_NAME "RESIDUAL_ADD"
#elif defined(KERNEL_RMS_NORM)
#define KERNEL_NAME "RMS_NORM"
#elif defined(KERNEL_TANH_GELU_MUL)
#define KERNEL_NAME "TANH_GELU_MUL"
#else
#error "select a kernel"
#endif

#if defined(KERNEL_BF16)
#define FORMAT "BF16"
typedef uint16_t Elem;
#else
#define FORMAT "F32"
typedef float Elem;
#endif
#define MARKER "CORAL_KERNEL_" KERNEL_NAME "_" FORMAT

extern "C" {
#if defined(KERNEL_RESIDUAL_ADD) && defined(KERNEL_BF16)
void rvv_residual_add_bf16(const __bf16*, const __bf16*, __bf16*, size_t);
#elif defined(KERNEL_RESIDUAL_ADD)
void rvv_residual_add_f32(const float*, const float*, float*, size_t);
#elif defined(KERNEL_RMS_NORM) && defined(KERNEL_BF16)
void RmsNormBf16(size_t, size_t, float, const __bf16*, const __bf16*, __bf16*);
#elif defined(KERNEL_RMS_NORM)
void RmsNormF(size_t, size_t, float, const float*, const float*, float*);
#elif defined(KERNEL_TANH_GELU_MUL) && defined(KERNEL_BF16)
void rvv_tanh_gelu_mul_bf16(const __bf16*, const __bf16*, __bf16*, size_t);
#else
void rvv_tanh_gelu_mul_f32(const float*, const float*, float*, size_t);
#endif
}

struct Shape { int rows, cols; };
// Tails (not a multiple of the 32-lane f32 vector length), several rows and a
// single row. Small, because the reference runs in the guest. It uses FP32
// (hardware) arithmetic, except the RMSNorm sum of squares; double precision
// is emulated in software and far too slow in an RTL simulation.
static const Shape kShapes[] = {{2, 160}, {1, 67}, {1, 33}};
constexpr int kMaxElements = 2 * 160, kMaxCols = 160, kGuard = 64;
constexpr float kEpsilon = 1e-6f;

// Tolerances follow the upstream cocotb tests.
#if defined(KERNEL_RESIDUAL_ADD) && !defined(KERNEL_BF16)
constexpr double kRtol = 1e-5, kAtol = 1e-5;
#elif defined(KERNEL_RMS_NORM) && !defined(KERNEL_BF16)
constexpr double kRtol = 1e-6, kAtol = 1e-6;
#elif defined(KERNEL_TANH_GELU_MUL) && !defined(KERNEL_BF16)
constexpr double kRtol = 1e-2, kAtol = 1e-2;
#else
constexpr double kRtol = 1e-2, kAtol = 1e-2;
#endif

static Elem input_a[kMaxElements];
#if defined(KERNEL_RMS_NORM)
static Elem weight[kMaxCols];
#else
static Elem input_b[kMaxElements];
#endif
static Elem output[kMaxElements + kGuard];
static uint32_t random_state = 42;

static float uniform(float low, float high) {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 17;
  random_state ^= random_state << 5;
  return low + (high - low) * static_cast<float>(random_state >> 8) * (1.0f / 16777216.0f);
}

#if defined(KERNEL_BF16)
static Elem encode(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof bits);
  return static_cast<uint16_t>((bits + 0x7fffu + ((bits >> 16) & 1)) >> 16);
}
static float decode(Elem value) {
  const uint32_t bits = static_cast<uint32_t>(value) << 16;
  float result;
  memcpy(&result, &bits, sizeof result);
  return result;
}
#else
static Elem encode(float value) { return value; }
static float decode(Elem value) { return value; }
#endif

static uint32_t cycles() {
  uint32_t value;
  asm volatile("csrr %0, mcycle" : "=r"(value));
  return value;
}

static void fill(Elem* data, int count, float low, float high) {
  for (int i = 0; i < count; ++i) data[i] = encode(uniform(low, high));
}

int main() {
  uint32_t total_cycles = 0, worst_abs_e9 = 0;
  int cases = 0;
  for (const Shape& shape : kShapes) {
    const int elements = shape.rows * shape.cols;
#if defined(KERNEL_RESIDUAL_ADD)
#if defined(KERNEL_BF16)
    fill(input_a, elements, -5.0f, 5.0f);
    fill(input_b, elements, -5.0f, 5.0f);
#else
    fill(input_a, elements, -1.0f, 1.0f);
    fill(input_b, elements, -0.5f, 0.5f);
#endif
#elif defined(KERNEL_RMS_NORM)
    fill(input_a, elements, -1.0f, 1.0f);
    fill(weight, shape.cols, -0.5f, 0.5f);
#else
#if defined(KERNEL_BF16)
    fill(input_a, elements, -3.0f, 3.0f);
    fill(input_b, elements, -3.0f, 3.0f);
#else
    fill(input_a, elements, -1.0f, 1.0f);
    fill(input_b, elements, -1.0f, 1.0f);
#endif
#endif
    for (int i = 0; i < elements + kGuard; ++i) output[i] = encode(123.0f);

    const uint32_t start = cycles();
#if defined(KERNEL_RESIDUAL_ADD) && defined(KERNEL_BF16)
    rvv_residual_add_bf16(reinterpret_cast<const __bf16*>(input_a),
                          reinterpret_cast<const __bf16*>(input_b),
                          reinterpret_cast<__bf16*>(output), elements);
#elif defined(KERNEL_RESIDUAL_ADD)
    rvv_residual_add_f32(input_a, input_b, output, elements);
#elif defined(KERNEL_RMS_NORM) && defined(KERNEL_BF16)
    RmsNormBf16(shape.rows, shape.cols, kEpsilon, reinterpret_cast<const __bf16*>(input_a),
                reinterpret_cast<const __bf16*>(weight), reinterpret_cast<__bf16*>(output));
#elif defined(KERNEL_RMS_NORM)
    RmsNormF(shape.rows, shape.cols, kEpsilon, input_a, weight, output);
#elif defined(KERNEL_TANH_GELU_MUL) && defined(KERNEL_BF16)
    rvv_tanh_gelu_mul_bf16(reinterpret_cast<const __bf16*>(input_a),
                           reinterpret_cast<const __bf16*>(input_b),
                           reinterpret_cast<__bf16*>(output), elements);
#else
    rvv_tanh_gelu_mul_f32(input_a, input_b, output, elements);
#endif
    const uint32_t spent = cycles() - start;
    total_cycles += spent;

    for (int row = 0; row < shape.rows; ++row) {
#if defined(KERNEL_RMS_NORM)
      double sum = 0;
      for (int col = 0; col < shape.cols; ++col) {
        const float x = decode(input_a[row * shape.cols + col]);
        sum += x * x;
      }
      const float scale = 1.0f / sqrtf(static_cast<float>(sum / shape.cols) + kEpsilon);
#endif
      for (int col = 0; col < shape.cols; ++col) {
        const int index = row * shape.cols + col;
        const float a = decode(input_a[index]);
#if defined(KERNEL_RESIDUAL_ADD)
        const float expected = a + decode(input_b[index]);
#elif defined(KERNEL_RMS_NORM)
        const float expected = a * scale * (1.0f + decode(weight[col]));
#else
        const float up = decode(input_b[index]);
        const float inner = 0.7978845608f * (a + 0.044715f * a * a * a);
        const float expected = 0.5f * a * (1.0f + tanhf(inner)) * up;
#endif
        const float actual = decode(output[index]);
        const float error = fabsf(actual - expected);
        if (!(error <= kAtol + kRtol * fabsf(expected))) {
          printf(MARKER "_FAIL case=%dx%d index=%d expected_e6=%d actual_e6=%d\n", shape.rows,
                 shape.cols, index, static_cast<int>(expected * 1e6), static_cast<int>(actual * 1e6));
          return 1;
        }
        const uint32_t error_e9 = static_cast<uint32_t>(error * 1e9);
        if (error_e9 > worst_abs_e9) worst_abs_e9 = error_e9;
      }
    }
    for (int i = elements; i < elements + kGuard; ++i) {
      if (output[i] != encode(123.0f)) {
        printf(MARKER "_FAIL case=%dx%d output guard=%d\n", shape.rows, shape.cols, i - elements);
        return 1;
      }
    }
    printf(MARKER "_CASE %dx%d cycles=%u\n", shape.rows, shape.cols, static_cast<unsigned>(spent));
    ++cases;
  }
  printf(MARKER "_PASS cases=%d cycles=%u max_abs_error_e9=%u\n", cases,
         static_cast<unsigned>(total_cycles), static_cast<unsigned>(worst_abs_e9));
  return 0;
}
