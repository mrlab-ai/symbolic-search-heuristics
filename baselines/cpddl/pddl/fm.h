/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FM_H__
#define __PDDL_FM_H__

#include <pddl/common.h>
#include <pddl/list.h>
#include <pddl/require_flags.h>
#include <pddl/param.h>
#include <pddl/obj.h>
#include <pddl/pred.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Types of formulas
 */
enum pddl_fm_type {
    /** Conjuction */
    PDDL_FM_AND = 0,
    /** Disjunction */
    PDDL_FM_OR,
    /** Universal quantifier */
    PDDL_FM_FORALL,
    /** Existential quantifier */
    PDDL_FM_EXIST,
    /** Conditional effect */
    PDDL_FM_WHEN,
    /** Atom in a positive or negative form */
    PDDL_FM_ATOM,
    /** True/False */
    PDDL_FM_BOOL,
    /** (imply X Y) */
    PDDL_FM_IMPLY,

    /** Numerical expression X + Y */
    PDDL_FM_NUM_EXP_PLUS,
    /** Numerical expression X - Y */
    PDDL_FM_NUM_EXP_MINUS,
    /** Numerical expression X * Y */
    PDDL_FM_NUM_EXP_MULT,
    /** Numerical expression X / Y */
    PDDL_FM_NUM_EXP_DIV,
    /** Numerical expression -- numeric fluent */
    PDDL_FM_NUM_EXP_FLUENT,
    /** Numerical expression -- integer constant */
    PDDL_FM_NUM_EXP_INUM,
    /** Numerical expression -- float constant */
    PDDL_FM_NUM_EXP_FNUM,

    /** Numerical comparator '=' */
    PDDL_FM_NUM_CMP_EQ,
    /** Numerical comparator '!=' */
    PDDL_FM_NUM_CMP_NEQ,
    /** Numerical comparator '>=' */
    PDDL_FM_NUM_CMP_GE,
    /** Numerical comparator '<=' */
    PDDL_FM_NUM_CMP_LE,
    /** Numerical comparator '>' */
    PDDL_FM_NUM_CMP_GT,
    /** Numerical comparator '<' */
    PDDL_FM_NUM_CMP_LT,

    /** Numerical operator assign (x = ...) */
    PDDL_FM_NUM_OP_ASSIGN,
    /** Numerical operator increase (x += ...) */
    PDDL_FM_NUM_OP_INCREASE,
    /** Numerical operator decrease (x -= ...) */
    PDDL_FM_NUM_OP_DECREASE,
    /** Numerical operator scale-up (x *= ...) */
    PDDL_FM_NUM_OP_SCALE_UP,
    /** Numerical operator scale-down (x /= ...) */
    PDDL_FM_NUM_OP_SCALE_DOWN,

    PDDL_FM_NUM_TYPES,
};
typedef enum pddl_fm_type pddl_fm_type_t;

const char *pddlFmTypeName(pddl_fm_type_t type);

/**
 * Abstract formula
 */
struct pddl_fm {
    /** Type of the formula */
    pddl_fm_type_t type;
    /** Connection to the parent formula */
    pddl_list_t conn;
};
typedef struct pddl_fm pddl_fm_t;

/**
 * Conjunction / Disjunction
 */
struct pddl_fm_junc {
    pddl_fm_t fm;
    /** List of parts */
    pddl_list_t part;
};
typedef struct pddl_fm_junc pddl_fm_junc_t;

/** Conjunction */
typedef pddl_fm_junc_t pddl_fm_and_t;
/** Disjunction */
typedef pddl_fm_junc_t pddl_fm_or_t;

/**
 * Quantifiers
 */
struct pddl_fm_quant {
    pddl_fm_t fm;
    /**List of parameters */
    pddl_params_t param;
    /** Quantified formula */
    pddl_fm_t *qfm;
};
typedef struct pddl_fm_quant pddl_fm_quant_t;

/** Universal quantifier */
typedef pddl_fm_quant_t pddl_fm_forall_t;
/** Existential quantifier */
typedef pddl_fm_quant_t pddl_fm_exist_t;

/**
 * Conditional effect
 */
struct pddl_fm_when {
    pddl_fm_t fm;
    pddl_fm_t *pre;
    pddl_fm_t *eff;
};
typedef struct pddl_fm_when pddl_fm_when_t;


/**
 * Argument of an atom
 */
struct pddl_fm_atom_arg {
    /** -1 or index of parameter */
    int param;
    /** object ID (constant) or -1 */
    int obj;
};
typedef struct pddl_fm_atom_arg pddl_fm_atom_arg_t;

/**
 * Atom
 */
struct pddl_fm_atom {
    pddl_fm_t fm;
    /** Predicate ID */
    int pred;
    /** List of arguments */
    pddl_fm_atom_arg_t *arg;
    /** Number of arguments */
    int arg_size;
    /** True if negated */
    pddl_bool_t neg;
};
typedef struct pddl_fm_atom pddl_fm_atom_t;


/**
 * Numerical expression
 */
struct pddl_fm_num_exp {
    pddl_fm_t fm;
    union {
        struct {
            struct pddl_fm_num_exp *left;
            struct pddl_fm_num_exp *right;
        } bin_op;
        pddl_fm_atom_t *fluent;
        int inum;
        float fnum;
    } e;
};
typedef struct pddl_fm_num_exp pddl_fm_num_exp_t;

/**
 * Numerical comparator "left ==/<=/>=/... right"
 */
struct pddl_fm_num_cmp {
    pddl_fm_t fm;
    pddl_fm_num_exp_t *left;
    pddl_fm_num_exp_t *right;
};
typedef struct pddl_fm_num_cmp pddl_fm_num_cmp_t;

/**
 * Numerical (assign) operator "left =/+=/-+/... right"
 */
struct pddl_fm_num_op {
    pddl_fm_t fm;
    /** Left hand side is always of type PDDL_FM_NUM_EXP_FLUENT */
    pddl_fm_num_exp_t *left;
    pddl_fm_num_exp_t *right;
};
typedef struct pddl_fm_num_op pddl_fm_num_op_t;


/**
 * Boolean value
 */
struct pddl_fm_bool {
    pddl_fm_t fm;
    pddl_bool_t val;
};
typedef struct pddl_fm_bool pddl_fm_bool_t;

/**
 * Imply: (imply (...) (...))
 */
struct pddl_fm_imply {
    pddl_fm_t fm;
    pddl_fm_t *left;
    pddl_fm_t *right;
};
typedef struct pddl_fm_imply pddl_fm_imply_t;


/**
 * Casting functions
 */
pddl_bool_t pddlFmIsJunc(const pddl_fm_t *c);
pddl_fm_junc_t *pddlFmToJunc(pddl_fm_t *c);
const pddl_fm_junc_t *pddlFmToJuncConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsAnd(const pddl_fm_t *c);
pddl_fm_and_t *pddlFmToAnd(pddl_fm_t *c);
const pddl_fm_and_t *pddlFmToAndConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsOr(const pddl_fm_t *c);
pddl_fm_or_t *pddlFmToOr(pddl_fm_t *c);
const pddl_fm_or_t *pddlFmToOrConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsBool(const pddl_fm_t *c);
pddl_bool_t pddlFmIsTrue(const pddl_fm_t *c);
pddl_bool_t pddlFmIsFalse(const pddl_fm_t *c);
pddl_fm_bool_t *pddlFmToBool(pddl_fm_t *c);
const pddl_fm_bool_t *pddlFmToBoolConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsAtom(const pddl_fm_t *c);
pddl_fm_atom_t *pddlFmToAtom(pddl_fm_t *c);
const pddl_fm_atom_t *pddlFmToAtomConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsWhen(const pddl_fm_t *c);
pddl_fm_when_t *pddlFmToWhen(pddl_fm_t *c);
const pddl_fm_when_t *pddlFmToWhenConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsNumExp(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpPlus(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpMinus(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpMult(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpDiv(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpBinOp(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpFluent(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpFNum(const pddl_fm_t *e);
pddl_bool_t pddlFmIsNumExpINum(const pddl_fm_t *e);
pddl_fm_num_exp_t *pddlFmToNumExp(pddl_fm_t *e);
const pddl_fm_num_exp_t *pddlFmToNumExpConst(const pddl_fm_t *e);
pddl_fm_atom_t *pddlFmNumExpGetFluentAtom(pddl_fm_num_exp_t *e);
const pddl_fm_atom_t *pddlFmNumExpGetFluentAtomConst(const pddl_fm_num_exp_t *e);
pddl_bool_t pddlFmNumExpCanRecastFNumToINum(const pddl_fm_num_exp_t *e);
void pddlFmNumExpRecastFNumToINum(pddl_fm_num_exp_t *e);

pddl_bool_t pddlFmIsNumCmp(const pddl_fm_t *c);
pddl_fm_num_cmp_t *pddlFmToNumCmp(pddl_fm_t *c);
const pddl_fm_num_cmp_t *pddlFmToNumCmpConst(const pddl_fm_t *c);

/**
 * Returns true if c is a simple numerical comparator of the form
 *      (= (ground-atom obj1 obj2 ...) non-negative-int-number)
 */
pddl_bool_t pddlFmIsNumCmpSimpleGroundEqNonNegInt(const pddl_fm_t *fm);

/**
 * Returns true if c is a simple numerical comparator of the form
 *      (= (ground-atom obj1 obj2 ...) number)
 */
pddl_bool_t pddlFmIsNumCmpSimpleGroundEq(const pddl_fm_t *fm);

/**
 * Checks whether the formula is a numeric comparator is of the form
 *      (= (ground-atom obj1 obj2 ...) number)
 * and if so, it returns the left hand side fluent and the right hand side
 * number.
 * Returns 0 if the numeric comparator has the right form and -1 otherwise.
 */
int pddlFmNumCmpCheckSimpleGroundEq(const pddl_fm_t *fm,
                                    const pddl_fm_atom_t **left_fluent,
                                    const pddl_fm_num_exp_t **right_value);

/**
 * Same as pddlFmNumCmpCheckSimpleGroundEq() but requires that the right
 * hand side number is a non-negative integer.
 */
int pddlFmNumCmpCheckSimpleGroundEqNonNegInt(const pddl_fm_t *fm,
                                             const pddl_fm_atom_t **left_fluent,
                                             int *value);

pddl_bool_t pddlFmIsNumOp(const pddl_fm_t *c);
pddl_bool_t pddlFmIsNumOpIncrease(const pddl_fm_t *c);
pddl_fm_num_op_t *pddlFmToNumOp(pddl_fm_t *c);
const pddl_fm_num_op_t *pddlFmToNumOpConst(const pddl_fm_t *c);

/**
 * Checks whether the numeric operator is of the form
 *      (increase (total-cost) integer-constant)
 *  or
 *      (increase (total-cost) (atom ...))
 * and if so, it returns the right hand side atom or value.
 * Return 0 if the numeric operator has the right form and -1 otherwise.
 */
int pddlFmNumOpCheckSimpleIncreaseTotalCost(const pddl_fm_t *fm,
                                            int func_total_cost_id,
                                            const pddl_fm_atom_t **atom_value,
                                            int *int_value);

pddl_bool_t pddlFmIsQuant(const pddl_fm_t *c);
pddl_fm_quant_t *pddlFmToQuant(pddl_fm_t *c);
const pddl_fm_quant_t *pddlFmToQuantConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsForAll(const pddl_fm_t *c);
pddl_fm_forall_t *pddlFmToForAll(pddl_fm_t *c);
const pddl_fm_forall_t *pddlFmToForAllConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsExist(const pddl_fm_t *c);
pddl_fm_exist_t *pddlFmToExist(pddl_fm_t *c);
const pddl_fm_exist_t *pddlFmToExistConst(const pddl_fm_t *c);

pddl_bool_t pddlFmIsImply(const pddl_fm_t *c);
pddl_fm_imply_t *pddlFmToImply(pddl_fm_t *c);
const pddl_fm_imply_t *pddlFmToImplyConst(const pddl_fm_t *c);

/**
 * Free memory.
 */
void pddlFmDel(pddl_fm_t *fm);

/**
 * Returns true if c is FALSE constant
 */
pddl_bool_t pddlFmIsFalse(const pddl_fm_t *c);

/**
 * Returns true if c is TRUE constant
 */
pddl_bool_t pddlFmIsTrue(const pddl_fm_t *c);

/**
 * Returns true if c is an atom
 */
pddl_bool_t pddlFmIsAtom(const pddl_fm_t *c);

/**
 * Returns true if {c} is a when (conditional effect) node
 */
pddl_bool_t pddlFmIsWhen(const pddl_fm_t *c);

/**
 * Creates an exact copy of the condition.
 */
pddl_fm_t *pddlFmClone(const pddl_fm_t *fm);

/**
 * Returns a negated copy of the condition.
 */
pddl_fm_t *pddlFmNegate(const pddl_fm_t *fm, const pddl_t *pddl);

/**
 * Returns true if the conds match exactly.
 */
pddl_bool_t pddlFmEq(const pddl_fm_t *c1, const pddl_fm_t *c2);

/**
 * Returns true if s is implied by c
 */
pddl_bool_t pddlFmIsImplied(const pddl_fm_t *s,
                            const pddl_fm_t *c,
                            const pddl_t *pddl,
                            const pddl_params_t *param);
#define pddlFmIsEntailed pddlFmIsImplied

struct pddl_fm_traverse {
    /** Function called before descending.
     *  If pre returns -1 the element is skipped (it is not traversed deeper).
     *  If pre returns -2 the whole traversing is terminated. */
    int (*pre)(pddl_fm_t *, void *);
    /** Function called after ascending.
     *  If post returns non-zero value the whole traversing is terminated. */
    int (*post)(pddl_fm_t *, void *);
    /** User provided data used as the last argument of the .pre/.post
     *  functions. */
    void *userdata;

    /** If set to true, traversing descends also into the numerical
     *  elements (i.e., num_exp, num_cmp and num_op). Default: true */
    pddl_bool_t descend_num;
};
typedef struct pddl_fm_traverse pddl_fm_traverse_t;

#define PDDL_FM_TRAVERSE_INIT(PRE, POST, USERDATA) \
    { \
        (PRE), /* .pre */ \
        (POST), /* .post */ \
        (void *)(USERDATA), /* .userdata */ \
        pddl_false, /* .descend_num */ \
    }

/**
 * Traverse all elements in the tree and call pre/post callbacks according
 * to the specification.
 * Note that by default traversing into numerical elements is disabled and
 * it has to be enabled by setting tr->descend_num to true. (This means
 * numerical elements can still be encountered if part of some formula, but
 * traversing does not descend into the numerical element itself.)
 */
void _pddlFmTraverse(pddl_fm_t *c, pddl_fm_traverse_t *tr);

/**
 * Traverse all elements in the tree and call pre callback before
 * descending and post after ascending.
 * If pre returns -1, the element is skipped (it is not traversed deeper).
 * If pre returns -2, the whole traversing is terminated.
 * If post returns non-zero value the whole traversing is terminated.
 */
void pddlFmTraverseAll(pddl_fm_t *c,
                       int (*pre)(pddl_fm_t *, void *),
                       int (*post)(pddl_fm_t *, void *),
                       void *userdata);

/**
 * Same as pddlFmTraverseAll() but descends only in propositional parts,
 * i.e., traversing never descends into numerical elements. This means
 * numerical elements are still encountered, but not traversed further.
 */
void pddlFmTraverseProp(pddl_fm_t *c,
                        int (*pre)(pddl_fm_t *, void *),
                        int (*post)(pddl_fm_t *, void *),
                        void *userdata);


struct pddl_fm_rebuild {
    /** Function called before descending.
     *  If pre returns -1 the element is skipped (it is not traversed deeper).
     *  If pre returns -2 the whole traversing is terminated. */
    int (*pre)(pddl_fm_t **, void *);
    /** Function called after ascending.
     *  If post returns non-zero value the whole traversing is terminated. */
    int (*post)(pddl_fm_t **, void *);
    /** User provided data used as the last argument of the .pre/.post
     *  functions. */
    void *userdata;

    /** If set to true, traversing descends also into the numerical
     *  elements (i.e., num_exp, num_cmp and num_op). Default: false */
    pddl_bool_t descend_num;
};
typedef struct pddl_fm_rebuild pddl_fm_rebuild_t;

#define PDDL_FM_REBUILD_INIT(PRE, POST, USERDATA) \
    { \
        (PRE), /* .pre */ \
        (POST), /* .post */ \
        (void *)(USERDATA), /* .userdata */ \
        pddl_false, /* .descend_num */ \
    }

/**
 * Same as _pddlFmTraverse() but pddl_fm_t structures are passed so that
 * they can be safely changed within callbacks.
 * The return values of pre and post and treated the same way as in
 * _pddlFmTraverse().
 */
void _pddlFmRebuild(pddl_fm_t **c, pddl_fm_rebuild_t *rb);

/**
 * As pddlFmTraverseAll() but elements can be changed/replaced.
 */
void pddlFmRebuildAll(pddl_fm_t **c,
                      int (*pre)(pddl_fm_t **, void *),
                      int (*post)(pddl_fm_t **, void *),
                      void *userdata);

/**
 * As pddlFmTraverseProp() but elements can be changed/replaced.
 */
void pddlFmRebuildProp(pddl_fm_t **c,
                       int (*pre)(pddl_fm_t **, void *),
                       int (*post)(pddl_fm_t **, void *),
                       void *userdata);

/**
 * Sort elements with dis/con-junction.
 */
void pddlFmJuncSort(pddl_fm_junc_t *fm,
                    int (*cmp)(const pddl_fm_t *fm1,
                               const pddl_fm_t *fm2,
                               void *userdata),
                    void *userdata);

/**
 * Returns number of predicate atoms appearing in the formula (i.e.,
 * fluents inside numerical elements are not counted).
 */
int pddlFmNumAtoms(const pddl_fm_t *fm);

/**
 * When first (when ...) node, that has non-static preconditions, is found,
 * it is removed and returned.
 * If no (when ...) is found, NULL is returned.
 * The function requires that c is the (and ...) node.
 */
pddl_fm_when_t *pddlFmRemoveFirstNonStaticWhen(pddl_fm_t *c, const pddl_t *pddl);
pddl_fm_when_t *pddlFmRemoveFirstWhen(pddl_fm_t *c, const pddl_t *pddl);

/**
 * Creates a new (and a) node.
 * The object a should not be used after this call.
 */
pddl_fm_t *pddlFmNewAnd1(pddl_fm_t *a);

/**
 * Creates a new (and a b) node.
 * The objects a and b should not be used after this call.
 */
pddl_fm_t *pddlFmNewAnd2(pddl_fm_t *a, pddl_fm_t *b);

/**
 * Creates a new empty (and ).
 */
pddl_fm_t *pddlFmNewEmptyAnd(void);

/**
 * Creates a new empty (or ).
 */
pddl_fm_t *pddlFmNewEmptyOr(void);

/**
 * Creates a new empty atom with the specified number of arguments all set
 * as "undefined".
 */
pddl_fm_atom_t *pddlFmNewEmptyAtom(int num_args);

/**
 * Creates false/true constants.
 */
pddl_fm_bool_t *pddlFmNewBool(int is_true);

/**
 * Constructs a new (imply {left} {right}).
 * {left} and {right} are used directly, i.e., they are not copied!
 */
pddl_fm_imply_t *pddlFmNewImply(pddl_fm_t *left, pddl_fm_t *right);

/**
 * Constructs a new (when {pre} {eff}).
 * {pre} and {eff} are used directly, i.e., they are not copied!
 */
pddl_fm_when_t *pddlFmNewWhen(pddl_fm_t *pre, pddl_fm_t *eff);

/**
 * Creates an empty forall/exist formula depending on the specified type.
 */
pddl_fm_quant_t *pddlFmNewEmptyQuant(int type);

/**
 * Creates an empty forall formula
 */
pddl_fm_forall_t *pddlFmNewEmptyForAll(void);

/**
 * Creates an empty exists formula
 */
pddl_fm_exist_t *pddlFmNewEmptyExist(void);

/**
 * Creates a new numerical expression.
 */
pddl_fm_num_exp_t *pddlFmNewNumExpPlus(pddl_fm_num_exp_t *left,
                                       pddl_fm_num_exp_t *right);
pddl_fm_num_exp_t *pddlFmNewNumExpMinus(pddl_fm_num_exp_t *left,
                                        pddl_fm_num_exp_t *right);
pddl_fm_num_exp_t *pddlFmNewNumExpMult(pddl_fm_num_exp_t *left,
                                       pddl_fm_num_exp_t *right);
pddl_fm_num_exp_t *pddlFmNewNumExpDiv(pddl_fm_num_exp_t *left,
                                      pddl_fm_num_exp_t *right);
pddl_fm_num_exp_t *pddlFmNewNumExpFluent(pddl_fm_atom_t *atom);
pddl_fm_num_exp_t *pddlFmNewNumExpINum(int value);
pddl_fm_num_exp_t *pddlFmNewNumExpFNum(float value);

/**
 * Creates a new numerical comparator.
 */
pddl_fm_num_cmp_t *pddlFmNewNumCmp(int type,
                                   pddl_fm_num_exp_t *left,
                                   pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpEq(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpNEq(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpGE(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpLE(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpGT(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);
pddl_fm_num_cmp_t *pddlFmNewNumCmpLT(pddl_fm_num_exp_t *left,
                                     pddl_fm_num_exp_t *right);

/**
 * Creates a new numerical operators
 */
pddl_fm_num_op_t *pddlFmNewNumOp(int type,
                                 pddl_fm_atom_t *left,
                                 pddl_fm_num_exp_t *right);
pddl_fm_num_op_t *pddlFmNewNumOpAssign(pddl_fm_atom_t *left,
                                       pddl_fm_num_exp_t *right);
pddl_fm_num_op_t *pddlFmNewNumOpIncrease(pddl_fm_atom_t *left,
                                         pddl_fm_num_exp_t *right);
pddl_fm_num_op_t *pddlFmNewNumOpDecrease(pddl_fm_atom_t *left,
                                         pddl_fm_num_exp_t *right);
pddl_fm_num_op_t *pddlFmNewNumOpScaleUp(pddl_fm_atom_t *left,
                                        pddl_fm_num_exp_t *right);
pddl_fm_num_op_t *pddlFmNewNumOpScaleDown(pddl_fm_atom_t *left,
                                          pddl_fm_num_exp_t *right);

/**
 * Returns true if the formula contains any predicate atom (i.e., fluents
 * inside numerical elements are not counted.).
 */
pddl_bool_t pddlFmHasAtom(const pddl_fm_t *c);

/**
 * Transforms atom into (and atom).
 */
pddl_fm_t *pddlFmAtomToAnd(pddl_fm_t *atom);

/**
 * Creates a new atom that corresponds to a grounded fact.
 */
pddl_fm_atom_t *pddlFmCreateFactAtom(int pred,
                                     int arg_size, 
                                     const int *arg);

/**
 * Adds {c} to and/or condition.
 */
void pddlFmJuncAdd(pddl_fm_junc_t *part, pddl_fm_t *c);

/**
 * Removes {c} from the and/or condition
 */
void pddlFmJuncRm(pddl_fm_junc_t *part, pddl_fm_t *c);

/**
 * Returns true if the and/or is empty
 */
pddl_bool_t pddlFmJuncIsEmpty(const pddl_fm_junc_t *part);

/**
 * Set .in_init flag of predicates and functions appearing in the given
 * formula.
 */
void pddlFmSetPredFuncInInit(const pddl_fm_t *init_fm,
                             pddl_preds_t *preds,
                             pddl_preds_t *funcs);

/**
 * Set .read and .write flags of predicates and functions based on atoms and
 * fluents appearing in pre and eff.
 * Everything appearing in pre will have a flag .read set to true.
 * Predicates appearing in eff will have a flag .write set to true, unless
 * a (when p e) formula is reached in which case p is treated as pre and e
 * is treated as eff in recursive call of this function.
 * Functions appearing in eff will have a flag .write set to true except
 * when (increase/assign/... dst src) is reached -- in this case functions
 * appearing in dst will have .write set to true and functions appearing in
 * src will have .read set to true.
 */
void pddlFmSetPredFuncReadWrite(const pddl_fm_t *pre,
                                const pddl_fm_t *eff,
                                pddl_preds_t *preds,
                                pddl_preds_t *funcs);

/**
 * Set preds_flags/funcs_flags to true whenver a corresponding
 * predicate/function is found in the given formula.
 * Note that preds_flags/funcs_flags is not reset to false (it is caller's
 * responsibility to do so), and it is assumed preds_flags and funcs_flags
 * have enough elements to cover all predicate/function IDs.
 */
void pddlFmSetPredFuncFlags(const pddl_fm_t *fm,
                            pddl_bool_t *preds_flags,
                            pddl_bool_t *funcs_flags);

/**
 * Set flags to true whenver a corresponding object appears in the given
 * formula.
 * Note that preds_flags/funcs_flags is not reset to false (it is caller's
 * responsibility to do so), and it is assumed preds_flags has at least
 * preds->pred_size elements and funcs_flags has at least funcs->pred_size
 * elements.
 */
void pddlFmSetObjsFlags(const pddl_fm_t *fm, pddl_bool_t *flags);

/**
 * Normalize conditionals by instantiation qunatifiers and transformation to
 * DNF so that the actions can be split.
 */
pddl_fm_t *pddlFmNormalize(pddl_fm_t *fm,
                           const pddl_t *pddl,
                           const pddl_params_t *params);

/**
 * Remove atom node duplicates.
 */
pddl_fm_t *pddlFmDeduplicateAtoms(pddl_fm_t *fm, const pddl_t *pddl);

/**
 * Remove duplicate formulas
 */
pddl_fm_t *pddlFmDeduplicate(pddl_fm_t *fm, const pddl_t *pddl);

/**
 * If conflicting literals are found
 *   1) in the and node, then the positive literal is kept (following the
 *      rule "first delete then add".
 *   2) in the or node, the error is reported.
 */
pddl_fm_t *pddlFmDeconflictEff(pddl_fm_t *fm,
                               const pddl_t *pddl,
                               const pddl_params_t *params);

/**
 * TODO
 */
pddl_fm_t *pddlFmSimplify(pddl_fm_t *fm,
                          const pddl_t *pddl,
                          const pddl_params_t *params);

/**
 * Returns true if the atom is a grounded fact.
 */
pddl_bool_t pddlFmAtomIsGrounded(const pddl_fm_atom_t *atom);

/**
 * Compares two atoms.
 */
int pddlFmAtomCmp(const pddl_fm_atom_t *a1, const pddl_fm_atom_t *a2);

/**
 * Compares two atoms without considering negation (.neg flag).
 */
int pddlFmAtomCmpNoNeg(const pddl_fm_atom_t *a1, const pddl_fm_atom_t *a2);

/**
 * Returns true if a1 and a2 are negations of each other.
 */
pddl_bool_t pddlFmAtomInConflict(const pddl_fm_atom_t *a1,
                                 const pddl_fm_atom_t *a2,
                                 const pddl_t *pddl);

/**
 * Remap objects.
 * It is assumed no object from {c} is deleted.
 */
void pddlFmRemapObjs(pddl_fm_t *c, const int *remap);

/**
 * TODO
 */
pddl_fm_t *pddlFmRemoveInvalidAtoms(pddl_fm_t *c);

/**
 * Remap predicates
 */
int pddlFmRemapPreds(pddl_fm_t *c,
                     const int *pred_remap,
                     const int *func_remap);


/**
 * Print the given formula
 */
void pddlFmPrint(const pddl_t *pddl,
                 const pddl_fm_t *fm,
                 const pddl_params_t *params,
                 FILE *fout);


/**
 * Format given formula and write result in [s]
 */
const char *pddlFmFmt(const pddl_fm_t *fm,
                      const pddl_t *pddl,
                      const pddl_params_t *params,
                      char *s,
                      size_t s_size);

/**
 * Print the given formula in PDDL format.
 */
void pddlFmPrintPDDL(const pddl_fm_t *fm,
                     const pddl_t *pddl,
                     const pddl_params_t *params,
                     FILE *fout);

const char *pddlFmPDDLFmt(const pddl_fm_t *fm,
                          const pddl_t *pddl,
                          const pddl_params_t *params,
                          char *s,
                          size_t s_size);



struct pddl_fm_const_it {
    const pddl_list_t *list;
    const pddl_list_t *cur;
};
typedef struct pddl_fm_const_it pddl_fm_const_it_t;
typedef pddl_fm_const_it_t pddl_fm_const_it_atom_t;
typedef pddl_fm_const_it_t pddl_fm_const_it_when_t;
typedef pddl_fm_const_it_t pddl_fm_const_it_increase_t;

const pddl_fm_t *pddlFmConstItInit(pddl_fm_const_it_atom_t *it,
                                   const pddl_fm_t *fm,
                                   int type);
const pddl_fm_t *pddlFmConstItNext(pddl_fm_const_it_atom_t *it,
                                   int type);

#define PDDL_FM_FOR_EACH(COND, IT, FM) \
    for ((FM) = pddlFmConstItInit((IT), (COND), -1); \
            (FM) != NULL; \
            (FM) = pddlFmConstItNext((IT), -1))

#define PDDL_FM_FOR_EACH_CONT(IT, FM) \
    for ((FM) = pddlFmConstItNext((IT), -1); \
            (FM) != NULL; \
            (FM) = pddlFmConstItNext((IT), -1))

const pddl_fm_atom_t *pddlFmConstItAtomInit(pddl_fm_const_it_atom_t *it,
                                            const pddl_fm_t *fm);
const pddl_fm_atom_t *pddlFmConstItAtomNext(pddl_fm_const_it_atom_t *it);

#define PDDL_FM_FOR_EACH_ATOM(COND, IT, ATOM) \
    for ((ATOM) = pddlFmConstItAtomInit((IT), (COND)); \
            (ATOM) != NULL; \
            (ATOM) = pddlFmConstItAtomNext((IT)))

#define PDDL_FM_FOR_EACH_ATOM_CONT(IT, ATOM) \
    for ((ATOM) = pddlFmConstItAtomNext((IT)); \
            (ATOM) != NULL; \
            (ATOM) = pddlFmConstItAtomNext((IT)))

const pddl_fm_when_t *pddlFmConstItWhenInit(pddl_fm_const_it_when_t *it,
                                            const pddl_fm_t *fm);
const pddl_fm_when_t *pddlFmConstItWhenNext(pddl_fm_const_it_when_t *it);

#define PDDL_FM_FOR_EACH_WHEN(COND, IT, WHEN) \
    for ((WHEN) = pddlFmConstItWhenInit((IT), (COND)); \
            (WHEN) != NULL; \
            (WHEN) = pddlFmConstItWhenNext((IT)))

#define PDDL_FM_FOR_EACH_WHEN_CONT(IT, WHEN) \
    for ((WHEN) = pddlFmConstItWhenNext((IT)); \
            (WHEN) != NULL; \
            (WHEN) = pddlFmConstItWhenNext((IT)))

struct pddl_fm_const_it_eff {
    const pddl_list_t *list;
    const pddl_list_t *cur;
    const pddl_fm_t *when_pre;
    const pddl_list_t *when_list;
    const pddl_list_t *when_cur;
};
typedef struct pddl_fm_const_it_eff pddl_fm_const_it_eff_t;

const pddl_fm_atom_t *pddlFmConstItEffInit(pddl_fm_const_it_eff_t *it,
                                           const pddl_fm_t *fm,
                                           const pddl_fm_t **pre);
const pddl_fm_atom_t *pddlFmConstItEffNext(pddl_fm_const_it_eff_t *it,
                                           const pddl_fm_t **pre);

#define PDDL_FM_FOR_EACH_EFF(COND, IT, ATOM, PRE) \
    for ((ATOM) = pddlFmConstItEffInit((IT), (COND), &(PRE)); \
            (ATOM) != NULL; \
            (ATOM) = pddlFmConstItEffNext((IT), &(PRE)))
#define PDDL_FM_FOR_EACH_EFF_CONT(IT, ATOM, PRE) \
    for ((ATOM) = pddlFmConstItEffNext((IT), &(PRE)); \
            (ATOM) != NULL; \
            (ATOM) = pddlFmConstItEffNext((IT), &(PRE)))

#define PDDL_FM_FOR_EACH_ADD_EFF(COND, IT, ATOM, PRE) \
    PDDL_FM_FOR_EACH_EFF((COND), (IT), (ATOM), (PRE)) \
        if (!(ATOM)->neg)
#define PDDL_FM_FOR_EACH_ADD_EFF_CONT(IT, ATOM, PRE) \
    PDDL_FM_FOR_EACH_EFF_CONT((IT), (ATOM), (PRE)) \
        if (!(ATOM)->neg)

#define PDDL_FM_FOR_EACH_DEL_EFF(COND, IT, ATOM, PRE) \
    PDDL_FM_FOR_EACH_EFF((COND), (IT), (ATOM), (PRE)) \
        if ((ATOM)->neg)
#define PDDL_FM_FOR_EACH_DEL_EFF_CONT(IT, ATOM, PRE) \
    PDDL_FM_FOR_EACH_EFF_CONT((IT), (ATOM), (PRE)) \
        if ((ATOM)->neg)

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FM_H__ */
