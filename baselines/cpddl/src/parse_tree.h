/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PARSE_TREE_H__
#define __PDDL_PARSE_TREE_H__

#include "parse_tokenizer.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_parse_toks {
    pddl_parse_token_t *tok;
    int tok_size;
    int tok_alloc;
};
typedef struct pddl_parse_toks pddl_parse_toks_t;

pddl_parse_toks_t *pddlParseToksNew(void);
void pddlParseToksDel(pddl_parse_toks_t *a);
void pddlParseToksAdd(pddl_parse_toks_t *a, const pddl_parse_token_t *tok);
void pddlParseToksPrepend(pddl_parse_toks_t *a, const pddl_parse_token_t *tok);
void pddlParseToksSort(pddl_parse_toks_t *a);

struct pddl_parse_typed_list {
    pddl_parse_toks_t *list;
    pddl_parse_toks_t *type_either;
    pddl_parse_token_t type_either_tok;
    pddl_parse_token_t type;
};
typedef struct pddl_parse_typed_list pddl_parse_typed_list_t;

pddl_parse_typed_list_t *pddlParseTypedListNew(pddl_parse_toks_t *list,
                                               const pddl_parse_token_t *type);
pddl_parse_typed_list_t *pddlParseTypedListNewNoType(pddl_parse_toks_t *list);
pddl_parse_typed_list_t *pddlParseTypedListNewEither(pddl_parse_toks_t *list,
                                                     pddl_parse_toks_t *either,
                                                     const pddl_parse_token_t *either_tok);
void pddlParseTypedListDel(pddl_parse_typed_list_t *tl);
void pddlParseTypedListSort(pddl_parse_typed_list_t *tl);

struct pddl_parse_typed_lists {
    pddl_parse_typed_list_t **list;
    int list_size;
    int list_alloc;
};
typedef struct pddl_parse_typed_lists pddl_parse_typed_lists_t;

pddl_parse_typed_lists_t *pddlParseTypedListsNew(void);
void pddlParseTypedListsDel(pddl_parse_typed_lists_t *tl);
void pddlParseTypedListsAdd(pddl_parse_typed_lists_t *tls,
                            pddl_parse_typed_list_t *tl);
void pddlParseTypedListsMerge(pddl_parse_typed_lists_t *dst,
                              pddl_parse_typed_lists_t *src);
void pddlParseTypedListsSort(pddl_parse_typed_lists_t *tls);

void pddlParseTypedListsDebugPrint(const pddl_parse_typed_lists_t *tl,
                                   FILE *fout);


struct pddl_parse_tok_type {
    pddl_parse_token_t tok;
    int no_type;
    pddl_parse_token_t type;
    const pddl_parse_toks_t *type_either;
    pddl_parse_token_t type_either_tok;
};
typedef struct pddl_parse_tok_type pddl_parse_tok_type_t;

struct pddl_parse_tok_types {
    pddl_parse_tok_type_t *tok_type;
    int tok_type_size;
    int tok_type_alloc;
};
typedef struct pddl_parse_tok_types pddl_parse_tok_types_t;

void pddlParseTokTypesInitFromTypedLists(pddl_parse_tok_types_t *tok_types,
                                         const pddl_parse_typed_lists_t *tl);
void pddlParseTokTypesFree(pddl_parse_tok_types_t *tok_types);
void pddlParseTokTypesAddTypedList(pddl_parse_tok_types_t *tok_types,
                                   const pddl_parse_typed_list_t *tl);

enum pddl_parse_fm_tree_kind {
    PDDL_PARSE_FM_ATOM,
    PDDL_PARSE_FM_AND,
    PDDL_PARSE_FM_OR,
    PDDL_PARSE_FM_IMPLY,
    PDDL_PARSE_FM_WHEN,
    PDDL_PARSE_FM_NOT,
    PDDL_PARSE_FM_EXISTS,
    PDDL_PARSE_FM_FORALL,
    PDDL_PARSE_FM_CMP,
    PDDL_PARSE_FM_FEXP,
    PDDL_PARSE_FM_NUM_OP,
    PDDL_PARSE_FM_LIST,
    PDDL_PARSE_FM_INUM,
};
typedef enum pddl_parse_fm_tree_kind pddl_parse_fm_tree_kind_t;

typedef struct pddl_parse_fm_tree pddl_parse_fm_tree_t;
struct pddl_parse_fm_tree {
    pddl_parse_fm_tree_kind_t kind;
    pddl_parse_token_t ref_tok;
    pddl_parse_token_t op;
    pddl_parse_toks_t *atom;
    pddl_parse_typed_lists_t *params;
    pddl_parse_fm_tree_t **child;
    int child_size;
    int child_alloc;
};

pddl_parse_fm_tree_t *pddlParseFmTreeNew(pddl_parse_fm_tree_kind_t kind,
                                         const pddl_parse_token_t *ref);
void pddlParseFmTreeDel(pddl_parse_fm_tree_t *t);
void pddlParseFmTreeAddChild(pddl_parse_fm_tree_t *t,
                             pddl_parse_fm_tree_t *child);
void pddlParseFmTreeSetRef(pddl_parse_fm_tree_t *t,
                           const pddl_parse_token_t *ref);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_PARSE_TREE_H__ */
