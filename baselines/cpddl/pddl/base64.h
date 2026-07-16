/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_BASE64_H__
#define __PDDL_BASE64_H__

#include <pddl/err.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

unsigned char *pddlBase64Encode(const unsigned char *src, int srclen,
                                int *out_len, pddl_err_t *err);
unsigned char *pddlBase64Decode(const unsigned char *base64src, int srclen,
                                int *out_len, pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_BASE64_H__ */
