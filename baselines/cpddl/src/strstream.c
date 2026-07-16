/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"

#ifdef __MACH__
# include <wchar.h>

/**
 * The code related to open_memstream (pddl_strstream) was adapted from
 * FreeBSD source https://github.com/freebsd/freebsd-src, file
 * lib/libc/stdio/open_memstream.c:
 * Copyright (c) 2013 Hudson River Trading LLC
 * Written by: John H. Baldwin <jhb@FreeBSD.org>
 * All rights reserved.
 *
 * The code related to fmemopen (pddl_staticstrstream) was adapted from
 * FreeBSD source https://github.com/freebsd/freebsd-src, file
 * lib/libc/stdio/fmemopen.c:
 * Copyright (C) 2013 Pietro Cerutti <gahr@FreeBSD.org>
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 * OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */

#define    FPOS_MAX    OFF_MAX

struct memstream {
    char **bufp;
    size_t *sizep;
    ssize_t len;
    fpos_t offset;
};

static int
memstream_grow(struct memstream *ms, fpos_t newoff)
{
    char *buf;
    ssize_t newsize;

    if (newoff < 0 || newoff >= SSIZE_MAX)
        newsize = SSIZE_MAX - 1;
    else
        newsize = newoff;
    if (newsize > ms->len) {
        buf = realloc(*ms->bufp, newsize + 1);
        if (buf != NULL) {
            memset(buf + ms->len + 1, 0, newsize - ms->len);
            *ms->bufp = buf;
            ms->len = newsize;
            return (1);
        }
        return (0);
    }
    return (1);
}

static void
memstream_update(struct memstream *ms)
{

    ASSERT(ms->len >= 0 && ms->offset >= 0);
    *ms->sizep = ms->len < ms->offset ? ms->len : ms->offset;
}

static int
memstream_write(void *cookie, const char *buf, int len)
{
    struct memstream *ms;
    ssize_t tocopy;

    ms = cookie;
    if (!memstream_grow(ms, ms->offset + len))
        return (-1);
    tocopy = ms->len - ms->offset;
    if (len < tocopy)
        tocopy = len;
    memcpy(*ms->bufp + ms->offset, buf, tocopy);
    ms->offset += tocopy;
    memstream_update(ms);
    return (tocopy);
}

static fpos_t
memstream_seek(void *cookie, fpos_t pos, int whence)
{
    struct memstream *ms;

    ms = cookie;
    switch (whence) {
    case SEEK_SET:
        /* _fseeko() checks for negative offsets. */
        ASSERT(pos >= 0);
        ms->offset = pos;
        break;
    case SEEK_CUR:
        /* This is only called by _ftello(). */
        ASSERT(pos == 0);
        break;
    case SEEK_END:
        if (pos < 0) {
            if (pos + ms->len < 0) {
                errno = EINVAL;
                return (-1);
            }
        } else {
            if (FPOS_MAX - ms->len < pos) {
                errno = EOVERFLOW;
                return (-1);
            }
        }
        ms->offset = ms->len + pos;
        break;
    }
    memstream_update(ms);
    return (ms->offset);
}

static int
memstream_close(void *cookie)
{

    free(cookie);
    return (0);
}

FILE * pddl_strstream(char **bufp, size_t *sizep)
{
    struct memstream *ms;
    int save_errno;
    FILE *fp;

    if (bufp == NULL || sizep == NULL) {
        errno = EINVAL;
        return (NULL);
    }
    *bufp = calloc(1, 1);
    if (*bufp == NULL)
        return (NULL);
    ms = malloc(sizeof(*ms));
    if (ms == NULL) {
        save_errno = errno;
        free(*bufp);
        *bufp = NULL;
        errno = save_errno;
        return (NULL);
    }
    ms->bufp = bufp;
    ms->sizep = sizep;
    ms->len = 0;
    ms->offset = 0;
    memstream_update(ms);
    fp = funopen(ms, NULL, memstream_write, memstream_seek,
        memstream_close);
    if (fp == NULL) {
        save_errno = errno;
        free(ms);
        free(*bufp);
        *bufp = NULL;
        errno = save_errno;
        return (NULL);
    }
    fwide(fp, -1);
    return (fp);
}


struct fmemopen_cookie
{
    char    *buf;    /* pointer to the memory region */
    size_t     size;    /* buffer length in bytes */
    size_t     len;    /* data length in bytes */
    size_t     off;    /* current offset into the buffer */
};

static int
fmemopen_write(void *cookie, const char *buf, int nbytes)
{
    struct fmemopen_cookie *ck = cookie;

    if (nbytes > ck->size - ck->off)
        nbytes = ck->size - ck->off;

    if (nbytes == 0)
        return (0);

    memcpy(ck->buf + ck->off, buf, nbytes);

    ck->off += nbytes;

    if (ck->off > ck->len)
        ck->len = ck->off;

    /*
     * We append a NULL byte if all these conditions are met:
     * - the buffer is not full
     * - the data just written doesn't already end with a NULL byte
     */
    if (ck->off < ck->size && ck->buf[ck->off - 1] != '\0')
        ck->buf[ck->off] = '\0';

    return (nbytes);
}

static fpos_t
fmemopen_seek(void *cookie, fpos_t offset, int whence)
{
    struct fmemopen_cookie *ck = cookie;


    switch (whence) {
    case SEEK_SET:
        if (offset > ck->size) {
            errno = EINVAL;
            return (-1);
        }
        ck->off = offset;
        break;

    case SEEK_CUR:
        if (ck->off + offset > ck->size) {
            errno = EINVAL;
            return (-1);
        }
        ck->off += offset;
        break;

    case SEEK_END:
        if (offset > 0 || -offset > ck->len) {
            errno = EINVAL;
            return (-1);
        }
        ck->off = ck->len + offset;
        break;

    default:
        errno = EINVAL;
        return (-1);
    }

    return (ck->off);
}

static int
fmemopen_close(void *cookie)
{
    struct fmemopen_cookie *ck = cookie;
    free(ck);
    return (0);
}

FILE *pddl_staticstrstream(char *buf, size_t size)
{
    struct fmemopen_cookie *ck;
    FILE *f;

    /*
     * POSIX says we shall return EINVAL if size is 0.
     */
    if (size == 0) {
        errno = EINVAL;
        return (NULL);
    }

    /*
     * There's no point in requiring an automatically allocated buffer
     * in write-only mode.
     */
    if (buf == NULL) {
        errno = EINVAL;
        return (NULL);
    }

    ck = malloc(sizeof(struct fmemopen_cookie));
    if (ck == NULL) {
        return (NULL);
    }

    ck->off  = 0;
    ck->size = size;
    ck->buf = buf;
    ck->buf[0] = '\0';

    f = funopen(ck, NULL, fmemopen_write, fmemopen_seek, fmemopen_close);

    if (f == NULL) {
        free(ck);
        return (NULL);
    }

    /*
     * Turn off buffering, so a write past the end of the buffer
     * correctly returns a short object count.
     */
    setvbuf(f, NULL, _IONBF, 0);

    return (f);
}

#else /* __MACH__ */

FILE *pddl_strstream(char **str, size_t *strsize)
{
    return open_memstream(str, strsize);
}

FILE *pddl_staticstrstream(char *str, size_t strsize)
{
    return fmemopen(str, strsize, "w");
}

#endif /* __MACH__ */
