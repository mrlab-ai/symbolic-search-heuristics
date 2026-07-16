/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HFUNC_H__
#define __PDDL_HFUNC_H__

#include <pddl/list.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * HFunc - Hash Functions
 * =======================
 */

/*
 * This algorithm was created for sdbm (a public-domain reimplementation of
 * ndbm) database library. it was found to do well in scrambling bits,
 * causing better distribution of the keys and fewer splits.
 * It also happens to be a good general hashing function with good distribution.
 * The actual function is hash(i) = hash(i - 1) * 65599 + str[i]; what is
 * included below is the faster version used in gawk. [there is even a
 * faster, duff-device version]
 * The magic constant 65599 was picked out of thin air while experimenting
 * with different constants, and turns out to be a prime. This is one of
 * the algorithms used in berkeley db (see sleepycat) and elsewhere.
 */
uint32_t pddlHashSDBM(const char *str);

/**
 * CityHash 32-bit hash function.
 * Taken from https://code.google.com/p/cityhash.
 */
uint32_t pddlCityHash_32(const void *buf, size_t size);

/**
 * CityHash 64-bit hash function.
 * Taken from https://code.google.com/p/cityhash.
 */
uint64_t pddlCityHash_64(const void *buf, size_t size);

/**
 * FastHash hash function.
 * Taken from https://code.google.com/p/fast-hash.
 */
uint64_t pddlFastHash_64(const void *buf, size_t size, uint64_t seed);

/**
 * FastHash hash function.
 * Taken from https://code.google.com/p/fast-hash.
 */
uint32_t pddlFastHash_32(const void *buf, size_t size, uint32_t seed);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_HFUNC_H__ */

