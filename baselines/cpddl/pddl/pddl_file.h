/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FILE_H__
#define __PDDL_FILE_H__

#include <pddl/err.h>
#include <pddl/config.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_FILE_MAX_PATH_LEN 4096
#define PDDL_FILE_MAX_NAME_LEN 128

struct pddl_files {
    char domain_pddl[PDDL_FILE_MAX_PATH_LEN];
    char problem_pddl[PDDL_FILE_MAX_PATH_LEN];
};
typedef struct pddl_files pddl_files_t;

int pddlFiles1(pddl_files_t *files, const char *s, pddl_err_t *err);
int pddlFiles(pddl_files_t *files, const char *s1, const char *s2,
              pddl_err_t *err);
int pddlFilesFindOptimalCost(pddl_files_t *files, pddl_err_t *err);

pddl_bool_t pddlIsFile(const char *);
pddl_bool_t pddlIsDir(const char *);
char *pddlDirname(const char *fn);
char **pddlListDir(const char *dname, int *list_size, pddl_err_t *err);
char **pddlListDirPDDLFiles(const char *dname, int *list_size, pddl_err_t *err);


struct pddl_bench_task {
    pddl_files_t pddl_files;
    int optimal_cost;
    char bench_name[PDDL_FILE_MAX_NAME_LEN];
    char domain_name[PDDL_FILE_MAX_NAME_LEN];
    char problem_name[PDDL_FILE_MAX_NAME_LEN];
};
typedef struct pddl_bench_task pddl_bench_task_t;

struct pddl_bench {
    pddl_bench_task_t *task;
    int task_size;
    int task_alloc;
};
typedef struct pddl_bench pddl_bench_t;

void pddlBenchInit(pddl_bench_t *bench);
void pddlBenchFree(pddl_bench_t *bench);
int pddlBenchLoadDir(pddl_bench_t *bench, const char *dirpath);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FILE_H__ */
