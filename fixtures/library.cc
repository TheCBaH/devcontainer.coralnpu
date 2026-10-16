#include <stdint.h>

// The host writes four words at each DDR address and reads back their sum.
static volatile uint32_t* const ddr_low = reinterpret_cast<volatile uint32_t*>(0x80000000u);
static volatile uint32_t* const ddr_high = reinterpret_cast<volatile uint32_t*>(0xbfffff00u);
// Outside DDR, the library routes every external address to the mailbox.
static volatile uint32_t* const mailbox = reinterpret_cast<volatile uint32_t*>(0x20000000u);
volatile uint32_t dtcm_result;

int main() {
  uint32_t low = 0, high = 0;
  for (int i = 0; i < 4; ++i) {
    low += ddr_low[i];
    high += ddr_high[i];
  }
  ddr_low[4] = low;
  ddr_high[4] = high;
  dtcm_result = low ^ high;
  mailbox[0] = 0xc0da11b0u;
  mailbox[1] = low;
  mailbox[2] = high;
  mailbox[3] = dtcm_result;
  asm volatile("wfi");
  return 0;
}
