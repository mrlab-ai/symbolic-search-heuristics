/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/hfunc.h"
#include "pddl/pddl.h"
#include "pddl/obj.h"
#include "pddl/require_flags.h"
#include "internal.h"

void pddlObjFree(pddl_obj_t *obj)
{
    if (obj->name != NULL)
        FREE(obj->name);
    obj->name = NULL;
}

struct obj_key {
    int obj_id;
    const char *name;
    uint32_t hash;
    pddl_list_t htable;
};
typedef struct obj_key obj_key_t;

static pddl_htable_key_t objHash(const pddl_list_t *key, void *_)
{
    const obj_key_t *obj = pddl_container_of(key, obj_key_t, htable);
    return obj->hash;
}

static int objEq(const pddl_list_t *key1, const pddl_list_t *key2, void *_)
{
    const obj_key_t *obj1 = pddl_container_of(key1, obj_key_t, htable);
    const obj_key_t *obj2 = pddl_container_of(key2, obj_key_t, htable);
    return strcmp(obj1->name, obj2->name) == 0;
}

void pddlObjsInit(pddl_objs_t *objs)
{
    ZEROIZE(objs);
    objs->htable = pddlHTableNew(objHash, objEq, NULL);
}

void pddlObjsInitCopy(pddl_objs_t *dst, const pddl_objs_t *src)
{
    ZEROIZE(dst);

    dst->htable = pddlHTableNew(objHash, objEq, NULL);

    dst->obj_size = dst->obj_alloc = src->obj_size;
    dst->obj = ZALLOC_ARR(pddl_obj_t, src->obj_size);
    for (int i = 0; i < src->obj_size; ++i){
        dst->obj[i] = src->obj[i];
        if (dst->obj[i].name != NULL)
            dst->obj[i].name = STRDUP(src->obj[i].name);

        obj_key_t *key;
        key = ALLOC(obj_key_t);
        key->obj_id = i;
        key->name = dst->obj[i].name;
        key->hash = pddlHashSDBM(dst->obj[i].name);
        pddlListInit(&key->htable);
        pddlHTableInsert(dst->htable, &key->htable);
    }
}

void pddlObjsFree(pddl_objs_t *objs)
{
    pddl_list_t list;
    pddl_list_t *item;
    obj_key_t *key;

    for (int i = 0; i < objs->obj_size; ++i)
        pddlObjFree(objs->obj + i);
    if (objs->obj != NULL)
        FREE(objs->obj);

    pddlListInit(&list);
    if (objs->htable != NULL){
        pddlHTableGather(objs->htable, &list);
        while (!pddlListEmpty(&list)){
            item = pddlListNext(&list);
            pddlListDel(item);
            key = PDDL_LIST_ENTRY(item, obj_key_t, htable);
            FREE(key);
        }
        pddlHTableDel(objs->htable);
    }
}

static obj_key_t *findByName(const pddl_objs_t *objs, const char *name)
{
    pddl_list_t *item;
    obj_key_t *key, keyin;

    keyin.name = name;
    keyin.hash = pddlHashSDBM(name);
    item = pddlHTableFind(objs->htable, &keyin.htable);
    if (item == NULL)
        return NULL;

    key = PDDL_LIST_ENTRY(item, obj_key_t, htable);
    return key;
}

int pddlObjsGet(const pddl_objs_t *objs, const char *name)
{
    obj_key_t *key = findByName(objs, name);
    if (key == NULL)
        return -1;
    return key->obj_id;
}

pddl_obj_t *pddlObjsAdd(pddl_objs_t *objs, const char *name)
{
    pddl_obj_t *o;
    obj_key_t *key;

    if (pddlObjsGet(objs, name) >= 0)
        return NULL;

    if (objs->obj_size >= objs->obj_alloc){
        if (objs->obj_alloc == 0){
            objs->obj_alloc = 2;
        }else{
            objs->obj_alloc *= 2;
        }
        objs->obj = REALLOC_ARR(objs->obj, pddl_obj_t, objs->obj_alloc);
    }

    o = objs->obj + objs->obj_size++;
    ZEROIZE(o);
    o->name = STRDUP(name);

    key = ALLOC(obj_key_t);
    key->obj_id = objs->obj_size - 1;
    key->name = o->name;
    key->hash = pddlHashSDBM(name);
    pddlListInit(&key->htable);
    pddlHTableInsert(objs->htable, &key->htable);

    return o;
}

void pddlObjsRemap(pddl_objs_t *objs, const int *remap)
{
    int new_size = 0;
    for (int i = 0; i < objs->obj_size; ++i)
        new_size = PDDL_MAX(new_size, remap[i] + 1);

    int *isset = ZALLOC_ARR(int, new_size);
    pddl_obj_t *nobjs = ZALLOC_ARR(pddl_obj_t, new_size);
    for (int i = 0; i < objs->obj_size; ++i){
        if (remap[i] >= 0 && !isset[remap[i]]){
            nobjs[remap[i]] = objs->obj[i];
            isset[remap[i]] = 1;
            if (nobjs[remap[i]].name != NULL){
                obj_key_t *key = findByName(objs, nobjs[remap[i]].name);
                if (key != NULL)
                    key->obj_id = remap[i];
            }

        }else{
            if (objs->obj[i].name != NULL){
                obj_key_t *key = findByName(objs, objs->obj[i].name);
                if (key != NULL){
                    pddlHTableErase(objs->htable, &key->htable);
                    FREE(key);
                }
            }
            pddlObjFree(objs->obj + i);
        }
    }

    FREE(objs->obj);
    objs->obj = nobjs;
    FREE(isset);
    objs->obj_size = new_size;
}

void pddlObjsRemapTypes(pddl_objs_t *objs, const int *remap_type)
{
    for (int i = 0; i < objs->obj_size; ++i)
        objs->obj[i].type = remap_type[objs->obj[i].type];
}

void pddlObjsPropagateToTypes(const pddl_objs_t *objs, pddl_types_t *types)
{
    for (int obji = 0; obji < objs->obj_size; ++obji)
        pddlTypesAddObj(types, obji, objs->obj[obji].type);
    pddlTypesBuildObjTypeMap(types, objs->obj_size);
}

void pddlObjsPrint(const pddl_objs_t *objs, FILE *fout)
{
    // TODO: Do not print is-private, owner, is-agent. This will require
    // fixing tests.
    // TODO: Rename the function to PrintDebug()
    fprintf(fout, "Obj[%d]:\n", objs->obj_size);
    for (int i = 0; i < objs->obj_size; ++i){
        fprintf(fout, "    [%d]: %s, type: %d, is-constant: %d,"
                " is-private: 0, owner: -1, is-agent: 0\n", i,
                objs->obj[i].name, objs->obj[i].type,
                objs->obj[i].is_constant);
    }
}

void pddlObjsPrintPDDLConstants(const pddl_objs_t *objs,
                                const pddl_types_t *ts,
                                const pddl_bool_t *only_selected,
                                FILE *fout)
{
    fprintf(fout, "(:constants\n");
    for (int i = 0; i < objs->obj_size; ++i){
        if (only_selected != NULL && !only_selected[i])
            continue;
        const pddl_obj_t *o = objs->obj + i;
        fprintf(fout, "    %s - %s\n", o->name, ts->type[o->type].name);
    }
    fprintf(fout, ")\n");
}

void pddlObjsPrintPDDLObjects(const pddl_objs_t *objs,
                              const pddl_types_t *ts,
                              const pddl_bool_t *only_selected,
                              FILE *fout)
{
    fprintf(fout, "(:objects\n");
    for (int i = 0; i < objs->obj_size; ++i){
        if (only_selected != NULL && !only_selected[i])
            continue;
        const pddl_obj_t *o = objs->obj + i;
        fprintf(fout, "    %s - %s\n", o->name, ts->type[o->type].name);
    }
    fprintf(fout, ")\n");
}
