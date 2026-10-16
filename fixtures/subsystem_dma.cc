#include <stdint.h>

#include "fpga/sw/dma.h"
#include "fpga/sw/uart.h"

// DMA writes reach ITCM through the core device port; guest stores cannot.
asm(".section .text.dma_target, \"ax\", @progbits\n"
    ".p2align 5\n"
    ".globl itcm_target\n"
    "itcm_target:\n"
    "  .skip 64\n"
    ".text\n");
extern "C" volatile uint32_t itcm_target[16];

constexpr uint32_t kWords = 16;
constexpr uintptr_t kSram = 0x20000000;
static volatile uint32_t* const sram_src = reinterpret_cast<volatile uint32_t*>(kSram + 0x4000);
static volatile uint32_t* const sram_dst = reinterpret_cast<volatile uint32_t*>(kSram + 0x5000);
static volatile dma_descriptor* const desc = reinterpret_cast<volatile dma_descriptor*>(kSram + 0x6000);
alignas(32) static volatile uint32_t dtcm_buffer[kWords];

static uint32_t address(const volatile void* pointer) {
  return static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pointer));
}

static bool copy(const volatile uint32_t* src, volatile uint32_t* dst) {
  desc->src_addr = address(src);
  desc->dst_addr = address(dst);
  desc->len_flags = dma_make_len_flags(kWords * 4, 2, 0, 0, 0);
  desc->next_desc = 0;
  desc->poll_addr = 0;
  desc->poll_mask = 0;
  desc->poll_value = 0;
  desc->reserved = 0;
  dma_start(address(desc));
  return dma_wait_done() == 0;
}

static bool check(const volatile uint32_t* data, uint32_t seed) {
  for (uint32_t i = 0; i < kWords; ++i)
    if (data[i] != seed + i) return false;
  return true;
}

static int fail(const char* message) {
  uart_puts(message);
  return 1;
}

int main() {
  uart_init();
  for (uint32_t i = 0; i < kWords; ++i) sram_src[i] = 0xC0DE0000 + i;
  if (!copy(sram_src, dtcm_buffer) || !check(dtcm_buffer, 0xC0DE0000))
    return fail("CORAL_SUBSYSTEM_DMA_SRAM_TO_DTCM_FAIL\r\n");
  for (uint32_t i = 0; i < kWords; ++i) dtcm_buffer[i] = 0xD7C30000 + i;
  if (!copy(dtcm_buffer, sram_dst) || !check(sram_dst, 0xD7C30000))
    return fail("CORAL_SUBSYSTEM_DMA_DTCM_TO_SRAM_FAIL\r\n");
  if (!copy(sram_src, itcm_target) || !check(itcm_target, 0xC0DE0000))
    return fail("CORAL_SUBSYSTEM_DMA_SRAM_TO_ITCM_FAIL\r\n");
  uart_puts("CORAL_SUBSYSTEM_DMA_PASS\r\n");
  return 0;
}
