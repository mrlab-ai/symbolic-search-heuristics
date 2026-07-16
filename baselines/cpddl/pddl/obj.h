/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_OBJ_H__
#define __PDDL_OBJ_H__

#include <pddl/common.h>
#include <pddl/htable.h>
#include <pddl/type.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_obj {
    /** Name of the object */
    char *name;
    /** Type ID of the object */
    int type;
    /** True if it is constant (defined in domain) */
    pddl_bool_t is_constant;
};
typedef struct pddl_obj pddl_obj_t;

struct pddl_objs {
    pddl_obj_t *obj;
    int obj_size;
    int obj_alloc;
    pddl_htable_t *htable;
};
typedef struct pddl_objs pddl_objs_t;

/**
 * Initialize empty set of objects.
 */
void pddlObjsInit(pddl_objs_t *objs);

/**
 * Initialize dst as a deep copy of src.
 */
void pddlObjsInitCopy(pddl_objs_t *dst, const pddl_objs_t *src);

/**
 * Frees allocated resources.
 */
void pddlObjsFree(pddl_objs_t *objs);

/**
 * Returns ID of the object of the specified name.
 */
int pddlObjsGet(const pddl_objs_t *objs, const char *name);

/**
 * Adds a new obj at the end of the array.
 */
pddl_obj_t *pddlObjsAdd(pddl_objs_t *objs, const char *name);

/**
 * Remap object IDs and remove those where remap[id] == -1
 */
void pddlObjsRemap(pddl_objs_t *objs, const int *remap);

/**
 * Remap type IDs assuming all object types are preserved.
 */
void pddlObjsRemapTypes(pddl_objs_t *objs, const int *remap_type);

/**
 * Propagate/relate all objects to their respective types.
 */
void pddlObjsPropagateToTypes(const pddl_objs_t *objs, pddl_types_t *types);

/**
 * Print formated objects.
 */
void pddlObjsPrint(const pddl_objs_t *objs, FILE *fout);

/**
 * Print objects in PDDL (:constants ) format.
 */
void pddlObjsPrintPDDLConstants(const pddl_objs_t *objs,
                                const pddl_types_t *ts,
                                const pddl_bool_t *only_selected,
                                FILE *fout);

void pddlObjsPrintPDDLObjects(const pddl_objs_t *objs,
                              const pddl_types_t *ts,
                              const pddl_bool_t *only_selected,
                              FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_OBJ_H__ */
