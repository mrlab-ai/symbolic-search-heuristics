/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRSTREAM_H__
#define __PDDL_STRSTREAM_H__

#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

FILE * pddl_strstream(char **bufp, size_t *sizep);
FILE *pddl_staticstrstream(char *buf, size_t size);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_STRSTREAM_H__ */
