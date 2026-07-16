/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/sort.h"
#include "pddl/pddl.h"
#include "pddl/fm.h"
#include "pddl/strstream.h"

static char *type_names[PDDL_FM_NUM_TYPES] = {
    "and",      /* PDDL_FM_AND */
    "or",       /* PDDL_FM_OR */
    "forall",   /* PDDL_FM_FORALL */
    "exist",    /* PDDL_FM_EXIST */
    "when",     /* PDDL_FM_WHEN */
    "atom",     /* PDDL_FM_ATOM */
    "bool",     /* PDDL_FM_BOOL */
    "imply",    /* PDDL_FM_IMPLY */

    "num-exp-plus", /* PDDL_FM_NUM_EXP_PLUS */
    "num-exp-minus", /* PDDL_FM_NUM_EXP_MINUS */
    "num-exp-mult", /* PDDL_FM_NUM_EXP_MULT */
    "num-exp-div", /* PDDL_FM_NUM_EXP_DIV */
    "num-exp-fatom", /* PDDL_FM_NUM_EXP_FATOM */
    "num-exp-inum", /* PDDL_FM_NUM_EXP_INUM */
    "num-exp-fnum", /* PDDL_FM_NUM_EXP_FNUM */

    "==", /* PDDL_FM_NUM_CMP_EQ */
    "!=", /* PDDL_FM_NUM_CMP_NEQ */
    ">=", /* PDDL_FM_NUM_CMP_GE */
    "<=", /* PDDL_FM_NUM_CMP_LE */
    ">", /* PDDL_FM_NUM_CMP_GT */
    "<", /* PDDL_FM_NUM_CMP_LT */

    "assign", /* PDDL_FM_NUM_OP_ASSIGN */
    "increase", /* PDDL_FM_NUM_OP_INCREASE */
    "decrease", /* PDDL_FM_NUM_OP_DECREASE */
    "scale-up", /* PDDL_FM_NUM_OP_SCALE_UP */
    "scale-down", /* PDDL_FM_NUM_OP_SCALE_DOWN */
};
static const char *fm_type_null = "(null)";

const char *pddlFmTypeName(pddl_fm_type_t type)
{
    if (type < 0 || type >= PDDL_FM_NUM_TYPES)
        return fm_type_null;
    return type_names[type];
}

typedef void (*pddl_fm_method_del_fn)(pddl_fm_t *);
typedef pddl_fm_t *(*pddl_fm_method_clone_fn)(const pddl_fm_t *);
typedef pddl_fm_t *(*pddl_fm_method_negate_fn)(const pddl_fm_t *,
                                               const pddl_t *);
typedef pddl_bool_t (*pddl_fm_method_eq_fn)(const pddl_fm_t *,
                                            const pddl_fm_t *);
typedef int (*pddl_fm_method_traverse_fn)(pddl_fm_t *, pddl_fm_traverse_t *tr);
typedef int (*pddl_fm_method_rebuild_fn)(pddl_fm_t **c, pddl_fm_rebuild_t *rb);
typedef void (*pddl_fm_method_print_pddl_fn)(
                                             const pddl_fm_t *c,
                                             const pddl_t *pddl,
                                             const pddl_params_t *params,
                                             FILE *fout);

static pddl_bool_t fmEq(const pddl_fm_t *, const pddl_fm_t *);
static int fmTraverse(pddl_fm_t *c, pddl_fm_traverse_t *tr);
static int fmRebuild(pddl_fm_t **c, pddl_fm_rebuild_t *rb);

struct pddl_fm_cls {
    pddl_fm_method_del_fn del;
    pddl_fm_method_clone_fn clone;
    pddl_fm_method_negate_fn negate;
    pddl_fm_method_eq_fn eq;
    pddl_fm_method_traverse_fn traverse;
    pddl_fm_method_rebuild_fn rebuild;
    pddl_fm_method_print_pddl_fn print_pddl;
};
typedef struct pddl_fm_cls pddl_fm_cls_t;

#define METHOD(X, NAME) ((pddl_fm_method_##NAME##_fn)(X))
#define MCLS(NAME) \
{ \
    .del = METHOD(fm##NAME##Del, del), \
    .clone = METHOD(fm##NAME##Clone, clone), \
    .negate = METHOD(fm##NAME##Negate, negate), \
    .eq = METHOD(fm##NAME##Eq, eq), \
    .traverse = METHOD(fm##NAME##Traverse, traverse), \
    .rebuild = METHOD(fm##NAME##Rebuild, rebuild), \
    .print_pddl = METHOD(fm##NAME##PrintPDDL, print_pddl), \
}


struct parse_ctx {
    pddl_types_t *types;
    const pddl_objs_t *objs;
    const pddl_preds_t *preds;
    const pddl_preds_t *funcs;
    const pddl_params_t *params;
    const char *err_prefix;
    pddl_err_t *err;
};
typedef struct parse_ctx parse_ctx_t;

static void fmPartDel(pddl_fm_junc_t *);
static pddl_fm_junc_t *fmPartClone(const pddl_fm_junc_t *p);
static pddl_fm_junc_t *fmPartNegate(const pddl_fm_junc_t *p, const pddl_t *pddl);
static pddl_bool_t fmPartEq(const pddl_fm_junc_t *c1, const pddl_fm_junc_t *c2);
static void fmPartAdd(pddl_fm_junc_t *p, pddl_fm_t *add);
static int fmPartTraverse(pddl_fm_junc_t *, pddl_fm_traverse_t *tr);
static int fmPartRebuild(pddl_fm_junc_t **p, pddl_fm_rebuild_t *rb);
static void fmPartPrintPDDL(const pddl_fm_junc_t *p,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout);

static void fmQuantDel(pddl_fm_quant_t *);
static pddl_fm_quant_t *fmQuantClone(const pddl_fm_quant_t *q);
static pddl_fm_quant_t *fmQuantNegate(const pddl_fm_quant_t *q,
                                      const pddl_t *pddl);
static pddl_bool_t fmQuantEq(const pddl_fm_quant_t *c1,
                             const pddl_fm_quant_t *c2);
static int fmQuantTraverse(pddl_fm_quant_t *, pddl_fm_traverse_t *tr);
static int fmQuantRebuild(pddl_fm_quant_t **q, pddl_fm_rebuild_t *rb);
static void fmQuantPrintPDDL(const pddl_fm_quant_t *q,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout);

static void fmWhenDel(pddl_fm_when_t *);
static pddl_fm_when_t *fmWhenClone(const pddl_fm_when_t *w);
static pddl_fm_when_t *fmWhenNegate(const pddl_fm_when_t *w,
                                    const pddl_t *pddl);
static pddl_bool_t fmWhenEq(const pddl_fm_when_t *c1, const pddl_fm_when_t *c2);
static int fmWhenTraverse(pddl_fm_when_t *w, pddl_fm_traverse_t *tr);
static int fmWhenRebuild(pddl_fm_when_t **w, pddl_fm_rebuild_t *rb);
static void fmWhenPrintPDDL(const pddl_fm_when_t *w,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout);

static void fmAtomDel(pddl_fm_atom_t *);
static pddl_fm_atom_t *fmAtomClone(const pddl_fm_atom_t *a);
static pddl_fm_atom_t *fmAtomNegate(const pddl_fm_atom_t *a,
                                    const pddl_t *pddl);
static pddl_bool_t fmAtomEq(const pddl_fm_atom_t *c1, const pddl_fm_atom_t *c2);
static int fmAtomTraverse(pddl_fm_atom_t *, pddl_fm_traverse_t *tr);
static int fmAtomRebuild(pddl_fm_atom_t **a, pddl_fm_rebuild_t *rb);
static void fmAtomPrintPDDL(const pddl_fm_atom_t *a,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout);

static void fmBoolDel(pddl_fm_bool_t *);
static pddl_fm_bool_t *fmBoolClone(const pddl_fm_bool_t *a);
static pddl_fm_bool_t *fmBoolNegate(const pddl_fm_bool_t *a,
                                    const pddl_t *pddl);
static pddl_bool_t fmBoolEq(const pddl_fm_bool_t *c1, const pddl_fm_bool_t *c2);
static int fmBoolTraverse(pddl_fm_bool_t *, pddl_fm_traverse_t *tr);
static int fmBoolRebuild(pddl_fm_bool_t **a, pddl_fm_rebuild_t *rb);
static void fmBoolPrintPDDL(const pddl_fm_bool_t *b,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout);

static void fmImplyDel(pddl_fm_imply_t *);
static pddl_fm_imply_t *fmImplyClone(const pddl_fm_imply_t *a);
static pddl_fm_t *fmImplyNegate(const pddl_fm_imply_t *a,
                                const pddl_t *pddl);
static pddl_bool_t fmImplyEq(const pddl_fm_imply_t *c1,
                             const pddl_fm_imply_t *c2);
static int fmImplyTraverse(pddl_fm_imply_t *, pddl_fm_traverse_t *tr);
static int fmImplyRebuild(pddl_fm_imply_t **a, pddl_fm_rebuild_t *rb);
static void fmImplyPrintPDDL(const pddl_fm_imply_t *b,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout);

static void fmNumExpDel(pddl_fm_num_exp_t *);
static pddl_fm_num_exp_t *fmNumExpClone(const pddl_fm_num_exp_t *);
static pddl_fm_num_exp_t *fmNumExpNegate(const pddl_fm_num_exp_t *,
                                         const pddl_t *pddl);
static pddl_bool_t fmNumExpEq(const pddl_fm_num_exp_t *c1,
                              const pddl_fm_num_exp_t *c2);
static int fmNumExpTraverse(pddl_fm_num_exp_t *, pddl_fm_traverse_t *tr);
static int fmNumExpRebuild(pddl_fm_num_exp_t **, pddl_fm_rebuild_t *rb);
static void fmNumExpPrintPDDL(const pddl_fm_num_exp_t *,
                              const pddl_t *pddl,
                              const pddl_params_t *params,
                              FILE *fout);

static void fmNumCmpDel(pddl_fm_num_cmp_t *);
static pddl_fm_num_cmp_t *fmNumCmpClone(const pddl_fm_num_cmp_t *);
static pddl_fm_num_cmp_t *fmNumCmpNegate(const pddl_fm_num_cmp_t *,
                                         const pddl_t *pddl);
static pddl_bool_t fmNumCmpEq(const pddl_fm_num_cmp_t *c1,
                              const pddl_fm_num_cmp_t *c2);
static int fmNumCmpTraverse(pddl_fm_num_cmp_t *, pddl_fm_traverse_t *tr);
static int fmNumCmpRebuild(pddl_fm_num_cmp_t **, pddl_fm_rebuild_t *rb);
static void fmNumCmpPrintPDDL(const pddl_fm_num_cmp_t *,
                              const pddl_t *pddl,
                              const pddl_params_t *params,
                              FILE *fout);

static void fmNumOpDel(pddl_fm_num_op_t *);
static pddl_fm_num_op_t *fmNumOpClone(const pddl_fm_num_op_t *);
static pddl_fm_num_op_t *fmNumOpNegate(const pddl_fm_num_op_t *,
                                       const pddl_t *pddl);
static pddl_bool_t fmNumOpEq(const pddl_fm_num_op_t *c1,
                             const pddl_fm_num_op_t *c2);
static int fmNumOpTraverse(pddl_fm_num_op_t *, pddl_fm_traverse_t *tr);
static int fmNumOpRebuild(pddl_fm_num_op_t **, pddl_fm_rebuild_t *rb);
static void fmNumOpPrintPDDL(const pddl_fm_num_op_t *,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout);


static pddl_fm_cls_t cond_cls[PDDL_FM_NUM_TYPES] = {
    MCLS(Part),   // PDDL_FM_AND
    MCLS(Part),   // PDDL_FM_OR
    MCLS(Quant),  // PDDL_FM_FORALL
    MCLS(Quant),  // PDDL_FM_EXIST
    MCLS(When),   // PDDL_FM_WHEN
    MCLS(Atom),   // PDDL_FM_ATOM
    MCLS(Bool),   // PDDL_FM_BOOL
    MCLS(Imply),  // PDDL_FM_IMPLY

    MCLS(NumExp), // PDDL_FM_NUM_EXP_PLUS
    MCLS(NumExp), // PDDL_FM_NUM_EXP_MINUS
    MCLS(NumExp), // PDDL_FM_NUM_EXP_MULT
    MCLS(NumExp), // PDDL_FM_NUM_EXP_DIV
    MCLS(NumExp), // PDDL_FM_NUM_EXP_FATOM
    MCLS(NumExp), // PDDL_FM_NUM_EXP_INUM
    MCLS(NumExp), // PDDL_FM_NUM_EXP_FNUM

    MCLS(NumCmp), // PDDL_FM_NUM_CMP_EQ
    MCLS(NumCmp), // PDDL_FM_NUM_CMP_NEQ
    MCLS(NumCmp), // PDDL_FM_NUM_CMP_GE
    MCLS(NumCmp), // PDDL_FM_NUM_CMP_LE
    MCLS(NumCmp), // PDDL_FM_NUM_CMP_GT
    MCLS(NumCmp), // PDDL_FM_NUM_CMP_LT

    MCLS(NumOp), // PDDL_FM_NUM_OP_ASSIGN
    MCLS(NumOp), // PDDL_FM_NUM_OP_INCREASE
    MCLS(NumOp), // PDDL_FM_NUM_OP_DECREASE
    MCLS(NumOp), // PDDL_FM_NUM_OP_SCALE_UP
    MCLS(NumOp), // PDDL_FM_NUM_OP_SCALE_DOWN
};

#define fmNew(CTYPE, TYPE) \
    (CTYPE *)_fmNew(sizeof(CTYPE), TYPE)

static pddl_fm_t *_fmNew(int size, unsigned type)
{
    pddl_fm_t *c = ZMALLOC(size);
    c->type = type;
    pddlListInit(&c->conn);
    return c;
}


/*** PART ***/
static pddl_fm_junc_t *fmPartNew(int type)
{
    pddl_fm_junc_t *p = fmNew(pddl_fm_junc_t, type);
    pddlListInit(&p->part);
    return p;
}

static void fmPartDel(pddl_fm_junc_t *p)
{
    pddl_list_t *item, *tmp;
    PDDL_LIST_FOR_EACH_SAFE(&p->part, item, tmp){
        pddl_fm_t *fm = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        pddlFmDel(fm);
    }

    FREE(p);
}

static pddl_fm_junc_t *fmPartClone(const pddl_fm_junc_t *p)
{
    pddl_fm_junc_t *n;
    pddl_fm_t *c, *nc;
    pddl_list_t *item;

    n = fmPartNew(p->fm.type);
    PDDL_LIST_FOR_EACH(&p->part, item){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        nc = pddlFmClone(c);
        pddlListAppend(&n->part, &nc->conn);
    }
    return n;
}

static pddl_fm_junc_t *fmPartNegate(const pddl_fm_junc_t *p,
                                    const pddl_t *pddl)
{
    pddl_fm_junc_t *n;
    pddl_fm_t *c, *nc;
    pddl_list_t *item;

    if (p->fm.type == PDDL_FM_AND){
        n = fmPartNew(PDDL_FM_OR);
    }else{
        n = fmPartNew(PDDL_FM_AND);
    }
    PDDL_LIST_FOR_EACH(&p->part, item){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        nc = pddlFmNegate(c, pddl);
        pddlListAppend(&n->part, &nc->conn);
    }
    return n;
}

static pddl_bool_t fmPartEq(const pddl_fm_junc_t *p1,
                            const pddl_fm_junc_t *p2)
{
    pddl_fm_t *c1, *c2;
    pddl_list_t *item1, *item2;
    PDDL_LIST_FOR_EACH(&p1->part, item1){
        c1 = PDDL_LIST_ENTRY(item1, pddl_fm_t, conn);
        int found = 0;
        PDDL_LIST_FOR_EACH(&p2->part, item2){
            c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (fmEq(c1, c2)){
                found = 1;
                break;
            }
        }
        if (!found)
            return pddl_false;
    }

    return pddl_true;
}

static void fmPartAdd(pddl_fm_junc_t *p, pddl_fm_t *add)
{
    pddlListInit(&add->conn);
    pddlListAppend(&p->part, &add->conn);
}

static int fmPartTraverse(pddl_fm_junc_t *p, pddl_fm_traverse_t *tr)
{
    pddl_fm_t *c;
    pddl_list_t *item, *tmp;

    PDDL_LIST_FOR_EACH_SAFE(&p->part, item, tmp){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (fmTraverse(c, tr) != 0)
            return -1;
    }

    return 0;
}

static int fmPartRebuild(pddl_fm_junc_t **p, pddl_fm_rebuild_t *rb)
{
    pddl_fm_t *c;
    pddl_list_t *item, *last;

    if (pddlListEmpty(&(*p)->part))
        return 0;

    last = pddlListPrev(&(*p)->part);
    do {
        item = pddlListNext(&(*p)->part);
        pddlListDel(item);
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (fmRebuild(&c, rb) != 0)
            return -1;
        if (c != NULL)
            pddlListAppend(&(*p)->part, &c->conn);
    } while (item != last);

    return 0;
}

/** Moves all parts of src to dst */
static void fmPartStealPart(pddl_fm_junc_t *dst,
                            pddl_fm_junc_t *src)
{
    pddl_list_t *item;

    while (!pddlListEmpty(&src->part)){
        item = pddlListNext(&src->part);
        pddlListDel(item);
        pddlListAppend(&dst->part, item);
    }
}

static void fmPartPrintPDDL(const pddl_fm_junc_t *p,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout)
{
    pddl_list_t *item;
    const pddl_fm_t *child;


    fprintf(fout, "(");
    if (p->fm.type == PDDL_FM_AND){
        fprintf(fout, "and");
    }else if (p->fm.type == PDDL_FM_OR){
        fprintf(fout, "or");
    }
    PDDL_LIST_FOR_EACH(&p->part, item){
        child = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        //fprintf(fout, "\n        ");
        fprintf(fout, " ");
        pddlFmPrintPDDL(child, pddl, params, fout);
    }
    fprintf(fout, ")");
}


/*** QUANT ***/
static pddl_fm_quant_t *fmQuantNew(int type)
{
    return fmNew(pddl_fm_quant_t, type);
}

static void fmQuantDel(pddl_fm_quant_t *q)
{
    pddlParamsFree(&q->param);
    if (q->qfm != NULL)
        pddlFmDel(q->qfm);
    FREE(q);
}

static pddl_fm_quant_t *fmQuantClone(const pddl_fm_quant_t *q)
{
    pddl_fm_quant_t *n;

    n = fmQuantNew(q->fm.type);
    pddlParamsInitCopy(&n->param, &q->param);
    n->qfm = pddlFmClone(q->qfm);
    return n;
}

static pddl_fm_quant_t *fmQuantNegate(const pddl_fm_quant_t *q,
                                      const pddl_t *pddl)
{
    pddl_fm_quant_t *n;

    if (q->fm.type == PDDL_FM_FORALL){
        n = fmQuantNew(PDDL_FM_EXIST);
    }else{
        n = fmQuantNew(PDDL_FM_FORALL);
    }
    pddlParamsInitCopy(&n->param, &q->param);
    n->qfm = pddlFmNegate(q->qfm, pddl);
    return n;
}

static pddl_bool_t fmQuantEq(const pddl_fm_quant_t *q1,
                             const pddl_fm_quant_t *q2)
{
    if (q1->param.param_size != q2->param.param_size)
        return pddl_false;
    for (int i = 0; i < q1->param.param_size; ++i){
        if (q1->param.param[i].type != q2->param.param[i].type
                || q1->param.param[i].is_agent != q2->param.param[i].is_agent
                || q1->param.param[i].inherit != q2->param.param[i].inherit)
            return pddl_false;
    }
    return fmEq(q1->qfm, q2->qfm);
}

static int fmQuantTraverse(pddl_fm_quant_t *q, pddl_fm_traverse_t *tr)
{
    if (q->qfm)
        return fmTraverse(q->qfm, tr);
    return 0;
}

static int fmQuantRebuild(pddl_fm_quant_t **q, pddl_fm_rebuild_t *rb)
{
    if ((*q)->qfm)
        return fmRebuild(&(*q)->qfm, rb);
    return 0;
}

static void fmQuantPrintPDDL(const pddl_fm_quant_t *q,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout)
{
    fprintf(fout, "(");
    if (q->fm.type == PDDL_FM_FORALL){
        fprintf(fout, "forall");
    }else if (q->fm.type == PDDL_FM_EXIST){
        fprintf(fout, "exists");
    }

    fprintf(fout, " (");
    pddlParamsPrintPDDL(&q->param, &pddl->type, fout);
    fprintf(fout, ") ");

    pddlFmPrintPDDL(q->qfm, pddl, &q->param, fout);

    fprintf(fout, ")");
}




/*** WHEN ***/
static pddl_fm_when_t *fmWhenNew(void)
{
    return fmNew(pddl_fm_when_t, PDDL_FM_WHEN);
}

static void fmWhenDel(pddl_fm_when_t *w)
{
    if (w->pre)
        pddlFmDel(w->pre);
    if (w->eff)
        pddlFmDel(w->eff);
    FREE(w);
}

static pddl_fm_when_t *fmWhenClone(const pddl_fm_when_t *w)
{
    pddl_fm_when_t *n;

    n = fmWhenNew();
    if (w->pre)
        n->pre = pddlFmClone(w->pre);
    if (w->eff)
        n->eff = pddlFmClone(w->eff);
    return n;
}

static pddl_fm_when_t *fmWhenNegate(const pddl_fm_when_t *w,
                                    const pddl_t *pddl)
{
    PANIC("Cannot negate (when ...)");
    return NULL;
}

static pddl_bool_t fmWhenEq(const pddl_fm_when_t *w1,
                            const pddl_fm_when_t *w2)
{
    return fmEq(w1->pre, w2->pre) && fmEq(w1->eff, w2->eff);
}

static int fmWhenTraverse(pddl_fm_when_t *w, pddl_fm_traverse_t *tr)
{
    if (w->pre != NULL && fmTraverse(w->pre, tr) != 0)
        return -1;
    if (w->eff != NULL && fmTraverse(w->eff, tr) != 0)
        return -1;
    return 0;
}

static int fmWhenRebuild(pddl_fm_when_t **w, pddl_fm_rebuild_t *rb)
{
    if ((*w)->eff != NULL){
        if (fmRebuild(&(*w)->eff, rb) != 0)
            return -1;

        if ((*w)->eff == NULL){
            pddlFmDel(&(*w)->fm);
            *w = NULL;
            return 0;
        }
    }

    if ((*w)->pre != NULL){
        if (fmRebuild(&(*w)->pre, rb) != 0)
            return -1;

        if ((*w)->pre == NULL){
            pddl_fm_t *eff = (*w)->eff;
            (*w)->eff = NULL;
            pddlFmDel(&(*w)->fm);
            *(pddl_fm_t **)w = eff;
        }
    }

    return 0;
}

static void fmWhenPrintPDDL(const pddl_fm_when_t *w,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout)
{
    fprintf(fout, "(when ");
    pddlFmPrintPDDL(w->pre, pddl, params, fout);
    fprintf(fout, " ");
    pddlFmPrintPDDL(w->eff, pddl, params, fout);
    fprintf(fout, ")");
}



/*** ATOM ***/
static pddl_fm_atom_t *fmAtomNew(void)
{
    return fmNew(pddl_fm_atom_t, PDDL_FM_ATOM);
}

static void fmAtomDel(pddl_fm_atom_t *a)
{
    if (a->arg != NULL)
        FREE(a->arg);
    FREE(a);
}

static pddl_fm_atom_t *fmAtomClone(const pddl_fm_atom_t *a)
{
    pddl_fm_atom_t *n;

    n = fmAtomNew();
    n->pred = a->pred;
    n->arg_size = a->arg_size;
    n->arg = ALLOC_ARR(pddl_fm_atom_arg_t, n->arg_size);
    memcpy(n->arg, a->arg, sizeof(pddl_fm_atom_arg_t) * n->arg_size);
    n->neg = !!(a->neg);

    return n;
}

static pddl_fm_atom_t *fmAtomNegate(const pddl_fm_atom_t *a,
                                    const pddl_t *pddl)
{
    pddl_fm_atom_t *n;

    n = fmAtomClone(a);
    if (pddl->pred.pred[a->pred].neg_of >= 0){
        n->pred = pddl->pred.pred[a->pred].neg_of;
    }else{
        n->neg = !a->neg;
    }
    return n;
}

static pddl_bool_t fmAtomEq(const pddl_fm_atom_t *a1,
                            const pddl_fm_atom_t *a2)
{
    if (a1->pred != a2->pred
            || !!(a1->neg) != !!(a2->neg)
            || a1->arg_size != a2->arg_size)
        return pddl_false;
    for (int i = 0; i < a1->arg_size; ++i){
        if (a1->arg[i].param != a2->arg[i].param
                || a1->arg[i].obj != a2->arg[i].obj){
            return pddl_false;
        }
    }
    return pddl_true;
}

static pddl_bool_t fmAtomEqNoNeg(const pddl_fm_atom_t *a1,
                         const pddl_fm_atom_t *a2)
{
    if (a1->pred != a2->pred
            || a1->arg_size != a2->arg_size)
        return pddl_false;
    for (int i = 0; i < a1->arg_size; ++i){
        if (a1->arg[i].param != a2->arg[i].param
                || a1->arg[i].obj != a2->arg[i].obj){
            return pddl_false;
        }
    }
    return pddl_true;
}

static int fmAtomTraverse(pddl_fm_atom_t *a, pddl_fm_traverse_t *tr)
{
    return 0;
}

static int fmAtomRebuild(pddl_fm_atom_t **a, pddl_fm_rebuild_t *rb)
{
    return 0;
}

static void atomPrintPDDL(const pddl_fm_atom_t *a,
                          const pddl_t *pddl,
                          const pddl_params_t *params,
                          int is_func,
                          FILE *fout)
{
    if (a->neg)
        fprintf(fout, "(not ");
    if (is_func){
        fprintf(fout, "(%s", pddl->func.pred[a->pred].name);
    }else{
        fprintf(fout, "(%s", pddl->pred.pred[a->pred].name);
    }
    for (int i = 0; i < a->arg_size; ++i){
        pddl_fm_atom_arg_t *arg = a->arg + i;
        if (arg->param >= 0){
            if (params->param[arg->param].name != NULL){
                fprintf(fout, " %s", params->param[arg->param].name);
            }else{
                if (params->param[arg->param].is_counted_var){
                    fprintf(fout, " c%d", arg->param);
                }else{
                    fprintf(fout, " x%d", arg->param);
                }
            }
        }else{
            fprintf(fout, " %s", pddl->obj.obj[arg->obj].name);
        }
    }
    fprintf(fout, ")");
    if (a->neg)
        fprintf(fout, ")");
}

static void fmAtomPrintPDDL(const pddl_fm_atom_t *a,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout)
{
    atomPrintPDDL(a, pddl, params, 0, fout);
}


/*** BOOL ***/
static pddl_fm_bool_t *fmBoolNew(int val)
{
    pddl_fm_bool_t *b;
    b = fmNew(pddl_fm_bool_t, PDDL_FM_BOOL);
    b->val = val;
    return b;
}

static void fmBoolDel(pddl_fm_bool_t *a)
{
    FREE(a);
}

static pddl_fm_bool_t *fmBoolClone(const pddl_fm_bool_t *a)
{
    return fmBoolNew(a->val);
}

static pddl_fm_bool_t *fmBoolNegate(const pddl_fm_bool_t *a,
                                    const pddl_t *pddl)
{
    pddl_fm_bool_t *b = fmBoolClone(a);
    b->val = !a->val;
    return b;
}

static pddl_bool_t fmBoolEq(const pddl_fm_bool_t *b1,
                            const pddl_fm_bool_t *b2)
{
    return !!(b1->val) == !!(b2->val);
}


static int fmBoolTraverse(pddl_fm_bool_t *a, pddl_fm_traverse_t *tr)
{
    return 0;
}

static int fmBoolRebuild(pddl_fm_bool_t **a, pddl_fm_rebuild_t *rb)
{
    return 0;
}

static void fmBoolPrintPDDL(const pddl_fm_bool_t *b,
                            const pddl_t *pddl,
                            const pddl_params_t *params,
                            FILE *fout)
{
    if (b->val){
        fprintf(fout, "(TRUE)");
    }else{
        fprintf(fout, "(FALSE)");
    }
}


/*** IMPLY ***/
static pddl_fm_imply_t *fmImplyNew(void)
{
    return fmNew(pddl_fm_imply_t, PDDL_FM_IMPLY);
}

static void fmImplyDel(pddl_fm_imply_t *a)
{
    if (a->left != NULL)
        pddlFmDel(a->left);
    if (a->right != NULL)
        pddlFmDel(a->right);
    FREE(a);
}

static pddl_fm_imply_t *fmImplyClone(const pddl_fm_imply_t *a)
{
    pddl_fm_imply_t *n = fmImplyNew();
    if (a->left != NULL)
        n->left = pddlFmClone(a->left);
    if (a->right != NULL)
        n->right = pddlFmClone(a->right);
    return n;
}

static pddl_fm_t *fmImplyNegate(const pddl_fm_imply_t *a,
                                const pddl_t *pddl)
{
    pddl_fm_junc_t *or;
    pddl_fm_t *left, *right;

    or = fmPartNew(PDDL_FM_AND);
    left = pddlFmClone(a->left);
    right = pddlFmNegate(a->right, pddl);
    pddlFmJuncAdd(or, left);
    pddlFmJuncAdd(or, right);
    return &or->fm;
}

static pddl_bool_t fmImplyEq(const pddl_fm_imply_t *i1,
                             const pddl_fm_imply_t *i2)
{
    return fmEq(i1->left, i2->left) && fmEq(i1->right, i2->right);
}

static int fmImplyTraverse(pddl_fm_imply_t *imp, pddl_fm_traverse_t *tr)
{
    if (imp->left != NULL){
        if (fmTraverse(imp->left, tr) != 0)
            return -1;
    }
    if (imp->right != NULL){
        if (fmTraverse(imp->right, tr) != 0)
            return -1;
    }
    return 0;
}

static int fmImplyRebuild(pddl_fm_imply_t **imp, pddl_fm_rebuild_t *rb)
{
    if ((*imp)->left != NULL){
        if (fmRebuild(&(*imp)->left, rb) != 0)
            return -1;
    }
    if ((*imp)->right != NULL){
        if (fmRebuild(&(*imp)->right, rb) != 0)
            return -1;
    }
    return 0;
}

static void fmImplyPrintPDDL(const pddl_fm_imply_t *imp,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout)
{
    fprintf(fout, "(imply ");
    if (imp->left == NULL){
        fprintf(fout, "()");
    }else{
        pddlFmPrintPDDL(imp->left, pddl, params, fout);
    }
    fprintf(fout, " ");
    if (imp->right == NULL){
        fprintf(fout, "()");
    }else{
        pddlFmPrintPDDL(imp->right, pddl, params, fout);
    }
    fprintf(fout, ")");
}


/*** NUM_EXP ***/
static pddl_fm_num_exp_t *fmNumExpNew(int type)
{
    return fmNew(pddl_fm_num_exp_t, type);
}

static void fmNumExpDel(pddl_fm_num_exp_t *e)
{
    if (e->fm.type == PDDL_FM_NUM_EXP_PLUS
            || e->fm.type == PDDL_FM_NUM_EXP_MINUS
            || e->fm.type == PDDL_FM_NUM_EXP_MULT
            || e->fm.type == PDDL_FM_NUM_EXP_DIV){
        if (e->e.bin_op.left != NULL)
            fmNumExpDel(e->e.bin_op.left);
        if (e->e.bin_op.right != NULL)
            fmNumExpDel(e->e.bin_op.right);

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        if (e->e.fluent != NULL)
            fmAtomDel(e->e.fluent);
    }

    FREE(e);
}

static pddl_fm_num_exp_t *fmNumExpClone(const pddl_fm_num_exp_t *e)
{
    pddl_fm_num_exp_t *n;
    n = fmNumExpNew(e->fm.type);
    if (e->fm.type == PDDL_FM_NUM_EXP_PLUS
            || e->fm.type == PDDL_FM_NUM_EXP_MINUS
            || e->fm.type == PDDL_FM_NUM_EXP_MULT
            || e->fm.type == PDDL_FM_NUM_EXP_DIV){
        if (e->e.bin_op.left != NULL)
            n->e.bin_op.left = fmNumExpClone(e->e.bin_op.left);
        if (e->e.bin_op.right != NULL)
            n->e.bin_op.right = fmNumExpClone(e->e.bin_op.right);

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        if (e->e.fluent != NULL)
            n->e.fluent = fmAtomClone(e->e.fluent);

    }else if (e->fm.type == PDDL_FM_NUM_EXP_INUM){
        n->e.inum = e->e.inum;

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FNUM){
        n->e.fnum = e->e.fnum;

    }else{
        PANIC("Unkown type of numerical expression (%d, %s)",
              e->fm.type, pddlFmTypeName(e->fm.type));
    }

    return n;
}

static pddl_fm_num_exp_t *fmNumExpNegate(const pddl_fm_num_exp_t *e,
                                         const pddl_t *pddl)
{
    // Numerical expression cannot be negated
    PANIC("Numerical expression cannot be negated.");
    return NULL;
}

static pddl_bool_t fmNumExpEq(const pddl_fm_num_exp_t *e1,
                              const pddl_fm_num_exp_t *e2)
{
    if (e1->fm.type != e2->fm.type)
        return pddl_false;

    if (e1->fm.type == PDDL_FM_NUM_EXP_PLUS
            || e1->fm.type == PDDL_FM_NUM_EXP_MINUS
            || e1->fm.type == PDDL_FM_NUM_EXP_MULT
            || e1->fm.type == PDDL_FM_NUM_EXP_DIV){
        if (e1->e.bin_op.left != NULL && e2->e.bin_op.left != NULL){
            if (!fmNumExpEq(e1->e.bin_op.left, e2->e.bin_op.left))
                return pddl_false;
        }else if (e1->e.bin_op.left != e2->e.bin_op.left){
                return pddl_false;
        }

        if (e1->e.bin_op.right != NULL && e2->e.bin_op.right != NULL){
            if (!fmNumExpEq(e1->e.bin_op.right, e2->e.bin_op.right))
                return pddl_false;
        }else if (e1->e.bin_op.right != e2->e.bin_op.right){
                return pddl_false;
        }

    }else if (e1->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        if (e1->e.fluent != NULL && e2->e.fluent != NULL)
            return fmAtomEq(e1->e.fluent, e2->e.fluent);

    }else if (e1->fm.type == PDDL_FM_NUM_EXP_INUM){
        return e1->e.inum == e2->e.inum;

    }else if (e1->fm.type == PDDL_FM_NUM_EXP_FNUM){
        // TODO: Should we compare with some slack?
        return e1->e.fnum == e2->e.fnum;

    }else{
        PANIC("Unkown type of numerical expression (%d, %s)",
              e1->fm.type, pddlFmTypeName(e1->fm.type));
    }
    return pddl_true;
}

static int fmNumExpTraverse(pddl_fm_num_exp_t *e, pddl_fm_traverse_t *tr)
{
    if (!tr->descend_num)
        return 0;

    if (e->fm.type == PDDL_FM_NUM_EXP_PLUS
            || e->fm.type == PDDL_FM_NUM_EXP_MINUS
            || e->fm.type == PDDL_FM_NUM_EXP_MULT
            || e->fm.type == PDDL_FM_NUM_EXP_DIV){
        if (e->e.bin_op.left != NULL
                && fmTraverse(&e->e.bin_op.left->fm, tr) != 0){
            return -1;
        }
        if (e->e.bin_op.right != NULL
                && fmTraverse(&e->e.bin_op.right->fm, tr) != 0){
            return -1;
        }

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        // Do not descend to the atom

    }else if (e->fm.type == PDDL_FM_NUM_EXP_INUM){
        (void)e; // ignore

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FNUM){
        (void)e; // ignore

    }else{
        PANIC("Unkown type of numerical expression (%d, %s)",
              e->fm.type, pddlFmTypeName(e->fm.type));
    }

    return 0;
}

static int fmNumExpRebuild(pddl_fm_num_exp_t **e, pddl_fm_rebuild_t *rb)
{
    if (!rb->descend_num)
        return 0;

    if ((*e)->fm.type == PDDL_FM_NUM_EXP_PLUS
            || (*e)->fm.type ==  PDDL_FM_NUM_EXP_MINUS
            || (*e)->fm.type ==  PDDL_FM_NUM_EXP_MULT
            || (*e)->fm.type ==  PDDL_FM_NUM_EXP_DIV){
        if ((*e)->e.bin_op.left != NULL){
            pddl_fm_t *fm = &(*e)->e.bin_op.left->fm;
            int st = fmRebuild(&fm, rb);

            if (fm != NULL && pddlFmIsNumExp(fm)){
                (*e)->e.bin_op.left = pddlFmToNumExp(fm);
            }else{
                if (fm != NULL)
                    pddlFmDel(fm);
                (*e)->e.bin_op.left = NULL;
            }

            if (st != 0)
                return -1;
        }

        if ((*e)->e.bin_op.right != NULL){
            pddl_fm_t *fm = &(*e)->e.bin_op.right->fm;
            int st = fmRebuild(&fm, rb);

            if (fm != NULL && pddlFmIsNumExp(fm)){
                (*e)->e.bin_op.right = pddlFmToNumExp(fm);
            }else{
                if (fm != NULL)
                    pddlFmDel(fm);
                (*e)->e.bin_op.right = NULL;
            }

            if (st != 0)
                return -1;
        }

        if ((*e)->e.bin_op.left == NULL || (*e)->e.bin_op.right == NULL){
            pddlFmDel(&(*e)->fm);
            *e = NULL;
        }

    }else if ((*e)->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        // Do not descend to the atom

    }else if ((*e)->fm.type == PDDL_FM_NUM_EXP_INUM){
        // nothing to do
    }else if ((*e)->fm.type == PDDL_FM_NUM_EXP_FNUM){
        // nothing to do
    }

    return 0;
}

static void fmNumExpPrintPDDL(const pddl_fm_num_exp_t *e,
                              const pddl_t *pddl,
                              const pddl_params_t *params,
                              FILE *fout)
{
    if (e->fm.type == PDDL_FM_NUM_EXP_PLUS){
        fprintf(fout, "(+ ");

    }else if (e->fm.type == PDDL_FM_NUM_EXP_MINUS){
        fprintf(fout, "(- ");

    }else if (e->fm.type == PDDL_FM_NUM_EXP_MULT){
        fprintf(fout, "(* ");

    }else if (e->fm.type == PDDL_FM_NUM_EXP_DIV){
        fprintf(fout, "(/ ");

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        atomPrintPDDL(e->e.fluent, pddl, params, 1, fout);

    }else if (e->fm.type == PDDL_FM_NUM_EXP_INUM){
        fprintf(fout, "%d", e->e.inum);

    }else if (e->fm.type == PDDL_FM_NUM_EXP_FNUM){
        fprintf(fout, "%f", e->e.fnum);

    }else{
        PANIC("Unkown type of numerical expression (%d, %s)",
              e->fm.type, pddlFmTypeName(e->fm.type));
    }

    if (e->fm.type == PDDL_FM_NUM_EXP_PLUS
            || e->fm.type == PDDL_FM_NUM_EXP_MINUS
            || e->fm.type == PDDL_FM_NUM_EXP_MULT
            || e->fm.type == PDDL_FM_NUM_EXP_DIV){
        fmNumExpPrintPDDL(e->e.bin_op.left, pddl, params, fout);
        fprintf(fout, " ");
        fmNumExpPrintPDDL(e->e.bin_op.right, pddl, params, fout);
        fprintf(fout, ")");
    }
}


/*** NUM_CMP ***/
static pddl_fm_num_cmp_t *fmNumCmpNew(int type)
{
    return fmNew(pddl_fm_num_cmp_t, type);
}

static void fmNumCmpDel(pddl_fm_num_cmp_t *c)
{
    if (c->left != NULL)
        fmNumExpDel(c->left);
    if (c->right != NULL)
        fmNumExpDel(c->right);
    FREE(c);
}

static pddl_fm_num_cmp_t *fmNumCmpClone(const pddl_fm_num_cmp_t *c)
{
    pddl_fm_num_cmp_t *n;
    n = fmNumCmpNew(c->fm.type);
    if (c->left != NULL)
        n->left = fmNumExpClone(c->left);
    if (c->right != NULL)
        n->right = fmNumExpClone(c->right);
    return n;
}

static pddl_fm_num_cmp_t *fmNumCmpNegate(const pddl_fm_num_cmp_t *c,
                                         const pddl_t *pddl)
{
    pddl_fm_num_cmp_t *r = fmNumCmpClone(c);
    if (c->fm.type == PDDL_FM_NUM_CMP_EQ){
        r->fm.type = PDDL_FM_NUM_CMP_NEQ;
    }else if (c->fm.type == PDDL_FM_NUM_CMP_NEQ){
        r->fm.type = PDDL_FM_NUM_CMP_EQ;
    }else if (c->fm.type == PDDL_FM_NUM_CMP_GE){
        r->fm.type = PDDL_FM_NUM_CMP_LT;
    }else if (c->fm.type == PDDL_FM_NUM_CMP_LE){
        r->fm.type = PDDL_FM_NUM_CMP_GT;
    }else if (c->fm.type == PDDL_FM_NUM_CMP_GT){
        r->fm.type = PDDL_FM_NUM_CMP_LE;
    }else if (c->fm.type == PDDL_FM_NUM_CMP_LT){
        r->fm.type = PDDL_FM_NUM_CMP_GE;
    }else{
        PANIC("Unkown type of numerical comparator (%d, %s)",
              c->fm.type, pddlFmTypeName(c->fm.type));
    }
    return r;
}

static pddl_bool_t fmNumCmpEq(const pddl_fm_num_cmp_t *c1,
                              const pddl_fm_num_cmp_t *c2)
{
    if (c1->fm.type != c2->fm.type)
        return pddl_false;

    if (c1->left != NULL && c2->left != NULL){
        if (!fmNumExpEq(c1->left, c2->left))
            return pddl_false;
    }else if (c1->left != c2->left){
        return pddl_false;
    }

    if (c1->right != NULL && c2->right != NULL){
        if (!fmNumExpEq(c1->right, c2->right))
            return pddl_false;
    }else if (c1->right != c2->right){
        return pddl_false;
    }

    return pddl_true;
}

static int fmNumCmpTraverse(pddl_fm_num_cmp_t *c, pddl_fm_traverse_t *tr)
{
    if (!tr->descend_num)
        return 0;

    if (c->left != NULL && fmTraverse(&c->left->fm, tr) != 0)
        return -1;
    if (c->right != NULL && fmTraverse(&c->right->fm, tr) != 0)
        return -1;
    return 0;
}

static int fmNumCmpRebuild(pddl_fm_num_cmp_t **c, pddl_fm_rebuild_t *rb)
{
    if (!rb->descend_num)
        return 0;

    if ((*c)->left != NULL){
        pddl_fm_t *fm = &(*c)->left->fm;
        int st = fmRebuild(&fm, rb);

        if (fm != NULL && pddlFmIsNumExp(fm)){
            (*c)->left = pddlFmToNumExp(fm);
        }else{
            if (fm != NULL)
                pddlFmDel(fm);
            (*c)->left = NULL;
        }

        if (st != 0)
            return -1;
    }

    if ((*c)->right != NULL){
        pddl_fm_t *fm = &(*c)->right->fm;
        int st = fmRebuild(&fm, rb);

        if (fm != NULL && pddlFmIsNumExp(fm)){
            (*c)->right = pddlFmToNumExp(fm);
        }else{
            if (fm != NULL)
                pddlFmDel(fm);
            (*c)->right = NULL;
        }

        if (st != 0)
            return -1;
    }

    if ((*c)->left == NULL || (*c)->right == NULL){
        pddlFmDel(&(*c)->fm);
        *c = NULL;
    }

    return 0;
}

static void fmNumCmpPrintPDDL(const pddl_fm_num_cmp_t *c,
                              const pddl_t *pddl,
                              const pddl_params_t *params,
                              FILE *fout)
{
    if (c->fm.type == PDDL_FM_NUM_CMP_EQ){
        fprintf(fout, "(= ");
    }else if (c->fm.type == PDDL_FM_NUM_CMP_NEQ){
        fprintf(fout, "(not (= ");
    }else if (c->fm.type == PDDL_FM_NUM_CMP_GE){
        fprintf(fout, "(>= ");
    }else if (c->fm.type == PDDL_FM_NUM_CMP_LE){
        fprintf(fout, "(<= ");
    }else if (c->fm.type == PDDL_FM_NUM_CMP_GT){
        fprintf(fout, "(> ");
    }else if (c->fm.type == PDDL_FM_NUM_CMP_LT){
        fprintf(fout, "(< ");
    }else{
        PANIC("Unkown type of numerical comparator (%d, %s)",
              c->fm.type, pddlFmTypeName(c->fm.type));
    }

    if (c->left != NULL){
        fmNumExpPrintPDDL(c->left, pddl, params, fout);
    }else{
        fprintf(fout, "(null)");
    }
    fprintf(fout, " ");
    if (c->right != NULL){
        fmNumExpPrintPDDL(c->right, pddl, params, fout);
    }else{
        fprintf(fout, "(null)");
    }
    fprintf(fout, ")");
    if (c->fm.type == PDDL_FM_NUM_CMP_NEQ)
        fprintf(fout, ")");
}


/*** NUM_OP ***/
static pddl_fm_num_op_t *fmNumOpNew(int type)
{
    return fmNew(pddl_fm_num_op_t, type);
}

static void fmNumOpDel(pddl_fm_num_op_t *c)
{
    if (c->left != NULL)
        fmNumExpDel(c->left);
    if (c->right != NULL)
        fmNumExpDel(c->right);
    FREE(c);
}

static pddl_fm_num_op_t *fmNumOpClone(const pddl_fm_num_op_t *c)
{
    pddl_fm_num_op_t *n;
    n = fmNumOpNew(c->fm.type);
    if (c->left != NULL)
        n->left = fmNumExpClone(c->left);
    if (c->right != NULL)
        n->right = fmNumExpClone(c->right);
    return n;
}

static pddl_fm_num_op_t *fmNumOpNegate(const pddl_fm_num_op_t *c,
                                       const pddl_t *pddl)
{
    PANIC("Cannot negate assignment operator.");
    return NULL;
}

static pddl_bool_t fmNumOpEq(const pddl_fm_num_op_t *c1,
                             const pddl_fm_num_op_t *c2)
{
    if (c1->fm.type != c2->fm.type)
        return pddl_false;

    if (c1->left != NULL && c2->left != NULL){
        ASSERT(c1->left->fm.type == PDDL_FM_NUM_EXP_FLUENT
                    && c1->left->fm.type == c2->left->fm.type);
        if (!fmAtomEq(c1->left->e.fluent, c2->left->e.fluent))
            return pddl_false;
    }else if (c1->left != c2->left){
        return pddl_false;
    }

    if (c1->right != NULL && c2->right != NULL){
        if (!fmNumExpEq(c1->right, c2->right))
            return pddl_false;
    }else if (c1->right != c2->right){
        return pddl_false;
    }

    return pddl_true;
}

static int fmNumOpTraverse(pddl_fm_num_op_t *c, pddl_fm_traverse_t *tr)
{
    if (!tr->descend_num)
        return 0;

    if (c->left != NULL && fmTraverse(&c->left->fm, tr) != 0)
        return -1;
    if (c->right != NULL && fmTraverse(&c->right->fm, tr) != 0)
        return -1;
    return 0;
}

static int fmNumOpRebuild(pddl_fm_num_op_t **c, pddl_fm_rebuild_t *rb)
{
    if (!rb->descend_num)
        return 0;

    if ((*c)->left != NULL){
        pddl_fm_t *fm = &(*c)->left->fm;
        int st = fmRebuild(&fm, rb);

        if (fm != NULL && pddlFmIsNumExpFluent(fm)){
            (*c)->left = pddlFmToNumExp(fm);
        }else{
            if (fm != NULL)
                pddlFmDel(fm);
            (*c)->left = NULL;
        }

        if (st != 0)
            return -1;
    }

    if ((*c)->right != NULL){
        pddl_fm_t *fm = &(*c)->right->fm;
        int st = fmRebuild(&fm, rb);

        if (fm != NULL && pddlFmIsNumExp(fm)){
            (*c)->right = pddlFmToNumExp(fm);
        }else{
            if (fm != NULL)
                pddlFmDel(fm);
            (*c)->right = NULL;
        }

        if (st != 0)
            return -1;
    }

    if ((*c)->left == NULL || (*c)->right == NULL){
        pddlFmDel(&(*c)->fm);
        *c = NULL;
    }

    return 0;
}

static void fmNumOpPrintPDDL(const pddl_fm_num_op_t *c,
                             const pddl_t *pddl,
                             const pddl_params_t *params,
                             FILE *fout)
{
    if (c->fm.type == PDDL_FM_NUM_OP_ASSIGN){
        fprintf(fout, "(assign ");
    }else if (c->fm.type == PDDL_FM_NUM_OP_INCREASE){
        fprintf(fout, "(increase ");
    }else if (c->fm.type == PDDL_FM_NUM_OP_DECREASE){
        fprintf(fout, "(decrease ");
    }else if (c->fm.type == PDDL_FM_NUM_OP_SCALE_UP){
        fprintf(fout, "(scale-up ");
    }else if (c->fm.type == PDDL_FM_NUM_OP_SCALE_DOWN){
        fprintf(fout, "(scale-down ");
    }else{
        PANIC("Unkown type of numerical operator (%d, %s)",
              c->fm.type, pddlFmTypeName(c->fm.type));
    }

    if (c->left != NULL){
        fmNumExpPrintPDDL(c->left, pddl, params, fout);
    }else{
        fprintf(fout, "(null)");
    }
    fprintf(fout, " ");
    if (c->right != NULL){
        fmNumExpPrintPDDL(c->right, pddl, params, fout);
    }else{
        fprintf(fout, "(null)");
    }
    fprintf(fout, ")");
}



pddl_bool_t pddlFmIsJunc(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_AND || c->type == PDDL_FM_OR;
}

pddl_fm_junc_t *pddlFmToJunc(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_AND || c->type == PDDL_FM_OR);
    return pddl_container_of(c, pddl_fm_junc_t, fm);
}

const pddl_fm_junc_t *pddlFmToJuncConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_AND || c->type == PDDL_FM_OR);
    return pddl_container_of(c, pddl_fm_junc_t, fm);
}

pddl_bool_t pddlFmIsAnd(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_AND;
}

pddl_fm_and_t *pddlFmToAnd(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_AND);
    return pddl_container_of(c, pddl_fm_and_t, fm);
}

const pddl_fm_and_t *pddlFmToAndConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_AND);
    return pddl_container_of(c, pddl_fm_and_t, fm);
}

pddl_bool_t pddlFmIsOr(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_OR;
}

pddl_fm_or_t *pddlFmToOr(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_OR);
    return pddl_container_of(c, pddl_fm_or_t, fm);
}

const pddl_fm_or_t *pddlFmToOrConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_OR);
    return pddl_container_of(c, pddl_fm_or_t, fm);
}

pddl_bool_t pddlFmIsBool(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_BOOL;
}

pddl_bool_t pddlFmIsTrue(const pddl_fm_t *c)
{
    if (c->type == PDDL_FM_BOOL){
        const pddl_fm_bool_t *b = pddlFmToBoolConst(c);
        return b->val;
    }
    return pddl_false;
}

pddl_bool_t pddlFmIsFalse(const pddl_fm_t *c)
{
    if (c->type == PDDL_FM_BOOL){
        const pddl_fm_bool_t *b = pddlFmToBoolConst(c);
        return !b->val;
    }
    return pddl_false;
}

pddl_fm_bool_t *pddlFmToBool(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_BOOL);
    return pddl_container_of(c, pddl_fm_bool_t, fm);
}

const pddl_fm_bool_t *pddlFmToBoolConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_BOOL);
    return pddl_container_of(c, pddl_fm_bool_t, fm);
}

pddl_bool_t pddlFmIsAtom(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_ATOM;
}

pddl_fm_atom_t *pddlFmToAtom(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_ATOM);
    return pddl_container_of(c, pddl_fm_atom_t, fm);
}

const pddl_fm_atom_t *pddlFmToAtomConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_ATOM);
    return pddl_container_of(c, pddl_fm_atom_t, fm);
}

pddl_bool_t pddlFmIsWhen(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_WHEN;
}

pddl_fm_when_t *pddlFmToWhen(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_WHEN);
    return pddl_container_of(c, pddl_fm_when_t, fm);
}

const pddl_fm_when_t *pddlFmToWhenConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_WHEN);
    return pddl_container_of(c, pddl_fm_when_t, fm);
}

pddl_bool_t pddlFmIsNumExp(const pddl_fm_t *c)
{
    if (c->type == PDDL_FM_NUM_EXP_PLUS
            || c->type == PDDL_FM_NUM_EXP_MINUS
            || c->type == PDDL_FM_NUM_EXP_MULT
            || c->type == PDDL_FM_NUM_EXP_DIV
            || c->type == PDDL_FM_NUM_EXP_FLUENT
            || c->type == PDDL_FM_NUM_EXP_INUM
            || c->type == PDDL_FM_NUM_EXP_FNUM){
        return pddl_true;
    }
    return pddl_false;
}

pddl_bool_t pddlFmIsNumExpPlus(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_PLUS;
}

pddl_bool_t pddlFmIsNumExpMinus(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_MINUS;
}

pddl_bool_t pddlFmIsNumExpMult(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_MULT;
}

pddl_bool_t pddlFmIsNumExpDiv(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_DIV;
}

pddl_bool_t pddlFmIsNumExpBinOp(const pddl_fm_t *e)
{
    return pddlFmIsNumExpPlus(e)
                || pddlFmIsNumExpMinus(e)
                || pddlFmIsNumExpMult(e)
                || pddlFmIsNumExpDiv(e);
}

pddl_bool_t pddlFmIsNumExpFluent(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_FLUENT;
}

pddl_bool_t pddlFmIsNumExpFNum(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_EXP_FNUM;
}

pddl_bool_t pddlFmIsNumExpINum(const pddl_fm_t *e)
{
    return e->type == PDDL_FM_NUM_EXP_INUM;
}

pddl_fm_num_exp_t *pddlFmToNumExp(pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumExp(c));
    return pddl_container_of(c, pddl_fm_num_exp_t, fm);
}

const pddl_fm_num_exp_t *pddlFmToNumExpConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumExp(c));
    return pddl_container_of(c, pddl_fm_num_exp_t, fm);
}

pddl_fm_atom_t *pddlFmNumExpGetFluentAtom(pddl_fm_num_exp_t *e)
{
    ASSERT(pddlFmIsNumExpFluent(&e->fm));
    return e->e.fluent;
}

const pddl_fm_atom_t *pddlFmNumExpGetFluentAtomConst(const pddl_fm_num_exp_t *e)
{
    ASSERT(pddlFmIsNumExpFluent(&e->fm));
    return e->e.fluent;
}

pddl_bool_t pddlFmNumExpCanRecastFNumToINum(const pddl_fm_num_exp_t *e)
{
    ASSERT(pddlFmIsNumExpFNum(&e->fm));
    return e->e.fnum == (float)((int)e->e.fnum);
}

void pddlFmNumExpRecastFNumToINum(pddl_fm_num_exp_t *e)
{
    ASSERT(pddlFmIsNumExpFNum(&e->fm));
    e->fm.type = PDDL_FM_NUM_EXP_INUM;
    int val = e->e.fnum;
    e->e.inum = val;
}

pddl_bool_t pddlFmIsNumCmp(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_CMP_EQ
            || c->type == PDDL_FM_NUM_CMP_NEQ
            || c->type == PDDL_FM_NUM_CMP_GE
            || c->type == PDDL_FM_NUM_CMP_LE
            || c->type == PDDL_FM_NUM_CMP_GT
            || c->type == PDDL_FM_NUM_CMP_LT;
}

pddl_fm_num_cmp_t *pddlFmToNumCmp(pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumCmp(c));
    return pddl_container_of(c, pddl_fm_num_cmp_t, fm);
}

const pddl_fm_num_cmp_t *pddlFmToNumCmpConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumCmp(c));
    return pddl_container_of(c, pddl_fm_num_cmp_t, fm);
}

pddl_bool_t pddlFmIsNumCmpSimpleGroundEqNonNegInt(const pddl_fm_t *fm)
{
    return pddlFmNumCmpCheckSimpleGroundEqNonNegInt(fm, NULL, NULL) == 0;
}

pddl_bool_t pddlFmIsNumCmpSimpleGroundEq(const pddl_fm_t *fm)
{
    return pddlFmNumCmpCheckSimpleGroundEq(fm, NULL, NULL) == 0;
}

int pddlFmNumCmpCheckSimpleGroundEq(const pddl_fm_t *fm,
                                    const pddl_fm_atom_t **left_fluent,
                                    const pddl_fm_num_exp_t **right_value)
{
    if (!pddlFmIsNumCmp(fm))
        return -1;
    const pddl_fm_num_cmp_t *c = pddlFmToNumCmpConst(fm);
    if (c->left == NULL || c->right == NULL)
        return -1;
    if (c->fm.type != PDDL_FM_NUM_CMP_EQ)
        return -1;
    if (c->left->fm.type != PDDL_FM_NUM_EXP_FLUENT)
        return -1;
    if (c->right->fm.type != PDDL_FM_NUM_EXP_INUM
            && c->right->fm.type != PDDL_FM_NUM_EXP_FNUM){
        return -1;
    }

    const pddl_fm_atom_t *latom = c->left->e.fluent;
    if (latom == NULL)
        return -1;
    if (!pddlFmAtomIsGrounded(latom))
        return -1;

    if (left_fluent != NULL)
        *left_fluent = latom;
    if (right_value != NULL)
        *right_value = c->right;

    return 0;
}

int pddlFmNumCmpCheckSimpleGroundEqNonNegInt(const pddl_fm_t *fm,
                                             const pddl_fm_atom_t **left_fluent,
                                             int *value)
{
    const pddl_fm_atom_t *left;
    const pddl_fm_num_exp_t *right;
    if (pddlFmNumCmpCheckSimpleGroundEq(fm, &left, &right) != 0)
        return -1;
    if (right->fm.type != PDDL_FM_NUM_EXP_INUM)
        return -1;
    if (right->e.inum < 0)
        return -1;

    if (left_fluent != NULL)
        *left_fluent = left;
    if (value != NULL)
        *value = right->e.inum;
    return 0;
}

pddl_bool_t pddlFmIsNumOp(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_OP_ASSIGN
            || c->type == PDDL_FM_NUM_OP_INCREASE
            || c->type == PDDL_FM_NUM_OP_DECREASE
            || c->type == PDDL_FM_NUM_OP_SCALE_UP
            || c->type == PDDL_FM_NUM_OP_SCALE_DOWN;
}

pddl_bool_t pddlFmIsNumOpIncrease(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_NUM_OP_INCREASE;
}

pddl_fm_num_op_t *pddlFmToNumOp(pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumOp(c));
    return pddl_container_of(c, pddl_fm_num_op_t, fm);
}

const pddl_fm_num_op_t *pddlFmToNumOpConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsNumOp(c));
    return pddl_container_of(c, pddl_fm_num_op_t, fm);
}

int pddlFmNumOpCheckSimpleIncreaseTotalCost(const pddl_fm_t *_fm,
                                            int func_total_cost_id,
                                            const pddl_fm_atom_t **atom_value,
                                            int *int_value)
{
    if (!pddlFmIsNumOp(_fm))
        return -1;
    const pddl_fm_num_op_t *fm = pddlFmToNumOpConst(_fm);
    if (fm->fm.type != PDDL_FM_NUM_OP_INCREASE)
        return -1;
    if (fm->left->e.fluent->pred != func_total_cost_id)
        return -1;

    if (fm->right->fm.type == PDDL_FM_NUM_EXP_INUM){
        *atom_value = NULL;
        *int_value = fm->right->e.inum;
        return 0;
    }

    if (fm->right->fm.type == PDDL_FM_NUM_EXP_FLUENT){
        *atom_value = fm->right->e.fluent;
        *int_value = -1;
        return 0;
    }

    return -1;
}

pddl_bool_t pddlFmIsQuant(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_FORALL || c->type == PDDL_FM_EXIST;
}

pddl_fm_quant_t *pddlFmToQuant(pddl_fm_t *c)
{
    ASSERT(pddlFmIsQuant(c));
    return pddl_container_of(c, pddl_fm_quant_t, fm);
}

const pddl_fm_quant_t *pddlFmToQuantConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsQuant(c));
    return pddl_container_of(c, pddl_fm_quant_t, fm);
}

pddl_bool_t pddlFmIsForAll(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_FORALL;
}

pddl_fm_forall_t *pddlFmToForAll(pddl_fm_t *c)
{
    ASSERT(pddlFmIsForAll(c));
    return pddl_container_of(c, pddl_fm_forall_t, fm);
}

const pddl_fm_forall_t *pddlFmToForAllConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsForAll(c));
    return pddl_container_of(c, pddl_fm_forall_t, fm);
}

pddl_bool_t pddlFmIsExist(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_EXIST;
}

pddl_fm_exist_t *pddlFmToExist(pddl_fm_t *c)
{
    ASSERT(pddlFmIsExist(c));
    return pddl_container_of(c, pddl_fm_exist_t, fm);
}

const pddl_fm_exist_t *pddlFmToExistConst(const pddl_fm_t *c)
{
    ASSERT(pddlFmIsExist(c));
    return pddl_container_of(c, pddl_fm_exist_t, fm);
}

pddl_bool_t pddlFmIsImply(const pddl_fm_t *c)
{
    return c->type == PDDL_FM_IMPLY;
}

pddl_fm_imply_t *pddlFmToImply(pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_IMPLY);
    return pddl_container_of(c, pddl_fm_imply_t, fm);
}

const pddl_fm_imply_t *pddlFmToImplyConst(const pddl_fm_t *c)
{
    ASSERT(c->type == PDDL_FM_IMPLY);
    return pddl_container_of(c, pddl_fm_imply_t, fm);
}

void pddlFmDel(pddl_fm_t *fm)
{
    cond_cls[fm->type].del(fm);
}

pddl_fm_t *pddlFmClone(const pddl_fm_t *fm)
{
    return cond_cls[fm->type].clone(fm);
}

pddl_fm_t *pddlFmNegate(const pddl_fm_t *fm, const pddl_t *pddl)
{
    return cond_cls[fm->type].negate(fm, pddl);
}

static pddl_bool_t fmEq(const pddl_fm_t *c1, const pddl_fm_t *c2)
{
    if (c1 == c2)
        return pddl_true;
    if ((c1 == NULL && c2 != NULL)
            || (c1 != NULL && c2 == NULL))
        return pddl_false;
    if (c1->type != c2->type)
        return pddl_false;
    return cond_cls[c1->type].eq(c1, c2);
}

pddl_bool_t pddlFmEq(const pddl_fm_t *c1, const pddl_fm_t *c2)
{
    return fmEq(c1, c2);
}

pddl_bool_t pddlFmIsImplied(const pddl_fm_t *s,
                            const pddl_fm_t *c,
                            const pddl_t *pddl,
                            const pddl_params_t *param)
{
    PANIC_IF(s->type != PDDL_FM_BOOL
                && s->type != PDDL_FM_ATOM
                && s->type != PDDL_FM_AND
                && s->type != PDDL_FM_OR
                && !pddlFmIsNumCmp(s),
             "Works only on bool, atom, and, or, and numerical comparator formulas");

    if (pddlFmEq(s, c))
        return pddl_true;

    if (s->type == PDDL_FM_BOOL && c->type == PDDL_FM_BOOL){
        if (pddlFmEq(s, c))
            return pddl_true;

    }else if (s->type == PDDL_FM_BOOL){
        if (pddlFmIsTrue(s))
            return pddl_true;
        return pddl_false;

    }else if (c->type == PDDL_FM_BOOL){
        if (pddlFmIsFalse(c))
            return pddl_true;
        return pddl_false;

    }else if (s->type == PDDL_FM_ATOM && c->type == PDDL_FM_ATOM){
        return pddlFmEq(s, c);

        if (pddl == NULL || param == NULL)
            return pddl_false;
        const pddl_fm_atom_t *sa = pddlFmToAtomConst(s);
        const pddl_fm_atom_t *ca = pddlFmToAtomConst(c);
        if (sa->pred != ca->pred)
            return pddl_false;
        for (int argi = 0; argi < sa->arg_size; ++argi){
            if (sa->arg[argi].param >= 0 && ca->arg[argi].param >= 0){
                int stype = param->param[sa->arg[argi].param].type;
                int ctype = param->param[ca->arg[argi].param].type;
                if (!pddlTypesIsSubset(&pddl->type, stype, ctype))
                    return pddl_false;

            }else if (sa->arg[argi].param >= 0){
                int type = param->param[sa->arg[argi].param].type;
                int cobj = ca->arg[argi].obj;
                if (pddlTypeNumObjs(&pddl->type, type) != 1
                        || pddlTypeGetObj(&pddl->type, type, 0) != cobj){
                    return pddl_false;
                }

            }else if (ca->arg[argi].param >= 0){
                int type = param->param[ca->arg[argi].param].type;
                if (!pddlTypesObjHasType(&pddl->type, type, sa->arg[argi].obj))
                    return pddl_false;

            }else{
                if (sa->arg[argi].obj != ca->arg[argi].obj)
                    return pddl_false;
            }
        }
        return pddl_true;

    }else if (s->type == PDDL_FM_OR){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(s);
        pddl_list_t *item;
        PDDL_LIST_FOR_EACH(&p->part, item){
            pddl_fm_t *e = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (pddlFmIsImplied(e, c, pddl, param))
                return pddl_true;
        }
        return pddl_false;

    }else if (s->type == PDDL_FM_AND){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(s);
        pddl_list_t *item;
        PDDL_LIST_FOR_EACH(&p->part, item){
            pddl_fm_t *e = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (!pddlFmIsImplied(e, c, pddl, param))
                return pddl_false;
        }
        return pddl_true;

    }else if (s->type == PDDL_FM_ATOM && c->type == PDDL_FM_AND){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(c);
        pddl_list_t *item;
        PDDL_LIST_FOR_EACH(&p->part, item){
            pddl_fm_t *e = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (pddlFmIsImplied(s, e, pddl, param))
                return pddl_true;
        }
        return pddl_false;

    }else if (s->type == PDDL_FM_ATOM && c->type == PDDL_FM_OR){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(c);
        pddl_list_t *item;
        PDDL_LIST_FOR_EACH(&p->part, item){
            pddl_fm_t *e = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (!pddlFmIsImplied(s, e, pddl, param))
                return pddl_false;
        }
        return pddl_true;
    }

    return pddl_false;
}

static int fmTraverse(pddl_fm_t *c, pddl_fm_traverse_t *tr)
{
    int ret;

    if (tr->pre != NULL){
        ret = tr->pre(c, tr->userdata);
        if (ret == -1)
            return 0;
        if (ret == -2)
            return -1;
    }

    ret = cond_cls[c->type].traverse(c, tr);
    if (ret < 0)
        return ret;

    if (tr->post != NULL)
        if (tr->post(c, tr->userdata) != 0)
            return -1;
    return 0;
}

void _pddlFmTraverse(pddl_fm_t *c, pddl_fm_traverse_t *tr)
{
    fmTraverse(c, tr);
}

void pddlFmTraverseAll(pddl_fm_t *c,
                       int (*pre)(pddl_fm_t *, void *),
                       int (*post)(pddl_fm_t *, void *),
                       void *u)
{
    pddl_fm_traverse_t tr = PDDL_FM_TRAVERSE_INIT(pre, post, u);
    tr.descend_num = pddl_true;
    _pddlFmTraverse(c, &tr);
}

void pddlFmTraverseProp(pddl_fm_t *c,
                        int (*pre)(pddl_fm_t *, void *),
                        int (*post)(pddl_fm_t *, void *),
                        void *u)
{
    pddl_fm_traverse_t tr = PDDL_FM_TRAVERSE_INIT(pre, post, u);
    tr.descend_num = pddl_false;
    _pddlFmTraverse(c, &tr);
}

static int fmRebuild(pddl_fm_t **c, pddl_fm_rebuild_t *rb)
{
    int ret;

    if (rb->pre != NULL){
        ret = rb->pre(c, rb->userdata);
        if (ret == -1)
            return 0;
        if (ret == -2)
            return -1;
    }

    ret = cond_cls[(*c)->type].rebuild(c, rb);
    if (ret < 0)
        return ret;

    if (rb->post != NULL)
        if (rb->post(c, rb->userdata) != 0)
            return -1;
    return 0;
}

void _pddlFmRebuild(pddl_fm_t **c, pddl_fm_rebuild_t *rb)
{
    fmRebuild(c, rb);
}

void pddlFmRebuildAll(pddl_fm_t **c,
                      int (*pre)(pddl_fm_t **, void *),
                      int (*post)(pddl_fm_t **, void *),
                      void *u)
{
    pddl_fm_rebuild_t rb = PDDL_FM_REBUILD_INIT(pre, post, u);
    rb.descend_num = pddl_true;
    _pddlFmRebuild(c, &rb);
}

void pddlFmRebuildProp(pddl_fm_t **c,
                       int (*pre)(pddl_fm_t **, void *),
                       int (*post)(pddl_fm_t **, void *),
                       void *u)
{
    pddl_fm_rebuild_t rb = PDDL_FM_REBUILD_INIT(pre, post, u);
    rb.descend_num = pddl_false;
    _pddlFmRebuild(c, &rb);
}

void pddlFmJuncSort(pddl_fm_junc_t *fm,
                    int (*cmp)(const pddl_fm_t *fm1,
                               const pddl_fm_t *fm2,
                               void *userdata),
                    void *userdata)
{
    // This is insert-sort on linked list
    pddl_list_t *list = &fm->part;
    pddl_list_t sorted;

    // empty list - no need to sort
    if (pddlListEmpty(list))
        return;

    // list with one item - no need to sort
    if (pddlListNext(list) == pddlListPrev(list))
        return;

    pddlListInit(&sorted);
    while (!pddlListEmpty(list)){
        // pick up next item from list
        pddl_list_t *cur = pddlListNext(list);
        pddlListDel(cur);
        const pddl_fm_t *curfm = PDDL_LIST_ENTRY(cur, pddl_fm_t, conn);

        // find the place where to put it
        pddl_list_t *item = pddlListPrev(&sorted);
        while (item != &sorted){
            const pddl_fm_t *itemfm = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (cmp(curfm, itemfm, userdata) >= 0)
                break;
            item = pddlListPrev(item);
        }

        // put it after the item
        pddlListPrepend(item, cur);
    }

    // and finally store sorted
    *list = sorted;
    list->next->prev = list;
    list->prev->next = list;
}

static int _countAtoms(pddl_fm_t *fm, void *u)
{
    if (pddlFmIsAtom(fm)){
        int *num = u;
        *num += 1;
    }
    return 0;
}

int pddlFmNumAtoms(const pddl_fm_t *fm)
{
    int num = 0;
    pddlFmTraverseProp((pddl_fm_t *)fm, _countAtoms, NULL, &num);
    return num;
}

struct test_static {
    const pddl_t *pddl;
    int ret;
};
static int atomIsStatic(pddl_fm_t *c, void *_ts)
{
    struct test_static *ts = _ts;
    if (c->type == PDDL_FM_ATOM){
        const pddl_fm_atom_t *a = pddlFmToAtomConst(c);
        if (!pddlPredIsStatic(ts->pddl->pred.pred + a->pred)){
            ts->ret = 0;
            return -2;
        }
        return 0;
    }
    return 0;
}

static int pddlFmIsStatic(pddl_fm_t *c, const pddl_t *pddl)
{
    struct test_static ts;
    ts.pddl = pddl;
    ts.ret = 1;

    pddlFmTraverseProp(c, atomIsStatic, NULL, &ts);
    return ts.ret;
}

pddl_fm_when_t *pddlFmRemoveFirstNonStaticWhen(pddl_fm_t *c,
                                               const pddl_t *pddl)
{
    pddl_fm_junc_t *cp;
    pddl_fm_t *cw;
    pddl_list_t *item, *tmp;

    if (c->type != PDDL_FM_AND)
        return NULL;
    cp = pddlFmToJunc(c);

    PDDL_LIST_FOR_EACH_SAFE(&cp->part, item, tmp){
        cw = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (cw->type == PDDL_FM_WHEN){
            pddl_fm_when_t *w = pddlFmToWhen(cw);
            if (!pddlFmIsStatic(w->pre, pddl)){
                pddlListDel(item);
                return w;
            }
        }
    }

    return NULL;
}

pddl_fm_when_t *pddlFmRemoveFirstWhen(pddl_fm_t *c, const pddl_t *pddl)
{
    pddl_fm_junc_t *cp;
    pddl_fm_t *cw;
    pddl_list_t *item, *tmp;

    if (c->type != PDDL_FM_AND)
        return NULL;
    cp = pddlFmToJunc(c);

    PDDL_LIST_FOR_EACH_SAFE(&cp->part, item, tmp){
        cw = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (cw->type == PDDL_FM_WHEN){
            pddl_fm_when_t *w = pddlFmToWhen(cw);
            pddlListDel(item);
            return w;
        }
    }

    return NULL;
}

pddl_fm_t *pddlFmNewAnd1(pddl_fm_t *a)
{
    pddl_fm_junc_t *p = fmPartNew(PDDL_FM_AND);
    fmPartAdd(p, a);
    return &p->fm;
}

pddl_fm_t *pddlFmNewAnd2(pddl_fm_t *a, pddl_fm_t *b)
{
    pddl_fm_junc_t *p = fmPartNew(PDDL_FM_AND);
    fmPartAdd(p, a);
    fmPartAdd(p, b);
    return &p->fm;
}

pddl_fm_t *pddlFmNewEmptyAnd(void)
{
    pddl_fm_junc_t *p = fmPartNew(PDDL_FM_AND);
    return &p->fm;
}

pddl_fm_t *pddlFmNewEmptyOr(void)
{
    pddl_fm_junc_t *p = fmPartNew(PDDL_FM_OR);
    return &p->fm;
}

pddl_fm_atom_t *pddlFmNewEmptyAtom(int num_args)
{
    pddl_fm_atom_t *atom = fmAtomNew();

    if (num_args > 0){
        atom->arg_size = num_args;
        atom->arg = ALLOC_ARR(pddl_fm_atom_arg_t, atom->arg_size);
        for (int i = 0; i < atom->arg_size; ++i){
            atom->arg[i].param = -1;
            atom->arg[i].obj = -1;
        }
    }

    return atom;
}

pddl_fm_bool_t *pddlFmNewBool(int is_true)
{
    return fmBoolNew(is_true);
}

pddl_fm_imply_t *pddlFmNewImply(pddl_fm_t *left, pddl_fm_t *right)
{
    pddl_fm_imply_t *imply = fmImplyNew();
    imply->left = left;
    imply->right = right;
    return imply;
}

pddl_fm_when_t *pddlFmNewWhen(pddl_fm_t *pre, pddl_fm_t *eff)
{
    pddl_fm_when_t *w = fmWhenNew();
    w->pre = pre;
    w->eff = eff;
    return w;
}

pddl_fm_quant_t *pddlFmNewEmptyQuant(int type)
{
    return fmQuantNew(type);
}

pddl_fm_forall_t *pddlFmNewEmptyForAll(void)
{
    return fmQuantNew(PDDL_FM_FORALL);
}

pddl_fm_exist_t *pddlFmNewEmptyExist(void)
{
    return fmQuantNew(PDDL_FM_EXIST);
}

pddl_fm_num_exp_t *pddlFmNewNumExpPlus(pddl_fm_num_exp_t *left,
                                       pddl_fm_num_exp_t *right)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_PLUS);
    e->e.bin_op.left = left;
    e->e.bin_op.right = right;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpMinus(pddl_fm_num_exp_t *left,
                                        pddl_fm_num_exp_t *right)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_MINUS);
    e->e.bin_op.left = left;
    e->e.bin_op.right = right;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpMult(pddl_fm_num_exp_t *left,
                                       pddl_fm_num_exp_t *right)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_MULT);
    e->e.bin_op.left = left;
    e->e.bin_op.right = right;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpDiv(pddl_fm_num_exp_t *left,
                                      pddl_fm_num_exp_t *right)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_DIV);
    e->e.bin_op.left = left;
    e->e.bin_op.right = right;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpFluent(pddl_fm_atom_t *atom)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_FLUENT);
    e->e.fluent = atom;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpINum(int value)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_INUM);
    e->e.inum = value;
    return e;
}

pddl_fm_num_exp_t *pddlFmNewNumExpFNum(float value)
{
    pddl_fm_num_exp_t *e = fmNumExpNew(PDDL_FM_NUM_EXP_FNUM);
    e->e.fnum = value;
    return e;
}

pddl_fm_num_cmp_t *pddlFmNewNumCmp(int type,
                                   pddl_fm_num_exp_t *left,
                                   pddl_fm_num_exp_t *right)
{
    pddl_fm_num_cmp_t *c = fmNumCmpNew(type);
    c->left = left;
    c->right = right;
    return c;
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpEq(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_EQ, left, right);
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpNEq(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_NEQ, left, right);
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpGE(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_GE, left, right);
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpLE(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_LE, left, right);
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpGT(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_GT, left, right);
}

pddl_fm_num_cmp_t *pddlFmNewNumCmpLT(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumCmp(PDDL_FM_NUM_CMP_LT, left, right);
}


pddl_fm_num_op_t *pddlFmNewNumOp(int type,
                                 pddl_fm_atom_t *left,
                                 pddl_fm_num_exp_t *right)
{
    pddl_fm_num_op_t *c = fmNumOpNew(type);
    c->left = pddlFmNewNumExpFluent(left);
    c->right = right;
    return c;
}

pddl_fm_num_op_t *pddlFmNewNumOpAssign(pddl_fm_atom_t *left,
                                       pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumOp(PDDL_FM_NUM_OP_ASSIGN, left, right);
}

pddl_fm_num_op_t *pddlFmNewNumOpIncrease(pddl_fm_atom_t *left,
                                         pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumOp(PDDL_FM_NUM_OP_INCREASE, left, right);
}

pddl_fm_num_op_t *pddlFmNewNumOpDecrease(pddl_fm_atom_t *left,
                                         pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumOp(PDDL_FM_NUM_OP_DECREASE, left, right);
}

pddl_fm_num_op_t *pddlFmNewNumOpScaleUp(pddl_fm_atom_t *left,
                                        pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumOp(PDDL_FM_NUM_OP_SCALE_UP, left, right);
}

pddl_fm_num_op_t *pddlFmNewNumOpScaleDown(pddl_fm_atom_t *left,
                                          pddl_fm_num_exp_t *right)
{
    return pddlFmNewNumOp(PDDL_FM_NUM_OP_SCALE_DOWN, left, right);
}



static int hasAtom(pddl_fm_t *c, void *_ret)
{
    pddl_bool_t *ret = _ret;

    if (c->type == PDDL_FM_ATOM){
        *ret = pddl_true;
        return -2;
    }
    return 0;
}

pddl_bool_t pddlFmHasAtom(const pddl_fm_t *c)
{
    int ret = pddl_false;
    pddlFmTraverseProp((pddl_fm_t *)c, hasAtom, NULL, &ret);
    return ret;
}

pddl_fm_t *pddlFmAtomToAnd(pddl_fm_t *atom)
{
    pddl_fm_junc_t *and;

    and = fmPartNew(PDDL_FM_AND);
    fmPartAdd(and, atom);
    return &and->fm;
}

pddl_fm_atom_t *pddlFmCreateFactAtom(int pred, int arg_size, 
                                     const int *arg)
{
    pddl_fm_atom_t *a;

    a = fmAtomNew();
    a->pred = pred;
    a->arg_size = arg_size;
    a->arg = ALLOC_ARR(pddl_fm_atom_arg_t, arg_size);
    for (int i = 0; i < arg_size; ++i){
        a->arg[i].param = -1;
        a->arg[i].obj = arg[i];
    }
    return a;
}

void pddlFmJuncAdd(pddl_fm_junc_t *part, pddl_fm_t *c)
{
    fmPartAdd(part, c);
}

void pddlFmJuncRm(pddl_fm_junc_t *part, pddl_fm_t *c)
{
    pddlListDel(&c->conn);
}

pddl_bool_t pddlFmJuncIsEmpty(const pddl_fm_junc_t *part)
{
    return pddlListEmpty(&part->part);
}

void pddlFmReplace(pddl_fm_t *c, pddl_fm_t *r)
{
    if (pddlListEmpty(&c->conn))
        return;
    c->conn.prev->next = &r->conn;
    c->conn.next->prev = &r->conn;
    r->conn.next = c->conn.next;
    r->conn.prev = c->conn.prev;
    pddlListInit(&c->conn);
}



struct preds_funcs {
    pddl_preds_t *preds;
    pddl_preds_t *funcs;
};

static int setPredFuncInInit(pddl_fm_t *fm, void *data)
{
    struct preds_funcs *pf = data;

    if (pddlFmIsAtom(fm)){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
        pf->preds->pred[atom->pred].in_init = pddl_true;

    }else if (pddlFmIsNumExpFluent(fm)){
        const pddl_fm_num_exp_t *exp = pddlFmToNumExp(fm);
        const pddl_fm_atom_t *atom = exp->e.fluent;
        pf->funcs->pred[atom->pred].in_init = pddl_true;
    }
    return 0;
}

void pddlFmSetPredFuncInInit(const pddl_fm_t *init_fm,
                             pddl_preds_t *preds,
                             pddl_preds_t *funcs)
{
    struct preds_funcs pf;
    pf.preds = preds;
    pf.funcs = funcs;

    pddlFmTraverseAll((pddl_fm_t *)init_fm, setPredFuncInInit, NULL, &pf);
}

static int setPredFuncRead(pddl_fm_t *fm, void *data)
{
    struct preds_funcs *pf = data;

    if (pddlFmIsAtom(fm)){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
        pf->preds->pred[atom->pred].read = pddl_true;

    }else if (pddlFmIsNumExpFluent(fm)){
        const pddl_fm_num_exp_t *exp = pddlFmToNumExp(fm);
        const pddl_fm_atom_t *atom = exp->e.fluent;
        pf->funcs->pred[atom->pred].read = pddl_true;
    }
    return 0;
}

static int setPredFuncReadWrite(pddl_fm_t *fm, void *data)
{
    struct preds_funcs *pf = data;

    if (fm->type == PDDL_FM_WHEN){
        pddl_fm_when_t *when = pddlFmToWhen(fm);
        pddlFmTraverseAll((pddl_fm_t *)when->pre, setPredFuncRead, NULL, data);
        pddlFmTraverseAll((pddl_fm_t *)when->eff, setPredFuncReadWrite, NULL, data);
        return -1;

    }else if (fm->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *atom = pddlFmToAtom(fm);
        if (pf->preds != NULL)
            pf->preds->pred[atom->pred].write = pddl_true;

    }else if (pddlFmIsNumOp(fm)){
        const pddl_fm_num_op_t *op = pddlFmToNumOpConst(fm);
        ASSERT(pddlFmIsNumExpFluent(&op->left->fm));
        if (pf->funcs != NULL)
            pf->funcs->pred[op->left->e.fluent->pred].write = pddl_true;
        pddlFmTraverseAll((pddl_fm_t *)&op->right->fm, setPredFuncRead, NULL, data);
        return -1;

    }else if (pddlFmIsNumExpFluent(fm)){
        const pddl_fm_num_exp_t *exp = pddlFmToNumExp(fm);
        const pddl_fm_atom_t *atom = exp->e.fluent;
        if (pf->funcs != NULL)
            pf->funcs->pred[atom->pred].write = pddl_true;
    }

    return 0;
}

void pddlFmSetPredFuncReadWrite(const pddl_fm_t *pre,
                                const pddl_fm_t *eff,
                                pddl_preds_t *preds,
                                pddl_preds_t *funcs)
{
    struct preds_funcs pf;
    pf.preds = preds;
    pf.funcs = funcs;

    if (pre != NULL)
        pddlFmTraverseAll((pddl_fm_t *)pre, setPredFuncRead, NULL, &pf);
    if (eff != NULL)
        pddlFmTraverseAll((pddl_fm_t *)eff, setPredFuncReadWrite, NULL, &pf);
}

struct preds_funcs_flags {
    pddl_bool_t *preds_flags;
    pddl_bool_t *funcs_flags;
};

static int setPredFuncFlags(pddl_fm_t *fm, void *data)
{
    struct preds_funcs_flags *pf = data;

    if (pddlFmIsAtom(fm)){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
        pf->preds_flags[atom->pred] = pddl_true;

    }else if (pddlFmIsNumExpFluent(fm)){
        const pddl_fm_num_exp_t *exp = pddlFmToNumExp(fm);
        const pddl_fm_atom_t *atom = exp->e.fluent;
        pf->funcs_flags[atom->pred] = pddl_true;
    }
    return 0;
}

void pddlFmSetPredFuncFlags(const pddl_fm_t *fm,
                            pddl_bool_t *preds_flags,
                            pddl_bool_t *funcs_flags)
{
    struct preds_funcs_flags pf;
    pf.preds_flags = preds_flags;
    pf.funcs_flags = funcs_flags;

    pddlFmTraverseAll((pddl_fm_t *)fm, setPredFuncFlags, NULL, &pf);
}

static int setObjsFlags(pddl_fm_t *fm, void *data)
{
    pddl_bool_t *flags = data;

    if (pddlFmIsAtom(fm)){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
        for (int i = 0; i < atom->arg_size; ++i){
            if (atom->arg[i].obj >= 0)
                flags[atom->arg[i].obj] = pddl_true;
        }

    }else if (pddlFmIsNumExpFluent(fm)){
        const pddl_fm_num_exp_t *exp = pddlFmToNumExp(fm);
        const pddl_fm_atom_t *atom = exp->e.fluent;
        for (int i = 0; i < atom->arg_size; ++i){
            if (atom->arg[i].obj >= 0)
                flags[atom->arg[i].obj] = pddl_true;
        }
    }
    return 0;
}

void pddlFmSetObjsFlags(const pddl_fm_t *fm, pddl_bool_t *flags)
{
    pddlFmTraverseAll((pddl_fm_t *)fm, setObjsFlags, NULL, (void *)flags);
}


/*** INSTANTIATE QUANTIFIERS ***/
struct instantiate_cond {
    int param_id;
    int obj_id;
};
typedef struct instantiate_cond instantiate_cond_t;

static int instantiateParentParam(pddl_fm_t *c, void *data)
{
    if (c->type == PDDL_FM_ATOM){
        const pddl_params_t *params = data;
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        for (int i = 0; i < params->param_size; ++i){
            if (params->param[i].inherit < 0)
                continue;

            for (int j = 0; j < a->arg_size; ++j){
                if (a->arg[j].param == i)
                    a->arg[j].param = params->param[i].inherit;
            }
        }

    }else if (c->type == PDDL_FM_NUM_EXP_FLUENT){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(c);
        return instantiateParentParam(&e->e.fluent->fm, data);
    }

    return 0;
}

static int instantiateCond(pddl_fm_t *c, void *data)
{
    const instantiate_cond_t *d = data;

    if (c->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        for (int i = 0; i < a->arg_size; ++i){
            if (a->arg[i].param == d->param_id){
                a->arg[i].param = -1;
                a->arg[i].obj = d->obj_id;
            }
        }

    }else if (c->type == PDDL_FM_NUM_EXP_FLUENT){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(c);
        return instantiateCond(&e->e.fluent->fm, data);
    }

    return 0;
}

static pddl_fm_junc_t *instantiatePart(pddl_fm_junc_t *p,
                                       int param_id,
                                       const int *objs,
                                       int objs_size)
{
    pddl_fm_junc_t *out;
    pddl_fm_t *c, *newc;
    pddl_list_t *item;
    instantiate_cond_t set;

    out = fmPartNew(p->fm.type);

    for (int i = 0; i < objs_size; ++i){
        PDDL_LIST_FOR_EACH(&p->part, item){
            c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            newc = pddlFmClone(c);
            set.param_id = param_id;
            set.obj_id = objs[i];
            pddl_fm_traverse_t tr
                = PDDL_FM_TRAVERSE_INIT(NULL, instantiateCond, &set);
            tr.descend_num = pddl_true;
            _pddlFmTraverse(newc, &tr);
            fmPartAdd(out, newc);
        }
    }

    pddlFmDel(&p->fm);
    return out;
}

static pddl_fm_t *instantiateQuant(pddl_fm_quant_t *q,
                                   const pddl_types_t *types)
{
    pddl_fm_junc_t *top;
    const pddl_param_t *param;
    const int *obj;
    int obj_size, bval;

    // The instantiation of universal/existential quantifier is a
    // conjuction/disjunction of all instances.
    if (q->fm.type == PDDL_FM_FORALL){
        top = fmPartNew(PDDL_FM_AND);
    }else{
        top = fmPartNew(PDDL_FM_OR);
    }
    fmPartAdd(top, q->qfm);
    q->qfm = NULL;

    // Apply object to each (non-inherited) parameter according to its type
    for (int i = 0; i < q->param.param_size; ++i){
        param = q->param.param + i;
        if (param->inherit >= 0)
            continue;

        obj = pddlTypesObjsByType(types, param->type, &obj_size);
        if (obj_size == 0){
            bval = q->fm.type == PDDL_FM_FORALL;
            pddlFmDel(&top->fm);
            pddlFmDel(&q->fm);
            return &fmBoolNew(bval)->fm;

        }else{
            top = instantiatePart(top, i, obj, obj_size);
        }
    }

    // Replace all parameters inherited from the parent with IDs of the
    // parent parameters.
    pddl_fm_traverse_t tr
            = PDDL_FM_TRAVERSE_INIT(NULL, instantiateParentParam, &q->param);
    tr.descend_num = pddl_true;
    _pddlFmTraverse(&top->fm, &tr);

    pddlFmDel(&q->fm);
    return &top->fm;
}

static int instantiateForall(pddl_fm_t **c, void *data)
{
    const pddl_types_t *types = data;

    if ((*c)->type != PDDL_FM_FORALL)
        return 0;

    *c = instantiateQuant(pddlFmToQuant(*c), types);
    return 0;
}

static int instantiateExist(pddl_fm_t **c, void *data)
{
    const pddl_types_t *types = data;

    if ((*c)->type != PDDL_FM_EXIST)
        return 0;

    *c = instantiateQuant(pddlFmToQuant(*c), types);
    return 0;
}

static void pddlFmInstantiateQuant(pddl_fm_t **fm, const pddl_types_t *types)
{
    pddlFmRebuildProp(fm, NULL, instantiateForall, (void *)types);
    pddlFmRebuildProp(fm, NULL, instantiateExist, (void *)types);
}



/*** SIMPLIFY ***/
static pddl_fm_t *removeBoolPart(pddl_fm_junc_t *part)
{
    pddl_list_t *item, *tmp;
    pddl_fm_t *c;
    int bval;

    PDDL_LIST_FOR_EACH_SAFE(&part->part, item, tmp){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c->type != PDDL_FM_BOOL)
            continue;

        bval = pddlFmToBool(c)->val;
        if (part->fm.type == PDDL_FM_AND){
            if (!bval){
                pddlFmDel(&part->fm);
                return &fmBoolNew(0)->fm;
            }else{
                pddlListDel(item);
                pddlFmDel(c);
            }

        }else{ // PDDL_FM_OR
            if (bval){
                pddlFmDel(&part->fm);
                return &fmBoolNew(1)->fm;
            }else{
                pddlListDel(item);
                pddlFmDel(c);
            }
        }
    }

    if (pddlListEmpty(&part->part)){
        if (part->fm.type == PDDL_FM_AND){
            pddlFmDel(&part->fm);
            return &fmBoolNew(1)->fm;

        }else{ // PDDL_FM_OR
            pddlFmDel(&part->fm);
            return &fmBoolNew(0)->fm;
        }
    }

    return &part->fm;
}

static pddl_fm_t *removeBoolWhen(pddl_fm_when_t *when)
{
    pddl_fm_t *c;
    int bval;

    if (when->pre->type != PDDL_FM_BOOL)
        return &when->fm;

    bval = pddlFmToBool(when->pre)->val;
    if (bval){
        c = when->eff;
        when->eff = NULL;
        pddlFmDel(&when->fm);
        return c;

    }else{ // !bval
        pddlFmDel(&when->fm);
        return &fmBoolNew(1)->fm;
    }
}

static pddl_bool_t atomIsInInit(const pddl_t *pddl, const pddl_fm_atom_t *atom)
{
    pddl_list_t *item;
    const pddl_fm_t *c;

    PDDL_LIST_FOR_EACH(&pddl->init->part, item){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c->type == PDDL_FM_ATOM
                && pddlFmAtomCmpNoNeg(atom, pddlFmToAtomConst(c)) == 0)
            return pddl_true;
    }
    return pddl_false;
}

/** Returns true if atom at least partially matches grounded atom ground_atom
 *  (disregarding negative flag), i.e., true is returned if the objects (in
 *  place of arguments) match. */
static pddl_bool_t atomPartialMatchNoNeg(const pddl_fm_atom_t *atom,
                                         const pddl_fm_atom_t *ground_atom)
{
    int cmp;

    cmp = atom->pred - ground_atom->pred;
    if (cmp == 0){
        if (atom->arg_size != ground_atom->arg_size)
            return pddl_false;

        for (int i = 0; i < atom->arg_size && cmp == 0; ++i){
            if (atom->arg[i].param >= 0)
                continue;
            cmp = atom->arg[i].obj - ground_atom->arg[i].obj;
        }
    }

    return cmp == 0;
}

static pddl_bool_t atomIsPartiallyInInit(const pddl_t *pddl,
                                         const pddl_fm_atom_t *atom)
{
    pddl_list_t *item;
    const pddl_fm_t *c;

    PDDL_LIST_FOR_EACH(&pddl->init->part, item){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c->type == PDDL_FM_ATOM
                && atomPartialMatchNoNeg(atom, pddlFmToAtomConst(c))){
            return pddl_true;
        }
    }
    return pddl_false;
}

static pddl_fm_t *removeBoolAtom(pddl_fm_atom_t *atom, const pddl_t *pddl)
{
    pddl_bool_t bval;

    if (pddlPredIsStatic(&pddl->pred.pred[atom->pred])){
        if (atom->pred == pddl->pred.eq_pred){
            ASSERT(atom->arg_size == 2);
            if (atom->arg[0].obj >= 0 && atom->arg[1].obj >= 0){
                // Evaluate fully grounded (= ...) atom
                if (atom->arg[0].obj == atom->arg[1].obj){
                    bval = !atom->neg;
                }else{
                    bval = !!(atom->neg);
                }
                pddlFmDel(&atom->fm);
                return &fmBoolNew(bval)->fm;
            }

        }else if (pddlFmAtomIsGrounded(atom)){
            // If the atom is static and fully grounded we can evaluate it
            // right now by comparing it to the inital state
            if (atomIsInInit(pddl, atom)){
                bval = !atom->neg;
            }else{
                bval = !!(atom->neg);
            }
            pddlFmDel(&atom->fm);
            return &fmBoolNew(bval)->fm;

        }else if (atom->neg && !atomIsPartiallyInInit(pddl, atom)){
            // If the atom is static but not fully grounded we can evaluate
            // it if there is no atom matching the grounded parts
            bval = !!(atom->neg);
            pddlFmDel(&atom->fm);
            return &fmBoolNew(bval)->fm;
        }
    }

    return &atom->fm;
}

static pddl_fm_t *removeBoolImply(pddl_fm_imply_t *imp)
{
    if (imp->left->type == PDDL_FM_BOOL){
        pddl_fm_bool_t *b = pddlFmToBool(imp->left);
        if (b->val){
            pddl_fm_t *ret = imp->right;
            imp->right = NULL;
            pddlFmDel(&imp->fm);
            return ret;

        }else{
            pddlFmDel(&imp->fm);
            return &fmBoolNew(1)->fm;
        }
    }

    return &imp->fm;
}

static int removeBool(pddl_fm_t **c, void *data)
{
    const pddl_t *pddl = data;

    if ((*c)->type == PDDL_FM_ATOM){
        *c = removeBoolAtom(pddlFmToAtom(*c), pddl);

    }else if ((*c)->type == PDDL_FM_AND
            || (*c)->type == PDDL_FM_OR){
        *c = removeBoolPart(pddlFmToJunc(*c));

    }else if ((*c)->type == PDDL_FM_WHEN){
        *c = removeBoolWhen(pddlFmToWhen(*c));

    }else if ((*c)->type == PDDL_FM_IMPLY){
        *c = removeBoolImply(pddlFmToImply(*c));
    }

    return 0;
}

static pddl_fm_t *flattenPart(pddl_fm_junc_t *part)
{
    pddl_list_t *item, *tmp;
    pddl_fm_t *c;
    pddl_fm_junc_t *p;

    if (pddlListEmpty(&part->part))
        return &part->fm;

    PDDL_LIST_FOR_EACH_SAFE(&part->part, item, tmp){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);

        if (c->type == part->fm.type){
            // Flatten con/disjunctions
            p = pddlFmToJunc(c);
            fmPartStealPart(part, p);

            pddlListDel(item);
            pddlFmDel(c);

        }else if ((c->type == PDDL_FM_AND || c->type == PDDL_FM_OR)
                && pddlListEmpty(&pddlFmToJunc(c)->part)){
            pddlListDel(item);
            pddlFmDel(c);
        }

    }

    // If the con/disjunction contains only one atom, remove the
    // con/disjunction and return the atom directly
    if (pddlListPrev(&part->part) == pddlListNext(&part->part)){
        item = pddlListNext(&part->part);
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        pddlListDel(item);
        pddlFmDel(&part->fm);
        return c;
    }

    return &part->fm;
}

/** Splits (when ...) if its precondition is disjunction */
static pddl_fm_t *flattenWhen(pddl_fm_when_t *when)
{
    pddl_list_t *item;
    pddl_fm_t *c;
    pddl_fm_junc_t *pre;
    pddl_fm_junc_t *and;
    pddl_fm_when_t *add;

    if (!when->pre || when->pre->type != PDDL_FM_OR)
        return &when->fm;

    and = fmPartNew(PDDL_FM_AND);
    pre = pddlFmToJunc(when->pre);
    when->pre = NULL;

    while (!pddlListEmpty(&pre->part)){
        item = pddlListNext(&pre->part);
        pddlListDel(item);
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        add = fmWhenClone(when);
        add->pre = c;
        fmPartAdd(and, &add->fm);
    }

    pddlFmDel(&pre->fm);
    pddlFmDel(&when->fm);

    return &and->fm;
}

static int flatten(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND
            || (*c)->type == PDDL_FM_OR){
        *c = flattenPart(pddlFmToJunc(*c));

    }else if ((*c)->type == PDDL_FM_WHEN){
        *c = flattenWhen(pddlFmToWhen(*c));
    }

    return 0;
}

static pddl_fm_junc_t *moveDisjunctionsCreate1(pddl_fm_junc_t *top,
                                               pddl_fm_junc_t *or)
{
    pddl_fm_junc_t *ret;
    pddl_list_t *item1, *item2;
    pddl_fm_t *c1, *c2;
    pddl_fm_junc_t *add;

    ret = fmPartNew(PDDL_FM_OR);
    PDDL_LIST_FOR_EACH(&top->part, item1){
        c1 = PDDL_LIST_ENTRY(item1, pddl_fm_t, conn);
        PDDL_LIST_FOR_EACH(&or->part, item2){
            c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            add = pddlFmToJunc(c1);
            add = fmPartClone(add);
            fmPartAdd(add, pddlFmClone(c2));
            fmPartAdd(ret, &add->fm);
        }
    }

    pddlFmDel(&top->fm);
    return ret;
}

static pddl_fm_t *moveDisjunctionsCreate(pddl_fm_junc_t *and,
                                         pddl_list_t *or_list)
{
    pddl_list_t *or_item;
    pddl_fm_junc_t *or;
    pddl_fm_junc_t *ret;

    ret = fmPartNew(PDDL_FM_OR);
    fmPartAdd(ret, &and->fm);
    while (!pddlListEmpty(or_list)){
        or_item = pddlListNext(or_list);
        pddlListDel(or_item);
        or = pddlFmToJunc(PDDL_LIST_ENTRY(or_item, pddl_fm_t, conn));
        ret = moveDisjunctionsCreate1(ret, or);
        pddlFmDel(&or->fm);
    }

    return &ret->fm;
}

static pddl_fm_t *moveDisjunctionsUpAnd(pddl_fm_junc_t *and)
{
    pddl_list_t *item, *tmp;
    pddl_list_t or_list;
    pddl_fm_t *c;

    pddlListInit(&or_list);
    PDDL_LIST_FOR_EACH_SAFE(&and->part, item, tmp){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c->type != PDDL_FM_OR)
            continue;

        pddlListDel(item);
        pddlListAppend(&or_list, item);
    }

    if (pddlListEmpty(&or_list)){
        return &and->fm;
    }

    return moveDisjunctionsCreate(and, &or_list);
}

static int moveDisjunctionsUp(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND)
        *c = moveDisjunctionsUpAnd(pddlFmToJunc(*c));

    if ((*c)->type == PDDL_FM_OR)
        *c = flattenPart(pddlFmToJunc(*c));
    return 0;
}

/** (imply ...) is considered static if it has a simple flattened left and
 *  right side and the left side consists solely of static predicates. */
static pddl_bool_t isStaticImply(const pddl_fm_imply_t *imp, const pddl_t *pddl)
{
    ASSERT(imp->left != NULL && imp->right != NULL);
    pddl_fm_t *c;
    pddl_list_t *item;

    if (imp->left->type == PDDL_FM_ATOM){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(imp->left);
        if (atom->pred < 0)
            return pddl_false;
        if (!pddlPredIsStatic(&pddl->pred.pred[atom->pred]))
            return pddl_false;

    }else if (imp->left->type == PDDL_FM_AND){
        const pddl_fm_junc_t *and = pddlFmToJuncConst(imp->left);
        PDDL_LIST_FOR_EACH(&and->part, item){
            c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (c->type != PDDL_FM_ATOM)
                return pddl_false;

            const pddl_fm_atom_t *atom = pddlFmToAtom(c);
            if (atom->pred < 0)
                return pddl_false;
            if (!pddlPredIsStatic(&pddl->pred.pred[atom->pred]))
                return pddl_false;
        }

    }else{
        return pddl_false;
    }

    if (imp->right->type == PDDL_FM_ATOM){
        return pddl_true;

    }else if (imp->right->type == PDDL_FM_AND){
        const pddl_fm_junc_t *and = pddlFmToJuncConst(imp->right);
        PDDL_LIST_FOR_EACH(&and->part, item){
            c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (c->type != PDDL_FM_ATOM)
                return pddl_false;
        }

    }else{
        return pddl_false;
    }

    return pddl_true;
}

static int removeNonStaticImply(pddl_fm_t **c, void *data)
{
    pddl_fm_imply_t *imp;
    const pddl_t *pddl = data;

    if ((*c)->type != PDDL_FM_IMPLY)
        return 0;
    imp = pddlFmToImply(*c);
    if (!isStaticImply(imp, pddl)){
        pddl_fm_junc_t *or;
        or = fmPartNew(PDDL_FM_OR);
        pddlFmJuncAdd(or, pddlFmNegate(imp->left, pddl));
        pddlFmJuncAdd(or, imp->right);
        *c = &or->fm;

        imp->right = NULL;
        pddlFmDel(&imp->fm);
    }

    return 0;
}


static void implyAtomParams(const pddl_fm_atom_t *atom, pddl_iset_t *params)
{
    for (int i = 0; i < atom->arg_size; ++i){
        if (atom->arg[i].param >= 0)
            pddlISetAdd(params, atom->arg[i].param);
    }
}

static int implyParams(pddl_fm_t *c, void *data)
{
    pddl_iset_t *params = data;
    pddl_fm_imply_t *imp;
    pddl_list_t *item;
    pddl_fm_junc_t *and;
    pddl_fm_t *p;

    if (c->type == PDDL_FM_IMPLY){
        imp = pddlFmToImply(c);
        if (imp->left->type == PDDL_FM_ATOM){
            implyAtomParams(pddlFmToAtom(imp->left), params);

        }else if (imp->left->type == PDDL_FM_AND){
            and = pddlFmToJunc(imp->left);
            PDDL_LIST_FOR_EACH(&and->part, item){
                p = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
                if (p->type == PDDL_FM_ATOM)
                    implyAtomParams(pddlFmToAtom(p), params);
            }
        }
    }

    return 0;
}

struct instantiate_ctx {
    const pddl_iset_t *params;
    const int *arg;
};
typedef struct instantiate_ctx instantiate_ctx_t;

static int instantiateTraverse(pddl_fm_t *fm, void *ud)
{
    const instantiate_ctx_t *ctx = ud;
    if (fm->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *atom = pddlFmToAtom(fm);
        for (int i = 0; i < atom->arg_size; ++i){
            for (int j = 0; j < pddlISetSize(ctx->params); ++j){
                if (atom->arg[i].param == pddlISetGet(ctx->params, j)){
                    atom->arg[i].param = -1;
                    atom->arg[i].obj = ctx->arg[j];
                    break;
                }
            }
        }
    }

    return 0;
}

static pddl_fm_t *instantiate(pddl_fm_t *fm,
                              const pddl_iset_t *params,
                              const int *arg,
                              int eq_pred)
{
    pddl_fm_junc_t *and;
    pddl_fm_atom_t *eq;
    pddl_fm_t *c = pddlFmClone(fm);
    instantiate_ctx_t ctx;

    and = fmPartNew(PDDL_FM_AND);
    for (int i = 0; i < pddlISetSize(params); ++i){
        int param = pddlISetGet(params, i);
        eq = fmAtomNew();
        eq->pred = eq_pred;
        eq->arg_size = 2;
        eq->arg = ALLOC_ARR(pddl_fm_atom_arg_t, 2);
        eq->arg[0].param = param;
        eq->arg[0].obj = -1;
        eq->arg[1].param = -1;
        eq->arg[1].obj = arg[i];
        pddlFmJuncAdd(and, &eq->fm);
    }

    ctx.params = params;
    ctx.arg = arg;
    pddlFmTraverseProp(c, NULL, instantiateTraverse, &ctx);

    pddlFmJuncAdd(and, c);
    return &and->fm;
}

static void removeStaticImplyRec(pddl_fm_junc_t *top,
                                 pddl_fm_t *fm,
                                 const pddl_t *pddl,
                                 const pddl_params_t *params,
                                 const pddl_iset_t *imp_params,
                                 int pidx,
                                 int *arg)
{
    const int *obj;
    int obj_size;

    if (pidx == pddlISetSize(imp_params)){
        pddl_fm_t *c = instantiate(fm, imp_params, arg, pddl->pred.eq_pred);
        pddlFmJuncAdd(top, c);
    }else{
        int param = pddlISetGet(imp_params, pidx);
        obj = pddlTypesObjsByType(&pddl->type, params->param[param].type,
                                  &obj_size);
        for (int i = 0; i < obj_size; ++i){
            arg[pidx] = obj[i];
            removeStaticImplyRec(top, fm, pddl, params,
                                 imp_params, pidx + 1, arg);
        }
    }
}

/** Implications are removed by instantiation of the left sides and putting
 *  the instantiated objects to (= ...) predicate. */
static int removeStaticImply(pddl_fm_t **fm, const pddl_t *pddl,
                             const pddl_params_t *params)
{
    pddl_fm_junc_t *or;
    PDDL_ISET(imply_params);
    int *obj;

    if (params == NULL)
        return 0;

    pddlFmTraverseProp(*fm, NULL, implyParams, &imply_params);
    if (pddlISetSize(&imply_params) > 0){
        obj = ALLOC_ARR(int, pddlISetSize(&imply_params));
        or = fmPartNew(PDDL_FM_OR);
        removeStaticImplyRec(or, *fm, pddl, params, &imply_params, 0, obj);
        FREE(obj);
        pddlFmDel(*fm);
        *fm = &or->fm;
    }
    pddlISetFree(&imply_params);
    return 0;
}

pddl_fm_t *pddlFmNormalize(pddl_fm_t *fm,
                           const pddl_t *pddl,
                           const pddl_params_t *params)
{
    pddl_fm_t *c = fm;

    // TODO: Check return values
    pddlFmInstantiateQuant(&c, &pddl->type);
    pddlFmRebuildProp(&c, NULL, removeNonStaticImply, (void *)pddl);
    removeStaticImply(&c, pddl, params);
    pddlFmRebuildProp(&c, NULL, removeBool, (void *)pddl);
    pddlFmRebuildProp(&c, NULL, flatten, NULL);
    pddlFmRebuildProp(&c, NULL, moveDisjunctionsUp, NULL);
    pddlFmRebuildProp(&c, NULL, flatten, NULL);
    c = pddlFmDeduplicateAtoms(c, pddl);
    return c;
}

static void _deduplicateAtoms(pddl_fm_junc_t *p)
{
    pddl_list_t *item = pddlListNext(&p->part);
    while (item != &p->part){
        pddl_fm_t *c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c1->type != PDDL_FM_ATOM){
            item = pddlListNext(item);
            continue;
        }

        pddl_list_t *item2 = pddlListNext(item);
        for (; item2 != &p->part;){
            pddl_fm_t *c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (c2->type == PDDL_FM_ATOM
                    && pddlFmAtomCmp(pddlFmToAtom(c1), pddlFmToAtom(c2)) == 0){
                pddl_list_t *item_del = item2;
                item2 = pddlListNext(item2);
                pddlListDel(item_del);
                pddlFmDel(c2);

            }else{
                item2 = pddlListNext(item2);
            }
        }
        item = pddlListNext(item);
    }
}

static int deduplicateAtoms(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR)
        _deduplicateAtoms(pddlFmToJunc(*c));
    return 0;
}

pddl_fm_t *pddlFmDeduplicateAtoms(pddl_fm_t *fm, const pddl_t *pddl)
{
    pddl_fm_t *c = fm;
    pddlFmRebuildProp(&c, NULL, deduplicateAtoms, NULL);
    return c;
}

static void _deduplicate(pddl_fm_junc_t *p)
{
    pddl_list_t *item = pddlListNext(&p->part);
    while (item != &p->part){
        pddl_fm_t *c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);

        pddl_list_t *item2 = pddlListNext(item);
        for (; item2 != &p->part;){
            pddl_fm_t *c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (pddlFmEq(c1, c2)){
                pddl_list_t *item_del = item2;
                item2 = pddlListNext(item2);
                pddlListDel(item_del);
                pddlFmDel(c2);

            }else{
                item2 = pddlListNext(item2);
            }
        }
        item = pddlListNext(item);
    }
}

static int deduplicate(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR)
        _deduplicate(pddlFmToJunc(*c));
    return 0;
}

pddl_fm_t *pddlFmDeduplicate(pddl_fm_t *fm, const pddl_t *pddl)
{
    pddl_fm_t *c = fm;
    pddlFmRebuildProp(&c, NULL, deduplicate, NULL);
    return c;
}


static int removeConflictsInEff(pddl_fm_junc_t *p)
{
    pddl_list_t *item, *item2, *tmp;
    pddl_fm_t *c1, *c2;
    pddl_fm_atom_t *a1, *a2;
    int change = 0;

    for (item = pddlListNext(&p->part); item != &p->part;){
        c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c1->type != PDDL_FM_ATOM){
            item = pddlListNext(item);
            continue;
        }
        a1 = pddlFmToAtom(c1);

        for (item2 = pddlListNext(item); item2 != &p->part;){
            c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (c2->type != PDDL_FM_ATOM){
                item2 = pddlListNext(item2);
                continue;
            }
            a2 = pddlFmToAtom(c2);

            if (pddlFmAtomInConflict(a1, a2, NULL)){
                if (a1->neg){
                    tmp = pddlListPrev(item);
                    pddlListDel(item);
                    pddlFmDel(&a1->fm);
                    item = tmp;
                    change = 1;
                    break;

                }else{
                    tmp = pddlListPrev(item2);
                    pddlListDel(item2);
                    pddlFmDel(&a2->fm);
                    item2 = tmp;
                    change = 1;
                }
            }
            item2 = pddlListNext(item2);
        }

        item = pddlListNext(item);
    }

    return change;
}

static int deconflictEffPost(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR){
        if (removeConflictsInEff(pddlFmToJunc(*c)))
            *((int *)data) = 1;
    }
    return 0;
}

static int deconflictEffPre(pddl_fm_t **c, void *data)
{
    ASSERT(*c != NULL);
    if ((*c)->type == PDDL_FM_WHEN){
        pddl_fm_when_t *w = pddlFmToWhen(*c);
        pddlFmRebuildProp(&w->eff, deconflictEffPre, deconflictEffPost, data);
        return -1;
    }
    return 0;
}

pddl_fm_t *pddlFmDeconflictEff(pddl_fm_t *fm, const pddl_t *pddl,
                               const pddl_params_t *params)
{
    pddl_fm_t *c = fm;
    int change = 0;
    pddlFmRebuildProp(&c, deconflictEffPre, deconflictEffPost, &change);
    if (change)
        c = pddlFmNormalize(c, pddl, params);
    return c;
}

struct simplify {
    const pddl_t *pddl;
    const pddl_params_t *params;
    int change;
};

static int reorderEqPredicates(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if ((*c)->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *a = pddlFmToAtom(*c);
        if (a->pred == d->pddl->pred.eq_pred){
            if (a->arg[0].param >= 0 && a->arg[1].param >= 0){
                if (a->arg[0].param > a->arg[1].param){
                    int p;
                    PDDL_SWAP(a->arg[0].param, a->arg[1].param, p);
                }
            }else if (a->arg[0].param >= 0){
                // Do nothing, it's already ordered
            }else if (a->arg[1].param >= 0){
                a->arg[0].param = a->arg[1].param;
                a->arg[1].obj = a->arg[0].obj;
                a->arg[0].obj = -1;
                a->arg[1].param = -1;
            }else{
                pddl_fm_t *b = NULL;
                if (!a->neg){
                    if (a->arg[0].obj == a->arg[1].obj){
                        b = &pddlFmNewBool(1)->fm;
                    }else{
                        b = &pddlFmNewBool(0)->fm;
                    }
                }else{ // a->neg
                    if (a->arg[0].obj == a->arg[1].obj){
                        b = &pddlFmNewBool(0)->fm;
                    }else{
                        b = &pddlFmNewBool(1)->fm;
                    }
                }
                pddlFmDel(*c);
                *c = b;
            }
        }
    }

    return 0;
}

static int simplifyBoolsInPart(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR){
        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        pddl_list_t *item, *itmp;
        PDDL_LIST_FOR_EACH_SAFE(&p->part, item, itmp){
            pddl_fm_t *cb = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (cb->type == PDDL_FM_BOOL){
                pddl_fm_bool_t *b = pddlFmToBool(cb);
                if (b->val){
                    if ((*c)->type == PDDL_FM_AND){
                        pddlListDel(&cb->conn);
                        pddlFmDel(cb);
                        d->change = 1;
                    }else{
                        pddlFmDel(*c);
                        *c = &pddlFmNewBool(1)->fm;
                        d->change = 1;
                        return 0;
                    }
                }else{
                    if ((*c)->type == PDDL_FM_AND){
                        pddlFmDel(*c);
                        *c = &pddlFmNewBool(0)->fm;
                        d->change = 1;
                        return 0;
                    }else{
                        pddlListDel(&cb->conn);
                        pddlFmDel(cb);
                        d->change = 1;
                    }
                }
            }
        }
    }
    return 0;
}

static int simplifySingletonPart(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR){
        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        pddl_list_t *next = pddlListNext(&p->part);
        if (next != &p->part && pddlListNext(next) == &p->part){
            pddl_fm_t *e = PDDL_LIST_ENTRY(next, pddl_fm_t, conn);
            pddlListDel(&e->conn);
            pddlFmDel(*c);
            *c = e;
            d->change = 1;
        }
    }
    return 0;
}

static int simplifyNestedPart(pddl_fm_t **c, void *data)
{
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR){
        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        *c = flattenPart(p);
    }
    return 0;
}

static int simplifyConflictAtoms(pddl_fm_t **c, void *data)
{
    if ((*c)->type != PDDL_FM_AND && (*c)->type != PDDL_FM_OR)
        return 0;

    struct simplify *d = data;
    pddl_fm_junc_t *p = pddlFmToJunc(*c);
    pddl_list_t *item;

    PDDL_LIST_FOR_EACH(&p->part, item){
        pddl_fm_t *c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c1->type != PDDL_FM_ATOM)
            continue;
        pddl_fm_atom_t *a1 = pddlFmToAtom(c1);

        pddl_list_t *item2 = pddlListNext(item);
        for (; item2 != &p->part; item2 = pddlListNext(item2)){
            pddl_fm_t *c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (c2->type != PDDL_FM_ATOM)
                continue;
            pddl_fm_atom_t *a2 = pddlFmToAtom(c2);

            if (pddlFmAtomInConflict(a1, a2, d->pddl)){
                if ((*c)->type == PDDL_FM_AND){
                    pddlFmDel(*c);
                    *c = &pddlFmNewBool(0)->fm;
                    d->change = 1;
                    return 0;
                }else{
                    pddlFmDel(*c);
                    *c = &pddlFmNewBool(1)->fm;
                    d->change = 1;
                    return 0;
                }
            }
        }
    }

    return 0;
}

static int simplifyConflictEqAtoms(pddl_fm_t **c, void *data)
{
    if ((*c)->type != PDDL_FM_AND)
        return 0;

    // Here, we assume that the arguments are already sorted with
    // reorderEqPredicates
    struct simplify *d = data;
    int eq_pred = d->pddl->pred.eq_pred;
    pddl_fm_junc_t *p = pddlFmToJunc(*c);
    pddl_list_t *item;

    PDDL_LIST_FOR_EACH(&p->part, item){
        pddl_fm_t *c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (c1->type != PDDL_FM_ATOM)
            continue;
        pddl_fm_atom_t *a1 = pddlFmToAtom(c1);
        if (a1->pred != eq_pred
                || a1->neg
                || a1->arg[0].param < 0
                || a1->arg[1].param >= 0){
            continue;
        }
        // Now a1 := (= p o)

        pddl_list_t *item2, *itmp;
        PDDL_LIST_FOR_EACH_SAFE(&p->part, item2, itmp){
            pddl_fm_t *c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            if (c2->type != PDDL_FM_ATOM)
                continue;
            pddl_fm_atom_t *a2 = pddlFmToAtom(c2);
            if (a2->pred == eq_pred
                    && a2->arg[0].param == a1->arg[0].param
                    && a2->arg[1].param < 0
                    && a2->arg[1].obj != a1->arg[1].obj){
                if (a2->neg){
                    // a1 := (= p o); a2 := (not (= p o')), o != o', so a2 is
                    // redundant
                    pddlListDel(&c2->conn);
                    pddlFmDel(c2);
                    d->change = 1;
                }else{
                    // a1 := (= p o); a2 := (= p o'), o != o', which can
                    // never be true
                    pddlFmDel(*c);
                    *c = &pddlFmNewBool(0)->fm;
                    d->change = 1;
                    return 0;
                }
            }
        }
    }

    return 0;
}

static int entailsAny(const pddl_fm_t *c,
                      const pddl_fm_junc_t *p,
                      const pddl_t *pddl,
                      const pddl_params_t *param)
{
    pddl_list_t *item;
    PDDL_LIST_FOR_EACH(&p->part, item){
        const pddl_fm_t *s = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (s == c)
            continue;
        if (pddlFmIsJunc(c) || pddlFmIsAtom(c) || pddlFmIsBool(c)){
            if (pddlFmIsEntailed(s, c, pddl, param))
                return 1;
        }
    }
    return 0;
}

/** ((A or B) and (A => B)) -> B
 *  ((A and B) and (A => B)) -> A */
static int simplifyByEntailement(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if ((*c)->type == PDDL_FM_AND){
        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        pddl_list_t *item = pddlListNext(&p->part);
        while (item != &p->part){
            pddl_fm_t *s = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (!pddlFmIsJunc(s) && !pddlFmIsAtom(s) && !pddlFmIsBool(s)){
                item = pddlListNext(item);
                continue;
            }

            pddl_list_t *item2, *tmp;
            PDDL_LIST_FOR_EACH_SAFE(&p->part, item2, tmp){
                if (item2 == item)
                    continue;
                pddl_fm_t *x = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
                if (!pddlFmIsJunc(x) && !pddlFmIsAtom(x) && !pddlFmIsBool(x))
                    continue;
                if (pddlFmIsEntailed(x, s, d->pddl, d->params)){
                    pddlListDel(&x->conn);
                    pddlFmDel(x);
                    d->change = 1;
                }
            }

            item = pddlListNext(item);
        }

    }else if ((*c)->type == PDDL_FM_OR){
        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        pddl_list_t *item, *tmp;
        PDDL_LIST_FOR_EACH_SAFE(&p->part, item, tmp){
            pddl_fm_t *x = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (pddlFmIsJunc(x) || pddlFmIsAtom(x) || pddlFmIsBool(x)){
                if (entailsAny(x, p, d->pddl, d->params)){
                    pddlListDel(&x->conn);
                    pddlFmDel(x);
                    d->change = 1;
                }
            }
        }
    }
    return 0;
}

static int atomHasNegationInDisjunction(const pddl_fm_atom_t *atom,
                                        const pddl_fm_junc_t *disj,
                                        pddl_fm_atom_t **witness)
{
    *witness = NULL;
    pddl_fm_const_it_atom_t it;
    const pddl_fm_atom_t *datom;
    PDDL_FM_FOR_EACH_ATOM(&disj->fm, &it, datom){
        if (fmAtomEqNoNeg(atom, datom) && !!(atom->neg) == !datom->neg){
            *witness = (pddl_fm_atom_t *)datom;
            return 1;
        }
    }
    return 0;
}

/** ((A or not B) and B) -> A and B
 *  ((A and not B) or B) -> A or B */
static int simplifyByNegationDistribution(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if ((*c)->type == PDDL_FM_AND || (*c)->type == PDDL_FM_OR){
        int other_type = PDDL_FM_OR;
        if ((*c)->type == PDDL_FM_OR)
            other_type = PDDL_FM_AND;

        pddl_fm_junc_t *p = pddlFmToJunc(*c);
        pddl_list_t *item = pddlListNext(&p->part);
        while (item != &p->part){
            pddl_fm_t *s1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
            if (s1->type != other_type && s1->type != PDDL_FM_ATOM){
                item = pddlListNext(item);
                continue;
            }

            pddl_list_t *item2 = pddlListNext(item);
            while (item2 != &p->part){
                pddl_fm_t *s2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
                pddl_fm_atom_t *atom = NULL;
                pddl_fm_junc_t *part = NULL;
                if (s1->type == other_type && s2->type == PDDL_FM_ATOM){
                    atom = pddlFmToAtom(s2);
                    part = pddlFmToJunc(s1);

                }else if (s2->type == other_type && s1->type == PDDL_FM_ATOM){
                    atom = pddlFmToAtom(s1);
                    part = pddlFmToJunc(s2);
                }

                if (atom != NULL && part != NULL){
                    pddl_fm_atom_t *witness;
                    if (atomHasNegationInDisjunction(atom, part, &witness)){
                        pddlFmJuncRm(part, &witness->fm);
                        d->change = 1;
                        return 0;
                    }
                }

                item2 = pddlListNext(item2);
            }

            item = pddlListNext(item);
        }
    }
    return 0;
}

static pddl_fm_t *computeBinOpWithFValues(const pddl_fm_num_exp_t *e,
                                          float l, float r)
{
    pddl_fm_num_exp_t *v = fmNumExpNew(PDDL_FM_NUM_EXP_FNUM);
    if (pddlFmIsNumExpPlus(&e->fm)){
        v->e.inum = l + r;

    }else if (pddlFmIsNumExpMinus(&e->fm)){
        v->e.inum = l - r;

    }else if (pddlFmIsNumExpMult(&e->fm)){
        v->e.inum = l * r;

    }else if (pddlFmIsNumExpDiv(&e->fm)){
        v->e.fnum = l / r;
    }
    return &v->fm;
}

static int simplifyNumExpBinOpValues(pddl_fm_t **c)
{
    if (!pddlFmIsNumExpBinOp(*c))
        return 0;

    pddl_fm_num_exp_t *e = pddlFmToNumExp(*c);
    pddl_fm_num_exp_t *left = e->e.bin_op.left;
    pddl_fm_num_exp_t *right = e->e.bin_op.right;

    if (pddlFmIsNumExpINum(&left->fm) && pddlFmIsNumExpINum(&right->fm)){
        int l = left->e.inum;
        int r = right->e.inum;
        pddl_fm_num_exp_t *v = fmNumExpNew(PDDL_FM_NUM_EXP_INUM);
        if (pddlFmIsNumExpPlus(&e->fm)){
#if defined(__GNUC__) || defined(__clang__)
            if (__builtin_sadd_overflow(l, r, &v->e.inum)){
                PANIC("Overflow when simplifying the numeric expression %d + %d", l, r);
            }
#else
            v->e.inum = l + r;
            // Ignore overflows if we cannot do it in a "nice" way
#endif

        }else if (pddlFmIsNumExpMinus(&e->fm)){
#if defined(__GNUC__) || defined(__clang__)
            if (__builtin_ssub_overflow(l, r, &v->e.inum)){
                PANIC("Overflow when simplifying the numeric expression %d - %d", l, r);
            }
#else
            v->e.inum = l - r;
            // Ignore overflows if we cannot do it in a "nice" way
#endif

        }else if (pddlFmIsNumExpMult(&e->fm)){
#if defined(__GNUC__) || defined(__clang__)
            if (__builtin_smul_overflow(l, r, &v->e.inum)){
                PANIC("Overflow when simplifying the numeric expression %d * %d", l, r);
            }
#else
            v->e.inum = l * r;
            // Ignore overflows if we cannot do it in a "nice" way
#endif

        }else if (pddlFmIsNumExpDiv(&e->fm)){
            v->fm.type = PDDL_FM_NUM_EXP_FNUM;
            v->e.fnum = (float)l / (float)r;
        }

        pddlFmDel(*c);
        *c = &v->fm;
        return 1;

    }else if (pddlFmIsNumExpINum(&left->fm) && pddlFmIsNumExpFNum(&right->fm)){
        pddl_fm_t *v = computeBinOpWithFValues(e, left->e.inum, right->e.fnum);
        pddlFmDel(*c);
        *c = v;
        return 1;

    }else if (pddlFmIsNumExpFNum(&left->fm) && pddlFmIsNumExpINum(&right->fm)){
        pddl_fm_t *v = computeBinOpWithFValues(e, left->e.fnum, right->e.inum);
        pddlFmDel(*c);
        *c = v;
        return 1;

    }else if (pddlFmIsNumExpFNum(&left->fm) && pddlFmIsNumExpFNum(&right->fm)){
        pddl_fm_t *v = computeBinOpWithFValues(e, left->e.fnum, right->e.fnum);
        pddlFmDel(*c);
        *c = v;
        return 1;
    }

    return 0;
}

/** (* 0 xxx) -> 0
 *  (+ 0 xxx) -> xxx
 *  (* 1 xxx) -> xxx
 *  (/ xxx 1) -> xxx
 *  (/ 0 xxx) -> 0 */
static int simplifyNumExpBinOpSpecialCases(pddl_fm_t **c)
{
    if (!pddlFmIsNumExpBinOp(*c))
        return 0;

    pddl_fm_num_exp_t *e = pddlFmToNumExp(*c);
    pddl_fm_num_exp_t *left = e->e.bin_op.left;
    pddl_fm_num_exp_t *right = e->e.bin_op.right;

    if (pddlFmIsNumExpPlus(&e->fm)){
        if (pddlFmIsNumExpINum(&left->fm) && left->e.inum == 0){
            e->e.bin_op.right = NULL;
            pddlFmDel(*c);
            *c = &right->fm;
            return 1;

        }else if (pddlFmIsNumExpINum(&right->fm) && right->e.inum == 0){
            e->e.bin_op.left = NULL;
            pddlFmDel(*c);
            *c = &left->fm;
            return 1;
        }

    }else if (pddlFmIsNumExpMinus(&e->fm)){
        if (pddlFmIsNumExpINum(&right->fm) && right->e.inum == 0){
            e->e.bin_op.left = NULL;
            pddlFmDel(*c);
            *c = &left->fm;
            return 1;
        }

    }else if (pddlFmIsNumExpMult(&e->fm)){
        if ((pddlFmIsNumExpINum(&left->fm) && left->e.inum == 0)
                || (pddlFmIsNumExpINum(&right->fm) && right->e.inum == 0)){
            pddl_fm_num_exp_t *v = fmNumExpNew(PDDL_FM_NUM_EXP_INUM);
            v->e.inum = 0;
            pddlFmDel(*c);
            *c = &v->fm;
            return 1;

        }else if (pddlFmIsNumExpINum(&left->fm) && left->e.inum == 1){
            e->e.bin_op.right = NULL;
            pddlFmDel(*c);
            *c = &right->fm;
            return 1;

        }else if (pddlFmIsNumExpINum(&right->fm) && right->e.inum == 1){
            e->e.bin_op.left = NULL;
            pddlFmDel(*c);
            *c = &left->fm;
            return 1;
        }

    }else if (pddlFmIsNumExpDiv(&e->fm)){
        if (pddlFmIsNumExpINum(&left->fm) && left->e.inum == 0){
            pddl_fm_num_exp_t *v = fmNumExpNew(PDDL_FM_NUM_EXP_INUM);
            v->e.inum = 0;
            pddlFmDel(*c);
            *c = &v->fm;
            return 1;

        }else if (pddlFmIsNumExpINum(&right->fm) && right->e.inum == 1){
            e->e.bin_op.left = NULL;
            pddlFmDel(*c);
            *c = &left->fm;
            return 1;
        }
    }

    return 0;
}

static int simplifyNumExp(pddl_fm_t **c, void *data)
{
    struct simplify *d = data;
    if (pddlFmIsNumExpFNum(*c)){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(*c);
        if (pddlFmNumExpCanRecastFNumToINum(e)){
            pddlFmNumExpRecastFNumToINum(e);
            d->change = 1;
            return 0;
        }

    }else if (simplifyNumExpBinOpValues(c)){
        d->change = 1;
        return 0;

    }else if (simplifyNumExpBinOpSpecialCases(c)){
        d->change = 1;
        return 0;
    }

    return 0;
}

pddl_fm_t *pddlFmSimplify(pddl_fm_t *fm,
                          const pddl_t *pddl,
                          const pddl_params_t *params)
{
    struct simplify d;
    pddl_fm_t *c = fm;

    d.pddl = pddl;
    d.params = params;
    d.change = 0;

    pddlFmRebuildProp(&c, NULL, reorderEqPredicates, &d);
    do {
        d.change = 0;
        pddlFmRebuildProp(&c, NULL, simplifyBoolsInPart, &d);
        pddlFmRebuildProp(&c, NULL, simplifySingletonPart, &d);
        pddlFmRebuildProp(&c, NULL, simplifyNestedPart, &d);
        pddlFmRebuildProp(&c, NULL, simplifyConflictAtoms, &d);
        pddlFmRebuildProp(&c, NULL, simplifyConflictEqAtoms, &d);
        pddlFmRebuildProp(&c, NULL, simplifyByEntailement, &d);
        pddlFmRebuildProp(&c, NULL, simplifyByNegationDistribution, &d);
        pddlFmRebuildAll(&c, NULL, simplifyNumExp, &d);
        c = pddlFmDeduplicate(c, pddl);
    } while (d.change);
    return c;
}

pddl_bool_t pddlFmAtomIsGrounded(const pddl_fm_atom_t *atom)
{
    for (int i = 0; i < atom->arg_size; ++i){
        if (atom->arg[i].param >= 0)
            return pddl_false;
    }
    return pddl_true;
}

static int cmpAtomArgs(const pddl_fm_atom_t *a1, const pddl_fm_atom_t *a2)
{
    int cmp = 0;
    if (a1->arg_size != a2->arg_size)
        return a1->arg_size - a2->arg_size;
    for (int i = 0; i < a1->arg_size && cmp == 0; ++i){
        cmp = a1->arg[i].param - a2->arg[i].param;
        if (cmp == 0)
            cmp = a1->arg[i].obj - a2->arg[i].obj;
    }
    return cmp;
}

static int cmpAtoms(const pddl_fm_atom_t *a1, const pddl_fm_atom_t *a2,
                    int neg)
{
    int cmp;

    cmp = a1->pred - a2->pred;
    if (cmp == 0){
        cmp = cmpAtomArgs(a1, a2);
        if (cmp == 0 && neg)
            return a1->neg - a2->neg;
    }

    return cmp;
}

int pddlFmAtomCmp(const pddl_fm_atom_t *a1,
                  const pddl_fm_atom_t *a2)
{
    return cmpAtoms(a1, a2, 1);
}

int pddlFmAtomCmpNoNeg(const pddl_fm_atom_t *a1,
                       const pddl_fm_atom_t *a2)
{
    return cmpAtoms(a1, a2, 0);
}

static int atomNegPred(const pddl_fm_atom_t *a, const pddl_t *pddl)
{
    int pred = a->pred;
    if (pddl->pred.pred[a->pred].neg_of >= 0)
        pred = PDDL_MIN(pred, pddl->pred.pred[a->pred].neg_of);
    return pred;
}

pddl_bool_t pddlFmAtomInConflict(const pddl_fm_atom_t *a1,
                                 const pddl_fm_atom_t *a2,
                                 const pddl_t *pddl)
{
    if (a1->pred == a2->pred && a1->neg != a2->neg)
        return cmpAtomArgs(a1, a2) == 0;
    if (pddl != NULL
            && a1->pred != a2->pred
            && atomNegPred(a1, pddl) == atomNegPred(a2, pddl)
            && !!(a1->neg) == !!(a2->neg)){
        return cmpAtomArgs(a1, a2) == 0;
    }
    return pddl_false;
}

static void fmAtomRemapObjs(pddl_fm_atom_t *a, const int *remap)
{
    for (int i = 0; i < a->arg_size; ++i){
        if (a->arg[i].obj >= 0)
            a->arg[i].obj = remap[a->arg[i].obj];
    }
}

static int fmRemapObjs(pddl_fm_t *c, void *_remap)
{
    const int *remap = _remap;
    if (c->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        fmAtomRemapObjs(a, remap);

    }else if (c->type == PDDL_FM_NUM_EXP_FLUENT){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(c);
        fmAtomRemapObjs(e->e.fluent, remap);
    }

    return 0;
}

void pddlFmRemapObjs(pddl_fm_t *c, const int *remap)
{
    pddl_fm_traverse_t tr
            = PDDL_FM_TRAVERSE_INIT(NULL, fmRemapObjs, (void *)remap);
    tr.descend_num = pddl_true;
    _pddlFmTraverse(c, &tr);
}

static int atomIsInvalid(const pddl_fm_atom_t *a)
{
    for (int i = 0; i < a->arg_size; ++i){
        if (a->arg[i].param < 0 && a->arg[i].obj < 0)
            return 1;
    }
    return 0;
}

static int fmRemoveInvalidAtoms(pddl_fm_t **c, void *_)
{
    if ((*c)->type == PDDL_FM_ATOM){
        if (atomIsInvalid(pddlFmToAtom(*c))){
            pddlFmDel(*c);
            *c = NULL;
            return 0;
        }

    }else if ((*c)->type == PDDL_FM_NUM_EXP_FLUENT){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(*c);
        if (e->e.fluent == NULL || atomIsInvalid(e->e.fluent)){
            pddlFmDel(*c);
            *c = NULL;
            return 0;
        }
    }

    return 0;
}

pddl_fm_t *pddlFmRemoveInvalidAtoms(pddl_fm_t *c)
{
    pddl_fm_rebuild_t rb
            = PDDL_FM_REBUILD_INIT(NULL, fmRemoveInvalidAtoms, NULL);
    rb.descend_num = pddl_true;
    _pddlFmRebuild(&c, &rb);
    return c;
}

struct pred_remap {
    const int *pred_remap;
    const int *func_remap;
    int fail;
};

static int fmRemapPreds(pddl_fm_t *c, void *_remap)
{
    struct pred_remap *remap = _remap;
    if (c->type == PDDL_FM_ATOM){
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        if (remap->pred_remap[a->pred] < 0)
            remap->fail = 1;
        a->pred = remap->pred_remap[a->pred];

    }else if (c->type == PDDL_FM_NUM_EXP_FLUENT){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(c);
        ASSERT(e->e.fluent != NULL);
        if (remap->func_remap[e->e.fluent->pred] < 0)
            remap->fail = 1;
        e->e.fluent->pred = remap->func_remap[e->e.fluent->pred];
    }

    return 0;
}

int pddlFmRemapPreds(pddl_fm_t *c,
                     const int *pred_remap,
                     const int *func_remap)
{
    struct pred_remap remap = { pred_remap, func_remap, 0};
    pddlFmTraverseProp(c, NULL, fmRemapPreds, (void *)&remap);
    if (remap.fail)
        return -1;
    return 0;
}


/*** PRINT ***/
static void fmPartPrint(const pddl_t *pddl,
                        const pddl_fm_junc_t *fm,
                        const char *name,
                        const pddl_params_t *params,
                        FILE *fout)
{
    pddl_list_t *item;
    const pddl_fm_t *child;

    fprintf(fout, "(%s", name);
    PDDL_LIST_FOR_EACH(&fm->part, item){
        child = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        fprintf(fout, " ");
        pddlFmPrint(pddl, child, params, fout);
    }
    fprintf(fout, ")");
}

static void fmQuantPrint(const pddl_t *pddl,
                         const pddl_fm_quant_t *q,
                         const char *name,
                         const pddl_params_t *params,
                         FILE *fout)
{
    fprintf(fout, "(%s", name);

    fprintf(fout, " (");
    pddlParamsPrint(&q->param, fout);
    fprintf(fout, ") ");

    pddlFmPrint(pddl, q->qfm, &q->param, fout);

    fprintf(fout, ")");
}

static void fmWhenPrint(const pddl_t *pddl,
                        const pddl_fm_when_t *w,
                        const pddl_params_t *params,
                        FILE *fout)
{
    fprintf(fout, "(when ");
    pddlFmPrint(pddl, w->pre, params, fout);
    fprintf(fout, " ");
    pddlFmPrint(pddl, w->eff, params, fout);
    fprintf(fout, ")");
}

static void fmAtomPrint(const pddl_t *pddl,
                        const pddl_fm_atom_t *atom,
                        const pddl_params_t *params,
                        FILE *fout, int is_func)
{
    const pddl_pred_t *pred;
    int i;

    if (is_func){
        pred = pddl->func.pred + atom->pred;
    }else{
        pred = pddl->pred.pred + atom->pred;
    }

    fprintf(fout, "(");
    if (atom->neg)
        fprintf(fout, "N:");
    if (pred->read)
        fprintf(fout, "R");
    if (pred->write)
        fprintf(fout, "W");
    fprintf(fout, ":%s", pred->name);

    for (i = 0; i < atom->arg_size; ++i){
        fprintf(fout, " ");
        if (atom->arg[i].param >= 0){
            if (params->param[atom->arg[i].param].name != NULL){
                fprintf(fout, "%s", params->param[atom->arg[i].param].name);
            }else{
                fprintf(fout, "x%d", atom->arg[i].param);
            }
        }else{
            fprintf(fout, "%s", pddl->obj.obj[atom->arg[i].obj].name);
        }
    }

    fprintf(fout, ")");
}

static void fmBoolPrint(const pddl_fm_bool_t *b, FILE *fout)
{
    if (b->val){
        fprintf(fout, "TRUE");
    }else{
        fprintf(fout, "FALSE");
    }
}

static void fmImplyPrint(const pddl_fm_imply_t *imp,
                         const pddl_t *pddl,
                         const pddl_params_t *params,
                         FILE *fout)

{
    fprintf(fout, "(imply ");
    if (imp->left)
        pddlFmPrint(pddl, imp->left, params, fout);
    fprintf(fout, " ");
    if (imp->right)
        pddlFmPrint(pddl, imp->right, params, fout);
    fprintf(fout, ")");
}

void pddlFmPrint(const struct pddl *pddl,
                 const pddl_fm_t *fm,
                 const pddl_params_t *params,
                 FILE *fout)
{
    if (fm->type == PDDL_FM_AND){
        fmPartPrint(pddl, pddlFmToAndConst(fm), "and", params, fout);

    }else if (fm->type == PDDL_FM_OR){
        fmPartPrint(pddl, pddlFmToOrConst(fm), "or", params, fout);

    }else if (fm->type == PDDL_FM_FORALL){
        fmQuantPrint(pddl, pddlFmToQuantConst(fm), "forall", params, fout);

    }else if (fm->type == PDDL_FM_EXIST){
        fmQuantPrint(pddl, pddlFmToQuantConst(fm), "exists", params, fout);

    }else if (fm->type == PDDL_FM_WHEN){
        fmWhenPrint(pddl, pddlFmToWhenConst(fm), params, fout);

    }else if (fm->type == PDDL_FM_ATOM){
        fmAtomPrint(pddl, pddlFmToAtomConst(fm), params, fout, 0);

    }else if (pddlFmIsNumExp(fm)){
        fmNumExpPrintPDDL(pddlFmToNumExpConst(fm), pddl, params, fout);

    }else if (pddlFmIsNumCmp(fm)){
        fmNumCmpPrintPDDL(pddlFmToNumCmpConst(fm), pddl, params, fout);

    }else if (pddlFmIsNumOp(fm)){
        fmNumOpPrintPDDL(pddlFmToNumOpConst(fm), pddl, params, fout);

    }else if (fm->type == PDDL_FM_BOOL){
        fmBoolPrint(pddlFmToBoolConst(fm), fout);

    }else if (fm->type == PDDL_FM_IMPLY){
        fmImplyPrint(pddlFmToImplyConst(fm), pddl, params, fout);

    }else{
        PANIC("Unknown type!");
    }
}

const char *pddlFmFmt(const pddl_fm_t *fm,
                      const pddl_t *pddl,
                      const pddl_params_t *params,
                      char *s,
                      size_t s_size)
{
    FILE *fout = pddl_staticstrstream(s, s_size - 1);
    pddlFmPrint(pddl, fm, params, fout);
    fflush(fout);
    if (ferror(fout) != 0 && s_size >= 4){
        s[s_size - 4] = '.';
        s[s_size - 3] = '.';
        s[s_size - 2] = '.';
    }
    fclose(fout);
    s[s_size - 1] = 0x0;
    return s;
}

void pddlFmPrintPDDL(const pddl_fm_t *fm,
                     const pddl_t *pddl,
                     const pddl_params_t *params,
                     FILE *fout)
{
    cond_cls[fm->type].print_pddl(fm, pddl, params, fout);
}

const char *pddlFmPDDLFmt(const pddl_fm_t *fm,
                          const pddl_t *pddl,
                          const pddl_params_t *params,
                          char *s,
                          size_t s_size)
{
    FILE *fout = pddl_staticstrstream(s, s_size - 1);
    pddlFmPrintPDDL(fm, pddl, params, fout);
    fflush(fout);
    if (ferror(fout) != 0 && s_size >= 4){
        s[s_size - 4] = '.';
        s[s_size - 3] = '.';
        s[s_size - 2] = '.';
    }
    fclose(fout);
    s[s_size - 1] = 0x0;
    return s;
}


const pddl_fm_t *pddlFmConstItInit(pddl_fm_const_it_t *it,
                                   const pddl_fm_t *fm,
                                   int type)
{
    ZEROIZE(it);

    if (fm == NULL)
        return NULL;

    if (type < 0 && fm->type != PDDL_FM_AND && fm->type != PDDL_FM_OR)
        return fm;

    if (fm->type == type)
        return fm;

    if (fm->type == PDDL_FM_AND || fm->type == PDDL_FM_OR){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(fm);
        it->list = &p->part;
        for (it->cur = pddlListNext((pddl_list_t *)it->list);
                it->cur != it->list;
                it->cur = pddlListNext((pddl_list_t *)it->cur)){
            const pddl_fm_t *c = PDDL_LIST_ENTRY(it->cur, pddl_fm_t, conn);
            if (type < 0 || c->type == type)
                return c;
        }
        return NULL;
    }

    return NULL;
}

const pddl_fm_t *pddlFmConstItNext(pddl_fm_const_it_t *it, int type)
{
    if (it->cur == it->list)
        return NULL;

    for (it->cur = pddlListNext((pddl_list_t *)it->cur);
            it->cur != it->list;
            it->cur = pddlListNext((pddl_list_t *)it->cur)){
        const pddl_fm_t *c = PDDL_LIST_ENTRY(it->cur, pddl_fm_t, conn);
        if (type < 0 || c->type == type)
            return c;
    }

    return NULL;
}

const pddl_fm_atom_t *pddlFmConstItAtomInit(pddl_fm_const_it_atom_t *it,
                                            const pddl_fm_t *fm)
{
    const pddl_fm_t *c;
    if ((c = pddlFmConstItInit(it, fm, PDDL_FM_ATOM)) == NULL)
        return NULL;
    return pddlFmToAtomConst(c);
}

const pddl_fm_atom_t *pddlFmConstItAtomNext(pddl_fm_const_it_atom_t *it)
{
    const pddl_fm_t *c;
    if ((c = pddlFmConstItNext(it, PDDL_FM_ATOM)) == NULL)
        return NULL;
    return pddlFmToAtomConst(c);
}

const pddl_fm_when_t *pddlFmConstItWhenInit(pddl_fm_const_it_when_t *it,
                                            const pddl_fm_t *fm)
{
    const pddl_fm_t *c;
    if ((c = pddlFmConstItInit(it, fm, PDDL_FM_WHEN)) == NULL)
        return NULL;
    return pddlFmToWhenConst(c);
}

const pddl_fm_when_t *pddlFmConstItWhenNext(pddl_fm_const_it_when_t *it)
{
    const pddl_fm_t *c;
    if ((c = pddlFmConstItNext(it, PDDL_FM_WHEN)) == NULL)
        return NULL;
    return pddlFmToWhenConst(c);
}



static const pddl_fm_t *constItEffNextCond(pddl_fm_const_it_eff_t *it,
                                           const pddl_fm_t **pre)
{
    if (pre != NULL)
        *pre = NULL;

    if (it->when_cur != NULL){
        it->when_cur = pddlListNext((pddl_list_t *)it->when_cur);
        if (it->when_cur == it->when_list){
            it->when_cur = it->when_list = NULL;
            it->when_pre = NULL;
        }else{
            if (pre != NULL)
                *pre = it->when_pre;
            return PDDL_LIST_ENTRY(it->when_cur, pddl_fm_t, conn);
        }
    }

    if (it->list == it->cur)
        return NULL;
    if (it->cur == NULL){
        it->cur = pddlListNext((pddl_list_t *)it->list);
    }else{
        it->cur = pddlListNext((pddl_list_t *)it->cur);
    }
    if (it->list == it->cur)
        return NULL;
    return PDDL_LIST_ENTRY(it->cur, pddl_fm_t, conn);
}

static const pddl_fm_atom_t *constItEffWhen(pddl_fm_const_it_eff_t *it,
                                            const pddl_fm_when_t *w,
                                            const pddl_fm_t **pre)
{
    if (w->eff == NULL){
        return NULL;

    }else if (w->eff->type == PDDL_FM_ATOM){
        if (pre != NULL)
            *pre = w->pre;
        return pddlFmToAtom(w->eff);

    }else if (w->eff->type == PDDL_FM_AND){
        const pddl_fm_junc_t *p = pddlFmToJunc(w->eff);
        it->when_pre = w->pre;
        it->when_list = &p->part;
        it->when_cur = it->when_list;
        return NULL;

    }else{
        PANIC_IF(w->eff->type == PDDL_FM_OR
                    || w->eff->type == PDDL_FM_FORALL
                    || w->eff->type == PDDL_FM_EXIST
                    || w->eff->type == PDDL_FM_IMPLY
                    || w->eff->type == PDDL_FM_WHEN,
                 "Effect is not normalized.");
    }
    return NULL;
}

const pddl_fm_atom_t *pddlFmConstItEffInit(pddl_fm_const_it_eff_t *it,
                                           const pddl_fm_t *fm,
                                           const pddl_fm_t **pre)
{
    ZEROIZE(it);

    if (pre != NULL)
        *pre = NULL;
    if (fm == NULL)
        return NULL;

    if (fm->type == PDDL_FM_ATOM){
        return pddlFmToAtomConst(fm);

    }else if (fm->type == PDDL_FM_AND){
        const pddl_fm_junc_t *p = pddlFmToJuncConst(fm);
        it->list = &p->part;
        return pddlFmConstItEffNext(it, pre);

    }else if (fm->type == PDDL_FM_WHEN){
        const pddl_fm_when_t *w = pddlFmToWhenConst(fm);
        const pddl_fm_atom_t *a = constItEffWhen(it, w, pre);
        if (a != NULL)
            return a;
        return pddlFmConstItEffNext(it, pre);

    }else{
        PANIC_IF(fm->type == PDDL_FM_OR
                    || fm->type == PDDL_FM_FORALL
                    || fm->type == PDDL_FM_EXIST
                    || fm->type == PDDL_FM_IMPLY,
                 "Effect is not normalized.");
    }
    return NULL;
}

const pddl_fm_atom_t *pddlFmConstItEffNext(pddl_fm_const_it_eff_t *it,
                                           const pddl_fm_t **pre)
{
    const pddl_fm_t *c;

    while (1){
        c = constItEffNextCond(it, pre);
        if (c == NULL){
            return NULL;

        }else if (c->type == PDDL_FM_ATOM){
            return pddlFmToAtomConst(c);

        }else if (c->type == PDDL_FM_WHEN){
            const pddl_fm_when_t *w = pddlFmToWhenConst(c);
            const pddl_fm_atom_t *a = constItEffWhen(it, w, pre);
            if (a != NULL)
                return a;
        }else{
            PANIC_IF(c->type == PDDL_FM_AND
                        || c->type == PDDL_FM_OR
                        || c->type == PDDL_FM_FORALL
                        || c->type == PDDL_FM_EXIST
                        || c->type == PDDL_FM_IMPLY
                        || c->type == PDDL_FM_WHEN,
                     "Effect is not normalized.");
        }
    }
}
