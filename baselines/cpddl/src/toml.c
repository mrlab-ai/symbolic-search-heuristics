/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "toml.h"

#define TERR(T, RET, ...) \
    do { \
        snprintf((T)->err_msg, PDDL_TOML_ERR_MSG_MAXSIZE, __VA_ARGS__); \
        (T)->err = pddl_true; \
        return RET; \
    } while (0)

int pddlTomlInitFile(pddl_toml_t *t, const char *fn, pddl_err_t *err)
{
    ZEROIZE(t);
    FILE *fin = fopen(fn, "r");
    if (fin == NULL)
        ERR_RET(err, -1, "Cannot open file %s", fn);

    t->root = pddl_toml_parse_file(fin, err);
    fclose(fin);
    if (t->root == NULL)
        TRACE_RET(err, -1);
    snprintf(t->fn, PDDL_TOML_FN_MAXSIZE, "%s", fn);

    t->cur_path_size = 0;
    t->stack[0].table = t->root;
    t->stack[0].path_idx = 0;
    t->stack_size = 1;
    return 0;
}

void pddlTomlFree(pddl_toml_t *t)
{
    if (t->root != NULL)
        pddl_toml_free(t->root);
}

int pddlTomlPush(pddl_toml_t *t, const char *key)
{
    if (t->err)
        return 1;

    PANIC_IF(t->stack_size == PDDL_TOML_STACK_MAXSIZE,
             "Maximum allowed number of nested tables in a .toml"
             " configuration file is %d", PDDL_TOML_STACK_MAXSIZE);

    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1;
    PANIC_IF(c->path_idx + strlen(key) + 1 >= PDDL_TOML_PATH_MAXSIZE,
             "Maximum allowed length of a path of keys in a .toml"
             " configuration file is %d", PDDL_TOML_PATH_MAXSIZE);

    if (!pddl_toml_key_exists(c->table, key)){
        TERR(t, -1, "Key %s%s not found in the config file %s",
             t->cur_path, key, t->fn);
    }

    pddl_toml_table_t *table = pddl_toml_table_in(c->table, key);
    if (table == NULL){
        TERR(t, -1, "Key %s%s in the config file %s is not a table",
             t->cur_path, key, t->fn);
    }

    pddl_toml_ctx_t *next = t->stack + t->stack_size++;
    next->table = table;
    int written = sprintf(t->cur_path + t->cur_path_size, "%s/", key);
    next->path_idx = t->cur_path_size;
    t->cur_path_size += written;

    return 0;
}

int pddlTomlPushFromArr(pddl_toml_t *t, const char *key, int idx)
{
    if (t->err)
        return 1;

    PANIC_IF(t->stack_size == PDDL_TOML_STACK_MAXSIZE,
             "Maximum allowed number of nested tables in a .toml"
             " configuration file is %d", PDDL_TOML_STACK_MAXSIZE);

    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1;
    PANIC_IF(c->path_idx + strlen(key) + 1 >= PDDL_TOML_PATH_MAXSIZE,
             "Maximum allowed length of a path of keys in a .toml"
             " configuration file is %d", PDDL_TOML_PATH_MAXSIZE);

    if (!pddl_toml_key_exists(c->table, key)){
        TERR(t, -1, "Key %s%s not found in the config file %s",
             t->cur_path, key, t->fn);
    }

    const pddl_toml_array_t *arr = pddl_toml_array_in(c->table, key);
    if (arr == NULL){
        TERR(t, -1, "Key %s/%s in the config file %s is not an array",
             t->cur_path, key, t->fn);
    }

    pddl_toml_table_t *table = pddl_toml_table_at(arr, idx);
    if (table == NULL){
        TERR(t, -1, "Key %s%s[%d] in the config file %s is not a table",
             t->cur_path, key, idx, t->fn);
    }

    pddl_toml_ctx_t *next = t->stack + t->stack_size++;
    next->table = table;
    int written = sprintf(t->cur_path + t->cur_path_size, "%s[%d]/", key, idx);
    next->path_idx = t->cur_path_size;
    t->cur_path_size += written;

    return 0;
}

void pddlTomlPop(pddl_toml_t *t)
{
    if (t->err)
        return;

    if (t->stack_size <= 1)
        return;
    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1;
    t->cur_path[c->path_idx] = '\x0';
    t->cur_path_size = c->path_idx;
    --t->stack_size;
}

#define READ_FN(name_suff, dst_type, dst_type_name, read_fn, read_enum) \
int pddlToml##name_suff(pddl_toml_t *t, \
                        const char *key, \
                        dst_type *dst, \
                        pddl_bool_t required) \
{ \
    if (t->err) \
        return 1; \
    \
    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1; \
    if (!pddl_toml_key_exists(c->table, key)){ \
        if (required){ \
            TERR(t, -1, "Key %s%s not found in the config file %s", \
                 t->cur_path, key, t->fn); \
        } \
        return 1; \
    } \
    \
    pddl_toml_datum_t d = pddl_toml_##read_fn##_in(c->table, key); \
    if (!d.ok){ \
        TERR(t, -1, "Key %s%s in the config file %s is not an " \
             #dst_type_name, t->cur_path, key, t->fn); \
    } \
    *dst = d.u.read_enum; \
    return 0; \
}

READ_FN(Int, int, integer, int, i)
READ_FN(Flt, float, double, double, d)
READ_FN(Dbl, double, double, double, d)
READ_FN(Bool, pddl_bool_t, boolean, bool, b)
READ_FN(Str, char *, string, string, s)

int pddlTomlArrStr(pddl_toml_t *t, const char *key, char ***dst, int *dst_size,
                   pddl_bool_t required)
{
    if (t->err)
        return 1;

    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1;
    if (!pddl_toml_key_exists(c->table, key)){
        if (required){
            TERR(t, -1, "Key %s%s not found in the config file %s",
                 t->cur_path, key, t->fn);
        }
        return 1;
    }

    const pddl_toml_array_t *arr = pddl_toml_array_in(c->table, key);
    if (arr == NULL){
        TERR(t, -1, "Key %s/%s in the config file %s is not an array",
             t->cur_path, key, t->fn);
    }

    if (pddl_toml_array_kind(arr) != 'v'
            || pddl_toml_array_type(arr) != 's'){
        TERR(t, -1, "Key %s%s in the config file %s is not an array"
             " of strings", t->cur_path, key, t->fn);
    }

    int size = pddl_toml_array_nelem(arr);
    *dst = ZALLOC_ARR(char *, size);
    *dst_size = size;
    for (int i = 0; i < size; ++i){
        pddl_toml_datum_t d = pddl_toml_string_at(arr, i);
        ASSERT(d.ok && d.u.s != NULL);
        (*dst)[i] = d.u.s;
    }
    return 0;
}

int pddlTomlArrSize(pddl_toml_t *t, const char *key)
{
    if (t->err)
        return -1;

    pddl_toml_ctx_t *c = t->stack + t->stack_size - 1;
    if (!pddl_toml_key_exists(c->table, key))
        return -1;

    const pddl_toml_array_t *arr = pddl_toml_array_in(c->table, key);
    if (arr == NULL)
        return -1;

    return pddl_toml_array_nelem(arr);
}

pddl_bool_t pddlTomlErr(pddl_toml_t *t, pddl_err_t *err)
{
    if (t->err)
        ERR_RET(err, pddl_true, "%s", t->err_msg);
    return pddl_false;
}
