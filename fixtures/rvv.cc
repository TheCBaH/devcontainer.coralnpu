#include <riscv_vector.h>
#include <stdint.h>
#include <unistd.h>

int32_t a[16], b[16], sum[16];

int main() {
  for (int i = 0; i < 16; ++i) {
    a[i] = i - 7;
    b[i] = 3 * i;
  }
  for (size_t i = 0; i < 16;) {
    size_t vl = __riscv_vsetvl_e32m1(16 - i);
    auto va = __riscv_vle32_v_i32m1(a + i, vl);
    auto vb = __riscv_vle32_v_i32m1(b + i, vl);
    __riscv_vse32_v_i32m1(sum + i, __riscv_vadd_vv_i32m1(va, vb, vl), vl);
    i += vl;
  }
  for (int i = 0; i < 16; ++i) if (sum[i] != 4 * i - 7) return 1;
  const char message[] = "CORAL_RVV_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
