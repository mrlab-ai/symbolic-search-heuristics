/***
 * Copyright (c)2025 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/opts.h"
#include "pddl/iarr.h"
#include "pddl/sarr.h"
#include "internal.h"

enum pddl_opts_opt_type {
    PDDL_OPTS_BOOL = 1,
    PDDL_OPTS_INT,
    PDDL_OPTS_FLT,
    PDDL_OPTS_DBL,
    PDDL_OPTS_STR,
    PDDL_OPTS_STR_REMAINDER,
};
typedef enum pddl_opts_opt_type pddl_opts_opt_type_t;

struct pddl_opts_opt {
    /** Type of the option -- see above */
    pddl_opts_opt_type_t type;
    /** Long name that appears as --{long_name} on the command line */
    char *long_name;
    /** Short name that appears as -{short_name} */
    char short_name;
    /** Destination where the value is stored */
    void *dst;
    int *dst_size;
    /** Textual description for help */
    char *desc;

    /** True if the option was set */
    pddl_bool_t is_set;
    /** Value of the option */
    union {
        pddl_bool_t val_bool;
        int val_int;
        float val_flt;
        double val_dbl;
        const char *val_str;
        pddl_sarr_t val_str_arr;
    } val;
};

struct pddl_opts_cmd {
    int cmd_id;
    char *name;
    char *desc;
    pddl_bool_t is_set;
    pddl_opts_opts_t req;
    pddl_opts_opts_t opt;
};



static void pddlOptsOptInitEmpty(pddl_opts_opt_t *opt)
{
    ZEROIZE(opt);
}

static void pddlOptsOptInit(pddl_opts_opt_t *opt,
                            pddl_opts_opt_type_t type,
                            const char *long_name,
                            char short_name,
                            void *dst,
                            const char *desc)
{
    opt->type = type;
    if (long_name != NULL)
        opt->long_name = STRDUP(long_name);
    opt->short_name = short_name;
    opt->dst = dst;
    if (desc != NULL)
        opt->desc = STRDUP(desc);
}

static void pddlOptsOptFree(pddl_opts_opt_t *opt)
{
    if (opt->long_name != NULL)
        FREE(opt->long_name);
    if (opt->desc != NULL)
        FREE(opt->desc);

    if (opt->type == PDDL_OPTS_STR_REMAINDER){
        pddlSArrFree(&opt->val.val_str_arr);
    }
}

static pddl_bool_t optIsAccumulative(const pddl_opts_opt_t *opt)
{
    if (opt->type == PDDL_OPTS_STR_REMAINDER)
        return pddl_true;
    return pddl_false;
}

static int checkMultiSet(const pddl_opts_opt_t *opt,
                         const char *opt_name,
                         const char *req_name)
{
    if (opt->is_set && !optIsAccumulative(opt)){
        if (opt_name != NULL){
            fprintf(stderr, "Error: The option '%s' is used multiple times.\n",
                    opt_name);

        }else if (req_name != NULL){
            fprintf(stderr, "Error: The argument {%s} is used multiple times.\n",
                    req_name);

        }else if (opt->long_name != NULL){
            fprintf(stderr, "Error: The option '%s' is used multiple times.\n",
                    opt->long_name);
        }else{
            fprintf(stderr, "Error: The option is used multiple times.\n");
        }
        return -1;
    }
    return 0;
}

static int optSetBool(pddl_opts_opt_t *opt,
                      const char *opt_name,
                      const char *req_name)
{
    if (checkMultiSet(opt, opt_name, req_name) != 0)
        return -1;
    opt->is_set = pddl_true;
    opt->val.val_bool = pddl_true;
    return 0;
}

static int optSetNoBool(pddl_opts_opt_t *opt,
                        const char *opt_name,
                        const char *req_name)
{
    if (checkMultiSet(opt, opt_name, req_name) != 0)
        return -1;
    opt->is_set = pddl_true;
    opt->val.val_bool = pddl_false;
    return 0;
}

enum {
    OPT_SET_STATUS_OK = 0,
    OPT_SET_STATUS_INVALID = 1,
    OPT_SET_STATUS_NOT_INT = 2,
    OPT_SET_STATUS_TWICE = 3,
};

static int optSetBoolVal(pddl_opts_opt_t *opt, const char *val)
{
    if (strcmp(val, "false") == 0 || strcmp(val, "0") == 0){
        opt->is_set = pddl_true;
        opt->val.val_bool = pddl_false;
        return OPT_SET_STATUS_OK;

    }else if (strcmp(val, "true") == 0 || strcmp(val, "1") == 0){
        opt->is_set = pddl_true;
        opt->val.val_bool = pddl_true;
        return OPT_SET_STATUS_OK;

    }else{
        return OPT_SET_STATUS_INVALID;
    }
}

static int optSetInt(pddl_opts_opt_t *opt, const char *val)
{
    char *end;
    long v = strtol(val, &end, 10);
    if (*end != 0x0){
        return OPT_SET_STATUS_INVALID;
    }
    if (v >= INT_MAX || v <= INT_MIN){
        return OPT_SET_STATUS_NOT_INT;
    }
    opt->is_set = pddl_true;
    opt->val.val_int = v;
    return OPT_SET_STATUS_OK;
}

static int optSetFlt(pddl_opts_opt_t *opt, const char *val)
{
    char *end;
    float v = strtof(val, &end);
    if (*end != 0x0){
        return OPT_SET_STATUS_INVALID;
    }
    opt->is_set = pddl_true;
    opt->val.val_flt = v;
    return OPT_SET_STATUS_OK;
}

static int optSetDbl(pddl_opts_opt_t *opt, const char *val)
{
    char *end;
    double v = strtod(val, &end);
    if (*end != 0x0){
        return OPT_SET_STATUS_INVALID;
    }
    opt->is_set = pddl_true;
    opt->val.val_dbl = v;
    return OPT_SET_STATUS_OK;
}

static int optSetStr(pddl_opts_opt_t *opt, const char *val)
{
    opt->is_set = pddl_true;
    opt->val.val_str = val;
    return OPT_SET_STATUS_OK;
}

static int optAddStrRemainder(pddl_opts_opt_t *opt, const char *val)
{
    opt->is_set = pddl_true;
    pddlSArrAdd(&opt->val.val_str_arr, val);
    return OPT_SET_STATUS_OK;
}

static int optSetVal(pddl_opts_opt_t *opt,
                     const char *val,
                     const char *opt_name,
                     const char *req_name)
{
    if (checkMultiSet(opt, opt_name, req_name) != 0)
        return -1;

    int st = 0;
    switch (opt->type){
        case PDDL_OPTS_BOOL:
            st = optSetBoolVal(opt, val);
            break;
        case PDDL_OPTS_INT:
            st = optSetInt(opt, val);
            break;
        case PDDL_OPTS_FLT:
            st = optSetFlt(opt, val);
            break;
        case PDDL_OPTS_DBL:
            st = optSetDbl(opt, val);
            break;
        case PDDL_OPTS_STR:
            st = optSetStr(opt, val);
            break;
        case PDDL_OPTS_STR_REMAINDER:
            st = optAddStrRemainder(opt, val);
            break;
    }

    if (st == OPT_SET_STATUS_OK)
        return 0;

    if (st == OPT_SET_STATUS_INVALID){
        if (opt_name != NULL){
            fprintf(stderr, "Error: Invalid value '%s' for the option %s.\n",
                    val, opt_name);

        }else if (req_name != NULL){
            fprintf(stderr, "Error: Invalid value '%s' for the required"
                    " argument {%s}.\n", val, req_name);

        }else{
            fprintf(stderr, "Error: Invalid value '%s.\n'", val);
        }

    }else if (st == OPT_SET_STATUS_NOT_INT){
        if (opt_name != NULL){
            fprintf(stderr, "Error: The value '%s' for the option %s is"
                    " not an integer.\n", val, opt_name);

        }else if (req_name != NULL){
            fprintf(stderr, "Error: The value '%s' for the required"
                    " argument {%s} is not an integer.\n", val, req_name);

        }else{
            fprintf(stderr, "Error: The value '%s' is not an integer.\n", val);
        }
    }

    return -1;
}


static void pddlOptsOptsFree(pddl_opts_opts_t *o)
{
    for (int i = 0; i < o->opt_size; ++i)
        pddlOptsOptFree(&o->opt[i]);
    if (o->opt != NULL)
        FREE(o->opt);
}

static pddl_opts_opt_t *pddlOptsOptsAdd(pddl_opts_opts_t *o)
{
    if (o->opt_alloc == o->opt_size){
        if (o->opt_alloc == 0)
            o->opt_alloc = 1;
        o->opt_alloc *= 2;
        o->opt = REALLOC_ARR(o->opt, pddl_opts_opt_t, o->opt_alloc);
    }

    pddl_opts_opt_t *opt = o->opt + o->opt_size++;
    pddlOptsOptInitEmpty(opt);
    return opt;
}


static void pddlOptsCmdInitEmpty(pddl_opts_cmd_t *opt)
{
    ZEROIZE(opt);
}

static void pddlOptsCmdFree(pddl_opts_cmd_t *cmd)
{
    if (cmd->name != NULL)
        FREE(cmd->name);
    if (cmd->desc != NULL)
        FREE(cmd->desc);
    pddlOptsOptsFree(&cmd->req);
    pddlOptsOptsFree(&cmd->opt);
}


static void pddlOptsCmdsFree(pddl_opts_cmds_t *c)
{
    for (int i = 0; i < c->cmd_size; ++i)
        pddlOptsCmdFree(&c->cmd[i]);
    if (c->cmd != NULL)
        FREE(c->cmd);
}

static pddl_opts_cmd_t *pddlOptsCmdsAdd(pddl_opts_cmds_t *c)
{
    if (c->cmd_alloc == c->cmd_size){
        if (c->cmd_alloc == 0)
            c->cmd_alloc = 1;
        c->cmd_alloc *= 2;
        c->cmd = REALLOC_ARR(c->cmd, pddl_opts_cmd_t, c->cmd_alloc);
    }

    pddl_opts_cmd_t *cmd = c->cmd + c->cmd_size++;
    pddlOptsCmdInitEmpty(cmd);
    return cmd;
}



static pddl_opts_opt_t *_pddlOptsOpt(pddl_opts_t *opts,
                                     pddl_opts_opt_type_t type,
                                     const char *long_name,
                                     char short_name,
                                     void *dst,
                                     const char *desc)
{
    pddl_opts_opt_t *opt = NULL;
    if (opts->set_cur_cmd != NULL){
        opt = pddlOptsOptsAdd(&opts->set_cur_cmd->opt);
    }else{
        opt = pddlOptsOptsAdd(&opts->opt);
    }

    pddlOptsOptInit(opt, type, long_name, short_name, dst, desc);
    return opt;
}

static pddl_opts_opt_t *_pddlOptsReq(pddl_opts_t *opts,
                                     pddl_opts_opt_type_t type,
                                     const char *long_name,
                                     void *dst,
                                     const char *desc)
{
    PANIC_IF(long_name == NULL, "Required arguments has to be named!");
    PANIC_IF(opts->set_cur_cmd == NULL, "Required argument can be added only to a command.");
    pddl_opts_opt_t *opt = pddlOptsOptsAdd(&opts->set_cur_cmd->req);
    pddlOptsOptInit(opt, type, long_name, 0x0, dst, desc);
    return opt;
}

static pddl_opts_opt_t *_findOptLong(char *name, pddl_opts_opts_t *opts,
                                     pddl_bool_t *no_variant)
{
    for (int i = 0; i < opts->opt_size; i++){
        if (opts->opt[i].long_name != NULL
                && strcmp(opts->opt[i].long_name, name) == 0)
            return opts->opt + i;

        if (opts->opt[i].long_name != NULL
                && opts->opt[i].type == PDDL_OPTS_BOOL
                && strncmp(name, "no-", 3) == 0
                && strcmp(opts->opt[i].long_name, name + 3) == 0){
            *no_variant = pddl_true;
            return opts->opt + i;
        }
    }
    return NULL;
}

static pddl_opts_opt_t *findOptLong(char *_arg,
                                    pddl_opts_opts_t *opts1,
                                    pddl_opts_opts_t *opts2,
                                    pddl_bool_t *no_variant)
{
    pddl_opts_opt_t *opt = _findOptLong(_arg, opts1, no_variant);
    if (opt == NULL && opts2 != NULL)
        return _findOptLong(_arg, opts2, no_variant);
    return opt;
}

static pddl_opts_opt_t *_findOptShort(char sname, pddl_opts_opts_t *opts)
{
    for (int i = 0; i < opts->opt_size; i++){
        if (sname == opts->opt[i].short_name)
            return opts->opt + i;
    }
    return NULL;
}

static pddl_opts_opt_t *findOptShort(char sname,
                                    pddl_opts_opts_t *opts1,
                                    pddl_opts_opts_t *opts2)
{
    pddl_opts_opt_t *opt = _findOptShort(sname, opts1);
    if (opt == NULL && opts2 != NULL)
        return _findOptShort(sname, opts2);
    return opt;
}

static pddl_opts_opt_t *findOpt(char *arg,
                                pddl_opts_opts_t *opts1,
                                pddl_opts_opts_t *opts2,
                                pddl_bool_t *no_variant)
{
    *no_variant = pddl_false;
    if (arg[0] == '-'){
        if (arg[1] == '-'){
            return findOptLong(arg + 2, opts1, opts2, no_variant);

        }else if (arg[1] == 0x0 || arg[2] != 0x0){
            return NULL;

        }else{
            return findOptShort(arg[1], opts1, opts2);
        }
    }

    return NULL;
}

static pddl_opts_cmd_t *findCmd(char *arg, pddl_opts_cmds_t *cmds)
{
    for (int i = 0; i < cmds->cmd_size; ++i){
        if (strcmp(arg, cmds->cmd[i].name) == 0)
            return cmds->cmd + i;
    }

    return NULL;
}

static void propagateValueOpt(pddl_opts_opt_t *opt)
{
    if (!opt->is_set)
        return;

    switch (opt->type){
        case PDDL_OPTS_BOOL:
            *(pddl_bool_t *)opt->dst = opt->val.val_bool;
            break;
        case PDDL_OPTS_INT:
            *(int *)opt->dst = opt->val.val_int;
            break;
        case PDDL_OPTS_FLT:
            *(float *)opt->dst = opt->val.val_flt;
            break;
        case PDDL_OPTS_DBL:
            *(double *)opt->dst = opt->val.val_dbl;
            break;
        case PDDL_OPTS_STR:
            *(char **)opt->dst = (char *)opt->val.val_str;
            break;
        case PDDL_OPTS_STR_REMAINDER:
            *(char ***)opt->dst = (char **)opt->val.val_str_arr.arr;
            *(int *)opt->dst_size = opt->val.val_str_arr.size;
            break;
    }
}

static void propagateValuesOpts(pddl_opts_opts_t *o)
{
    for (int oi = 0; oi < o->opt_size; ++oi){
        pddl_opts_opt_t *opt = o->opt + oi;
        if (opt->is_set)
            propagateValueOpt(opt);
    }
}

static void propagateValues(pddl_opts_t *opts)
{
    propagateValuesOpts(&opts->opt);
    for (int ci = 0; ci < opts->cmd.cmd_size; ++ci){
        if (opts->cmd.cmd[ci].is_set){
            propagateValuesOpts(&opts->cmd.cmd[ci].req);
            propagateValuesOpts(&opts->cmd.cmd[ci].opt);
        }
    }
}

void pddlOptsInit(pddl_opts_t *opts)
{
    ZEROIZE(opts);
}

void pddlOptsFree(pddl_opts_t *opts)
{
    pddlOptsOptsFree(&opts->opt);
    pddlOptsCmdsFree(&opts->cmd);
}

#define __pddlOptsOptFunc(Name, dst_type, TYPE) \
void pddlOpts##Name(pddl_opts_t *opts, \
                    const char *long_name, \
                    char short_name, \
                    dst_type *dst, \
                    const char *desc) \
{ \
    _pddlOptsOpt(opts, (TYPE), long_name, short_name, (void *)dst, desc); \
}

__pddlOptsOptFunc(Bool, pddl_bool_t, PDDL_OPTS_BOOL)
__pddlOptsOptFunc(Int, int, PDDL_OPTS_INT)
__pddlOptsOptFunc(Flt, float, PDDL_OPTS_FLT)
__pddlOptsOptFunc(Dbl, double, PDDL_OPTS_DBL)
__pddlOptsOptFunc(Str, char *, PDDL_OPTS_STR)

#define __pddlOptsReqFunc(Name, dst_type, TYPE) \
void pddlOptsReq##Name(pddl_opts_t *opts, \
                       const char *long_name, \
                       dst_type *dst, \
                       const char *desc) \
{ \
    _pddlOptsReq(opts, (TYPE), long_name, (void *)dst, desc); \
}

__pddlOptsReqFunc(Bool, pddl_bool_t, PDDL_OPTS_BOOL)
__pddlOptsReqFunc(Int, int, PDDL_OPTS_INT)
__pddlOptsReqFunc(Flt, float, PDDL_OPTS_FLT)
__pddlOptsReqFunc(Dbl, double, PDDL_OPTS_DBL)
__pddlOptsReqFunc(Str, char *, PDDL_OPTS_STR)

void pddlOptsReqStrRemainder(pddl_opts_t *opts,
                             const char *name,
                             char ***dst,
                             int *dst_size,
                             const char *desc)
{
    pddl_opts_opt_t *opt = _pddlOptsReq(opts, PDDL_OPTS_STR_REMAINDER,
                                        name, dst, desc);
    opt->dst_size = dst_size;
}


void pddlOptsCmd(pddl_opts_t *opts, int cmd_id, const char *cmd,
                 const char *desc)
{
    PANIC_IF(cmd == NULL, "command has to have a name");
    PANIC_IF(cmd_id <= 0, "command ID must be >0");
    pddl_opts_cmd_t *c = pddlOptsCmdsAdd(&opts->cmd);
    c->cmd_id = cmd_id;
    c->name = STRDUP(cmd);
    if (desc != NULL)
        c->desc = STRDUP(desc);

    opts->set_cur_cmd = c;
}


int pddlOptsParse(pddl_opts_t *opts, int argc, char *argv[], int *cmd_out)
{
    int st = 0;
    pddl_bool_t after_two_dashes = pddl_false;
    pddl_opts_cmd_t *cmd = NULL;
    int next_req = 0;
    int next_req_remainder = -1;
    *cmd_out = -1;

    if (argc <= 1)
        return 0;

    int argi = 0;
    for (argi = 1; argi < argc; argi++){
        if (strcmp(argv[argi], "--") == 0){
            after_two_dashes = pddl_true;
            continue;
        }

        // Find next option.
        // If the command is not set yet, use only global options.
        // If the command is set, first search among command's options and
        // then among global options.
        pddl_opts_opt_t *opt = NULL;
        pddl_bool_t no_variant = pddl_false;
        if (!after_two_dashes){
            if (cmd == NULL){
                opt = findOpt(argv[argi], &opts->opt, NULL, &no_variant);
            }else{
                opt = findOpt(argv[argi], &cmd->opt, &opts->opt, &no_variant);
            }
        }

        if (opt == NULL){
            // Option was not recognized. This may mean either:
            // (a) We arrived at the command name, if the command is not set yet.
            // (b) It is a required argument
            if (cmd == NULL){
                // (a) command is not set yet, so it must be a command name
                if ((cmd = findCmd(argv[argi], &opts->cmd)) == NULL){
                    fprintf(stderr, "Error: Expecting command, but found"
                            " unrecognized '%s'.\n", argv[argi]);
                    st = -1;
                    break;
                }
                cmd->is_set = pddl_true;
                *cmd_out = cmd->cmd_id;
                continue;
            }

            // (b) the command is set and therefore it must be a required
            //     argument -- we use iterator next_req to keep track of
            //     which required argument we are looking for
            if (!after_two_dashes && strncmp(argv[argi], "-", 1) == 0){
                fprintf(stderr, "Error: Unrecognized option '%s'.\n",
                        argv[argi]);
                st = -1;
                break;
            }

            pddl_opts_opt_t *req = NULL;
            if (next_req_remainder >= 0){
                req = cmd->req.opt + next_req_remainder;

            }else if (cmd->req.opt_size <= next_req){
                fprintf(stderr, "Error: Unrecognized option `%s'\n", argv[argi]);
                st = -1;
                break;

            }else{
                req = cmd->req.opt + next_req++;
            }

            if (optSetVal(req, argv[argi], NULL, req->long_name) != 0){
                st = -1;
                break;
            }
            if (req->type == PDDL_OPTS_STR_REMAINDER)
                next_req_remainder = next_req - 1;

            continue;
        }


        if (opt != NULL){
            if (opt->type == PDDL_OPTS_BOOL){
                if (no_variant){
                    if (optSetNoBool(opt, argv[argi], NULL) != 0){
                        st = -1;
                        break;
                    }
                }else{
                    if (optSetBool(opt, argv[argi], NULL) != 0){
                        st = -1;
                        break;
                    }
                }
            }else{
                if (argi + 1 >= argc){
                    fprintf(stderr, "Error: Missing value for the option %s\n",
                            argv[argi]);
                    st = -1;
                    break;
                }

                if (optSetVal(opt, argv[argi + 1], argv[argi], NULL) != 0){
                    st = -1;
                    break;
                }
                ++argi;
            }
        }
    }

    propagateValues(opts);

    if (st != 0)
        return st;

    if (cmd == NULL){
        fprintf(stderr, "Error: Missing command!\n");
        return -1;

    }else if (next_req < cmd->req.opt_size){
        fprintf(stderr, "Error: Missing required arguments: ");
        for (int i = next_req; i < cmd->req.opt_size; ++i){
            fprintf(stderr, " {%s}", cmd->req.opt[i].long_name);
        }
        fprintf(stderr, "\n");
        return -1;

    }else if (argi != argc){
        fprintf(stderr, "Error: Unrecognized arguments: \"");
        for (int i = argi; i < argc; ++i)
            fprintf(stderr, " %s", argv[i]);
        fprintf(stderr, "\".\n");
    }

    return 0;
}

static int optsMaxLen(const pddl_opts_opts_t *opts)
{
    int maxlen = 0;
    for (int i = 0; i < opts->opt_size; ++i){
        const pddl_opts_opt_t *opt = opts->opt + i;

        int len = 0;
        if (opt->long_name != NULL){
            len = 2 + strlen(opt->long_name);
            if (opt->type == PDDL_OPTS_BOOL){
                len += 5;
            }
            if (opt->short_name != 0x0){
                len += 3;
            }
        }else{
            len = 2;
        }
        maxlen = PDDL_MAX(maxlen, len);
    }
    return maxlen;
}

static void optsPrintVal(const pddl_opts_opt_t *opt, FILE *fout)
{
    fprintf(fout, " (value: ");
    switch (opt->type){
        case PDDL_OPTS_BOOL:
            if (*(pddl_bool_t *)opt->dst){
                fprintf(fout, "true");
            }else{
                fprintf(fout, "false");
            }
            break;
        case PDDL_OPTS_INT:
            fprintf(fout, "%d", *(int *)opt->dst);
            break;
        case PDDL_OPTS_FLT:
            fprintf(fout, "%.4f", *(float *)opt->dst);
            break;
        case PDDL_OPTS_DBL:
            fprintf(fout, "%.4f", *(double *)opt->dst);
            break;
        case PDDL_OPTS_STR:
            {
                const char *s = *(char **)opt->dst;
                if (s == NULL){
                    fprintf(fout, "nil");
                }else{
                    fprintf(fout, "\"%s\"", s);
                }
            }
            break;
        case PDDL_OPTS_STR_REMAINDER:
            for (int i = 0; i < *opt->dst_size; ++i){
                if (i > 0)
                    fprintf(fout, " ");
                const char *s = (*(char ***)opt->dst)[i];
                if (s == NULL){
                    fprintf(fout, "nil");
                }else{
                    fprintf(fout, "\"%s\"", s);
                }
            }
            break;
    }
    fprintf(fout, ")");
}

static void printDesc(const char *desc, int indent, FILE *fout)
{
    if (desc == NULL)
        return;

    int maxlen = 120 - indent;
    int len = strlen(desc);
    int ci = 0;
    while (ci < len){
        int end = PDDL_MIN(ci + maxlen, len);
        // Go backwards to find a word separator
        while (end > ci
                && end < len
                && desc[end - 1] != ' '
                && desc[end - 1] != '\t'
                && desc[end - 1] != '\n'){
            --end;
        }
        // If we didn't find out, give up and just live with breaking in
        // the middle of the word
        if (end == ci + 1)
            end = PDDL_MIN(ci + maxlen, len);

        // Indent next line (except for the first one).
        if (ci != 0){
            fprintf(fout, "\n");
            for (int i = 0; i < indent; ++i)
                fprintf(fout, " ");
        }
        for (; ci < end; ++ci){
            if (desc[ci] == '\n'){
                // When breaking, we need to print indent
                ++ci;
                break;
            }
            fprintf(fout, "%c", desc[ci]);
        }
    }
}

static void optsPrint(const pddl_opts_opts_t *opts,
                      int indent,
                      pddl_bool_t is_req,
                      FILE *fout)
{
    int width = optsMaxLen(opts);
    for (int i = 0; i < opts->opt_size; ++i){
        const pddl_opts_opt_t *opt = opts->opt + i;

        for (int j = 0; j < indent; ++j)
            fprintf(fout, " ");
        int prefixlen = indent;

        int len = 0;
        if (opt->long_name != NULL){
            if (is_req){
                fprintf(fout, "{%s}", opt->long_name);
                len += 2 + strlen(opt->long_name);

            }else if (opt->type == PDDL_OPTS_BOOL){
                fprintf(fout, "--(no-)%s", opt->long_name);
                len += 7 + strlen(opt->long_name);
            }else{
                fprintf(fout, "--%s", opt->long_name);
                len += 2 + strlen(opt->long_name);
            }
        }

        if (opt->short_name != 0x0){
            if (opt->long_name != NULL){
                fprintf(fout, "/");
                len += 1;
            }
            fprintf(fout, "-%c", opt->short_name);
            len += 2;
        }
        for (int i = len; i < width; ++i)
            fprintf(fout, " ");
        prefixlen += width;

        fprintf(fout, "  ");
        prefixlen += 2;

        switch (opt->type){
            case PDDL_OPTS_BOOL:
                fprintf(fout, "   ");
                break;
            case PDDL_OPTS_INT:
                fprintf(fout, "int");
                break;
            case PDDL_OPTS_FLT:
                fprintf(fout, "flt");
                break;
            case PDDL_OPTS_DBL:
                fprintf(fout, "dbl");
                break;
            case PDDL_OPTS_STR:
                fprintf(fout, "str");
                break;
            case PDDL_OPTS_STR_REMAINDER:
                fprintf(fout, "str");
                break;
        }
        prefixlen += 3;

        if (opt->desc != NULL){
            fprintf(fout, "  ");
            printDesc(opt->desc, prefixlen + 2, fout);
        }
        optsPrintVal(opt, fout);
        fprintf(fout, "\n");
    }
}

void pddlOptsPrint(const pddl_opts_t *opts, const char *prog, FILE *fout)
{
    pddlOptsPrintCmd(opts, prog, INT_MIN, fout);
}

void pddlOptsPrintCmd(const pddl_opts_t *opts, const char *prog,
                      int cmd_id, FILE *fout)
{
    const char *cmdname = "COMMAND";
    if (cmd_id != INT_MIN){
        for (int cmdi = 0; cmdi < opts->cmd.cmd_size; ++cmdi){
            const pddl_opts_cmd_t *cmd = opts->cmd.cmd + cmdi;
            if (cmd->cmd_id == cmd_id){
                cmdname = cmd->name;
                break;
            }
        }

    }

    fprintf(fout, "Usage: %s [GLOBAL OPTIONS] %s [OPTIONS] ...\n",
            prog, cmdname);
    fprintf(fout, "\n");
    fprintf(fout, "GLOBAL OPTIONS:\n");
    optsPrint(&opts->opt, 2, pddl_false, fout);
    fprintf(fout, "\n");

    for (int cmdi = 0; cmdi < opts->cmd.cmd_size; ++cmdi){
        const pddl_opts_cmd_t *cmd = opts->cmd.cmd + cmdi;
        if (cmd_id != INT_MIN && cmd->cmd_id != cmd_id)
            continue;

        fprintf(fout, "COMMAND %s", cmd->name);
        if (cmd->opt.opt_size > 0)
            fprintf(fout, " [OPTIONS]");
        for (int ri = 0; ri < cmd->req.opt_size; ++ri){
            fprintf(fout, " {%s}", cmd->req.opt[ri].long_name);
            if (cmd->req.opt[ri].type == PDDL_OPTS_STR_REMAINDER)
                fprintf(fout, "...");
        }
        fprintf(fout, "\n");

        if (cmd->desc != NULL){
            fprintf(fout, "\n");
            fprintf(fout, "  ");
            printDesc(cmd->desc, 2, fout);
            fprintf(fout, "\n");
        }

        if (cmd->req.opt_size > 0){
            fprintf(fout, "\n");
            fprintf(fout, "  REQUIRED:\n");
            optsPrint(&cmd->req, 4, pddl_true, fout);
        }
        if (cmd->opt.opt_size > 0){
            fprintf(fout, "\n");
            fprintf(fout, "  OPTIONS:\n");
            optsPrint(&cmd->opt, 4, pddl_false, fout);
        }
        fprintf(fout, "\n");
    }
}
