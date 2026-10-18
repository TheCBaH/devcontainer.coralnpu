int main() { return 99; }

// Fixed entry points bypass CRT startup for exact instruction boundaries.
asm(R"(
  .section .batch_limits,"ax",@progbits
  .option norvc
  .option norelax
  .global batch_loop
batch_loop:
  j batch_loop
  .global batch_mpause
batch_mpause:
  nop
  .word 0x08000073
  .global batch_ebreak
batch_ebreak:
  nop
  ebreak

  .macro batch_exit name, payload
  .global \name
\name:
  lui t0, %hi(tohost)
  addi t0, t0, %lo(tohost)
  li t1, \payload
  sw t1, 0(t0)
  sw zero, 4(t0)
  lui t0, %hi(tohost_ready)
  addi t0, t0, %lo(tohost_ready)
  fence rw, w
  li t1, 1
  sw t1, 0(t0)
  .endm

  .org 0x40
  batch_exit batch_exit0, 1
  .org 0x80
  batch_exit batch_exit77, 155
  .org 0xc0
  batch_exit batch_exit124, 249

  .org 0x100
  .global batch_trap
batch_trap:
  li t0, 0x1110
  csrw mtvec, t0
  .word 0xffffffff
batch_trap_handler:
  j batch_trap_handler

  .org 0x140
  .global batch_csr
batch_csr:
  csrw minstret, zero
  csrw minstreth, zero
  j batch_csr
  .text
)");
