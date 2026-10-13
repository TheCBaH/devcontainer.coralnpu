#include <riscv_vector.h>
#include <stdint.h>
#include <unistd.h>

float a[16], b[16], sum[16];

int main() {
  for (int i = 0; i < 16; ++i) {
    a[i] = 0.5f * i - 2.0f;
    b[i] = 2.0f * i + 1.25f;
  }
  for (size_t i = 0; i < 16;) {
    size_t vl = __riscv_vsetvl_e32m1(16 - i);
    auto va = __riscv_vle32_v_f32m1(a + i, vl);
    auto vb = __riscv_vle32_v_f32m1(b + i, vl);
    __riscv_vse32_v_f32m1(sum + i, __riscv_vfadd_vv_f32m1(va, vb, vl), vl);
    i += vl;
  }
  for (int i = 0; i < 16; ++i) if (sum[i] != 2.5f * i - 0.75f) return 1;
  uint32_t bf16;
  asm volatile("fcvt.bf16.s ft0, %1\nfmv.x.w %0, ft0"
               : "=r"(bf16) : "f"(1.5f) : "ft0");
  if ((bf16 & 0xffff) != 0x3fc0) return 1;
  static const char message[] = "CORAL_RVV_FP_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
