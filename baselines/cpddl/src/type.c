/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pddl.h"
#include "pddl/type.h"
#include "pddl/obj.h"
#include "internal.h"

static const char *object_name = "object";

static void pddlTypeInit(pddl_type_t *t)
{
    ZEROIZE(t);
}

static void pddlTypeFree(pddl_type_t *t)
{
    if (t->name != NULL)
        FREE(t->name);
    pddlISetFree(&t->child);
    pddlISetFree(&t->either);
    pddlISetFree(&t->obj);
    pddlISetFree(&t->parent_either);
}

static void pddlTypeInitCopy(pddl_type_t *dst, const pddl_type_t *src)
{
    pddlTypeInit(dst);
    if (src->name != NULL)
        dst->name = STRDUP(src->name);
    dst->parent = src->parent;
    pddlISetUnion(&dst->child, &src->child);
    pddlISetUnion(&dst->either, &src->either);
    pddlISetUnion(&dst->obj, &src->obj);
    pddlISetUnion(&dst->parent_either, &src->parent_either);
}

int pddlTypesGet(const pddl_types_t *t, const char *name)
{
    for (int i = 0; i < t->type_size; ++i){
        if (strcmp(t->type[i].name, name) == 0)
            return i;
    }

    return -1;
}


int pddlTypesAdd(pddl_types_t *t, const char *name, int parent)
{
    int id;

    if ((id = pddlTypesGet(t, name)) != -1)
        return id;

    if (t->type_size >= t->type_alloc){
        if (t->type_alloc == 0)
            t->type_alloc = 2;
        t->type_alloc *= 2;
        t->type = REALLOC_ARR(t->type, pddl_type_t, t->type_alloc);
    }

    id = t->type_size++;
    pddl_type_t *type = t->type + id;
    pddlTypeInit(type);
    if (name != NULL)
        type->name = STRDUP(name);
    type->parent = parent;
    if (parent >= 0)
        pddlISetAdd(&t->type[parent].child, id);
    return id;
}

int pddlTypesAddEither(pddl_types_t *ts, const pddl_iset_t *either)
{
    int tid;

    // Try to find already created (either ...) type
    for (int i = 0; i < ts->type_size; ++i){
        if (pddlTypesIsEither(ts, i)
                && pddlISetEq(&ts->type[i].either, either)){
            return i;
        }
    }

    // Construct a name of the (either ...) type
    char *name, *cur;
    int eid;
    int slen = 0;
    PDDL_ISET_FOR_EACH(either, eid)
        slen += 1 + strlen(ts->type[eid].name);
    slen += 2 + 6 + 1;
    name = cur = ALLOC_ARR(char, slen);
    cur += sprintf(cur, "(either");
    PDDL_ISET_FOR_EACH(either, eid)
        cur += sprintf(cur, " %s", ts->type[eid].name);
    sprintf(cur, ")");

    tid = pddlTypesAdd(ts, name, -1);
    if (name != NULL)
        FREE(name);
    pddl_type_t *type = ts->type + tid;
    pddlISetUnion(&type->child, either);
    pddlISetUnion(&type->either, either);

    PDDL_ISET_FOR_EACH(either, eid){
        // Set reverse reference from type to its "either" parent.
        pddlISetAdd(&ts->type[eid].parent_either, tid);

        // Merge obj IDs from all simple types from which this (either ...)
        // type consists of.
        const pddl_type_t *et = ts->type + eid;
        int obj;
        PDDL_ISET_FOR_EACH(&et->obj, obj)
            pddlTypesAddObj(ts, obj, tid);
    }

    return tid;
}

void pddlTypesInit(pddl_types_t *types)
{
    ZEROIZE(types);
    // Create a default "object" type
    pddlTypesAdd(types, object_name, -1);
}

void pddlTypesInitCopy(pddl_types_t *dst, const pddl_types_t *src)
{
    ZEROIZE(dst);
    dst->type_size = src->type_size;
    dst->type_alloc = src->type_alloc;
    dst->type = ZALLOC_ARR(pddl_type_t, dst->type_alloc);
    for (int i = 0; i < dst->type_size; ++i)
        pddlTypeInitCopy(dst->type + i, src->type + i);

    if (src->obj_type_map != NULL){
        dst->obj_type_map_memsize = src->obj_type_map_memsize;
        dst->obj_type_map = ALLOC_ARR(char, dst->obj_type_map_memsize);
        memcpy(dst->obj_type_map, src->obj_type_map, dst->obj_type_map_memsize);
    }
}

void pddlTypesFree(pddl_types_t *types)
{
    for (int i = 0; i < types->type_size; ++i)
        pddlTypeFree(types->type + i);
    if (types->type != NULL)
        FREE(types->type);

    if (types->obj_type_map != NULL)
        FREE(types->obj_type_map);
}

void pddlTypesPrint(const pddl_types_t *t, FILE *fout)
{
    fprintf(fout, "Type[%d]:\n", t->type_size);
    for (int i = 0; i < t->type_size; ++i){
        fprintf(fout, "    [%d]: %s, parent: %d", i,
                t->type[i].name, t->type[i].parent);
        fprintf(fout, "\n");
    }

    fprintf(fout, "Obj-by-Type:\n");
    for (int i = 0; i < t->type_size; ++i){
        fprintf(fout, "    [%d]:", i);
        int o;
        PDDL_ISET_FOR_EACH(&t->type[i].obj, o)
            fprintf(fout, " %d", (int)o);
        fprintf(fout, "\n");
    }
}

pddl_bool_t pddlTypesIsEither(const pddl_types_t *ts, int tid)
{
    return pddlISetSize(&ts->type[tid].either) > 0;
}

void pddlTypesAddObj(pddl_types_t *ts, int obj_id, int type_id)
{
    pddl_type_t *t = ts->type + type_id;
    pddlISetAdd(&t->obj, obj_id);
    if (t->parent != -1)
        pddlTypesAddObj(ts, obj_id, t->parent);

    int eid;
    PDDL_ISET_FOR_EACH(&t->parent_either, eid)
        pddlTypesAddObj(ts, obj_id, eid);
}

void pddlTypesBuildObjTypeMap(pddl_types_t *ts, int obj_size)
{
    if (ts->obj_type_map != NULL)
        FREE(ts->obj_type_map);
    ts->obj_type_map = ZALLOC_ARR(char, obj_size * ts->type_size);
    ts->obj_type_map_memsize = obj_size * ts->type_size;
    for (int type_id = 0; type_id < ts->type_size; ++type_id){
        const pddl_iset_t *tobj = &ts->type[type_id].obj;
        int obj;
        PDDL_ISET_FOR_EACH(tobj, obj){
            ts->obj_type_map[obj * ts->type_size + type_id] = 1;
        }
    }
}

const int *pddlTypesObjsByType(const pddl_types_t *ts, int type_id,
                                         int *size)
{
    if (size != NULL)
        *size = ts->type[type_id].obj.size;
    return ts->type[type_id].obj.s;
}

int pddlTypeNumObjs(const pddl_types_t *ts, int type_id)
{
    return pddlISetSize(&ts->type[type_id].obj);
}

int pddlTypeGetObj(const pddl_types_t *ts, int type_id, int idx)
{
    return pddlISetGet(&ts->type[type_id].obj, idx);
}

pddl_bool_t pddlTypesObjHasType(const pddl_types_t *ts, int type, int obj)
{
    if (ts->obj_type_map != NULL){
        return ts->obj_type_map[obj * ts->type_size + type];

    }else{
        const int *objs;
        int size;

        objs = pddlTypesObjsByType(ts, type, &size);
        for (int i = 0; i < size; ++i){
            if (objs[i] == obj)
                return pddl_true;
        }
        return pddl_false;
    }
}

pddl_bool_t pddlTypesIsParent(const pddl_types_t *ts, int child, int parent)
{
    const pddl_type_t *tparent = ts->type + parent;
    int eid;

    for (int cur_type = child; cur_type >= 0;){
        if (cur_type == parent)
            return pddl_true;
        PDDL_ISET_FOR_EACH(&tparent->either, eid){
            if (cur_type == eid)
                return pddl_true;
        }
        cur_type = ts->type[cur_type].parent;
    }

    return pddl_false;
}

pddl_bool_t pddlTypesAreDisjunct(const pddl_types_t *ts, int t1, int t2)
{
    return !pddlTypesIsParent(ts, t1, t2) && !pddlTypesIsParent(ts, t2, t1);
}

pddl_bool_t pddlTypesAreDisjoint(const pddl_types_t *ts, int t1, int t2)
{
    return pddlTypesAreDisjunct(ts, t1, t2);
}

pddl_bool_t pddlTypesIsSubset(const pddl_types_t *ts, int t1id, int t2id)
{
    const pddl_type_t *t1 = ts->type + t1id;
    const pddl_type_t *t2 = ts->type + t2id;
    return pddlISetIsSubset(&t1->obj, &t2->obj);
}

pddl_bool_t pddlTypesIsMinimal(const pddl_types_t *ts, int type)
{
    return pddlISetSize(&ts->type[type].child) == 0;
}

pddl_bool_t pddlTypesHasStrictPartitioning(const pddl_types_t *ts,
                                           const pddl_objs_t *obj)
{
    int is_strict = 0;

    for (int t1 = 0; t1 < ts->type_size; ++t1){
        if (pddlISetSize(&ts->type[t1].either) > 0)
            return pddl_false;
        for (int t2 = 0; t2 < ts->type_size; ++t2){
            if (t1 == t2)
                continue;
            if (!pddlTypesAreDisjunct(ts, t1, t2)
                    && !pddlTypesIsSubset(ts, t1, t2)
                    && !pddlTypesIsSubset(ts, t2, t1))
                return pddl_false;
        }
    }

    PDDL_ISET(all);
    for (int ti = 0; ti < ts->type_size; ++ti){
        if (pddlISetSize(&ts->type[ti].child) == 0
                && pddlISetSize(&ts->type[ti].either) == 0){
            pddlISetUnion(&all, &ts->type[ti].obj);
        }
    }
    if (pddlISetSize(&all) == obj->obj_size)
        is_strict = 1;
    pddlISetFree(&all);
    return is_strict;
}

void pddlTypesRemapObjs(pddl_types_t *ts,
                        const int *remap)
{
    int num_objs = 0;
    for (int ti = 0; ti < ts->type_size; ++ti){
        pddl_type_t *t = ts->type + ti;
        PDDL_ISET(newset);
        int obj;
        PDDL_ISET_FOR_EACH(&t->obj, obj){
            if (remap[obj] >= 0){
                pddlISetAdd(&newset, remap[obj]);
                num_objs = PDDL_MAX(num_objs, remap[obj] + 1);
            }
        }

        pddlISetFree(&t->obj);
        t->obj = newset;
    }

    if (ts->obj_type_map != NULL)
        pddlTypesBuildObjTypeMap(ts, num_objs);
}

int pddlTypesComplement(const pddl_types_t *ts, int t, int p)
{
    int t_size = pddlTypeNumObjs(ts, t);
    int p_size = pddlTypeNumObjs(ts, p);

    for (int c = 0; c < ts->type_size; ++c){
        if (pddlTypesAreDisjunct(ts, t, c)
                && pddlTypesIsSubset(ts, c, p)
                && pddlTypeNumObjs(ts, c) == p_size - t_size)
            return c;
    }
    return -1;
}

void pddlTypesRemoveEmpty(pddl_types_t *ts, int obj_size, int *type_remap)
{
    PDDL_ISET(rm);
    int type_size = 1;
    type_remap[0] = 0;
    for (int t = 1; t < ts->type_size; ++t){
        if (pddlTypeNumObjs(ts, t) == 0){
            type_remap[t] = -1;
            pddlISetAdd(&rm, t);
        }else{
            type_remap[t] = type_size++;
        }
    }
    if (type_size == ts->type_size)
        return;

    for (int t = 0; t < ts->type_size; ++t){
        pddl_type_t *type = ts->type + t;
        if (type_remap[t] >= 0){
            if (type->parent >= 0)
                type->parent = type_remap[type->parent];
            pddlISetMinus(&type->child, &rm);
            pddlISetRemap(&type->child, type_remap);
            pddlISetMinus(&type->either, &rm);
            pddlISetRemap(&type->either, type_remap);
            ts->type[type_remap[t]] = *type;
        }else{
            pddlTypeFree(type);
        }
    }
    pddlISetFree(&rm);
    ts->type_size = type_size;

    if (ts->obj_type_map != NULL)
        pddlTypesBuildObjTypeMap(ts, obj_size);
}

void pddlTypesPrintPDDL(const pddl_types_t *ts, FILE *fout)
{
    int q[ts->type_size];
    int qi = 0, qsize = 0;

    fprintf(fout, "(:types\n");
    for (int i = 0; i < ts->type_size; ++i){
        if (ts->type[i].parent == 0)
            q[qsize++] = i;
    }

    for (qi = 0; qi < qsize; ++qi){
        fprintf(fout, "    %s - %s\n",
                ts->type[q[qi]].name,
                ts->type[ts->type[q[qi]].parent].name);
        for (int i = 0; i < ts->type_size; ++i){
            if (ts->type[i].parent == q[qi] && !pddlTypesIsEither(ts, i))
                q[qsize++] = i;
        }
    }

    fprintf(fout, ")\n");
}
