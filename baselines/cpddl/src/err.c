/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/err.h"

static void printSourceFilePointer(FILE *fout,
                                   const pddl_err_source_file_ptr_t *p)
{
    if (!p->is_set)
        return;
    FILE *fin = fopen(p->fn, "r");
    if (fin == NULL){
        fprintf(fout, "%s:%d:%d: Cannot open the file\n", p->fn, p->line, p->column);
        return;
    }

    int start_line = p->line - p->num_preceding_lines;
    if (start_line < 1)
        start_line = 1;

    fprintf(fout, "%s:%d:%d:\n", p->fn, p->line, p->column);

    char *lbuf = NULL;
    size_t lsize = 0;
    ssize_t readsize = 0;
    for (int line = 1;
            line <= p->line && (readsize = getline(&lbuf, &lsize, fin)) > 0;
            ++line){

        // Never print more than 180 characters per line unless necessary
        int maxprintlinesize = 180 - 9; // -9 for "% 6d | "
        if (line == p->line)
            maxprintlinesize = PDDL_MAX(maxprintlinesize, p->column + 10);
        if (lsize > maxprintlinesize){
            strcpy(lbuf + maxprintlinesize - 7, " [...]");
            lbuf[maxprintlinesize - 1] = '\n';
            lbuf[maxprintlinesize] = '\x0';
        }

        if (line >= start_line)
            fprintf(fout, "% 6d | %s", line, lbuf);
    }
    fprintf(fout, "       | ");
    for (int i = 1; i < p->column; ++i){
        if (lbuf[i - 1] == '\t'){
            fprintf(fout, "\t");
        }else{
            fprintf(fout, " ");
        }
    }
    fprintf(fout, "^--- here\n");
    fclose(fin);
}

static void pddlErrPrintMsg(const pddl_err_t *err, FILE *fout)
{
    if (!err->err)
        return;

    fprintf(fout, "Error: %s\n", err->msg);
    printSourceFilePointer(fout, &err->err_source_file);
    fflush(fout);
}

static void pddlErrPrintTraceback(const pddl_err_t *err, FILE *fout)
{
    if (!err->err)
        return;

    fprintf(fout, "Traceback:\n");
    for (int i = 0; i < err->trace_depth; ++i){
        for (int j = 0; j < i; ++j)
            fprintf(fout, "  ");
        fprintf(fout, "  ");
        fprintf(fout, "%s:%d (%s)\n",
                err->trace[i].filename,
                err->trace[i].line,
                err->trace[i].func);
    }
    fflush(fout);
}

void pddlErrInit(pddl_err_t *err)
{
    ZEROIZE(err);
}

int pddlErrIsSet(const pddl_err_t *err)
{
    if (err == NULL)
        return 0;
    return err->err;
}

void pddlErrPrint(const pddl_err_t *err, int with_traceback, FILE *fout)
{
    if (err == NULL)
        return;
    pddlErrPrintMsg(err, fout);
    if (with_traceback)
        pddlErrPrintTraceback(err, fout);
}

void pddlErrLogEnable(pddl_err_t *err, FILE *fout)
{
    if (err == NULL)
        return;
    err->log_out = fout;
}

void pddlErrLogPause(pddl_err_t *err)
{
    if (err == NULL)
        return;
    err->log_out_pause = err->log_out;
    err->log_out = NULL;
}

void pddlErrLogContinue(pddl_err_t *err)
{
    if (err == NULL)
        return;
    err->log_out = err->log_out_pause;
    err->log_out_pause = NULL;
}

void pddlErrLogDisablePrintResources(pddl_err_t *err, int disable)
{
    if (err == NULL)
        return;
    err->log_print_resources_disabled = disable;
}

void pddlErrFlush(pddl_err_t *err)
{
    if (err == NULL)
        return;
    if (err->log_out != NULL)
        fflush(err->log_out);
}

void pddlErrSetSourceFilePointer(pddl_err_t *err,
                                 const char *source_file_name,
                                 int line_number,
                                 int column_number,
                                 int num_additional_preceding_lines)
{
    PANIC_IF(strlen(source_file_name) >= PDDL_ERR_PATH_MAXLEN,
             "The path '%s' is too long.", source_file_name);

    err->err_source_file.is_set = 1;
    strcpy(err->err_source_file.fn, source_file_name);
    err->err_source_file.line = line_number;
    err->err_source_file.column = column_number;
    err->err_source_file.num_preceding_lines = num_additional_preceding_lines;
}

void _pddlErr(pddl_err_t *err, const char *filename, int line, const char *func,
              const char *format, ...)
{
    if (err == NULL)
        return;

    va_list ap;

    err->trace[0].filename = filename;
    err->trace[0].line = line;
    err->trace[0].func = func;
    err->trace_depth = 1;
    err->trace_more = 0;

    va_start(ap, format);
    vsnprintf(err->msg, PDDL_ERR_MSG_MAXLEN, format, ap);
    va_end(ap);
    err->err = 1;
}

void _pddlPanic(const char *filename, int line, const char *func,
                const char *format, ...)
{
    va_list ap;
    va_start(ap, format);
    fprintf(stderr, "FATAL ERROR: %s:%d [%s]: ", filename, line, func);
    vfprintf(stderr, format, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    exit(-1);
}

void _pddlErrPrepend(pddl_err_t *err, const char *format, ...)
{
    if (err == NULL)
        return;

    va_list ap;
    char msg[PDDL_ERR_MSG_MAXLEN];
    int size;

    strcpy(msg, err->msg);
    va_start(ap, format);
    size = vsnprintf(err->msg, PDDL_ERR_MSG_MAXLEN, format, ap);
    snprintf(err->msg + size, PDDL_ERR_MSG_MAXLEN - size, "%s", msg);
    va_end(ap);

}

void _pddlTrace(pddl_err_t *err, const char *filename, int line, const char *func)
{
    if (err == NULL)
        return;

    if (err->trace_depth == PDDL_ERR_TRACE_DEPTH){
        err->trace_more = 1;
    }else{
        err->trace[err->trace_depth].filename = filename;
        err->trace[err->trace_depth].line = line;
        err->trace[err->trace_depth].func = func;
        ++err->trace_depth;
    }
}

void _pddlCtx(pddl_err_t *err, int time, const char *fmt, ...)
{
    if (err == NULL || err->ctx_size == PDDL_ERR_CTX_MAXLEN)
        return;

    pddl_err_ctx_t *ctx = err->ctx + err->ctx_size++;

    va_list ap;
    va_start(ap, fmt);
    vsnprintf(ctx->prefix, PDDL_ERR_CTX_PREFIX_MAXLEN, fmt, ap);
    va_end(ap);
    ctx->prefix[PDDL_ERR_CTX_PREFIX_MAXLEN - 1] = '\0';

    ctx->use_time = time;
    if (time){
        pddlTimerStart(&ctx->timer);
        _pddlLog(err, "BEGIN");
    }
}

void _pddlCtxEnd(pddl_err_t *err)
{
    if (err != NULL && err->ctx_size > 0){
        pddl_err_ctx_t *ctx = err->ctx + err->ctx_size - 1;
        if (ctx->use_time){
            pddlTimerStop(&ctx->timer);
            if (err->log_print_resources_disabled){
                _pddlLog(err, "END");
            }else{
                _pddlLog(err, "END elapsed time: %.3f",
                         pddlTimerElapsedInSF(&ctx->timer));
            }
        }
        --err->ctx_size;
    }
}

static void logResources(pddl_err_t *err)
{
    if (!err->log_timer_init){
        pddlTimerStart(&err->log_timer);
        err->log_timer_init = 1;
    }

    if (err->log_out == NULL)
        return;

    if (!err->log_print_resources_disabled){
        struct rusage usg;
        long peak_mem = 0L;
        if (getrusage(RUSAGE_SELF, &usg) == 0)
            peak_mem = usg.ru_maxrss / 1024L;
        pddlTimerStop(&err->log_timer);
        fprintf(err->log_out, "[%.3fs %ldMB] ",
                pddlTimerElapsedInSF(&err->log_timer), peak_mem);
    }
}

void _pddlLog(pddl_err_t *err, const char *fmt, ...)
{
    if (err == NULL || err->log_out == NULL)
        return;

    logResources(err);
    for (int pi = 0; pi < err->ctx_size; ++pi)
        fprintf(err->log_out, "%s: ", err->ctx[pi].prefix);

    va_list va;
    va_start(va, fmt);
    vfprintf(err->log_out, fmt, va);
    fprintf(err->log_out, "\n");
    fflush(err->log_out);
    va_end(va);
}
