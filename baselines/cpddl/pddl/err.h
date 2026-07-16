/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ERR_H__
#define __PDDL_ERR_H__

#include <pddl/timer.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/** Maximal length of an error message */
#define PDDL_ERR_MSG_MAXLEN 4096
/** Maximal length of an error prefix */
#define PDDL_ERR_MSG_PREFIX_MAXLEN 32
/** Maximal depth of a trace */
#define PDDL_ERR_TRACE_DEPTH 32
/** Maximal length of a prefix */
#define PDDL_ERR_PREFIX_MAXLEN 32
/** Number of prefixes */
#define PDDL_ERR_PREFIX_NUM 8
/** Maximum number of contexts */
#define PDDL_ERR_CTX_MAXLEN 32
/** Maximum length of each prefix */
#define PDDL_ERR_CTX_PREFIX_MAXLEN 32
/** Maximum length of a path */
#define PDDL_ERR_PATH_MAXLEN 1024


struct pddl_err_trace {
    const char *filename;
    int line;
    const char *func;
};
typedef struct pddl_err_trace pddl_err_trace_t;

struct pddl_err_ctx {
    char prefix[PDDL_ERR_CTX_PREFIX_MAXLEN];
    int use_time;
    pddl_timer_t timer;
};
typedef struct pddl_err_ctx pddl_err_ctx_t;

struct pddl_err_source_file_ptr {
    /** True if this is set */
    int is_set;
    /** Path to the source file */
    char fn[PDDL_ERR_PATH_MAXLEN];
    /** Line to print */
    int line;
    /** Column to point at */
    int column;
    /** Number of additional preceding lines that should be printed */
    int num_preceding_lines;
};
typedef struct pddl_err_source_file_ptr pddl_err_source_file_ptr_t;

struct pddl_err {
    pddl_err_trace_t trace[PDDL_ERR_TRACE_DEPTH];
    int trace_depth;
    int trace_more;
    char msg[PDDL_ERR_MSG_MAXLEN];
    int err;

    pddl_err_ctx_t ctx[PDDL_ERR_CTX_MAXLEN];
    int ctx_size;

    FILE *log_out;
    FILE *log_out_pause;
    int log_print_resources_disabled;
    pddl_timer_t log_timer;
    int log_timer_init;

    pddl_err_source_file_ptr_t err_source_file;
};
typedef struct pddl_err pddl_err_t;

#define PDDL_ERR_INIT { 0 }

/**
 * Initialize error structure.
 */
void pddlErrInit(pddl_err_t *err);

/**
 * Returns true if an error message is set.
 */
int pddlErrIsSet(const pddl_err_t *err);

/**
 * Print the stored error message.
 */
void pddlErrPrint(const pddl_err_t *err, int with_traceback, FILE *fout);

/**
 * Enable/disable info messages.
 */
void pddlErrLogEnable(pddl_err_t *err, FILE *fout);

/**
 * Temporarily disable logging.
 */
void pddlErrLogPause(pddl_err_t *err);

/**
 * Continue logging after it was previously paused by pddlErrLogPause()
 */
void pddlErrLogContinue(pddl_err_t *err);

/**
 * Disable printing resources with PDDL_LOG
 */
void pddlErrLogDisablePrintResources(pddl_err_t *err, int disable);

/**
 * Flush all buffers.
 */
void pddlErrFlush(pddl_err_t *err);

/**
 * Sets source file with identification of the line and column of the
 * error. The line and column numbers start at 1.
 */
void pddlErrSetSourceFilePointer(pddl_err_t *err,
                                 const char *source_file_name,
                                 int line_number,
                                 int column_number,
                                 int num_additional_preceding_lines);

/**
 * Sets error message and starts tracing the calls.
 */
#define PDDL_ERR(E, ...) \
    _pddlErr((E), __FILE__, __LINE__, __func__, __VA_ARGS__)

/**
 * Same as PDDL_ERR() but also returns the value V immediatelly.
 */
#define PDDL_ERR_RET(E, V, ...) do { \
        PDDL_ERR((E), __VA_ARGS__); \
        return (V); \
    } while (0)


/**
 * Fatal error that causes exit.
 */
#define PDDL_PANIC(...) _pddlPanic(__FILE__, __LINE__, __func__, __VA_ARGS__)
#define PDDL_PANIC_IF(COND, ...) do { \
        if (!!(COND)) PDDL_PANIC(__VA_ARGS__); \
    } while (0)


/**
 * Prints warning.
 */
#define PDDL_WARN(E, ...) \
    _pddlLog((E), "WARNING: " __VA_ARGS__)

/**
 * Enter another level of context.
 */
#define PDDL_CTX(E, ...) _pddlCtx((E), 1, __VA_ARGS__)
#define PDDL_CTX_NO_TIME(E, ...) _pddlCtx((E), 0, __VA_ARGS__)

/**
 * Leave current context.
 */
#define PDDL_CTXEND(E) _pddlCtxEnd(E)

/**
 * Prints a log line with timestamp and memory consumption.
 */
#define PDDL_LOG(E, ...) _pddlLog((E), __VA_ARGS__)
#define PDDL_LOG_IN_CTX(E, CTX_I, format, ...) \
    do { \
        PDDL_CTX_NO_TIME((E), (CTX_I)); \
        PDDL_LOG((E), format, __VA_ARGS__); \
        PDDL_CTXEND((E)); \
    } while (0)


/**
 * Trace the error -- record the current file, line and function.
 */
#define PDDL_TRACE(E) \
   _pddlTrace((E), __FILE__, __LINE__, __func__)

/**
 * Same as PDDL_TRACE() but also returns the value V.
 */
#define PDDL_TRACE_RET(E, V) do { \
        PDDL_TRACE(E); \
        return (V); \
    } while (0)

/**
 * Prepends the message before the current error message and trace the
 * call.
 */
#define PDDL_TRACE_PREPEND(E, format, ...) do { \
        _pddlErrPrepend((E), format, __VA_ARGS__); \
        PDDL_TRACE(E); \
    } while (0)
#define PDDL_TRACE_PREPEND_RET(E, V, format, ...) do { \
        _pddlErrPrepend((E), format, __VA_ARGS__); \
        PDDL_TRACE_RET((E), V); \
    } while (0)


void _pddlErr(pddl_err_t *err, const char *filename, int line, const char *func,
              const char *format, ...) __PDDL_ATTR_PRINTF(5, 6);
void _pddlPanic(const char *filename, int line, const char *func,
                const char *format, ...) __PDDL_ATTR_PRINTF(4, 5);
void _pddlErrPrepend(pddl_err_t *err, const char *format, ...);
void _pddlTrace(pddl_err_t *err, const char *fn, int line, const char *func);
void _pddlCtx(pddl_err_t *err, int time, const char *info, ...)
    __PDDL_ATTR_PRINTF(3, 4);
void _pddlCtxEnd(pddl_err_t *err);
void _pddlLog(pddl_err_t *err, const char *fmt, ...) __PDDL_ATTR_PRINTF(2, 3);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_ERR_H__ */
