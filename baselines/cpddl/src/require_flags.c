/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/pddl_struct.h"
#include "pddl/require_flags.h"

unsigned pddlRequireFlagsToMask(const pddl_require_flags_t *flags)
{
    unsigned mask = 0u;
    unsigned flag = 1u;
    if (flags->strips)
        mask |= flag;
    flag <<= 1;
    if (flags->typing)
        mask |= flag;
    flag <<= 1;
    if (flags->negative_pre)
        mask |= flag;
    flag <<= 1;
    if (flags->disjunctive_pre)
        mask |= flag;
    flag <<= 1;
    if (flags->equality)
        mask |= flag;
    flag <<= 1;
    if (flags->existential_pre)
        mask |= flag;
    flag <<= 1;
    if (flags->universal_pre)
        mask |= flag;
    flag <<= 1;
    if (flags->conditional_eff)
        mask |= flag;
    flag <<= 1;
    if (flags->numeric_fluent)
        mask |= flag;
    flag <<= 1;
    if (flags->object_fluent)
        mask |= flag;
    flag <<= 1;
    if (flags->durative_action)
        mask |= flag;
    flag <<= 1;
    if (flags->duration_inequality)
        mask |= flag;
    flag <<= 1;
    if (flags->continuous_eff)
        mask |= flag;
    flag <<= 1;
    if (flags->derived_pred)
        mask |= flag;
    flag <<= 1;
    if (flags->timed_initial_literal)
        mask |= flag;
    flag <<= 1;
    if (flags->preference)
        mask |= flag;
    flag <<= 1;
    if (flags->constraint)
        mask |= flag;
    flag <<= 1;
    if (flags->action_cost)
        mask |= flag;
    flag <<= 1;
    if (flags->multi_agent)
        mask |= flag;
    flag <<= 1;
    if (flags->unfactored_privacy)
        mask |= flag;
    flag <<= 1;
    if (flags->factored_privacy)
        mask |= flag;

    return mask;
}

void pddlRequireFlagsSetADL(pddl_require_flags_t *flags)
{
    flags->strips = 1;
    flags->typing = 1;
    flags->negative_pre = 1;
    flags->disjunctive_pre = 1;
    flags->equality = 1;
    flags->existential_pre = 1;
    flags->universal_pre = 1;
    flags->conditional_eff = 1;
}

void pddlRequireFlagsPrintPDDL(const pddl_require_flags_t *flags, FILE *fout)
{
    fprintf(fout, "(:requirements\n");
    if (flags->strips)
        fprintf(fout, "    :strips\n");
    if (flags->typing)
        fprintf(fout, "    :typing\n");
    if (flags->negative_pre)
        fprintf(fout, "    :negative-preconditions\n");
    if (flags->disjunctive_pre)
        fprintf(fout, "    :disjunctive-preconditions\n");
    if (flags->equality)
        fprintf(fout, "    :equality\n");
    if (flags->existential_pre)
        fprintf(fout, "    :existential-preconditions\n");
    if (flags->universal_pre)
        fprintf(fout, "    :universal-preconditions\n");
    if (flags->conditional_eff)
        fprintf(fout, "    :conditional-effects\n");
    if (flags->numeric_fluent)
        fprintf(fout, "    :numeric-fluents\n");
    if (flags->object_fluent)
        fprintf(fout, "    :object-fluents\n");
    if (flags->durative_action)
        fprintf(fout, "    :durative-actions\n");
    if (flags->duration_inequality)
        fprintf(fout, "    :duration-inequalities\n");
    if (flags->continuous_eff)
        fprintf(fout, "    :continuous-effects\n");
    if (flags->derived_pred)
        fprintf(fout, "    :derived-predicates\n");
    if (flags->timed_initial_literal)
        fprintf(fout, "    :timed-initial-literals\n");
    if (flags->preference)
        fprintf(fout, "    :preferences\n");
    if (flags->constraint)
        fprintf(fout, "    :constraints\n");
    if (flags->action_cost)
        fprintf(fout, "    :action-costs\n");
    if (flags->multi_agent)
        fprintf(fout, "    :multi-agent\n");
    if (flags->unfactored_privacy)
        fprintf(fout, "    :unfactored-privacy\n");
    if (flags->factored_privacy)
        fprintf(fout, "    :factored-privacy\n");
    fprintf(fout, ")\n");
}

struct infer {
    pddl_require_flags_t *flags;
    const pddl_t *pddl;
    int total_cost_id;
};

static int inferPre(pddl_fm_t *fm, void *_d)
{
    struct infer *d = _d;
    if (pddlFmIsAtom(fm)){
        const pddl_fm_atom_t *a = pddlFmToAtom(fm);
        if (a->neg)
            d->flags->negative_pre = 1;

        if (a->pred == d->pddl->pred.eq_pred)
            d->flags->equality = 1;

    }else if (pddlFmIsOr(fm)){
        d->flags->disjunctive_pre = 1;

    }else if (pddlFmIsNumCmp(fm)){
        d->flags->numeric_fluent = 1;
        return -1;

    }else if (pddlFmIsForAll(fm)){
        d->flags->universal_pre = 1;

    }else if (pddlFmIsExist(fm)){
        d->flags->existential_pre = 1;

    }else if (pddlFmIsNumExpFluent(fm)){
        d->flags->numeric_fluent = 1;
    }
    return 0;
}

static int inferEff(pddl_fm_t *fm, void *_d)
{
    struct infer *d = _d;
    if (pddlFmIsWhen(fm)){
        pddl_fm_when_t *w = pddlFmToWhen(fm);
        d->flags->conditional_eff = 1;

        if (w->pre != NULL)
            pddlFmTraverseAll(w->pre, inferPre, NULL, _d);
        if (w->eff != NULL)
            pddlFmTraverseAll(w->eff, inferEff, NULL, _d);

        return -1;

    }else if (pddlFmIsNumOp(fm)){
        const pddl_fm_atom_t *a = NULL;
        int val = 0;
        if (d->total_cost_id >= 0
                && pddlFmNumOpCheckSimpleIncreaseTotalCost(
                            fm, d->total_cost_id, &a, &val) == 0){
            d->flags->action_cost = 1;

        }else{
            d->flags->numeric_fluent = 1;
        }
        return -1;

    }else if (pddlFmIsNumExpFluent(fm)){
        pddl_fm_num_exp_t *e = pddlFmToNumExp(fm);
        ASSERT(e->e.fluent != NULL);
        if (e->e.fluent->pred != d->total_cost_id){
            d->flags->numeric_fluent = 1;
        }else{
            d->flags->action_cost = 1;
        }

    }else if (pddlFmIsNumExp(fm)){ // && !pddlFmIsNumExpFluent(fm)
        d->flags->numeric_fluent = 1;
    }

    return 0;
}

void pddlRequireFlagsInfer(pddl_require_flags_t *flags, const pddl_t *pddl)
{
    bzero(flags, sizeof(*flags));

    if (pddl->type.type_size > 1)
        flags->typing = 1;

    if (pddl->action.action_size > 0)
        flags->strips = 1;

    struct infer d;
    d.flags = flags;
    d.pddl = pddl;
    d.total_cost_id = pddlPredsGet(&pddl->func, "total-cost");
    if (pddl->goal != NULL)
        pddlFmTraverseAll(pddl->goal, inferPre, NULL, (void *)&d);

    if (pddl->minimize != NULL)
        pddlFmTraverseAll(&pddl->minimize->fm, inferEff, NULL, (void *)&d);

    for (int ai = 0; ai < pddl->action.action_size; ++ai){
        const pddl_action_t *a = pddl->action.action + ai;
        if (a->pre != NULL)
            pddlFmTraverseAll(a->pre, inferPre, NULL, (void *)&d);
        if (a->eff != NULL)
            pddlFmTraverseAll(a->eff, inferEff, NULL, (void *)&d);
    }

    if (flags->numeric_fluent)
        flags->action_cost = 0;
}
