/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/subprocess.h"

static void waitForSubprocess(pid_t pid, pddl_exec_status_t *status)
{
    int wstatus;
    waitpid(pid, &wstatus, 0);
    if (WIFEXITED(wstatus)){
        if (status != NULL){
            status->exited = 1;
            status->exit_status = WEXITSTATUS(wstatus);
        }

    }else if (WIFSIGNALED(wstatus)){
        if (status != NULL){
            status->signaled = 1;
            status->signum = WTERMSIG(wstatus);
        }
    }
}

#define CMD_BUFSIZ 1024
#define READ_INIT_BUFSIZ 256
static void logCommand(char *const argv[], pddl_err_t *err)
{
    char cmd[CMD_BUFSIZ];
    int written = 0;
    for (int i = 0; argv[i] != NULL && CMD_BUFSIZ - written > 0; ++i)
        written += snprintf(cmd + written, CMD_BUFSIZ - written, " '%s'", argv[i]);
    LOG(err, "Command:%s", cmd);
}

struct buf {
    char *buf;
    int size;
    int alloc;

    char **out;
    int *outsize;
};

static void bufInit(struct buf *buf, char **out, int *outsize)
{
    if (out != NULL){
        *out = NULL;
        *outsize = 0;
    }
    ZEROIZE(buf);
    buf->out = out;
    buf->outsize = outsize;
}

static void bufAlloc(struct buf *buf)
{
    ASSERT(buf->out != NULL);
    if (buf->alloc == buf->size){
        if (buf->alloc == 0)
            buf->alloc = READ_INIT_BUFSIZ;
        buf->alloc *= 2;
        buf->buf = REALLOC_ARR(buf->buf, char, buf->alloc);
    }
}

static int bufRead(struct buf *buf, int fd)
{
    ASSERT(buf->out != NULL);
    bufAlloc(buf);
    int remain = buf->alloc - buf->size;
    ssize_t r = read(fd, buf->buf + buf->size, remain);
    if (r > 0){
        buf->size += r;
        return 0;

    }else if (r < 0){
        return -2;
    }
    return -1;
}

static void bufFinalize(struct buf *buf)
{
    if (buf->out == NULL)
        return;

    bufAlloc(buf);
    buf->buf[buf->size] = '\x0';
    *buf->out = buf->buf;
    *buf->outsize = buf->size;
}

int pddlExecvp(char *const argv[],
               pddl_exec_status_t *status,
               const char *write_stdin,
               int write_stdin_size,
               char **read_stdout,
               int *read_stdout_size,
               char **read_stderr,
               int *read_stderr_size,
               pddl_err_t *err)
{
    return pddlExecvpLimits(argv, status,
                            write_stdin, write_stdin_size,
                            read_stdout, read_stdout_size,
                            read_stderr, read_stderr_size,
                            -1., -1, err);
}

int pddlExecvpLimits(char *const argv[],
                     pddl_exec_status_t *status,
                     const char *write_stdin,
                     int write_stdin_size,
                     char **read_stdout,
                     int *read_stdout_size,
                     char **read_stderr,
                     int *read_stderr_size,
                     float time_limit_in_s,
                     int mem_limit_in_mb,
                     pddl_err_t *err)
{
    CTX(err, "exec");
    logCommand(argv, err);
    fflush(stdout);
    fflush(stderr);
    pddlErrFlush(err);

    if (status != NULL)
        ZEROIZE(status);

    pddl_timer_t timer;
    pddlTimerStart(&timer);
    struct buf bufout, buferr;
    bufInit(&bufout, read_stdout, read_stdout_size);
    bufInit(&buferr, read_stderr, read_stderr_size);

    int fd_stdin[2] = { -1, -1 };
    int fd_stdout[2] = { -1, -1 };
    int fd_stderr[2] = { -1, -1 };

    int written = 0;
    if (write_stdin != NULL){
        if (pipe(fd_stdin) != 0){
            CTXEND(err);
            ERR_RET(err, -1, "pipe() failed: %s", strerror(errno));
        }
    }
    if (read_stdout != NULL){
        if (pipe(fd_stdout) != 0){
            if (fd_stdin[0] >= 0)
                close(fd_stdin[0]);
            if (fd_stdin[1] >= 0)
                close(fd_stdin[1]);
            CTXEND(err);
            ERR_RET(err, -1, "pipe() failed: %s", strerror(errno));
        }
    }

    if (read_stderr != NULL){
        if (pipe(fd_stderr) != 0){
            if (fd_stdin[0] >= 0)
                close(fd_stdin[0]);
            if (fd_stdin[1] >= 0)
                close(fd_stdin[1]);
            if (fd_stdout[0] >= 0)
                close(fd_stdout[0]);
            if (fd_stdout[1] >= 0)
                close(fd_stdout[1]);
            CTXEND(err);
            ERR_RET(err, -1, "pipe() failed: %s", strerror(errno));
        }
    }

    pid_t pid = fork();
    if (pid < 0){
        PANIC("fork() failed: %s", strerror(errno));

    }else if (pid == 0){
        if (fd_stdin[1] >= 0)
            close(fd_stdin[1]);
        if (fd_stdin[0] >= 0){
            dup2(fd_stdin[0], STDIN_FILENO);
            close(fd_stdin[0]);
        }

        if (fd_stdout[0] >= 0)
            close(fd_stdout[0]);
        if (fd_stdout[1] >= 0){
            dup2(fd_stdout[1], STDOUT_FILENO);
            close(fd_stdout[1]);
        }else{
            int fd = open("/dev/null", O_WRONLY | O_CLOEXEC);
            if (fd >= 0){
                dup2(fd, STDOUT_FILENO);
                close(fd);
            }
        }

        if (fd_stderr[0] >= 0)
            close(fd_stderr[0]);
        if (fd_stderr[1] >= 0){
            dup2(fd_stderr[1], STDERR_FILENO);
            close(fd_stderr[1]);
        }else{
            int fd = open("/dev/null", O_WRONLY | O_CLOEXEC);
            if (fd >= 0){
                dup2(fd, STDERR_FILENO);
                close(fd);
            }
        }

        if (mem_limit_in_mb > 0){
            struct rlimit mem_limit;
            mem_limit.rlim_cur
                = mem_limit.rlim_max = mem_limit_in_mb * 1024UL * 1024UL;
            setrlimit(RLIMIT_AS, &mem_limit);
        }

        execvp(argv[0], argv);
        PANIC("exec failed: %s", strerror(errno));
    }

    sigset_t old_signals;
    sigset_t blocked_signals;
    sigemptyset(&blocked_signals);
    sigaddset(&blocked_signals, SIGPIPE);
    if (sigprocmask(SIG_BLOCK, &blocked_signals, &old_signals) != 0){
        kill(pid, SIGKILL);
        waitpid(pid, NULL, 0);
        CTXEND(err);
        ERR_RET(err, -1, "Could not block SIGPIPE signal: %s", strerror(errno));
    }

    struct pollfd pfd[3];
    int pfdsize = 0;

    if (fd_stdin[0] >= 0)
        close(fd_stdin[0]);
    if (fd_stdin[1] >= 0){
        pfd[pfdsize].fd = fd_stdin[1];
        pfd[pfdsize].events = POLLOUT | POLLWRBAND | POLLHUP;
        ++pfdsize;
    }

    if (fd_stdout[1] >= 0)
        close(fd_stdout[1]);
    if (fd_stdout[0] >= 0){
        pfd[pfdsize].fd = fd_stdout[0];
        pfd[pfdsize].events = POLLIN | POLLRDNORM | POLLRDBAND | POLLPRI | POLLHUP;
        ++pfdsize;
    }

    if (fd_stderr[1] >= 0)
        close(fd_stderr[1]);
    if (fd_stderr[0] >= 0){
        pfd[pfdsize].fd = fd_stderr[0];
        pfd[pfdsize].events = POLLIN | POLLRDNORM | POLLRDBAND | POLLPRI | POLLHUP;
        ++pfdsize;
    }

    int timelimit = -1;
    if (time_limit_in_s > 0.){
        pddlTimerStop(&timer);
        timelimit = ceil((time_limit_in_s - pddlTimerElapsedInSF(&timer)) * 1000);
        LOG(err, "Setting time limit to %d ms", timelimit);
    }

    int rpoll = 0;
    while (pfdsize > 0 && (rpoll = poll(pfd, pfdsize, timelimit)) >= 0){
        if (rpoll == 0){
            // Time limit reached, notify the child and wait for it
            // to terminate.
            pddlTimerStop(&timer);
            LOG(err, "Time limit reached (%.2fs). Sending SIGALRM to %d",
                pddlTimerElapsedInSF(&timer), pid);
            kill(pid, SIGALRM);
            // Give the child process 100ms to terminate and then kill it
            // with SIGKILL
            usleep(100UL * 1000UL);
            kill(pid, SIGKILL);
            status->timed_out = pddl_true;
            break;
        }

        pfdsize = 0;
        int fdi = 0;
        if (fd_stdin[1] >= 0){
            if ((pfd[fdi].revents & POLLOUT)
                    || (pfd[fdi].revents & POLLWRBAND)){
                int remaining = write_stdin_size - written;
                ssize_t w = write(fd_stdin[1], write_stdin, remaining);
                if (w < 0){
                    LOG(err, "Got error while writing to pipe: %s",
                        strerror(errno));
                    LOG(err, "Closing the write pipe...");
                    close(fd_stdin[1]);
                    fd_stdin[1] = -1;
                }
                if (w > 0)
                    written += w;
                if (written == write_stdin_size){
                    close(fd_stdin[1]);
                    fd_stdin[1] = -1;
                }

            }else if (pfd[fdi].revents & POLLHUP){
                close(fd_stdin[1]);
                fd_stdin[1] = -1;

            }else if (pfd[fdi].revents & POLLERR){
                LOG(err, "Cannot write to the write pipe.");
                close(fd_stdin[1]);
                fd_stdin[1] = -1;
            }

            if (fd_stdin[1] >= 0){
                pfd[pfdsize].fd = fd_stdin[1];
                pfd[pfdsize].events = POLLOUT | POLLWRBAND | POLLHUP;
                ++pfdsize;
            }
            ++fdi;
        }

        if (fd_stdout[0] >= 0){
            if ((pfd[fdi].revents & POLLIN)
                    || (pfd[fdi].revents & POLLRDNORM)
                    || (pfd[fdi].revents & POLLRDBAND)
                    || (pfd[fdi].revents & POLLPRI)){
                int st;
                if ((st = bufRead(&bufout, fd_stdout[0])) != 0){
                    if (st < -1){
                        LOG(err, "Got error while reading from stdout pipe: %s",
                            strerror(errno));
                        LOG(err, "Closing the stdout pipe...");
                    }
                    close(fd_stdout[0]);
                    fd_stdout[0] = -1;
                }

            }else if (pfd[fdi].revents & POLLHUP){
                close(fd_stdout[0]);
                fd_stdout[0] = -1;

            }else if (pfd[fdi].revents & POLLERR){
                LOG(err, "Error occurred on stdout pipe.");
                close(fd_stdin[1]);
                fd_stdin[1] = -1;
            }

            if (fd_stdout[0] >= 0){
                pfd[pfdsize].fd = fd_stdout[0];
                pfd[pfdsize].events = POLLIN | POLLRDNORM | POLLRDBAND | POLLPRI | POLLHUP;
                ++pfdsize;
            }
            ++fdi;
        }

        if (fd_stderr[0] >= 0){
            if ((pfd[fdi].revents & POLLIN)
                    || (pfd[fdi].revents & POLLRDNORM)
                    || (pfd[fdi].revents & POLLRDBAND)
                    || (pfd[fdi].revents & POLLPRI)){
                int st;
                if ((st = bufRead(&buferr, fd_stderr[0])) != 0){
                    if (st < -1){
                        LOG(err, "Got error while reading from stderr pipe: %s",
                            strerror(errno));
                        LOG(err, "Closing the stderr pipe...");
                    }
                    close(fd_stderr[0]);
                    fd_stderr[0] = -1;
                }

            }else if (pfd[fdi].revents & POLLHUP){
                close(fd_stderr[0]);
                fd_stderr[0] = -1;

            }else if (pfd[fdi].revents & POLLERR){
                LOG(err, "Error occurred on stderr pipe.");
                close(fd_stdin[1]);
                fd_stdin[1] = -1;
            }

            if (fd_stderr[0] >= 0){
                pfd[pfdsize].fd = fd_stderr[0];
                pfd[pfdsize].events = POLLIN | POLLRDNORM | POLLRDBAND | POLLPRI | POLLHUP;
                ++pfdsize;
            }
        }

        if (time_limit_in_s > 0.){
            pddlTimerStop(&timer);
            timelimit = ceil((time_limit_in_s - pddlTimerElapsedInSF(&timer)) * 1000);
            //LOG(err, "Setting time limit to %d ms", timelimit);
        }
    }

    waitForSubprocess(pid, status);

    if (fd_stdin[1] >= 0)
        close(fd_stdin[1]);
    if (fd_stdout[0] >= 0)
        close(fd_stdout[0]);
    if (fd_stderr[0] >= 0)
        close(fd_stderr[0]);

    bufFinalize(&bufout);
    bufFinalize(&buferr);

    if (write_stdin != NULL)
        LOG(err, "Written %d / %d", written, write_stdin_size);

    if (read_stdout != NULL){
        LOG(err, "Read %d bytes from stdout, allocated %d bytes",
            bufout.size, bufout.alloc);
    }

    if (read_stderr != NULL){
        LOG(err, "Read %d bytes from stderr, allocated %d bytes",
            buferr.size, buferr.alloc);
    }

    if (status != NULL){
        LOG(err, "status: exited: %d, exit_status: %d,"
            " signaled: %d, signum: %d (%s)",
            status->exited, status->exit_status,
            status->signaled, status->signum,
            (status->signaled ? strsignal(status->signum) : "" ));
    }

    CTXEND(err);

    // Restore blocking of signals
    if (sigprocmask(SIG_BLOCK, &old_signals, NULL) != 0){
        ERR_RET(err, -1, "Could not restored signal blocking: %s", strerror(errno));
    }
    return 0;
}

int pddlForkSharedMem(int (*fn)(void *sharedmem, void *userdata),
                      void *in_out_data,
                      size_t data_size,
                      void *userdata,
                      pddl_exec_status_t *status,
                      pddl_err_t *err)
{
    CTX(err, "fork");
    fflush(stdout);
    fflush(stderr);
    pddlErrFlush(err);

    if (status != NULL)
        ZEROIZE(status);

    void *shared = mmap(NULL, data_size, PROT_WRITE | PROT_READ,
                        MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (shared == MAP_FAILED){
        LOG(err, "Could not allocate shared memory of size %lu using mmap: %s",
            (unsigned long)data_size, strerror(errno));
        CTXEND(err);
        return -1;
    }

    memcpy(shared, in_out_data, data_size);
    LOG(err, "In data copied to the shared memory.");
    pid_t pid = fork();
    if (pid < 0){
        PANIC("fork() failed: %s", strerror(errno));

    }else if (pid == 0){
        int ret = fn(shared, userdata);
        exit(ret);
    }

    waitForSubprocess(pid, status);

    memcpy(in_out_data, shared, data_size);
    LOG(err, "Out data copied to the output memory.");
    if (munmap(shared, data_size) != 0){
        LOG(err, "Could not release mmaped memory: %s", strerror(errno));
        CTXEND(err);
        return -1;
    }

    CTXEND(err);
    return 0;
}

int pddlForkPipe(int (*fn)(int fdout, void *userdata),
                 void *userdata,
                 void **out,
                 int *out_size,
                 pddl_exec_status_t *status,
                 pddl_err_t *err)
{
    CTX(err, "fork");
    fflush(stdout);
    fflush(stderr);
    pddlErrFlush(err);

    if (status != NULL)
        ZEROIZE(status);

    int fd[2];
    if (pipe(fd) != 0){
        PANIC("pipe() failed: %s", strerror(errno));
    }

    pid_t pid = fork();
    if (pid < 0){
        PANIC("fork() failed: %s", strerror(errno));

    }else if (pid == 0){
        close(fd[0]);
        int ret = fn(fd[1], userdata);
        close(fd[1]);
        exit(ret);
    }

    close(fd[1]);
    struct buf buf;
    bufInit(&buf, (char **)out, out_size);
    while (bufRead(&buf, fd[0]) == 0)
        ;
    close(fd[0]);
    bufFinalize(&buf);
    LOG(err, "Read %d bytes, allocated %d bytes", buf.size, buf.alloc);

    waitForSubprocess(pid, status);
    if (status != NULL){
        LOG(err, "status: exited: %d, exit_status: %d,"
            " signaled: %d, signum: %d (%s)",
            status->exited, status->exit_status,
            status->signaled, status->signum,
            (status->signaled ? strsignal(status->signum) : "" ));
    }

    CTXEND(err);
    return 0;
}
