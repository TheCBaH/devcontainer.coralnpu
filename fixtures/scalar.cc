#include <unistd.h>

volatile float a = 1.25f;
volatile float b = 2.5f;
volatile float sum;

int main() {
  sum = a + b;
  if (sum != 3.75f) return 1;
  static const char message[] = "CORAL_SCALAR_PASS\n";
  write(1, message, sizeof(message) - 1);
  return 0;
}
