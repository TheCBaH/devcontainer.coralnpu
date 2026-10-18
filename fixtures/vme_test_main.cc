#include <unistd.h>

extern "C" int __real_main(int argc, char **argv);

extern "C" int __wrap_main(int argc, char **argv) {
  int status = __real_main(argc, argv);
  if (status == 0) {
    static const char message[] = "CORAL_VME_TEST_PASS\n";
    write(1, message, sizeof(message) - 1);
  }
  return status;
}
