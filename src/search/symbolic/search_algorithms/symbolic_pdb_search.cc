#include "symbolic_pdb_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_pdb_levels.h"
#include "../wbh_profile.h"
#include "../wbh_stats.h"

#include "../../plugins/plugin.h"
#include "../../utils/logging.h"
#include "../../utils/system.h"
#include "../../utils/timer.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../plan_selection/plan_selector.h"
#include "../searches/heuristic_fw_search.h"
#include "../searches/uniform_cost_search.h"

#include <limits>

using namespace std;

namespace symbolic {
SymbolicPdbForwardSearch::SymbolicPdbForwardSearch(const plugins::Options &opts)
    : SymbolicSearch(opts), state_budget(opts.get<int>("budget")),
      goal_directed(opts.get<bool>("goal_directed")),
      pattern_selection(opts.get<PdbPatternSelection>("pattern_selection")),
      cegar_max_time(opts.get<double>("cegar_max_time")),
      cegar_seed(opts.get<int>("cegar_seed")),
      cofactor_width_budget(opts.get<int>("cofactor_width_budget")),
      total_add_node_budget(opts.get<int>("total_add_node_budget")),
      value_cap(opts.get<int>("value_cap")),
      select_value_cap(opts.get<bool>("select_value_cap")),
      dynamic_reordering(opts.get<bool>("dynamic_reordering")),
      shadow_partition(opts.get<bool>("shadow_partition")),
      prune_only(opts.get<bool>("prune_only")),
      batch_f_window(opts.get<int>("batch_f_window")) {
}

void SymbolicPdbForwardSearch::initialize() {
    SymbolicSearch::initialize();
    verify_heuristic_positive_costs();
    if (pattern_selection == PdbPatternSelection::EXACT_WIDTH_FILTER &&
        dynamic_reordering) {
        utils::g_log
            << "pattern_selection=exact_width_filter requires "
               "dynamic_reordering=false; exact candidate widths must remain "
               "valid throughout selection and search."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (select_value_cap &&
        pattern_selection != PdbPatternSelection::EXACT_WIDTH_FILTER) {
        utils::g_log
            << "select_value_cap=true requires "
               "pattern_selection=exact_width_filter."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (select_value_cap && value_cap != -1) {
        utils::g_log
            << "select_value_cap=true cannot be combined with a fixed "
               "value_cap."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    const bool finite_width_budget =
        cofactor_width_budget != numeric_limits<int>::max();
    const bool finite_add_budget =
        total_add_node_budget != numeric_limits<int>::max();
    if (finite_width_budget && finite_add_budget) {
        utils::g_log
            << "A finite total_add_node_budget cannot be combined with a "
               "finite cofactor_width_budget."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (finite_add_budget &&
        pattern_selection != PdbPatternSelection::EXACT_WIDTH_FILTER) {
        utils::g_log
            << "A finite total_add_node_budget requires "
               "pattern_selection=exact_width_filter."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (shadow_partition && !sym_params.profile) {
        utils::g_log
            << "shadow_partition=true requires a nonempty wbh_profile_log."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (shadow_partition && dynamic_reordering) {
        utils::g_log
            << "shadow_partition=true requires dynamic_reordering=false so "
               "all masked certificates retain their recorded cut order."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (shadow_partition && (prune_only || batch_f_window != 0)) {
        utils::g_log
            << "shadow_partition=true cannot be combined with prune_only or "
               "a nonzero batch_f_window."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    mgr =
        make_shared<SymStateSpaceManager>(vars.get(), sym_params, search_task);

    utils::Timer construction_timer;
    level_sets =
        make_shared<PdbLevelSets>(
            vars.get(), search_task, state_budget, pattern_selection,
            goal_directed, cegar_max_time, cegar_seed,
            cofactor_width_budget, total_add_node_budget, value_cap,
            select_value_cap);
    if (level_sets->uses_exact_width_filter()) {
        utils::g_log << "wbh PDB heuristic: pattern_size="
                     << level_sets->get_pattern().size()
                     << ", selected_source="
                     << level_sets->get_selected_source()
                     << ", abstract_states="
                     << level_sets->get_num_abstract_states();
        if (level_sets->uses_total_add_node_budget()) {
            utils::g_log << ", total_add_node_budget="
                         << level_sets->get_total_add_node_budget();
        } else {
            utils::g_log << ", cofactor_width_budget="
                         << level_sets->get_cofactor_width_budget();
        }
        if (level_sets->get_value_cap() >= 0 || select_value_cap) {
            utils::g_log << ", value_cap=" << level_sets->get_value_cap();
        }
        utils::g_log << ", values=" << level_sets->get_level_sets().size()
                     << ", cofactor_width="
                     << level_sets->get_cofactor_width()
                     << ", width_upper_bound="
                     << level_sets->get_width_upper_bound() << endl;
    } else {
        utils::g_log << "wbh PDB heuristic: pattern_size="
                     << level_sets->get_pattern().size()
                     << ", values=" << level_sets->get_level_sets().size();
        if (level_sets->get_value_cap() >= 0) {
            utils::g_log << ", value_cap=" << level_sets->get_value_cap();
        }
        utils::g_log
                     << ", cofactor_width="
                     << level_sets->get_cofactor_width()
                     << ", width_upper_bound="
                     << level_sets->get_width_upper_bound() << endl;
    }
    if (sym_params.stats) {
        level_sets->log_heuristic(*sym_params.stats);
    }
    if (sym_params.profile) {
        sym_params.profile->log_heuristic(
            vars.get(), level_sets->get_add(), level_sets->get_add_stats());
    }

    if (shadow_partition) {
        auto search_ptr = unique_ptr<UniformCostSearch>(
            new UniformCostSearch(this, sym_params));
        search_ptr->init(mgr, true, nullptr);
        const double construction_time = construction_timer();
        if (sym_params.stats) {
            sym_params.stats->log_construction(
                "pdb_shadow_" + level_sets->get_selection_name(),
                construction_time, state_budget, level_sets->get_value_cap(),
                true);
        }
        auto sym_trs =
            search_ptr->getStateSpaceShared()->get_transition_relations();
        solution_registry->init(
            vars, search_ptr->getClosedShared(), nullptr, sym_trs,
            plan_data_base, true, simple);
        search = move(search_ptr);
        return;
    }

    // A completed PDB may prove the initial state dead. Record its construction
    // before HeuristicFwSearch reports that clean unsolvability outcome; every
    // ordinary path retains the legacy post-init timing semantics.
    bool construction_prelogged = false;
    if (sym_params.stats) {
        bool initial_dead_end =
            !(mgr->get_initial_state() * level_sets->get_dead_ends()).IsZero();
        if (level_sets->uses_exact_width_filter() &&
            initial_dead_end != level_sets->selected_initial_is_dead_end()) {
            ABORT(
                "PDB width-selector initial-dead metadata disagrees with its "
                "selected dead-end BDD.");
        }
        construction_prelogged = initial_dead_end;
        if (construction_prelogged) {
            sym_params.stats->log_construction(
                "pdb_" + level_sets->get_selection_name(),
                construction_timer(), state_budget,
                level_sets->get_value_cap(), true);
        }
    }

    auto search_ptr =
        unique_ptr<HeuristicFwSearch>(new HeuristicFwSearch(this, sym_params));
    search_ptr->init(
        mgr, &level_sets->get_level_sets(), level_sets->get_dead_ends(),
        prune_only, batch_f_window);
    if (sym_params.profile) {
        sym_params.profile->attach_heuristic_closed(
            vars.get(), search_ptr->getClosedShared());
    }
    double construction_time = construction_timer();
    if (!construction_prelogged && sym_params.stats) {
        sym_params.stats->log_construction(
            "pdb_" + level_sets->get_selection_name(),
            construction_time, state_budget, level_sets->get_value_cap(), true);
    }

    auto sym_trs = search_ptr->getStateSpaceShared()->get_transition_relations();
    solution_registry->init(
        vars, search_ptr->getClosedShared(), nullptr, sym_trs, plan_data_base,
        true, simple);

    search = move(search_ptr);
}

void SymbolicPdbForwardSearch::new_solution(const SymSolutionCut &sol) {
    if (!solution_registry->found_all_plans() && sol.get_f() < upper_bound) {
        solution_registry->register_solution(sol);
        upper_bound = sol.get_f();
    }
}

class SymbolicPdbForwardSearchFeature
    : public plugins::TypedFeature<
          SearchAlgorithm, SymbolicPdbForwardSearch> {
public:
    SymbolicPdbForwardSearchFeature() : TypedFeature("sym_fw_pdb") {
        document_title(
            "Symbolic Forward Search with a budget-bounded pattern database "
            "heuristic");
        document_synopsis("");
        symbolic::SymbolicSearch::add_options_to_feature(*this);
        add_option<int>(
            "budget",
            "Abstract-state budget B: variables are selected greedily in the "
            "chosen order while their domain-size product stays <= B.",
            "100000", plugins::Bounds("1", "infinity"));
        add_option<bool>(
            "goal_directed",
            "Legacy compatibility switch, used only when pattern_selection="
            "legacy. True selects the historical goal/causal-graph prefix; "
            "false selects the historical BDD-order prefix.",
            "false");
        add_option<PdbPatternSelection>(
            "pattern_selection",
            "Pattern strategy. legacy preserves goal_directed behavior; "
            "goal_fill skips variables that do not fit instead of wasting the "
            "remaining budget; cegar uses counterexample-guided refinement; "
            "exact_width_filter applies a deterministic score to a fixed "
            "candidate-generator pool under one exact cofactor-width or "
            "total-ADD-node budget.",
            "legacy");
        add_option<double>(
            "cegar_max_time",
            "Maximum CEGAR pattern-generation time in seconds (used for "
            "pattern_selection=cegar and for the exact_width_filter pool).",
            "10.0", plugins::Bounds("0.0", "infinity"));
        add_option<int>(
            "cegar_seed",
            "Deterministic CEGAR random seed (used for "
            "pattern_selection=cegar and for the exact_width_filter pool).",
            "2011", plugins::Bounds("0", "infinity"));
        add_option<int>(
            "cofactor_width_budget",
            "Hard exact ADD cofactor-width budget K, used only for "
            "pattern_selection=exact_width_filter. The selector materializes "
            "and scores a fixed deduplicated pool of empty, BDD-prefix, "
            "goal-prefix, goal-fill, and one seeded CEGAR pattern. Scoring is "
            "deterministic for the materialized pool; a finite "
            "cegar_max_time remains a wall-clock generator limit.",
            "infinity", plugins::Bounds("1", "infinity"));
        add_option<int>(
            "total_add_node_budget",
            "Hard total ADD-node budget U=A+T, used only for "
            "pattern_selection=exact_width_filter. A finite value is "
            "mutually exclusive with a finite cofactor_width_budget and "
            "applies to the same fixed candidate pool and score.",
            "infinity", plugins::Bounds("1", "infinity"));
        add_option<int>(
            "value_cap",
            "Apply the safe terminal transform min(h_PDB, K) to every finite "
            "PDB value before exact-width filtering and search. K >= 0 "
            "preserves admissibility, consistency, and abstract dead ends "
            "while using at most K+1 finite values; -1 keeps exact values.",
            "-1", plugins::Bounds("-1", "infinity"));
        add_option<bool>(
            "select_value_cap",
            "With pattern_selection=exact_width_filter, materialize each raw "
            "PDB once and test the distinct safe transforms with caps "
            "0,1,2,4,...,256 plus the exact values. For each pattern retain "
            "its strongest feasible transform under the active exact width "
            "or total-ADD-node budget, then apply the frozen quality score "
            "across patterns.",
            "false");
        add_option<bool>(
            "shadow_partition",
            "Build and log the selected PDB but run forward blind uniform-cost "
            "search. Each exact blind g-layer is partitioned by the PDB only "
            "inside the profile stream, so all heuristics can be compared on "
            "a fixed frontier without affecting search behavior. Requires "
            "wbh_profile_log and dynamic_reordering=false, and records the "
            "reconstructed partition cost as an audit target, not as a "
            "predictor.",
            "false");
        add_option<bool>(
            "prune_only",
            "Use the heuristic only for pruning (dead ends and, once an "
            "anytime upper bound is known, the g+h >= bound slice); layers "
            "stay whole as in blind search (paper Cor. cor-prune).",
            "false");
        add_option<int>(
            "batch_f_window",
            "Speculatively image fresh (g,h) buckets at the same g and with "
            "f at most batch_f_window above the selected minimum in one BDD "
            "union. Logical A* selection, goal tests, and closing remain in "
            "the legacy order. Requires a consistent heuristic; 0 is exactly "
            "the legacy product-at-evaluation behavior.",
            "0", plugins::Bounds("0", "infinity"));
        this->add_option<shared_ptr<symbolic::PlanSelector>>(
            "plan_selection", "plan selection strategy", "top_k(num_plans=1)");
    }

    virtual shared_ptr<SymbolicPdbForwardSearch> create_component(
        const plugins::Options &options) const override {
        utils::g_log << "Search Algorithm: Symbolic Forward Search with "
                        "budget-bounded pattern database heuristic"
                     << endl;
        return make_shared<SymbolicPdbForwardSearch>(options);
    }
};

static plugins::FeaturePlugin<SymbolicPdbForwardSearchFeature> _plugin;

static plugins::TypedEnumPlugin<PdbPatternSelection>
    _pdb_pattern_selection_enum_plugin(
        {{"legacy", "preserve the historical goal_directed switch"},
         {"bdd_prefix", "greedy prefix of the BDD variable order"},
         {"goal_prefix", "greedy prefix of the goal/causal-graph order"},
         {"goal_fill", "goal/causal order, skipping variables that do not fit"},
         {"cegar", "counterexample-guided pattern refinement"},
         {"exact_width_filter",
          "deterministic scoring of a fixed generator pool under an exact "
          "ADD cofactor-width budget"}});
}
