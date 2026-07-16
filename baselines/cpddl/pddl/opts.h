/***
 * Copyright (c)2025 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_OPTS_H__
#define __PDDL_OPTS_H__

#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef struct pddl_opts_opt pddl_opts_opt_t;
typedef struct pddl_opts_cmd pddl_opts_cmd_t;

struct pddl_opts_opts {
    pddl_opts_opt_t *opt;
    int opt_size;
    int opt_alloc;
};
typedef struct pddl_opts_opts pddl_opts_opts_t;

struct pddl_opts_cmds {
    pddl_opts_cmd_t *cmd;
    int cmd_size;
    int cmd_alloc;
};
typedef struct pddl_opts_cmds pddl_opts_cmds_t;

struct pddl_opts {
    pddl_opts_opts_t opt;
    pddl_opts_cmds_t cmd;
    pddl_opts_cmd_t *set_cur_cmd;
};
typedef struct pddl_opts pddl_opts_t;

/**
 * Initialize empty set of options.
 */
void pddlOptsInit(pddl_opts_t *opts);

/**
 * Free allocated memory.
 */
void pddlOptsFree(pddl_opts_t *opts);

/**
 * Add option --{long_name}/-{short_name}.
 * {dst} is where the value will be stored when the option is used.
 */
void pddlOptsBool(pddl_opts_t *opts,
                  const char *long_name,
                  char short_name,
                  pddl_bool_t *dst,
                  const char *desc);
void pddlOptsInt(pddl_opts_t *opts,
                 const char *long_name,
                 char short_name,
                 int *dst,
                 const char *desc);
void pddlOptsFlt(pddl_opts_t *opts,
                 const char *long_name,
                 char short_name,
                 float *dst,
                 const char *desc);
void pddlOptsDbl(pddl_opts_t *opts,
                 const char *long_name,
                 char short_name,
                 double *dst,
                 const char *desc);
void pddlOptsStr(pddl_opts_t *opts,
                 const char *long_name,
                 char short_name,
                 char **dst,
                 const char *desc);

/**
 * Add required argument. {name} must be non-empty. {dst} is where the
 * value is stored.
 * Required arguments can be used only within a command (see pddlOptsCmd()
 * below).
 */
void pddlOptsReqBool(pddl_opts_t *opts,
                     const char *name,
                     pddl_bool_t *dst,
                     const char *desc);
void pddlOptsReqInt(pddl_opts_t *opts,
                    const char *name,
                    int *dst,
                    const char *desc);
void pddlOptsReqFlt(pddl_opts_t *opts,
                    const char *name,
                    float *dst,
                    const char *desc);
void pddlOptsReqDbl(pddl_opts_t *opts,
                    const char *name,
                    double *dst,
                    const char *desc);
void pddlOptsReqStr(pddl_opts_t *opts,
                    const char *name,
                    char **dst,
                    const char *desc);

/**
 * Required argument that accumulates the remainder of arguments, i.e., it
 * results in one or more string arguments.
 */
void pddlOptsReqStrRemainder(pddl_opts_t *opts,
                             const char *name,
                             char ***dst,
                             int *dst_size,
                             const char *desc);

/**
 * Adds a command, subsequent calls to pddlOpts*() add options and required
 * arguments specific to this command.
 * The name {cmd} must be non-empty and unique.
 * {cmd_id} must be a unique identifier >0.
 * It is callers responsibility to keep track of command IDs and there are
 * no checks whether {cmd} or {cmd_id} is repeated.
 *
 * All options and required arguments add after calling this function will
 * be added to this command.
 */
void pddlOptsCmd(pddl_opts_t *opts, int cmd_id, const char *cmd,
                 const char *desc);

int pddlOptsParse(pddl_opts_t *opts, int argc, char *argv[], int *cmd);

/**
 * Prints formatted help for all options, commands, etc.
 */
void pddlOptsPrint(const pddl_opts_t *opts, const char *prog, FILE *fout);

/**
 * Prints formatted help for the specified command.
 */
void pddlOptsPrintCmd(const pddl_opts_t *opts, const char *prog,
                      int cmd_id, FILE *fout);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_OPTS_H__ */
