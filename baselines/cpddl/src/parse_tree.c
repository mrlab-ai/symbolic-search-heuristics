/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "parse_tree.h"
#include "internal.h"
#include "pddl/sort.h"

pddl_parse_toks_t *pddlParseToksNew(void)
{
    return ZALLOC(pddl_parse_toks_t);
}

void pddlParseToksDel(pddl_parse_toks_t *a)
{
    if (a->tok != NULL)
        FREE(a->tok);
    FREE(a);
}

void pddlParseToksAdd(pddl_parse_toks_t *a, const pddl_parse_token_t *tok)
{
    if (a->tok_size == a->tok_alloc){
        if (a->tok_alloc == 0)
            a->tok_alloc = 2;
        a->tok_alloc *= 2;
        a->tok = REALLOC_ARR(a->tok, pddl_parse_token_t, a->tok_alloc);
    }
    a->tok[a->tok_size++] = *tok;
}

void pddlParseToksPrepend(pddl_parse_toks_t *a, const pddl_parse_token_t *tok)
{
    if (a->tok_size == a->tok_alloc){
        if (a->tok_alloc == 0)
            a->tok_alloc = 2;
        a->tok_alloc *= 2;
        a->tok = REALLOC_ARR(a->tok, pddl_parse_token_t, a->tok_alloc);
    }
    for (int i = a->tok_size; i >= 1; --i)
        a->tok[i] = a->tok[i - 1];
    a->tok[0] = *tok;
    a->tok_size++;
}

static int cmpTok(const void *a, const void *b, void *_)
{
    const pddl_parse_token_t *t1 = a;
    const pddl_parse_token_t *t2 = b;
    int cmp = t1->line - t2->line;
    if (cmp == 0)
        cmp = t1->column - t2->column;
    return cmp;
}

void pddlParseToksSort(pddl_parse_toks_t *a)
{
    pddlSort(a->tok, a->tok_size, sizeof(pddl_parse_token_t), cmpTok, NULL);
}

pddl_parse_typed_list_t *pddlParseTypedListNew(pddl_parse_toks_t *list,
                                               const pddl_parse_token_t *type)
{
    pddl_parse_typed_list_t *tl = ZALLOC(pddl_parse_typed_list_t);
    tl->list = list;
    tl->type = *type;
    return tl;
}

pddl_parse_typed_list_t *pddlParseTypedListNewNoType(pddl_parse_toks_t *list)
{
    pddl_parse_token_t type = { 0 };
    type.token = -1;
    return pddlParseTypedListNew(list, &type);
}

pddl_parse_typed_list_t *pddlParseTypedListNewEither(pddl_parse_toks_t *list,
                                                     pddl_parse_toks_t *either,
                                                     const pddl_parse_token_t *either_tok)
{
    pddl_parse_typed_list_t *tl = ZALLOC(pddl_parse_typed_list_t);
    tl->list = list;
    tl->type_either = either;
    tl->type_either_tok = *either_tok;
    tl->type.token = -1;
    return tl;
}

void pddlParseTypedListDel(pddl_parse_typed_list_t *tl)
{
    if (tl->list != NULL)
        pddlParseToksDel(tl->list);
    if (tl->type_either != NULL)
        pddlParseToksDel(tl->type_either);
    FREE(tl);
}

void pddlParseTypedListSort(pddl_parse_typed_list_t *tl)
{
    if (tl->list != NULL)
        pddlParseToksSort(tl->list);
    if (tl->type_either != NULL)
        pddlParseToksSort(tl->type_either);
}


pddl_parse_typed_lists_t *pddlParseTypedListsNew(void)
{
    return ZALLOC(pddl_parse_typed_lists_t);
}

void pddlParseTypedListsDel(pddl_parse_typed_lists_t *tl)
{
    for (int i = 0; i < tl->list_size; ++i)
        pddlParseTypedListDel(tl->list[i]);
    if (tl->list != NULL)
        FREE(tl->list);
    FREE(tl);
}

void pddlParseTypedListsAdd(pddl_parse_typed_lists_t *tls,
                            pddl_parse_typed_list_t *tl)
{
    if (tls->list_size == tls->list_alloc){
        if (tls->list_alloc == 0)
            tls->list_alloc = 2;
        tls->list_alloc *= 2;
        tls->list = REALLOC_ARR(tls->list, pddl_parse_typed_list_t *,
                                tls->list_alloc);
    }

    tls->list[tls->list_size++] = tl;
}

void pddlParseTypedListsMerge(pddl_parse_typed_lists_t *dst,
                              pddl_parse_typed_lists_t *src)
{
    for (int i = 0; i < src->list_size; ++i)
        pddlParseTypedListsAdd(dst, src->list[i]);
    src->list_size = 0;
}

static int cmpTypedList(const void *a, const void *b, void *_)
{
    const pddl_parse_typed_list_t *t1 = *(const pddl_parse_typed_list_t **)a;
    const pddl_parse_typed_list_t *t2 = *(const pddl_parse_typed_list_t **)b;
    if ((t1->list == NULL || t1->list->tok_size == 0)
            && (t2->list == NULL || t2->list->tok_size == 0)){
        return 0;
    }
    if (t1->list == NULL || t1->list->tok_size == 0)
        return 1;
    if (t2->list == NULL || t2->list->tok_size == 0)
        return -1;

    int cmp = t1->list->tok[0].line - t2->list->tok[0].line;
    if (cmp == 0)
        cmp = t1->list->tok[0].column - t2->list->tok[0].column;
    return cmp;
}

void pddlParseTypedListsSort(pddl_parse_typed_lists_t *tls)
{
    for (int i = 0; i < tls->list_size; ++i)
        pddlParseTypedListSort(tls->list[i]);

    if (tls->list_size > 0){
        pddlSort(tls->list, tls->list_size, sizeof(*tls->list),
                 cmpTypedList, NULL);
    }
}

void pddlParseTypedListsDebugPrint(const pddl_parse_typed_lists_t *tl,
                                   FILE *fout)
{
    for (int i = 0; i < tl->list_size; ++i){
        const pddl_parse_typed_list_t *l = tl->list[i];
        fprintf(fout, "Typed List:");
        for (int j = 0; j < l->list->tok_size; ++j){
            fprintf(fout, " %s[%d/%d]",
                    l->list->tok[j].str,
                    l->list->tok[j].line,
                    l->list->tok[j].column);
        }
        fprintf(fout, " :-:");
        if (l->type_either != NULL){
            fprintf(fout, " either:");
            for (int j = 0; j < l->type_either->tok_size; ++j){
                fprintf(fout, " %s[%d/%d]",
                        l->type_either->tok[j].str,
                        l->type_either->tok[j].line,
                        l->type_either->tok[j].column);
            }
        }else{
            if (l->type.str_id >= 0){
                fprintf(fout, " %s[%d/%d]",
                        l->type.str,
                        l->type.line,
                        l->type.column);
            }else{
                fprintf(fout, " object");
            }
        }
        fprintf(fout, "\n");
    }
}

void pddlParseTokTypesInitFromTypedLists(pddl_parse_tok_types_t *tok_types,
                                         const pddl_parse_typed_lists_t *tl)
{
    tok_types->tok_type_size = 0;
    tok_types->tok_type_alloc = 4;
    tok_types->tok_type = ALLOC_ARR(pddl_parse_tok_type_t,
                                    tok_types->tok_type_alloc);

    for (int i = 0; i < tl->list_size; ++i)
        pddlParseTokTypesAddTypedList(tok_types, tl->list[i]);
}

void pddlParseTokTypesFree(pddl_parse_tok_types_t *tok_types)
{
    if (tok_types->tok_type != NULL)
        FREE(tok_types->tok_type);
}

static void _pddlParseTokTypesAdd(pddl_parse_tok_types_t *tok_types,
                                  const pddl_parse_token_t *tok,
                                  const pddl_parse_token_t *type,
                                  const pddl_parse_toks_t *type_either,
                                  const pddl_parse_token_t *type_either_tok)
{
    if (tok_types->tok_type_size == tok_types->tok_type_alloc){
        ASSERT(tok_types->tok_type_alloc > 0);
        tok_types->tok_type_alloc *= 2;
        tok_types->tok_type = REALLOC_ARR(tok_types->tok_type,
                                          pddl_parse_tok_type_t,
                                          tok_types->tok_type_alloc);

    }

    pddl_parse_tok_type_t *tt = tok_types->tok_type + tok_types->tok_type_size++;
    ZEROIZE(tt);
    tt->tok = *tok;
    if (type != NULL){
        tt->type = *type;

    }else if (type_either != NULL){
        tt->type_either = type_either;
        tt->type_either_tok = *type_either_tok;

    }else{
        tt->no_type = 1;
    }
}

void pddlParseTokTypesAddTypedList(pddl_parse_tok_types_t *tok_types,
                                   const pddl_parse_typed_list_t *tl)
{
    for (int i = 0; i < tl->list->tok_size; ++i){
        if (tl->type_either != NULL){
            _pddlParseTokTypesAdd(tok_types, tl->list->tok + i, NULL,
                                  tl->type_either, &tl->type_either_tok);

        }else if (tl->type.token >= 0){
            _pddlParseTokTypesAdd(tok_types, tl->list->tok + i, &tl->type,
                                  NULL, NULL);
        }else{
            _pddlParseTokTypesAdd(tok_types, tl->list->tok + i, NULL, NULL, NULL);
        }
    }
}

pddl_parse_fm_tree_t *pddlParseFmTreeNew(pddl_parse_fm_tree_kind_t kind,
                                         const pddl_parse_token_t *ref)
{
    pddl_parse_fm_tree_t *t = ZALLOC(pddl_parse_fm_tree_t);
    t->kind = kind;
    if (ref != NULL)
        t->ref_tok = *ref;
    return t;
}

void pddlParseFmTreeDel(pddl_parse_fm_tree_t *t)
{
    if (t->atom != NULL)
        pddlParseToksDel(t->atom);
    if (t->params != NULL)
        pddlParseTypedListsDel(t->params);
    for (int i = 0; i < t->child_size; ++i)
        pddlParseFmTreeDel(t->child[i]);
    if (t->child != NULL)
        FREE(t->child);
    FREE(t);
}

void pddlParseFmTreeAddChild(pddl_parse_fm_tree_t *t,
                             pddl_parse_fm_tree_t *child)
{
    if (t->child_size == t->child_alloc){
        if (t->child_alloc == 0)
            t->child_alloc = 1;
        t->child_alloc *= 2;
        t->child = REALLOC_ARR(t->child, pddl_parse_fm_tree_t *,
                               t->child_alloc);
    }
    t->child[t->child_size++] = child;
}

void pddlParseFmTreeSetRef(pddl_parse_fm_tree_t *t,
                           const pddl_parse_token_t *ref)
{
    if (ref != NULL)
        t->ref_tok = *ref;
}
