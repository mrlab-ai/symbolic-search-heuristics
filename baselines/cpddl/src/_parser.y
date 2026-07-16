/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

%name pddlInternalParse
%extra_context { pddl_parse_ctx_t *ctx }
%token_type {pddl_parse_token_t}
%token_prefix PDDL_TOKEN_

%token
    LPAREN
    RPAREN
    DASH
    IDNT
    VAR_IDNT
    INUM
    FNUM

    KEYWORDS
    UNKNOWN_KW

    DEFINE
    DOMAIN
    PROBLEM
    PROB_DOMAIN
    REQUIREMENTS
    TYPES
    PREDICATES
    FUNCTIONS
    CONSTANTS
    ACTION
    PARAMETERS
    PRECONDITION
    EFFECT
    DERIVED

    REQUIRE_STRIPS
    REQUIRE_TYPING
    REQUIRE_NEGATIVE_PRE
    REQUIRE_DISJUNCTIVE_PRE
    REQUIRE_EQUALITY
    REQUIRE_EXISTENTIAL_PRE
    REQUIRE_UNIVERSAL_PRE
    REQUIRE_CONDITIONAL_EFF
    REQUIRE_NUMERIC_FLUENT
    REQUIRE_OBJECT_FLUENT
    REQUIRE_DURATIVE_ACTION
    REQUIRE_DURATION_INEQUALITY
    REQUIRE_CONTINUOUS_EFF
    REQUIRE_DERIVED_PRED
    REQUIRE_TIMED_INITIAL_LITERAL
    REQUIRE_PREFERENCE
    REQUIRE_CONSTRAINT
    REQUIRE_ACTION_COST
    REQUIRE_QUANTIFIED_PRE
    REQUIRE_FLUENTS
    REQUIRE_ADL

    NUMBER
    OBJECTS
    INIT
    GOAL
    METRIC
    MINIMIZE
    MAXIMIZE
    ASSIGN
    INCREASE
    DECREASE
    SCALE_UP
    SCALE_DOWN

    CMP_EQ
    CMP_LE
    CMP_GE
    CMP_LT
    CMP_GT

    PLUS
    MINUS
    MULT
    DIV
    FEXP_ATOM

    AND
    OR
    NOT
    IMPLY
    EXISTS
    FORALL
    WHEN

    EITHER
    .

%default_destructor {
    // Just to shut-up compiler
    (void)ctx;
}

%parse_accept {
    ctx->accept = 1;
}

%parse_failure {
    if (!ctx->abort){
        _ERRS(ctx->err, ctx->tokenizer, &ctx->cur_token, "Syntax error.");
        ctx->abort = 1;
    }
}

%stack_overflow {
    PANIC("Parser stack overflow while on line %d and column %d."
          " This should never happen as we allocate the stack dynamically.",
          ctx->cur_token.line, ctx->cur_token.column);
    ctx->abort = 1;
}

%syntax_error {
    if (!ctx->abort){
        _ERRSV(ctx->err, ctx->tokenizer, &yyminor,
               "Syntax error when processing token '%s'.", yyminor.str);
        ctx->abort = 1;
    }
}

%wildcard TERM.


root ::= domain_name.
root ::= prob_name.
root ::= prob_domain_name.
root ::= require_section.
root ::= types_section.
root ::= constants_section.
root ::= predicates_section.
root ::= functions_section.
root ::= action_section.
//root ::= durative_action_section.
root ::= derived_section.
root ::= objects.
root ::= init_state.
root ::= goal.
root ::= metric.

domain_name ::= LPAREN DOMAIN IDNT(T) RPAREN. {
    ctx->pddl->domain_name = STRDUP(T.str);
}

prob_name ::= LPAREN PROBLEM IDNT(T) RPAREN. {
    ctx->pddl->problem_name = STRDUP(T.str);
}

prob_domain_name ::= LPAREN PROB_DOMAIN IDNT(T) RPAREN. {
    if (!ctx->abort
            && ctx->pddl->domain_name != NULL
            && strcmp(T.str, ctx->pddl->domain_name) != 0){
        if (ctx->pddl->cfg.pedantic){
            _ERRSV(ctx->err, ctx->tokenizer, &T,
                   "Mismatch between the domain names in the domain and"
                   " problem pddl files; domain pddl: '%s', problem pddl: '%s'.",
                   ctx->pddl->domain_name, T.str);
            ctx->abort = 1;
        }else{
            WARN(ctx->err, "Mismatch between the domain names in the domain"
                 " and problem pddl files; domain pddl: '%s',"
                 " problem pddl: '%s'.",
                 ctx->pddl->domain_name, T.str);
        }
    }
}

require_section ::= LPAREN REQUIREMENTS require_kws RPAREN.
require_kws ::= require_kws require_kw.
require_kws ::= .
require_kw ::= REQUIRE_STRIPS. { ctx->pddl->require.strips = 1; }
require_kw ::= REQUIRE_TYPING. { ctx->pddl->require.typing = 1; }
require_kw ::= REQUIRE_NEGATIVE_PRE. { ctx->pddl->require.negative_pre = 1; }
require_kw ::= REQUIRE_DISJUNCTIVE_PRE. { ctx->pddl->require.disjunctive_pre = 1; }
require_kw ::= REQUIRE_EQUALITY. { ctx->pddl->require.equality = 1; }
require_kw ::= REQUIRE_EXISTENTIAL_PRE. { ctx->pddl->require.existential_pre = 1; }
require_kw ::= REQUIRE_UNIVERSAL_PRE. { ctx->pddl->require.universal_pre = 1; }
require_kw ::= REQUIRE_CONDITIONAL_EFF. { ctx->pddl->require.conditional_eff = 1; }
require_kw ::= REQUIRE_NUMERIC_FLUENT. { ctx->pddl->require.numeric_fluent = 1; }
require_kw ::= REQUIRE_OBJECT_FLUENT. { ctx->pddl->require.object_fluent = 1; }
require_kw ::= REQUIRE_DURATIVE_ACTION. { ctx->pddl->require.durative_action = 1; }
require_kw ::= REQUIRE_DURATION_INEQUALITY. { ctx->pddl->require.duration_inequality = 1; }
require_kw ::= REQUIRE_CONTINUOUS_EFF. { ctx->pddl->require.continuous_eff = 1; }
require_kw ::= REQUIRE_DERIVED_PRED. { ctx->pddl->require.derived_pred = 1; }
require_kw ::= REQUIRE_TIMED_INITIAL_LITERAL. { ctx->pddl->require.timed_initial_literal = 1; }
require_kw ::= REQUIRE_PREFERENCE. { ctx->pddl->require.preference = 1; }
require_kw ::= REQUIRE_CONSTRAINT. { ctx->pddl->require.constraint = 1; }
require_kw ::= REQUIRE_ACTION_COST. { ctx->pddl->require.action_cost = 1; }
require_kw ::= REQUIRE_QUANTIFIED_PRE. {
    ctx->pddl->require.existential_pre = 1;
    ctx->pddl->require.universal_pre = 1;
}
require_kw ::= REQUIRE_FLUENTS. {
    ctx->pddl->require.numeric_fluent = 1;
    ctx->pddl->require.object_fluent = 1;
}
require_kw ::= REQUIRE_ADL. {
    ctx->pddl->require.strips = 1;
    ctx->pddl->require.typing = 1;
    ctx->pddl->require.negative_pre = 1;
    ctx->pddl->require.disjunctive_pre = 1;
    ctx->pddl->require.equality = 1;
    ctx->pddl->require.existential_pre = 1;
    ctx->pddl->require.universal_pre = 1;
    ctx->pddl->require.conditional_eff = 1;
}
require_kw ::= REQUIRE_MULTI_AGENT. { ctx->pddl->require.multi_agent = 1; }
require_kw ::= REQUIRE_UNFACTORED_PRIVACY. { ctx->pddl->require.unfactored_privacy = 1; }
require_kw ::= REQUIRE_FACTORED_PRIVACY. { ctx->pddl->require.factored_privacy = 1; }
require_kw ::= TERM(T). {
    if (T.token == PDDL_TOKEN_UNKNOWN_KW
            || T.token == PDDL_TOKEN_IDNT
            || T.token == PDDL_TOKEN_VAR_IDNT){
        _ERRSV(ctx->err, ctx->tokenizer, &T,
              "Invalid keyword %s in the (:requirements ...) section.", T.str);
    }else{
        _ERRS(ctx->err, ctx->tokenizer, &T, "Syntax error.");
    }
    ctx->abort = 1;
}


types_section ::= LPAREN TYPES(KW) typed_lists(T) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(T);
        if (addTypes(ctx->pddl, T, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;

        if (T->list_size == 0){
            LOG(ctx->err, "Empty (:types ...) section (line %d, column %d).",
                KW.line, KW.column);
        }
    }
    pddlParseTypedListsDel(T);
}

constants_section ::= LPAREN CONSTANTS(KW) typed_lists(T) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(T);
        if (addConstants(ctx->pddl, T, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;

        if (T->list_size == 0){
            LOG(ctx->err, "Empty (:constants ...) section (line %d, column %d).",
                KW.line, KW.column);
        }
    }
    pddlParseTypedListsDel(T);
}

predicates_section ::= LPAREN PREDICATES predicate_list RPAREN.

predicate_list ::= predicate_list predicate_def.
predicate_list ::= .

predicate_def ::= LPAREN IDNT(H) typed_lists(A) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(A);
        if (addPred(ctx->pddl, &H, A, ctx->tokenizer, ctx->err) < 0)
            ctx->abort = 1;
    }
    pddlParseTypedListsDel(A);
}

functions_section ::= LPAREN FUNCTIONS function_list RPAREN.

function_list ::= function_list function_def.
function_list ::= .

function_def ::= function_def_notype DASH NUMBER.
function_def ::= function_def_notype.
function_def_notype ::= LPAREN IDNT(H) typed_lists(A) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(A);
        if (addFunc(ctx->pddl, &H, A, ctx->tokenizer, ctx->err) < 0)
            ctx->abort = 1;
    }
    pddlParseTypedListsDel(A);
    // TODO: This is not very accurate, because :action-costs specifies
    // only a small subset of what :numeric-fluents allow
    checkRequire(ctx, ctx->pddl->require.numeric_fluent
                        || ctx->pddl->require.action_cost, &H,
                 ":numeric-fluents or :fluents or :action-costs",
                 "a (:functions ...) section", "");
}


action_section
    ::= LPAREN ACTION IDNT(Name)
            PARAMETERS LPAREN typed_lists(Params) RPAREN
            action_pre(Pre) action_eff(Eff) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(Params);
        if (addAction(ctx->pddl, &Name, Params, Pre, Eff, ctx->tokenizer,
                      ctx->err) < 0){
            ctx->abort = 1;
        }
    }

    pddlParseTypedListsDel(Params);
    if (Pre != NULL)
        pddlParseFmTreeDel(Pre);
    if (Eff != NULL)
        pddlParseFmTreeDel(Eff);
}

// This rule is just for better analysis of the error when missing
// :parameters section which is mandatory according to the specification
action_section ::= LPAREN ACTION IDNT(Name) action_pre action_eff RPAREN. {
    if (!ctx->abort){
        _ERRSV(ctx->err, ctx->tokenizer, &Name,
               "Syntax error: Missing the mandatory ':parameters' section"
               " in the action %s", Name.str);
        ctx->abort = 1;
    }
}

%type action_pre { pddl_parse_fm_tree_t * }
%destructor action_pre { if ($$ != NULL) pddlParseFmTreeDel($$); }
%type action_eff { pddl_parse_fm_tree_t * }
%destructor action_eff { if ($$ != NULL) pddlParseFmTreeDel($$); }
action_pre(E) ::= PRECONDITION LPAREN(Ref) RPAREN. {
    E = pddlParseFmTreeNew(PDDL_PARSE_FM_AND, &Ref);
}
action_pre(E) ::= PRECONDITION pre_formula(F). {
    E = F;
}
action_pre(E) ::= . {
    E = pddlParseFmTreeNew(PDDL_PARSE_FM_AND, NULL);
}

action_eff(E) ::= EFFECT LPAREN(Ref) RPAREN. {
    E = pddlParseFmTreeNew(PDDL_PARSE_FM_AND, &Ref);
}
action_eff(E) ::= EFFECT eff_formula(F). {
    E = F;
}
action_eff(E) ::= . {
    E = pddlParseFmTreeNew(PDDL_PARSE_FM_AND, NULL);
}

derived_section ::= LPAREN DERIVED(R) LPAREN IDNT typed_lists(P) action_pre(C) RPAREN. {
    if (!ctx->abort){
        _ERRS(ctx->err, ctx->tokenizer, &R,
              "Derived predicates are not supported.");
        ctx->abort = 1;
    }

    pddlParseTypedListsDel(P);
    if (C != NULL)
        pddlParseFmTreeDel(C);
}


%type pre_formula { pddl_parse_fm_tree_t * }
%destructor pre_formula { if ($$ != NULL) pddlParseFmTreeDel($$); }
pre_formula(O) ::= LPAREN AND(Ref) pre_formula_list(IN) RPAREN. {
    O = IN;
    O->kind = PDDL_PARSE_FM_AND;
    O->ref_tok = Ref;
}
pre_formula(O) ::= LPAREN OR(Ref) pre_formula_list(IN) RPAREN. {
    O = IN;
    O->kind = PDDL_PARSE_FM_OR;
    O->ref_tok = Ref;
    checkRequire(ctx, ctx->pddl->require.disjunctive_pre, &Ref,
                 ":disjunctive-preconditions or :adl", "an (or ...) formula", "");
}
pre_formula(O) ::= LPAREN NOT(Ref) pre_formula(F) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_NOT, &Ref);
    pddlParseFmTreeAddChild(O, F);
    checkRequire(ctx, ctx->pddl->require.negative_pre, &Ref,
                 ":negative-preconditions or :adl", "a (not ...) formula", "");
}
pre_formula(O) ::= LPAREN IMPLY(Ref) pre_formula(L) pre_formula(R) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_IMPLY, &Ref);
    pddlParseFmTreeAddChild(O, L);
    pddlParseFmTreeAddChild(O, R);
    checkRequire(ctx, ctx->pddl->require.disjunctive_pre, &Ref,
                 ":disjunctive-preconditions or :adl", "an (imply ...) formula", "");
}
pre_formula(O) ::= LPAREN EXISTS(Ref) LPAREN typed_lists(P) RPAREN pre_formula(F) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_EXISTS, &Ref);
    O->params = P;
    pddlParseFmTreeAddChild(O, F);
    checkRequire(ctx, ctx->pddl->require.existential_pre, &Ref,
                 ":existential-preconditions or :quantified-preconditions or :adl",
                 "an (exists ...) formula", "");
}
pre_formula(O) ::= LPAREN FORALL(Ref) LPAREN typed_lists(P) RPAREN pre_formula(F) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FORALL, &Ref);
    O->params = P;
    pddlParseFmTreeAddChild(O, F);
    checkRequire(ctx, ctx->pddl->require.universal_pre, &Ref,
                 ":universal-preconditions or :quantified-preconditions or :adl",
                 "a (forall ...) formula", "");
}
pre_formula(F) ::= comparator(A). {
    F = A;
    checkRequire(ctx, ctx->pddl->require.numeric_fluent, &A->ref_tok,
                 ":numeric-fluents",
                 "a numeric comparator", "");
}
pre_formula(F) ::= atom(A). { F = A; }

%type pre_formula_list { pddl_parse_fm_tree_t * }
%destructor pre_formula_list { if ($$ != NULL) pddlParseFmTreeDel($$); }
pre_formula_list(L) ::= pre_formula_list(IN) pre_formula(F). {
    L = IN;
    pddlParseFmTreeAddChild(L, F);
}
pre_formula_list(L) ::= . {
    L = pddlParseFmTreeNew(PDDL_PARSE_FM_LIST, NULL);
}


%type eff_formula { pddl_parse_fm_tree_t * }
%destructor eff_formula { if ($$ != NULL) pddlParseFmTreeDel($$); }
eff_formula(O) ::= LPAREN AND(Ref) eff_formula_list(IN) RPAREN. {
    O = IN;
    O->kind = PDDL_PARSE_FM_AND;
    O->ref_tok = Ref;
}
eff_formula(O) ::= LPAREN NOT(Ref) eff_formula(F) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_NOT, &Ref);
    pddlParseFmTreeAddChild(O, F);
}
eff_formula(O) ::= LPAREN FORALL(Ref) LPAREN typed_lists(P) RPAREN eff_formula(F) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FORALL, &Ref);
    O->params = P;
    pddlParseFmTreeAddChild(O, F);
    checkRequire(ctx, ctx->pddl->require.conditional_eff, &Ref,
                 ":conditional-effects or :adl", "a (forall ...) formula",
                 " in an action effect");
}
eff_formula(O) ::= LPAREN WHEN(Ref) pre_formula(C) eff_formula(E) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_WHEN, &Ref);
    pddlParseFmTreeAddChild(O, C);
    pddlParseFmTreeAddChild(O, E);
    checkRequire(ctx, ctx->pddl->require.conditional_eff, &Ref,
                 ":conditional-effects or :adl", "a (when ...) formula", "");
}
eff_formula(O) ::= LPAREN(Ref) func_op(Op) func_op_dst(Dst) fexp(Src) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_NUM_OP, &Ref);
    O->op = Op;
    pddlParseFmTreeAddChild(O, Dst);
    pddlParseFmTreeAddChild(O, Src);
    checkRequire(ctx, ctx->pddl->require.action_cost
                        || ctx->pddl->require.numeric_fluent, &Ref,
                 ":action-cost or :numeric-fluents",
                 "a numeric expression", " in the actions' effects");
}
eff_formula(F) ::= atom(A). { F = A; }

%type func_op { pddl_parse_token_t }
func_op(D) ::= ASSIGN(S). { D = S; }
func_op(D) ::= INCREASE(S). { D = S; }
func_op(D) ::= DECREASE(S). { D = S; }
func_op(D) ::= SCALE_UP(S). { D = S; }
func_op(D) ::= SCALE_DOWN(S). { D = S; }

%type func_op_dst { pddl_parse_fm_tree_t * }
%destructor func_op_dst { if ($$ != NULL) pddlParseFmTreeDel($$); }
func_op_dst(O) ::= IDNT(S). {
    pddl_parse_fm_tree_t *A = pddlParseFmTreeNew(PDDL_PARSE_FM_ATOM, &S);
    A->atom = pddlParseToksNew();
    pddlParseToksAdd(A->atom, &S);

    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &A->ref_tok);
    O->op.token = PDDL_TOKEN_FEXP_ATOM;
    pddlParseFmTreeAddChild(O, A);
}
func_op_dst(O) ::= atom(A). {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &A->ref_tok);
    O->op.token = PDDL_TOKEN_FEXP_ATOM;
    pddlParseFmTreeAddChild(O, A);
}



%type eff_formula_list { pddl_parse_fm_tree_t * }
%destructor eff_formula_list { if ($$ != NULL) pddlParseFmTreeDel($$); }
eff_formula_list(L) ::= eff_formula_list(IN) eff_formula(F). {
    L = IN;
    pddlParseFmTreeAddChild(L, F);
}
eff_formula_list(L) ::= . {
    L = pddlParseFmTreeNew(PDDL_PARSE_FM_LIST, NULL);
}


%type comparator { pddl_parse_fm_tree_t * }
%destructor comparator { if ($$ != NULL) pddlParseFmTreeDel($$); }
comparator(O) ::= LPAREN(Ref) compare_op(Op) fexp(X) fexp(Y) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_CMP, &Ref);
    O->op = Op;
    pddlParseFmTreeAddChild(O, X);
    pddlParseFmTreeAddChild(O, Y);
}

%type compare_op { pddl_parse_token_t }
compare_op(D) ::= CMP_EQ(T). { D = T; }
compare_op(D) ::= CMP_LE(T). { D = T; }
compare_op(D) ::= CMP_GE(T). { D = T; }
compare_op(D) ::= CMP_LT(T). { D = T; }
compare_op(D) ::= CMP_GT(T). { D = T; }

%type fexp { pddl_parse_fm_tree_t * }
%destructor fexp { if ($$ != NULL) pddlParseFmTreeDel($$); }
%type fexp_op_list { pddl_parse_fm_tree_t * }
%destructor fexp_op_list { if ($$ != NULL) pddlParseFmTreeDel($$); }
fexp_op_list(O) ::= fexp_op(Op) fexp(X). {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &Op);
    O->op = Op;
    pddlParseFmTreeAddChild(O, X);
}
fexp_op_list(O) ::= fexp_op_list(Q) fexp(X). {
    O = Q;
    pddlParseFmTreeAddChild(O, X);
}
fexp(O) ::= LPAREN(Ref) fexp_op_list(Q) RPAREN. {
    O = Q;
    pddlParseFmTreeSetRef(O, &Ref);
    checkRequire(ctx, ctx->pddl->require.numeric_fluent, &Ref,
                 ":numeric-fluents", "a numeric comparator", "");
}
/* Old rule for binary-only operators:
fexp(O) ::= LPAREN(Ref) fexp_op(Op) fexp(X) fexp(Y) RPAREN. {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &Ref);
    O->op = Op;
    pddlParseFmTreeAddChild(O, X);
    pddlParseFmTreeAddChild(O, Y);
    checkRequire(ctx, ctx->pddl->require.numeric_fluent, &Ref,
                 ":numeric-fluents", "a numeric comparator", "");
}
*/
fexp(O) ::= atom(A). {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &A->ref_tok);
    O->op.token = PDDL_TOKEN_FEXP_ATOM;
    pddlParseFmTreeAddChild(O, A);
}
fexp(O) ::= INUM(R). {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &R);
    O->op = R;
}
fexp(O) ::= FNUM(R). {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_FEXP, &R);
    O->op = R;
}

%type fexp_op { pddl_parse_token_t }
fexp_op(D) ::= PLUS(T). { D = T; }
fexp_op(D) ::= DASH(T). {
    D = T;
    D.token = PDDL_TOKEN_MINUS;
}
fexp_op(D) ::= MULT(T). { D = T; }
fexp_op(D) ::= DIV(T). { D = T; }


%type atom { pddl_parse_fm_tree_t * }
%destructor atom { if ($$ != NULL) pddlParseFmTreeDel($$); }
atom(F) ::= LPAREN(Ref) idnt_list(A) RPAREN. {
    F = pddlParseFmTreeNew(PDDL_PARSE_FM_ATOM, &Ref);
    F->atom = A;
}
atom(F) ::= LPAREN(Ref) CMP_EQ(Eq) idnt_list(A) RPAREN. {
    F = pddlParseFmTreeNew(PDDL_PARSE_FM_ATOM, &Ref);
    F->atom = A;
    Eq.token = PDDL_TOKEN_IDNT;
    pddlParseToksPrepend(F->atom, &Eq);
}


objects ::= LPAREN OBJECTS(KW) typed_lists(T) RPAREN. {
    if (!ctx->abort){
        pddlParseTypedListsSort(T);
        if (addObjects(ctx->pddl, T, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;

        if (T->list_size == 0){
            LOG(ctx->err, "Empty (:objects ...) section (line %d, column %d).",
                KW.line, KW.column);
        }
    }
    pddlParseTypedListsDel(T);
}

init_state ::= LPAREN INIT init_state_atoms(I) RPAREN. {
    if (!ctx->abort){
        if (setInit(ctx->pddl, I, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;
    }
    pddlParseFmTreeDel(I);
}

%type init_state_atoms { pddl_parse_fm_tree_t * }
%destructor init_state_atoms { if ($$ != NULL) pddlParseFmTreeDel($$); }
init_state_atoms(O) ::= init_state_atoms(L) init_state_atom(A). {
    O = L;
    pddlParseFmTreeAddChild(O, A);
}
init_state_atoms(O) ::= . {
    O = pddlParseFmTreeNew(PDDL_PARSE_FM_LIST, NULL);
}

%type init_state_atom { pddl_parse_fm_tree_t * }
%destructor init_state_atom { if ($$ != NULL) pddlParseFmTreeDel($$); }
init_state_atom(O) ::= atom(A). { O = A; }
init_state_atom(O) ::= comparator(C). {
    O = C;
    checkRequire(ctx, ctx->pddl->require.action_cost
                        || ctx->pddl->require.numeric_fluent, &C->ref_tok,
                 ":action-cost or :numeric-fluents",
                 "a numerical comparator", " in the (:init ...) section");
}

goal ::= LPAREN GOAL pre_formula(G) RPAREN. {
    if (!ctx->abort){
        if (setGoal(ctx->pddl, G, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;
    }
    pddlParseFmTreeDel(G);
}

metric ::= LPAREN METRIC metric_opt RPAREN.
metric_opt ::= MINIMIZE(H) fexp(M). {
    if (!ctx->abort){
        if (setMetric(ctx->pddl, M, ctx->tokenizer, ctx->err) != 0)
            ctx->abort = 1;
    }
    pddlParseFmTreeDel(M);
    checkRequire(ctx, ctx->pddl->require.action_cost
                        || ctx->pddl->require.numeric_fluent, &H,
                 ":action-cost or :numeric-fluents",
                 "the (:metric (minimize ...))", "");
}
metric_opt ::= MAXIMIZE(M) fexp(E). {
    _ERRS(ctx->err, ctx->tokenizer, &M, "Maximization is not supported.");
    ctx->abort = 1;
    pddlParseFmTreeDel(E);
}


%type typed_lists { pddl_parse_typed_lists_t * }
%destructor typed_lists { if ($$ != NULL) pddlParseTypedListsDel($$); }
%type typed_lists_wtype { pddl_parse_typed_lists_t * }
%destructor typed_lists_wtype { if ($$ != NULL) pddlParseTypedListsDel($$); }
%type typed_lists_wotype { pddl_parse_typed_lists_t * }
%destructor typed_lists_wotype { if ($$ != NULL) pddlParseTypedListsDel($$); }
typed_lists(L) ::= typed_lists_wtype(H) typed_lists_wotype(T). {
    L = H;
    pddlParseTypedListsMerge(L, T);
    pddlParseTypedListsDel(T);
}

typed_lists_wtype(L) ::= typed_lists_wtype(LIN)
        idnt_list(T) DASH LPAREN EITHER(ET) idnt_list(E) RPAREN. {
    L = LIN;
    pddl_parse_typed_list_t *tl = pddlParseTypedListNewEither(T, E, &ET);
    pddlParseTypedListsAdd(L, tl);
}
typed_lists_wtype(L) ::= typed_lists_wtype(LIN) idnt_list(S) DASH IDNT(T). {
    L = LIN;
    pddl_parse_typed_list_t *tl = pddlParseTypedListNew(S, &T);
    pddlParseTypedListsAdd(L, tl);
    checkRequire(ctx, ctx->pddl->require.typing, &T,
                 ":typing or :adl", "a type", "");
}
typed_lists_wtype(L) ::= . { L = pddlParseTypedListsNew(); }

typed_lists_wotype(L) ::= idnt_list(S). {
    L = pddlParseTypedListsNew();
    pddl_parse_typed_list_t *tl = pddlParseTypedListNewNoType(S);
    pddlParseTypedListsAdd(L, tl);
}
typed_lists_wotype(L) ::= . { L = pddlParseTypedListsNew(); }


%type idnt_list { pddl_parse_toks_t * }
%destructor idnt_list { if ($$ != NULL) pddlParseToksDel($$); }
idnt_list(L) ::= idnt_list(L) idnt_list_tok(T). {
    pddlParseToksAdd(L, &T);
}
idnt_list(L) ::= idnt_list_tok(T). {
    L = pddlParseToksNew();
    pddlParseToksAdd(L, &T);
}

%type idnt_list_tok { pddl_parse_token_t }
idnt_list_tok(D) ::= IDNT(T). { D = T; }
idnt_list_tok(D) ::= VAR_IDNT(T). { D = T; }
