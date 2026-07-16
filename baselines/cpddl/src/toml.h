/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef _PDDL_TOML_H_
#define _PDDL_TOML_H_

#include <pddl/common.h>
#include <pddl/err.h>
#include "_toml.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_TOML_FN_MAXSIZE 256
#define PDDL_TOML_PATH_MAXSIZE 1024
#define PDDL_TOML_STACK_MAXSIZE 8
#define PDDL_TOML_ERR_MSG_MAXSIZE (2 * PDDL_TOML_PATH_MAXSIZE)

struct pddl_toml_ctx{
    pddl_toml_table_t *table;
    int path_idx;
};
typedef struct pddl_toml_ctx pddl_toml_ctx_t;

struct pddl_toml {
    /** Filename of the input .toml file */
    char fn[PDDL_TOML_FN_MAXSIZE];
    /** Root table of the parsed file */
    pddl_toml_table_t *root;
    /** String representing path to the element on the of the stack. Used
     *  for error messages. */
    char cur_path[PDDL_TOML_PATH_MAXSIZE];
    /** Size of .cur_path to avoid calling strlen() */
    int cur_path_size;
    /** Stack of tables -- see pddlTomlPush/Pop() */
    pddl_toml_ctx_t stack[PDDL_TOML_STACK_MAXSIZE];
    int stack_size;
    /** True if an error was detected. Once true all functions refuse to do
     *  anything. */
    pddl_bool_t err;
    /** Stored error message */
    char err_msg[PDDL_TOML_ERR_MSG_MAXSIZE];
};
typedef struct pddl_toml pddl_toml_t;

/**
 * Open and parse the input .toml file.
 * Returns 0 on success, -1 on error.
 */
int pddlTomlInitFile(pddl_toml_t *t, const char *fn, pddl_err_t *err);

/**
 * Free allocated memory.
 */
void pddlTomlFree(pddl_toml_t *t);

/**
 * Push table on the stack thus changing the current context.
 * If the specificied table is not in the current context, it is considered
 * as an error.
 * Returns 0 on success, -1 on error.
 */
int pddlTomlPush(pddl_toml_t *t, const char *key);

/**
 * As pddlTomlPush() but it requires that {key} is an array and its element
 * on index {idx} is a table which gets pushed on top of the stack.
 */
int pddlTomlPushFromArr(pddl_toml_t *t, const char *key, int idx);

/**
 * Pop table from top of the stack.
 */
void pddlTomlPop(pddl_toml_t *t);

/**
 * Retrieval functions.
 * Return 0 on success.
 * If required is true, but the key is not found, then it is considered an
 * error and -1 is returnd.
 * If required is false and the key is not found, nothin happens and 1 is
 * returned.
 */
int pddlTomlInt(pddl_toml_t *t, const char *key, int *dst, pddl_bool_t required);
int pddlTomlFlt(pddl_toml_t *t, const char *key, float *dst, pddl_bool_t req);
int pddlTomlDbl(pddl_toml_t *t, const char *key, double *dst, pddl_bool_t req);
int pddlTomlBool(pddl_toml_t *t, const char *key, pddl_bool_t *dst, pddl_bool_t req);
int pddlTomlStr(pddl_toml_t *t, const char *key, char **dst, pddl_bool_t required);
int pddlTomlArrStr(pddl_toml_t *t, const char *key, char ***dst, int *dst_size,
                   pddl_bool_t required);

/**
 * Returns number of elements of the given array, if {key} is not an array,
 * then -1 is returned.
 */
int pddlTomlArrSize(pddl_toml_t *t, const char *key);

/**
 * Returns true if error was set at any point, in which case also sets the
 * error message via {err}.
 * Otherwise returns false, meaning everything worked without any error.
 */
pddl_bool_t pddlTomlErr(pddl_toml_t *t, pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* _PDDL_TOML_H_ */
