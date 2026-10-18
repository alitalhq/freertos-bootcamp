/* The application uses snprintf only; no POSIX file or console I/O. */
#include <errno.h>
#include <sys/stat.h>
#include <stddef.h>
int _close(int fd) { (void)fd; errno=EBADF; return -1; }
int _read(int fd, char *buf, int count) { (void)fd;(void)buf;(void)count;errno=EBADF;return -1; }
int _write(int fd, const char *buf, int count) { (void)fd;(void)buf;(void)count;errno=EBADF;return -1; }
int _lseek(int fd, int offset, int whence) { (void)fd;(void)offset;(void)whence;errno=EBADF;return -1; }
int _fstat(int fd, struct stat *s) { (void)fd; s->st_mode=S_IFCHR; return 0; }
int _isatty(int fd) { (void)fd; return 0; }
