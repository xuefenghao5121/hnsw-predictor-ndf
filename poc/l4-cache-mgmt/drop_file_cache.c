// drop_file_cache.c - Evict page cache for specified files using posix_fadvise
// Usage: ./drop_file_cache <file1> [file2] ...
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "Usage: %s <file1> [file2] ...\n", argv[0]); return 1; }
    for (int i = 1; i < argc; i++) {
        int fd = open(argv[i], O_RDONLY);
        if (fd < 0) { perror(argv[i]); continue; }
        struct stat st;
        if (fstat(fd, &st) < 0) { perror("fstat"); close(fd); continue; }
        if (posix_fadvise(fd, 0, st.st_size, POSIX_FADV_DONTNEED) < 0) {
            perror("posix_fadvise");
        } else {
            printf("Evicted %s (%ld bytes)\n", argv[i], (long)st.st_size);
        }
        close(fd);
    }
    return 0;
}
