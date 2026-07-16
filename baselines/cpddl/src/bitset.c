/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/bitset.h"

void pddlBitsetInit(pddl_bitset_t *b, int bitsize)
{
    ZEROIZE(b);

    b->bitsize = bitsize;
    b->wordsize = bitsize / PDDL_BITSET_WORD_BITSIZE;
    if (bitsize % PDDL_BITSET_WORD_BITSIZE != 0)
        b->wordsize += 1;

    int last_word_bitsize = bitsize % PDDL_BITSET_WORD_BITSIZE;
    if (last_word_bitsize > 0){
        b->last_word_mask = 1;
        for (int i = 1; i < last_word_bitsize; ++i)
            b->last_word_mask = (b->last_word_mask << (pddl_bitset_word_t)1) | (pddl_bitset_word_t)1;
    }else{
        b->last_word_mask = ~((pddl_bitset_word_t)0);
    }

    b->bitset = ZALLOC_ARR(pddl_bitset_word_t, b->wordsize);
}

void pddlBitsetFree(pddl_bitset_t *b)
{
    if (b->bitset != NULL)
        FREE(b->bitset);
}
