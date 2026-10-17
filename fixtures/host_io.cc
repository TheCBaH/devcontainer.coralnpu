#include <fcntl.h>
#include <unistd.h>

int main() {
  static const char name[] = "coral-host-io.tmp";
  int fd = open(name, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0 || write(fd, "first", 5) != 5 || close(fd) != 0) return 1;
  fd = open(name, O_WRONLY | O_APPEND);
  if (fd < 0 || lseek(fd, 0, SEEK_SET) != 0 ||
      write(fd, "+append", 7) != 7 || close(fd) != 0) return 2;
  fd = open(name, O_RDONLY);
  char buffer[16] = {};
  if (fd < 0 || read(fd, buffer, sizeof(buffer)) != 12 || close(fd) != 0) return 3;
  for (int i = 0; i < 12; ++i) {
    if (buffer[i] != "first+append"[i]) return 4;
  }
  if (open(name, O_WRONLY | O_CREAT | O_EXCL, 0600) >= 0) return 5;
  fd = open(name, O_WRONLY | O_TRUNC);
  if (fd < 0 || write(fd, "ok", 2) != 2 || close(fd) != 0) return 6;
  fd = open(name, O_RDONLY);
  if (fd < 0 || read(fd, buffer, sizeof(buffer)) != 2 ||
      buffer[0] != 'o' || buffer[1] != 'k' || close(fd) != 0) return 7;
  static const char out[] = "CORAL_STDOUT_ONLY\n";
  static const char err[] = "CORAL_STDERR_ONLY\n";
  static const char marker[] = "CORAL_HOST_IO_PASS\n";
  if (write(1, out, sizeof(out) - 1) != sizeof(out) - 1 ||
      write(2, err, sizeof(err) - 1) != sizeof(err) - 1) return 8;
  write(1, marker, sizeof(marker) - 1);
  return 0;
}
