/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/asnets_dynet.h"
#include "pddl/libs_info.h"

#ifndef PDDL_DYNET
# error "asnets_dynet.cpp requires DyNet library!"
#endif /* PDDL_DYNET */

#include <dynet/dynet.h>
#include <dynet/expr.h>
#include <dynet/training.h>
#include <dynet/param-init.h>

extern "C" const char * const pddl_dynet_version = "not exported";

#define DYNET_PANIC_EXCEPTION(e) \
    PANIC("Something went wrong (probably) in DyNet: %s" \
          " (Inf/NaN errors can be caused by having too many layers)", \
          (e).what())

static const float SMALL_CONST = 1e-6f;
static const float MIN_ACTIVATION_VALUE = -1.f;


static dynet::Expression poolMax(const std::vector<dynet::Expression> &in)
{
    if (in.size() == 1)
        return in[0];

    dynet::Expression mat = dynet::concatenate(in, 1);
    return dynet::max_dim(mat, 1);
}

static dynet::Expression maskedSoftmax(dynet::ComputationGraph &cg,
                                       const dynet::Expression &in,
                                       const dynet::Expression &mask)
{
    // Subtract maximum for numerical stability
    dynet::Expression sm = in - dynet::max_dim(in);

    // Compute exponentials
    sm = dynet::exp(sm);

    // Multiply by the mask
    sm = dynet::cmult(sm, mask);

    // Compute sum and clip it so that we don't divide by zero
    dynet::Dim min_sum_dim({1}, sm.dim().batch_elems());
    dynet::Expression min_sum = dynet::constant(cg, min_sum_dim, SMALL_CONST);
    dynet::Expression sum = dynet::max(dynet::sum_rows(sm), min_sum);

    // Normalize each element
    sm = dynet::cdiv(sm, sum);

    return sm;
}

static dynet::Expression crossEntropyLoss(dynet::ComputationGraph &cg,
                                          dynet::Expression output,
                                          dynet::Expression labels)
{
    dynet::Expression o1 = 1 - output;
    dynet::Expression o2 = output;

    // Avoid log(0)
    dynet::Expression small_const = dynet::constant(cg, o1.dim(), SMALL_CONST);
    o1 = dynet::max(o1, small_const);
    o2 = dynet::max(o2, small_const);

    // (1 - y) * log (1 - \pi)
    dynet::Expression e = dynet::cmult(1 - labels, dynet::log(o1));
    // y * log(\pi)
    e = e + dynet::cmult(labels, dynet::log(o2));

    e = dynet::sum_elems(e);
    e = dynet::sum_batches(e);
    e = -e;
    return e;
}


struct ActionModule {
    int layer;
    bool is_output;
    dynet::Parameter W;
    dynet::Parameter bias;

    ActionModule(const ActionModule&) = delete;

    ActionModule(int hidden_dimension,
                 int num_related_propositions,
                 int layer,
                 bool use_lmc,
                 bool use_op_history,
                 bool is_output,
                 dynet::ParameterCollection &model)
        : layer(layer), is_output(is_output)
    {
        int input_vec_size = 0;
        int output_dim = 0;

        if (layer == 0){
            // input state
            input_vec_size = num_related_propositions;
            // goal specification
            input_vec_size += num_related_propositions;
            // applicability of the action
            input_vec_size += 1;
            // three flags for landmarks
            if (use_lmc)
                input_vec_size += 3;
            if (use_op_history)
                input_vec_size += 1;

        }else{
            // Related propositions
            input_vec_size = num_related_propositions * hidden_dimension;
            // Skip connection
            input_vec_size += hidden_dimension;
        }

        if (is_output){
            output_dim = 1;
        }else{
            output_dim = hidden_dimension;
        }

        std::vector<long> dim_W(2);
        dim_W[0] = output_dim;
        dim_W[1] = input_vec_size;
        W = model.add_parameters(dynet::Dim(dim_W), dynet::ParameterInitNormal());

        std::vector<long> dim_bias(1);
        dim_bias[0] = output_dim;
        bias = model.add_parameters(dynet::Dim(dim_bias), dynet::ParameterInitNormal());
    }

    dynet::Expression expr(dynet::ComputationGraph &cg,
                           const std::vector<dynet::Expression> &input) const
    {
        dynet::Expression w = dynet::parameter(cg, W);
        dynet::Expression b = dynet::parameter(cg, bias);
        dynet::Expression u = dynet::concatenate(input);
        dynet::Expression e = (w * u) + b;
        if (is_output)
            return e;
        return dynet::elu(e);
    }

    dynet::Expression exprInput(dynet::ComputationGraph &cg,
                                const std::vector<dynet::Expression> &input_state,
                                const std::vector<dynet::Expression> &input_goal,
                                const dynet::Expression &input_applicable,
                                const std::vector<dynet::Expression> &input_ldms,
                                const std::vector<dynet::Expression> &input_op_history) const
    {
        ASSERT(layer == 0);
        std::vector<dynet::Expression> input;
        input.insert(input.end(), input_state.begin(), input_state.end());
        input.insert(input.end(), input_goal.begin(), input_goal.end());
        input.push_back(input_applicable);
        input.insert(input.end(), input_ldms.begin(), input_ldms.end());
        input.insert(input.end(), input_op_history.begin(), input_op_history.end());
        return expr(cg, input);
    }
};

struct PropositionModule {
    dynet::Parameter W;
    dynet::Parameter bias;

    PropositionModule(const PropositionModule&) = delete;

    PropositionModule(int hidden_dimension,
                      int num_related_actions,
                      int layer,
                      dynet::ParameterCollection &model)
    {
        // Related actions
        int input_vec_size = num_related_actions * hidden_dimension;
        if (layer > 0){
            // Skip connection
            input_vec_size += hidden_dimension;
        }

        std::vector<long> dim_W(2);
        dim_W[0] = hidden_dimension;
        dim_W[1] = input_vec_size;
        W = model.add_parameters(dynet::Dim(dim_W), dynet::ParameterInitNormal());

        std::vector<long> dim_bias(1);
        dim_bias[0] = hidden_dimension;
        bias = model.add_parameters(dynet::Dim(dim_bias), dynet::ParameterInitNormal());
    }

    dynet::Expression expr(dynet::ComputationGraph &cg,
                           const std::vector<std::vector<dynet::Expression>> &input) const 
    {
        std::vector<dynet::Expression> pooled_input(input.size());
        for (size_t i = 0; i < input.size(); ++i)
            pooled_input[i] = poolMax(input[i]);

        dynet::Expression w = dynet::parameter(cg, W);
        dynet::Expression b = dynet::parameter(cg, bias);
        dynet::Expression u = dynet::concatenate(pooled_input);
        return dynet::elu((w * u) + b);
    }
};

struct ModelParameters {
    int num_layers;
    int hidden_dim;
    std::vector<std::vector<ActionModule *>> action;
    std::vector<std::vector<PropositionModule *>> prop;
    dynet::ParameterCollection model;

    ModelParameters(const ModelParameters &) = delete;

    ModelParameters(int hidden_dimension,
                    int num_layers,
                    bool use_lmc,
                    bool use_op_history,
                    const pddl_asnets_lifted_task_t *task)
        : num_layers(num_layers),
          hidden_dim(hidden_dimension)
    {
        action.resize(num_layers + 1);
        prop.resize(num_layers);

        for (int layer = 0; layer < num_layers; ++layer){
            for (int aid = 0; aid < task->action_size; ++aid){
                ActionModule *am;
                am = new ActionModule(hidden_dimension,
                                      task->action[aid].related_atom_size,
                                      layer, use_lmc, use_op_history, false,
                                      model);
                action[layer].push_back(am);
            }

            for (int pid = 0; pid < task->pred_size; ++pid){
                ASSERT(pid != task->pddl.pred.eq_pred
                        || task->pred[pid].related_action_size == 0);
                PropositionModule *pm;
                pm = new PropositionModule(hidden_dimension,
                                           task->pred[pid].related_action_size,
                                           layer, model);
                prop[layer].push_back(pm);
            }
        }

        for (int aid = 0; aid < task->action_size; ++aid){
            ActionModule *am;
            am = new ActionModule(hidden_dimension,
                                  task->action[aid].related_atom_size,
                                  num_layers, use_lmc, use_op_history, true,
                                  model);
            action[num_layers].push_back(am);
        }

        ASSERT(num_layers == (int)action.size() - 1);
        ASSERT(num_layers == (int)prop.size());
    }

    ~ModelParameters()
    {
        for (size_t i = 0; i < action.size(); ++i){
            for (size_t j = 0; j < action[i].size(); ++j)
                delete action[i][j];
        }
        for (size_t i = 0; i < prop.size(); ++i){
            for (size_t j = 0; j < prop[i].size(); ++j)
                delete prop[i][j];
        }
    }
};

class MissingInput {
    dynet::Expression input;
    bool created;
    int dimension;

  public:
    MissingInput(int dimension)
        : created(false), dimension(dimension)
    {
    }

    dynet::Expression &get(dynet::ComputationGraph &cg)
    {
        if (!created){
            std::vector<long> d(1, dimension);
            dynet::Dim dim(d);
            // Input is set to the minimum value of the activation function.
            input = dynet::constant(cg, dim, MIN_ACTIVATION_VALUE);
            created = true;
        }

        return input;
    }

};

static void _firstActionLayer(const pddl_asnets_ground_task_t *g,
                              const ModelParameters &model,
                              dynet::ComputationGraph &cg,
                              dynet::Expression input_state,
                              dynet::Expression input_goal_condition,
                              dynet::Expression input_applicable_ops,
                              dynet::Expression input_ldms,
                              dynet::Expression input_op_history,
                              std::vector<dynet::Expression> &action_layer)
{
    MissingInput missing_input(1);

    for (int op_id = 0; op_id < g->op_size; ++op_id){
        std::vector<dynet::Expression> in_state;
        std::vector<dynet::Expression> in_goal;
        dynet::Expression in_applicable;
        std::vector<dynet::Expression> in_ldms;
        std::vector<dynet::Expression> in_op_history;
        for (int i = 0; i < g->op[op_id].related_fact_size; ++i){
            int fact_id = g->op[op_id].related_fact[i];
            if (fact_id < 0){
                in_state.push_back(missing_input.get(cg));
                in_goal.push_back(missing_input.get(cg));

            }else{
                in_state.push_back(dynet::pick(input_state, fact_id));
                in_goal.push_back(dynet::pick(input_goal_condition, fact_id));
            }
        }
        in_applicable = dynet::pick(input_applicable_ops, op_id);

        if (!input_ldms.is_stale()){
            in_ldms.push_back(dynet::pick(input_ldms, 3 * op_id));
            in_ldms.push_back(dynet::pick(input_ldms, 3 * op_id + 1));
            in_ldms.push_back(dynet::pick(input_ldms, 3 * op_id + 2));
        }

        if (!input_op_history.is_stale())
            in_op_history.push_back(dynet::pick(input_op_history, op_id));

        int action_id = g->op[op_id].action->action_id;
        ActionModule *am = model.action[0][action_id];
        dynet::Expression e = am->exprInput(cg, in_state, in_goal,
                                            in_applicable, in_ldms,
                                            in_op_history);
        action_layer.push_back(e);
    }
}

static void _actionLayer(const pddl_asnets_ground_task_t *g,
                         const ModelParameters &model,
                         dynet::ComputationGraph &cg,
                         int layer,
                         const std::vector<dynet::Expression> &prop_layer,
                         const std::vector<dynet::Expression> &prev_action_layer,
                         std::vector<dynet::Expression> &action_layer,
                         float dropout_rate)
{
    MissingInput missing_input(model.hidden_dim);

    for (int op_id = 0; op_id < g->op_size; ++op_id){
        std::vector<dynet::Expression> in;
        for (int i = 0; i < g->op[op_id].related_fact_size; ++i){
            int fact_id = g->op[op_id].related_fact[i];
            if (fact_id < 0){
                in.push_back(missing_input.get(cg));

            }else{
                in.push_back(prop_layer[fact_id]);
            }
        }
        in.push_back(prev_action_layer[op_id]);
        int action_id = g->op[op_id].action->action_id;
        ActionModule *am = model.action[layer][action_id];
        dynet::Expression e = am->expr(cg, in);
        if (dropout_rate > 0.f && layer != model.num_layers){
            e = dynet::dropout(e, dropout_rate);
        }
        action_layer.push_back(e);
    }
}

static void _propLayer(const pddl_asnets_ground_task_t *g,
                       const ModelParameters &model,
                       dynet::ComputationGraph &cg,
                       int layer,
                       const std::vector<dynet::Expression> &action_layer,
                       const std::vector<dynet::Expression> *prev_prop_layer,
                       std::vector<dynet::Expression> &prop_layer,
                       float dropout_rate)
{
    MissingInput missing_input(model.hidden_dim);

    for (int fact_id = 0; fact_id < g->fact_size; ++fact_id){
        int pred_id = g->fact[fact_id].pred->pred_id;
        PropositionModule *pm = model.prop[layer][pred_id];

        std::vector<std::vector<dynet::Expression>> input;
        int input_size = g->fact[fact_id].related_op_size;
        if (prev_prop_layer != NULL)
            input_size += 1;
        input.resize(input_size);
        for (int ri = 0; ri < g->fact[fact_id].related_op_size; ++ri){
            int op_id;
            PDDL_IARR_FOR_EACH(g->fact[fact_id].related_op + ri, op_id){
                input[ri].push_back(action_layer[op_id]);
            }

            if (input[ri].size() == 0)
                input[ri].push_back(missing_input.get(cg));
        }
        if (prev_prop_layer != NULL)
            input[input_size - 1].push_back((*prev_prop_layer)[fact_id]);

        dynet::Expression e = pm->expr(cg, input);
        if (dropout_rate > 0.f){
            e = dynet::dropout(e, dropout_rate);
        }
        prop_layer.push_back(e);
    }
}

static dynet::Expression asnetsExpr(const pddl_asnets_ground_task_t *g,
                                    const ModelParameters &model,
                                    dynet::ComputationGraph &cg,
                                    dynet::Expression input_state,
                                    dynet::Expression input_goal_condition,
                                    dynet::Expression input_applicable_ops,
                                    dynet::Expression input_ldms,
                                    dynet::Expression input_op_history,
                                    float dropout_rate)
{
    std::vector<std::vector<dynet::Expression>> action_layer;
    action_layer.resize(model.num_layers + 1);
    std::vector<std::vector<dynet::Expression>> prop_layer;
    prop_layer.resize(model.num_layers);

    int layer = 0;
    // First action layer needs to be connected to inputs
    _firstActionLayer(g, model, cg, input_state, input_goal_condition,
                      input_applicable_ops, input_ldms, input_op_history,
                      action_layer[0]);

    for (; layer < model.num_layers; ++layer){
        const std::vector<dynet::Expression> *prev_prop_layer = NULL;
        if (layer > 0)
            prev_prop_layer = &prop_layer[layer - 1];
        _propLayer(g, model, cg, layer, action_layer[layer],
                   prev_prop_layer, prop_layer[layer], dropout_rate);

        _actionLayer(g, model, cg, layer + 1, prop_layer[layer],
                     action_layer[layer], action_layer[layer + 1],
                     dropout_rate);
    }

    dynet::Expression out = dynet::concatenate(action_layer[layer]);

    return maskedSoftmax(cg, out, input_applicable_ops);
}

static void setStateVector(const pddl_asnets_ground_task_t *task,
                           const pddl_iset_t *strips_state,
                           std::vector<float> &state)
{
    state.resize(task->strips.fact.fact_size);
    for (size_t i = 0; i < state.size(); ++i)
        state[i] = 0;
    int fact_id;
    PDDL_ISET_FOR_EACH(strips_state, fact_id)
        state[fact_id] = 1;
}

static void setApplicableOpsVector(const pddl_asnets_ground_task_t *task,
                                   const pddl_iset_t *applicable_op_ids,
                                   std::vector<float> &applicable_ops)
{
    applicable_ops.resize(task->strips.op.op_size);
    for (size_t i = 0; i < applicable_ops.size(); ++i)
        applicable_ops[i] = 0;

    int op_id;
    PDDL_ISET_FOR_EACH(applicable_op_ids, op_id)
        applicable_ops[op_id] = 1;
}

static void setGoalVector(const pddl_asnets_ground_task_t *task,
                          const pddl_iset_t *strips_goal,
                          std::vector<float> &goal)
{
    goal.resize(task->strips.fact.fact_size);
    for (size_t i = 0; i < goal.size(); ++i)
        goal[i] = 0;

    int fact_id;
    PDDL_ISET_FOR_EACH(strips_goal, fact_id)
        goal[fact_id] = 1;
}

static void setFDRStateVector(const pddl_asnets_ground_task_t *task,
                              const int *s,
                              std::vector<float> &state,
                              std::vector<float> &applicable_ops)
{
    PDDL_ISET(strips_state);
    pddlASNetsGroundTaskFDRStateToStrips(task, s, &strips_state);
    setStateVector(task, &strips_state, state);
    pddlISetFree(&strips_state);

    PDDL_ISET(ops);
    pddlASNetsGroundTaskFDRApplicableOps(task, s, &ops);
    setApplicableOpsVector(task, &ops, applicable_ops);
    pddlISetFree(&ops);
}


static void setFDRGoalVector(const pddl_asnets_ground_task_t *task,
                             const pddl_fdr_part_state_t *fdr_goal,
                             std::vector<float> &goal)
{
    PDDL_ISET(strips_g);
    pddlASNetsGroundTaskFDRPartStateToStrips(task, fdr_goal, &strips_g);
    setGoalVector(task, &strips_g, goal);
    pddlISetFree(&strips_g);
}

static void setLDMs(const pddl_asnets_ground_task_t *task,
                    const pddl_set_iset_t *in_ldms,
                    std::vector<float> &ldms)
{
    if (in_ldms == NULL)
        return;

    ldms.resize(task->strips.op.op_size * 3, 0.f);
    const pddl_iset_t *ldm;
    PDDL_SET_ISET_FOR_EACH_ID_SET(in_ldms, ldm_id, ldm){
        if (pddlISetSize(ldm) == 1){
            int op_id = pddlISetGet(ldm, 0);
            ldms[3 * op_id] = 1;

        }else{
            int op_id;
            PDDL_ISET_FOR_EACH(ldm, op_id)
                ldms[3 * op_id + 1] = 1;
        }
    }

    for (int op_id = 0; op_id < task->strips.op.op_size; ++op_id){
        if (ldms[3 * op_id] < .5 && ldms[3 * op_id + 1] < .5)
            ldms[3 * op_id + 2] = 1;
    }
}

static void setOpHistory(const pddl_asnets_ground_task_t *task,
                         const pddl_iarr_t *path,
                         std::vector<float> &op_history)
{
    if (path == NULL)
        return;

    op_history.resize(task->strips.op.op_size, 0.f);
    int op_id;
    PDDL_IARR_FOR_EACH(path, op_id)
        op_history[op_id] += 1.f;
}


struct ASNetsTrainMiniBatchTask {
    int task_id;
    int size;
    int fact_size;
    int op_size;
    std::vector<float> state;
    std::vector<float> goal;
    std::vector<float> applicable_ops;
    std::vector<float> ldms;
    std::vector<float> op_history;
    std::vector<unsigned int> selected_op;
    dynet::Expression e_state;
    dynet::Expression e_goal;
    dynet::Expression e_applicable_ops;
    dynet::Expression e_ldms;
    dynet::Expression e_op_history;
    dynet::Expression e_output;

    ASNetsTrainMiniBatchTask()
        : task_id(-1), size(0), fact_size(0), op_size(0)
    {}

    void add(std::vector<float> &in_state,
             std::vector<float> &in_applicable_ops,
             std::vector<float> &in_goal,
             int in_selected_op,
             std::vector<float> &in_ldms,
             std::vector<float> &in_op_history)
    {
        state.insert(state.end(), in_state.begin(), in_state.end());
        applicable_ops.insert(applicable_ops.end(),
                              in_applicable_ops.begin(),
                              in_applicable_ops.end());
        goal.insert(goal.end(), in_goal.begin(), in_goal.end());

        ASSERT(in_selected_op >= 0 && in_selected_op < op_size);
        selected_op.push_back(in_selected_op);
        ldms.insert(ldms.end(), in_ldms.begin(), in_ldms.end());
        op_history.insert(op_history.end(), in_op_history.begin(), in_op_history.end());
        ++size;
    }

    void createInputs(dynet::ComputationGraph &cg)
    {
        if (size == 0)
            return;
        ASSERT((int)state.size() == size * fact_size);
        ASSERT((int)applicable_ops.size() == size * op_size);
        ASSERT((int)selected_op.size() == size);
        ASSERT((int)goal.size() == size * fact_size);

        std::vector<long> dim(1);
        dim[0] = fact_size;
        e_state = dynet::input(cg, dynet::Dim(dim, size), state);
        e_goal = dynet::input(cg, dynet::Dim(dim, size), goal);

        dim[0] = op_size;
        e_applicable_ops = dynet::input(cg, dynet::Dim(dim, size),
                                        applicable_ops);

        if (ldms.size() > 0){
            dim[0] = 3 * op_size;
            e_ldms = dynet::input(cg, dynet::Dim(dim, size), ldms);
        }

        if (op_history.size() > 0){
            dim[0] = op_size;
            e_op_history = dynet::input(cg, dynet::Dim(dim, size), op_history);
        }

        e_output = dynet::one_hot(cg, op_size, selected_op);
    }
};

struct ASNetsTrainMiniBatch {
    std::vector<ASNetsTrainMiniBatchTask> batch;

    ASNetsTrainMiniBatch(const pddl_asnets_train_data_t *data,
                         int minibatch_size,
                         bool use_ldms,
                         bool use_op_history)
    {
        if (minibatch_size < 0)
            minibatch_size = data->sample_size;
        minibatch_size = PDDL_MIN(minibatch_size, data->sample_size);
        batch.resize(data->task_size);
        for (int i = 0; i < data->task_size; ++i){
            batch[i].task_id = i;
            batch[i].fact_size = data->task[i]->strips.fact.fact_size;
            batch[i].op_size = data->task[i]->strips.op.op_size;
        }

        PDDL_ISET(sample_state);
        PDDL_ISET(sample_applicable_ops);
        PDDL_ISET(sample_goal);
        for (int sample = 0; sample < minibatch_size; ++sample){
            int task_id, selected_op;
            const pddl_set_iset_t *sample_ldms = NULL;
            const pddl_iarr_t *sample_path = NULL;
            pddlASNetsTrainDataGetSample(data, sample, &task_id, &selected_op,
                                         &sample_state, &sample_applicable_ops,
                                         &sample_goal,
                                         (use_ldms ? &sample_ldms : NULL),
                                         (use_op_history ? &sample_path : NULL));

            std::vector<float> state, applicable_ops, goal, ldms, op_history;
            setStateVector(data->task[task_id], &sample_state, state);
            setApplicableOpsVector(data->task[task_id],
                                   &sample_applicable_ops, applicable_ops);
            setGoalVector(data->task[task_id], &sample_goal, goal);
            if (use_ldms)
                setLDMs(data->task[task_id], sample_ldms, ldms);
            if (use_op_history)
                setOpHistory(data->task[task_id], sample_path, op_history);
            batch[task_id].add(state, applicable_ops, goal, selected_op,
                               ldms, op_history);
        }
        pddlISetFree(&sample_state);
        pddlISetFree(&sample_applicable_ops);
        pddlISetFree(&sample_goal);
    }

    void createInputs(dynet::ComputationGraph &cg)
    {
        for (size_t task_id = 0; task_id < batch.size(); ++task_id){
            if (batch[task_id].size == 0)
                continue;
            batch[task_id].createInputs(cg);
        }
    }
};


static dynet::Expression asnetsTrainExpr(pddl_asnets_train_data_t *data,
                                         const ModelParameters &params,
                                         int minibatch_size,
                                         float dropout_rate,
                                         bool use_lmc,
                                         bool use_op_history,
                                         dynet::ComputationGraph &cg)
{
    cg.clear();

    // Sample a minibatch
    ASNetsTrainMiniBatch batch(data, minibatch_size, use_lmc, use_op_history);
    batch.createInputs(cg);

    // Construct network for all relevant ground tasks at once
    std::vector<dynet::Expression> nets;
    int batch_size = 0;
    for (int task_id = 0; task_id < data->task_size; ++task_id){
        if (batch.batch[task_id].size == 0)
            continue;
        const ASNetsTrainMiniBatchTask &b = batch.batch[task_id];
        //LOG(err, "Batch: task: %d, size: %d", task_id, b.size);
        dynet::Expression e = asnetsExpr(data->task[task_id],
                                         params,
                                         cg,
                                         b.e_state,
                                         b.e_goal,
                                         b.e_applicable_ops,
                                         b.e_ldms,
                                         b.e_op_history,
                                         dropout_rate);
        dynet::Expression e_loss = crossEntropyLoss(cg, e, b.e_output);
        nets.push_back(e_loss);
        batch_size += b.size;
    }

    ASSERT(nets.size() > 0);
    // Compute mean over all losses
    dynet::Expression e_loss = dynet::sum(nets) / batch_size;
    return e_loss;
}




struct pddl_asnets_model {
    pddl_asnets_model_config_t cfg;
    dynet::ComputationGraph *cg;
    dynet::Trainer *trainer;
    ModelParameters *params;
};

static pddl_asnets_model_t *asnets_model_singleton = NULL;
static int asnets_model_counter = 0;

pddl_asnets_model_t *pddlASNetsModelNew(const pddl_asnets_lifted_task_t *task,
                                        const pddl_asnets_model_config_t *cfg,
                                        pddl_err_t *err)
{
    if (asnets_model_counter > 0){
        // TODO: Add check for the version of DyNet with correctly implemented
        //       ::cleanup() function which allows to call this function
        //       more than once without memory leak.
        ERR_RET(err, NULL,
                "Creating more than one instance of ASNets leads to a"
                " memory leak due to current DyNet implementation."
                " Therefore, we disallow it completely.");
    }
    if (asnets_model_singleton != NULL){
        ERR_RET(err, NULL,
                "Cannot create a second instance of an ASNets model."
                " DyNet allows us to have at most one ASNets model at the time.");
    }

    CTX(err, "ASNets-Model-Init");
    LOG(err, "Model Init for %s", task->pddl.domain_file);
    pddl_asnets_model_t *m = ZALLOC(pddl_asnets_model_t);
    m->cfg = *cfg;

    dynet::DynetParams dynet_params;
    dynet_params.autobatch = false;
    //dynet_params.mem_descriptor = "4096";
    //dynet_params.profiling = 10;
    dynet_params.random_seed = m->cfg.random_seed;
    //dynet_params.shared_parameters = true;
    dynet_params.weight_decay = m->cfg.weight_decay;
    dynet::initialize(dynet_params);

    m->params = new ModelParameters(m->cfg.hidden_dimension,
                                    m->cfg.num_layers,
                                    m->cfg.lmc,
                                    m->cfg.op_history,
                                    task);

    // TODO: Parametrize
    m->trainer = new dynet::AdamTrainer(m->params->model);
    m->cg = new dynet::ComputationGraph();
#ifdef PDDL_DEBUG
    m->cg->set_check_validity(true);
    m->cg->set_immediate_compute(true);
#endif /* PDDL_DEBUG */

    CTXEND(err);

    // Store the singleton object
    asnets_model_singleton = m;
    // Increase the counter of calls to this function
    ++asnets_model_counter;
    return m;
}

void pddlASNetsModelDel(pddl_asnets_model_t *a)
{
    PANIC_IF(asnets_model_singleton != a,
             "Something is wrong: Trying to delete ASNets model that wasn't"
             " created before.");
    delete a->params;
    if (a->trainer != NULL)
        delete a->trainer;
    if (a->cg != NULL)
        delete a->cg;
    FREE(a);
    dynet::cleanup();

    // Clear the pointer to the singleton object
    asnets_model_singleton = NULL;
    // Decrease the counter
    --asnets_model_counter;
}

int pddlASNetsModelCheckCompatibleCfg(const pddl_asnets_model_t *model,
                                      const pddl_asnets_config_t *cfg,
                                      pddl_err_t *err)
{
    if (model->cfg.hidden_dimension != cfg->hidden_dimension){
        ERR_RET(err, -1, "Model has a different hidden dimension than the"
                " configuration (%d vs %d).", model->cfg.hidden_dimension,
                cfg->hidden_dimension);
    }
    if (model->cfg.num_layers != cfg->num_layers){
        ERR_RET(err, -1, "Model has a different number of layers than the"
                " configuration (%d vs %d).", model->cfg.num_layers,
                cfg->num_layers);
    }
    if (model->cfg.lmc != cfg->lmc){
        if (model->cfg.lmc){
            ERR_RET(err, -1, "Model assumes landmark input, but the"
                    " configuration does not.");
        }else{
            ERR_RET(err, -1, "The configuration assumes landmark input, but the"
                    " model does not.");
        }
    }
    if (model->cfg.op_history != cfg->op_history){
        if (model->cfg.op_history){
            ERR_RET(err, -1, "Model assumes operator history input, but the"
                    " configuration does not.");
        }else{
            ERR_RET(err, -1, "The configuration assumes operator history input, but the"
                    " model does not.");
        }
    }

    return 0;
}

static void paramToArr(const dynet::Parameter &param, float **w, int *w_size)
{
    // Raw weights are not scaled by weight_decay so we need to do that
    // before saving the weights
    const dynet::ParameterStorage &p = param.get_storage();
    float weight_decay = p.owner->get_weight_decay().current_weight_decay();
    std::vector<float> vals = dynet::as_scale_vector(p.values, weight_decay);

    if (*w == NULL){
        *w = ALLOC_ARR(float, vals.size());

    }else {
        if (*w_size < (int)vals.size())
            *w = REALLOC_ARR(*w, float, vals.size());
    }
    *w_size = vals.size();

    for (size_t i = 0; i < vals.size(); ++i)
        (*w)[i] = vals[i];
}

static int arrToParam(const float *w, int w_size, dynet::Parameter &param,
                      pddl_err_t *err)
{
    std::vector<float> warr(w, w + w_size);
    dynet::TensorTools::set_elements(param.get_storage().values, warr);
    if (w_size != (int)param.get_storage().values.d.size()){
        ERR_RET(err, -1, "Mismatch between the input array and the number"
                " of model's parameters.");
    }
    return 0;
}

int pddlASNetsModelSetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    const float *w,
                                    int w_size,
                                    pddl_err_t *err)
{
    if (layer < 0 || layer > m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (action_id < 0 || action_id >= (int)m->params->action[layer].size())
        ERR_RET(err, -1, "Invalid action ID %d", action_id);

    dynet::Parameter &param = m->params->action[layer][action_id]->W;
    return arrToParam(w, w_size, param, err);
}

int pddlASNetsModelSetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 const float *w,
                                 int w_size,
                                 pddl_err_t *err)
{
    if (layer < 0 || layer > m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (action_id < 0 || action_id >= (int)m->params->action[layer].size())
        ERR_RET(err, -1, "Invalid action ID %d", action_id);

    dynet::Parameter &param = m->params->action[layer][action_id]->bias;
    return arrToParam(w, w_size, param, err);
}

int pddlASNetsModelSetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  const float *w,
                                  int w_size,
                                  pddl_err_t *err)
{
    if (layer < 0 || layer >= m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (pred_id < 0 || pred_id >= (int)m->params->prop[layer].size())
        ERR_RET(err, -1, "Invalid pred ID %d", pred_id);

    dynet::Parameter &param = m->params->prop[layer][pred_id]->W;
    return arrToParam(w, w_size, param, err);
}

int pddlASNetsModelSetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               const float *w,
                               int w_size,
                               pddl_err_t *err)
{
    if (layer < 0 || layer >= m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (pred_id < 0 || pred_id >= (int)m->params->prop[layer].size())
        ERR_RET(err, -1, "Invalid pred ID %d", pred_id);

    dynet::Parameter &param = m->params->prop[layer][pred_id]->bias;
    return arrToParam(w, w_size, param, err);
}

int pddlASNetsModelGetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    float **w,
                                    int *w_size,
                                    pddl_err_t *err)
{
    if (layer < 0 || layer > m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (action_id < 0 || action_id >= (int)m->params->action[layer].size())
        ERR_RET(err, -1, "Invalid action ID %d", action_id);

    const dynet::Parameter &param = m->params->action[layer][action_id]->W;
    paramToArr(param, w, w_size);
    return 0;
}

int pddlASNetsModelGetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 float **w,
                                 int *w_size,
                                 pddl_err_t *err)
{
    if (layer < 0 || layer > m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (action_id < 0 || action_id >= (int)m->params->action[layer].size())
        ERR_RET(err, -1, "Invalid action ID %d", action_id);

    const dynet::Parameter &param = m->params->action[layer][action_id]->bias;
    paramToArr(param, w, w_size);
    return 0;
}

int pddlASNetsModelGetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  float **w,
                                  int *w_size,
                                  pddl_err_t *err)
{
    if (layer < 0 || layer >= m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (pred_id < 0 || pred_id >= (int)m->params->prop[layer].size())
        ERR_RET(err, -1, "Invalid pred ID %d", pred_id);

    const dynet::Parameter &param = m->params->prop[layer][pred_id]->W;
    paramToArr(param, w, w_size);
    return 0;
}

int pddlASNetsModelGetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               float **w,
                               int *w_size,
                               pddl_err_t *err)
{
    if (layer < 0 || layer >= m->params->num_layers)
        ERR_RET(err, -1, "Invalid layer %d", layer);
    if (pred_id < 0 || pred_id >= (int)m->params->prop[layer].size())
        ERR_RET(err, -1, "Invalid pred ID %d", pred_id);

    const dynet::Parameter &param = m->params->prop[layer][pred_id]->bias;
    paramToArr(param, w, w_size);
    return 0;
}


int pddlASNetsModelTrainStep(pddl_asnets_model_t *m,
                             pddl_asnets_train_data_t *data,
                             int minibatch_size,
                             float dropout_rate,
                             float *out_loss,
                             pddl_err_t *err)
{
    if (data->sample_size == 0){
        ERR_RET(err, -1, "No training data samples: Cannot train a model"
                " without any input data.");
    }

    try {
        // Sample a minibatch
        pddlASNetsTrainDataShuffle(data);

        // Construct network with the right input data
        dynet::Expression e_loss = asnetsTrainExpr(data, *m->params, minibatch_size,
                                                   dropout_rate, m->cfg.lmc,
                                                   m->cfg.op_history, *m->cg);

        // Learn parameters
        float loss_val = dynet::as_scalar(m->cg->forward(e_loss));
        m->cg->backward(e_loss);
        m->trainer->update();

        if (out_loss != NULL)
            *out_loss = loss_val;
        return 0;

    } catch(std::runtime_error &e){
        DYNET_PANIC_EXCEPTION(e);
        return -1;
    }
}

float pddlASNetsModelOverallLoss(pddl_asnets_model_t *m,
                                 pddl_asnets_train_data_t *data,
                                 float dropout_rate)
{
    try {
        dynet::Expression e_loss = asnetsTrainExpr(data, *m->params, -1,
                                                   dropout_rate, m->cfg.lmc,
                                                   m->cfg.op_history, *m->cg);
        return dynet::as_scalar(m->cg->forward(e_loss));
    } catch(std::runtime_error &e){
        DYNET_PANIC_EXCEPTION(e);
        return -1.;
    }
}

static int _pddlASNetsModelEvalFDRState(pddl_asnets_model_t *m,
                                        const pddl_asnets_ground_task_t *task,
                                        const int *in_state,
                                        const pddl_fdr_part_state_t *in_goal,
                                        const pddl_set_iset_t *in_ldms,
                                        const pddl_iarr_t *in_path,
                                        pddl_asnets_policy_distribution_t *distr)
{
    std::vector<float> state;
    std::vector<float> goal;
    std::vector<float> applicable_ops;
    std::vector<float> ldms;
    std::vector<float> op_history;

    setFDRGoalVector(task, in_goal, goal);
    setFDRStateVector(task, in_state, state, applicable_ops);
    if (in_ldms != NULL)
        setLDMs(task, in_ldms, ldms);
    if (in_path != NULL)
        setOpHistory(task, in_path, op_history);

    m->cg->clear();

    std::vector<long> dim(1);
    dim[0] = state.size();
    dynet::Expression e_state = dynet::input(*m->cg, dynet::Dim(dim), state);
    dynet::Expression e_goal = dynet::input(*m->cg, dynet::Dim(dim), goal);

    dim[0] = applicable_ops.size();
    dynet::Expression e_applicable_ops
            = dynet::input(*m->cg, dynet::Dim(dim), applicable_ops);

    dynet::Expression e_ldms;
    if (in_ldms != NULL){
        dim[0] = ldms.size();
        e_ldms = dynet::input(*m->cg, dynet::Dim(dim), ldms);
    }

    dynet::Expression e_op_history;
    if (in_path != NULL){
        dim[0] = op_history.size();
        e_op_history = dynet::input(*m->cg, dynet::Dim(dim), op_history);
    }

    // Dropout is used *only* during training -- we don't need to use it here
    dynet::Expression e_output = asnetsExpr(task, *m->params, *m->cg, e_state,
                                            e_goal, e_applicable_ops,
                                            e_ldms, e_op_history, -1);

    std::vector<float> out = dynet::as_vector(m->cg->forward(e_output));
    ASSERT((int)out.size() == task->strips.op.op_size);

    int best_op_id = -1;
    float best_value = -1;
    for (size_t op_id = 0; op_id < out.size(); ++op_id){
        ASSERT(out[op_id] >= 0.f);
        // Skip operators that are not applicable
        if (applicable_ops[op_id] < .5)
            continue;
        if (out[op_id] > best_value){
            best_op_id = op_id;
            best_value = out[op_id];
        }

        if (distr != NULL){
            if (distr->op_size == distr->op_alloc){
                if (distr->op_alloc == 0)
                    distr->op_alloc = 4;
                distr->op_alloc *= 2;
                distr->op_id = REALLOC_ARR(distr->op_id, int, distr->op_alloc);
                distr->prob = REALLOC_ARR(distr->prob, float, distr->op_alloc);
            }

            distr->op_id[distr->op_size] = op_id;
            distr->prob[distr->op_size] = out[op_id];
            ++distr->op_size;
        }
    }

    return best_op_id;
}

int pddlASNetsModelEvalFDRState(pddl_asnets_model_t *m,
                                const pddl_asnets_ground_task_t *task,
                                const int *in_state,
                                const pddl_fdr_part_state_t *in_goal,
                                const pddl_set_iset_t *in_ldms,
                                const pddl_iarr_t *in_path,
                                pddl_asnets_policy_distribution_t *distr)
{
    PANIC_IF(m->cfg.lmc && in_ldms == NULL,
             "Landmarks are required by this model but none were provided.");
    PANIC_IF(m->cfg.op_history && in_path == NULL,
             "Operator history is required by this model but it was not provided.");

    try {
        return _pddlASNetsModelEvalFDRState(m, task, in_state, in_goal,
                                            in_ldms, in_path, distr);
    } catch(std::runtime_error &e){
        DYNET_PANIC_EXCEPTION(e);
        return -1;
    }
}
