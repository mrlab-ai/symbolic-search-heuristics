/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

//%stack_size 2000
//%start_symbol pddl

%name pddlInternalParse
//%extra_argument { pddl_t *pddl }
%extra_context { pddl_parser_ctx_t *ctx }
%token_type {pddl_parse_token_t}
//%type formula {pddl_parse_token_t *}
//%include { ... }
%token_prefix TOKEN_

/*
%parse_accept {
    printf("parsing complete!\n");
}
*/

%parse_failure {
    fprintf(stderr,"Giving up.  Parser is hopelessly lost...\n");
    /* TODO
    ERR(ctx->err, "Parser failure while on line %d and column %d."
        " This should never happen!",
        ctx->tokenizer->cur_line,
        ctx->tokenizer->cur_column);
    */
    ctx->abort = 1;
}

%stack_overflow {
    /* TODO
    ERR(ctx->err, "Parser stack overflow while on line %d and column %d."
        " Aborting...", ctx->tokenizer->cur_line, ctx->tokenizer->cur_column);
    */
    ctx->abort = 1;
}

%syntax_error {
    ERR(ctx->err, "Syntax error on line %d and column %d",
        yyminor.line, yyminor.column);
    ctx->abort = 1;
}

%default_destructor {
    // Just to shut-up compiler
    (void)ctx;
}

%wildcard TERM.

pddl_domain ::= LPAREN DEFINE domain_name domain_sections RPAREN. {
    // TODO: Record that we successfully parsed a domain
}
domain_name ::= LPAREN DOMAIN IDNT RPAREN. {
    // TODO: Save domain name to the ctx->pddl struct
}

domain_sections ::= domain_sections require_section.
domain_sections ::= domain_sections types_section.
domain_sections ::= domain_sections constants_section.
domain_sections ::= domain_sections predicates_section.
domain_sections ::= domain_sections functions_section.
domain_sections ::= domain_sections action_def.
// TODO: domain_sections ::= derived_def domain_sections.
domain_sections ::= .


require_section ::= LPAREN REQUIREMENTS require_kws RPAREN. {
    // TODO: Check order of sections
}
require_kws ::= require_kws require_kw.
require_kws ::= require_kw.
require_kw ::= REQUIRE_STRIPS. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_TYPING. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_NEGATIVE_PRE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_DISJUNCTIVE_PRE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_EQUALITY. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_EXISTENTIAL_PRE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_UNIVERSAL_PRE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_CONDITIONAL_EFF. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_NUMERIC_FLUENT. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_OBJECT_FLUENT. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_DURATIVE_ACTION. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_DURATION_INEQUALITY. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_CONTINUOUS_EFF. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_DERIVED_PRED. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_TIMED_INITIAL_LITERAL. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_PREFERENCE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_CONSTRAINT. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_ACTION_COST. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_QUANTIFIED_PRE. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_FLUENTS. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_ADL. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_MULTI_AGENT. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_UNFACTORED_PRIVACY. {
    // TODO: Set requirement flag
}
require_kw ::= REQUIRE_FACTORED_PRIVACY. {
    // TODO: Set requirement flag
}
require_kw ::= TERM(Tok). {
    /* TODO
    TOKEN_S(s, &Tok);
    ERR(ctx->err, "Invalid keyword %s in the (:requirements ...) section"
        " on line %d, column %d",
        s, Tok.line, Tok.column);
    */
    ctx->abort = 1;
}

types_section ::= LPAREN TYPES(KW) typed_lists(T) RPAREN. {
    pddlParserTypedListsSort(T);
    pddlParserTypedListsDebugPrint(T, &ctx->str, stderr);
    // TODO: Record that :types was successfully parsed
    // TODO: Warning about empty :types section if that is the case
    //       Or error if configured as "strict"
    if (ctx->pddl->type.type_size == 0){
        WARN(ctx->err, "Empty (:types ...) section (line %d, column %d).",
             KW.line, KW.column);
        //ERR(ctx->err, "Empty (:types ...) section.");
        //ctx->abort = 1;
    }
}

%type typed_lists { pddl_parser_typed_lists_t * }
%destructor typed_lists { pddlParserTypedListsDel($$); }
typed_lists(L) ::= idnt_list(T) DASH LPAREN EITHER idnt_list(E) RPAREN typed_lists(LIN). {
    L = LIN;
    pddlParserTypedListsAddTypedListEither(L, T, E);
}
typed_lists(L) ::= idnt_list(S) DASH IDNT(T) typed_lists(LIN). {
    L = LIN;
    pddlParserTypedListsAddTypedList(L, S, &ctx->str, &T);
}
typed_lists(L) ::= idnt_list(S). { L = pddlParserTypedListsNewList(S); }
typed_lists(L) ::= . { L = pddlParserTypedListsNew(); }

%type idnt_list { pddl_parser_toks_t * }
%destructor idnt_list { pddlParserToksDel($$); }
idnt_list(L) ::= idnt_list(L) idnt_list_tok(T). {
    pddlParserToksAdd(L, &ctx->str, &T);
}
idnt_list(L) ::= idnt_list_tok(T). { L = pddlParserToksNewTok(&ctx->str, &T); }

%type idnt_list_tok { pddl_parse_token_t }
idnt_list_tok(D) ::= IDNT(T). { D = T; }
idnt_list_tok(D) ::= VAR_IDNT(T). { D = T; }


constants_section ::= LPAREN CONSTANTS constants_lists RPAREN.
constants_lists ::= constant_names DASH IDNT constants_lists.
constants_lists ::= constant_names.
constants_lists ::= .
constant_names ::= constant_names IDNT.
constant_names ::= IDNT.

predicates_section ::= LPAREN PREDICATES predicates_def RPAREN.
predicates_def ::= predicate_def predicates_def.
predicates_def ::= .
predicate_def ::= LPAREN IDNT predicate_params RPAREN.
predicate_params ::= predicate_param predicate_params.
predicate_params ::= .
predicate_param ::= VAR_IDNT DASH IDNT.
predicate_param ::= VAR_IDNT.

functions_section ::= LPAREN FUNCTIONS functions_def RPAREN.
functions_def ::= function_def functions_def.
functions_def ::= .
function_def ::= LPAREN IDNT function_params RPAREN.
function_params ::= function_param function_params.
function_params ::= .
function_param ::= VAR_IDNT DASH IDNT.
function_param ::= VAR_IDNT.

action_def ::= LPAREN ACTION IDNT action_param_def action_pre action_eff RPAREN.
action_param_def ::= PARAMETERS LPAREN action_params RPAREN.
action_param_def ::= .
action_params ::= action_param action_params.
action_params ::= .
action_param ::= VAR_IDNT DASH IDNT.
action_param ::= VAR_IDNT.
action_pre ::= PRECONDITION formula.
action_pre ::= .
action_eff ::= EFFECT formula.
action_eff ::= .

formula ::= fm_atom.
formula ::= LPAREN NOT formula RPAREN.
formula ::= LPAREN AND formula RPAREN.
formula ::= LPAREN OR formula RPAREN.
formula ::= LPAREN IMPLY formula formula RPAREN.
formula ::= LPAREN WHEN formula formula RPAREN.
formula ::= LPAREN FORALL LPAREN params RPAREN formula RPAREN.
formula ::= LPAREN EXISTS LPAREN params RPAREN formula RPAREN.
formula ::= LPAREN INCREASE fm_atom fm_atom_or_const RPAREN.
fm_atom ::= LPAREN IDNT fm_args RPAREN.
fm_args ::= fm_args fm_arg.
fm_args ::= .
fm_arg ::= VAR_IDNT.
fm_arg ::= IDNT.
fm_atom_or_const ::= fm_atom.
fm_atom_or_const ::= IDNT.

params ::= params param.
params ::= .
param ::= VAR_IDNT DASH IDNT.
param ::= VAR_IDNT.
