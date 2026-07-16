/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ASNETS_CONVERT_FROM_SQL_H__
#define __PDDL_ASNETS_CONVERT_FROM_SQL_H__

#include <pddl/err.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * This function converts the old models stored as an sqlite database to
 * the new text-based format.
 */
int pddlASNetsConvertFromSql(const char *input_model_sql,
                             const char *output_model,
                             pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_ASNETS_CONVERT_FROM_SQL_H__ */
