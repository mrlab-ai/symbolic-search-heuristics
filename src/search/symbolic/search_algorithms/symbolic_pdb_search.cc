#include "symbolic_pdb_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_cofactor_profiles.h"
#include "../wbh_dual_metric_selector.h"
#include "../wbh_incidence_selector.h"
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
#include <chrono>
#include <cmath>

using namespace std;

namespace symbolic {
SymbolicPdbForwardSearch::SymbolicPdbForwardSearch(const plugins::Options &opts)
    : SymbolicSearch(opts), state_budget(opts.get<int>("budget")),
      goal_directed(opts.get<bool>("goal_directed")),
      pattern_selection(opts.get<PdbPatternSelection>("pattern_selection")),
      cegar_max_time(opts.get<double>("cegar_max_time")),
      cegar_seed(opts.get<int>("cegar_seed")),
      cegar_max_refinements(opts.get<int>("cegar_max_refinements")),
      cofactor_width_budget(opts.get<int>("cofactor_width_budget")),
      total_add_node_budget(opts.get<int>("total_add_node_budget")),
      value_cap(opts.get<int>("value_cap")),
      select_value_cap(opts.get<bool>("select_value_cap")),
      dynamic_reordering(opts.get<bool>("dynamic_reordering")),
      gamer_ordering(opts.get<bool>("gamer_ordering")),
      shadow_partition(opts.get<bool>("shadow_partition")),
      prune_only(opts.get<bool>("prune_only")),
      batch_f_window(opts.get<int>("batch_f_window")),
      incidence_selector_log(opts.get<string>("incidence_selector_log")) {
}

void SymbolicPdbForwardSearch::initialize() {
    SymbolicSearch::initialize();
    verify_heuristic_positive_costs();
    const bool incidence_selector =
        pattern_selection == PdbPatternSelection::TERMINAL_INCIDENCE_GUIDED ||
        pattern_selection ==
            PdbPatternSelection::TERMINAL_INCIDENCE_MATCHED_CONTROL;
    const bool dual_selector =
        pattern_selection ==
            PdbPatternSelection::TERMINAL_DUAL_INCIDENCE_GUIDED ||
        pattern_selection == PdbPatternSelection::TERMINAL_DUAL_MJ_GUIDED ||
        pattern_selection ==
            PdbPatternSelection::TERMINAL_DUAL_MATCHED_CONTROL;
    const bool terminal_selector = incidence_selector || dual_selector;
    if (pattern_selection == PdbPatternSelection::EXACT_WIDTH_FILTER &&
        dynamic_reordering) {
        utils::g_log
            << "pattern_selection=exact_width_filter requires "
               "dynamic_reordering=false; exact candidate widths must remain "
               "valid throughout selection and search."
            << endl;
        utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
    }
    if (terminal_selector && dynamic_reordering) {
        utils::g_log
            << "Terminal-metric PDB selection requires "
               "dynamic_reordering=false."
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
    if (terminal_selector) {
        bool fd_order = true;
        const vector<int> &order = vars->get_var_order();
        for (size_t i = 0; i < order.size(); ++i) {
            if (order[i] != static_cast<int>(i)) {
                fd_order = false;
                break;
            }
        }
        const bool frozen_options =
            state_budget == 100000 && !gamer_ordering && fd_order &&
            cegar_seed == 2011 && isinf(cegar_max_time) &&
            cegar_max_time > 0 && cegar_max_refinements == 128 &&
            !finite_width_budget && !finite_add_budget && value_cap == -1 &&
            !select_value_cap && !shadow_partition && !prune_only &&
            batch_f_window == 0 && !incidence_selector_log.empty();
        if (!frozen_options) {
            utils::g_log
                << "Terminal-metric selectors require the frozen options "
                   "budget=100000, gamer_ordering=false, "
                   "dynamic_reordering=false, cegar_seed=2011, "
                   "cegar_max_time=infinity, cegar_max_refinements=128, "
                   "value_cap=-1, select_value_cap=false, "
                   "cofactor_width_budget=infinity, "
                   "total_add_node_budget=infinity, shadow_partition=false, "
                   "prune_only=false, batch_f_window=0, and a nonempty "
                   "incidence_selector_log."
                << endl;
            utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
        }
    } else if (!incidence_selector_log.empty()) {
        utils::g_log
            << "incidence_selector_log is only valid for a "
               "terminal-metric selector."
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
    unique_ptr<WbhSelectorTrace> selector_trace;
    unique_ptr<WbhStateCutCertificate> state_cut_certificate;
    unique_ptr<WbhIncidenceProbe> incidence_probe;
    if (terminal_selector) {
        if (dual_selector) {
            state_cut_certificate = make_unique<WbhStateCutCertificate>(
                make_wbh_state_cut_certificate(vars.get()));
            selector_trace = make_unique<WbhDualMetricTrace>(
                incidence_selector_log, *state_cut_certificate);
        } else {
            selector_trace =
                make_unique<WbhIncidenceTrace>(incidence_selector_log);
        }
        incidence_probe = make_unique<WbhIncidenceProbe>(vars.get(), 16);
        SymParameters probe_params = sym_params;
        probe_params.stats.reset();
        probe_params.profile.reset();
        probe_params.wbh_profile_self_test = false;
        auto probe_search =
            make_unique<UniformCostSearch>(this, probe_params);
        probe_search->set_wbh_detached_probe(incidence_probe.get());

        utils::Timer probe_cpu_timer;
        const auto probe_wall_start = chrono::steady_clock::now();
        const int probe_peak_before = utils::get_peak_memory_in_kb();
        probe_search->init(mgr, true, nullptr);
        while (!incidence_probe->complete() && !probe_search->finished()) {
            probe_search->step();
        }
        const double probe_cpu_seconds = probe_cpu_timer();
        const double probe_wall_seconds = chrono::duration<double>(
                                                chrono::steady_clock::now() -
                                                probe_wall_start)
                                                .count();
        const int probe_peak_after = utils::get_peak_memory_in_kb();
        incidence_probe->log_probe(
            *selector_trace, probe_cpu_seconds, probe_wall_seconds,
            probe_peak_before, probe_peak_after);
        if (!incidence_probe->complete()) {
            utils::g_log
                << "Terminal-metric selector could not complete its frozen "
                   "16-layer blind probe; no fallback is permitted."
                << endl;
            utils::exit_with(utils::ExitCode::SEARCH_UNSUPPORTED);
        }
    }
    level_sets =
        make_shared<PdbLevelSets>(
            vars.get(), search_task, state_budget, pattern_selection,
            goal_directed, cegar_max_time, cegar_seed,
            cegar_max_refinements,
            cofactor_width_budget, total_add_node_budget, value_cap,
            select_value_cap, incidence_probe.get(), selector_trace.get(),
            state_cut_certificate.get());
    if (level_sets->uses_terminal_incidence_selector()) {
        utils::g_log << "wbh PDB heuristic: pattern_size="
                     << level_sets->get_pattern().size()
                     << ", selected_source="
                     << level_sets->get_selected_source()
                     << ", abstract_states="
                     << level_sets->get_num_abstract_states()
                     << ", terminal_incidence_budget="
                     << level_sets->get_terminal_incidence_budget()
                     << ", terminal_incidence="
                     << level_sets->get_selected_terminal_incidence()
                     << ", pool_sha256=" << level_sets->get_pool_sha256()
                     << ", preselection_sha256="
                     << level_sets->get_preselection_sha256();
        if (level_sets->get_value_cap() >= 0) {
            utils::g_log << ", value_cap=" << level_sets->get_value_cap();
        }
        utils::g_log << ", values=" << level_sets->get_level_sets().size()
                     << ", cofactor_width="
                     << level_sets->get_cofactor_width()
                     << ", width_upper_bound="
                     << level_sets->get_width_upper_bound() << endl;
    } else if (level_sets->uses_terminal_dual_metric_selector()) {
        utils::g_log << "wbh PDB heuristic: pattern_size="
                     << level_sets->get_pattern().size()
                     << ", selected_source="
                     << level_sets->get_selected_source()
                     << ", abstract_states="
                     << level_sets->get_num_abstract_states()
                     << ", terminal_incidence_budget="
                     << level_sets->get_terminal_incidence_budget()
                     << ", terminal_incidence="
                     << level_sets->get_selected_terminal_incidence()
                     << ", masked_joint_budget="
                     << level_sets->get_masked_joint_budget()
                     << ", masked_joint="
                     << level_sets->get_selected_masked_joint()
                     << ", pool_sha256=" << level_sets->get_pool_sha256()
                     << ", preselection_sha256="
                     << level_sets->get_preselection_sha256();
        if (level_sets->get_value_cap() >= 0) {
            utils::g_log << ", value_cap=" << level_sets->get_value_cap();
        }
        utils::g_log << ", values=" << level_sets->get_level_sets().size()
                     << ", cofactor_width="
                     << level_sets->get_cofactor_width()
                     << ", width_upper_bound="
                     << level_sets->get_width_upper_bound() << endl;
    } else if (level_sets->uses_exact_width_filter()) {
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
        if (level_sets->uses_candidate_pool() &&
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
            "total-ADD-node budget; the terminal-incidence modes and the "
            "terminal-dual modes use the frozen cap grid and common K=32 "
            "reference protocol.",
            "legacy");
        add_option<double>(
            "cegar_max_time",
            "Maximum CEGAR pattern-generation time in seconds (used for "
            "pattern_selection=cegar and for the fixed selector pools).",
            "10.0", plugins::Bounds("0.0", "infinity"));
        add_option<int>(
            "cegar_seed",
            "Deterministic CEGAR random seed (used for "
            "pattern_selection=cegar and for the fixed selector pools).",
            "2011", plugins::Bounds("0", "infinity"));
        add_option<int>(
            "cegar_max_refinements",
            "Maximum number of CEGAR refinement calls. Solution, decisive "
            "unsolvability, and empty-flaw detection precede the limit check. "
            "The terminal-metric modes require 128.",
            "infinity", plugins::Bounds("0", "infinity"));
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
        add_option<string>(
            "incidence_selector_log",
            "Dedicated create-or-truncate JSON-lines trace for the "
            "terminal-incidence and terminal-dual-metric selectors. A "
            "nonempty path is mandatory for those modes and invalid for "
            "every other mode.",
            "\"\"");
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
          "ADD cofactor-width budget"},
         {"terminal_incidence_guided",
          "prospective fixed-pool cap selection under the terminal-incidence "
          "budget of the cap-aware exact-width K=32 reference"},
         {"terminal_incidence_matched_control",
          "perform identical incidence-guided preselection work but execute "
          "the cap-aware exact-width K=32 reference"},
         {"terminal_dual_incidence_guided",
          "measure terminal incidence and masked joint cofactors for every "
          "candidate, then select under the incidence budget of the common "
          "cap-aware exact-width K=32 reference"},
         {"terminal_dual_mj_guided",
          "measure terminal incidence and masked joint cofactors for every "
          "candidate, then select under the masked-joint budget of the common "
          "cap-aware exact-width K=32 reference"},
         {"terminal_dual_matched_control",
          "perform identical dual-metric preselection work but execute the "
          "common cap-aware exact-width K=32 reference"}});
}
