#ifndef MERGE_AND_SHRINK_MERGE_AND_SHRINK_REPRESENTATION_H
#define MERGE_AND_SHRINK_MERGE_AND_SHRINK_REPRESENTATION_H

#include <memory>
#include <vector>

class State;

namespace utils {
class LogProxy;
}

namespace merge_and_shrink {
class Distances;
class MergeAndShrinkRepresentation {
protected:
    int domain_size;

public:
    explicit MergeAndShrinkRepresentation(int domain_size);
    virtual ~MergeAndShrinkRepresentation() = 0;

    int get_domain_size() const;

    // Store distances instead of abstract state numbers.
    virtual void set_distances(const Distances &) = 0;
    virtual void apply_abstraction_to_lookup_table(
        const std::vector<int> &abstraction_mapping) = 0;
    /*
      Return the value that state is mapped to. This is either an abstract
      state (if set_distances has not been called) or a distance (if it has).
      If the represented function is not total, the returned value is DEAD_END
      if the abstract state is PRUNED_STATE or if the (distance) value is INF.
    */
    virtual int get_value(const State &state) const = 0;
    /* Return true iff the represented function is total, i.e., does not map
       to PRUNED_STATE. */
    virtual bool is_total() const = 0;
    virtual void dump(utils::LogProxy &log) const = 0;
};

class MergeAndShrinkRepresentationLeaf : public MergeAndShrinkRepresentation {
    const int var_id;

    std::vector<int> lookup_table;
public:
    MergeAndShrinkRepresentationLeaf(int var_id, int domain_size);
    virtual ~MergeAndShrinkRepresentationLeaf() = default;

    virtual void set_distances(const Distances &) override;
    virtual void apply_abstraction_to_lookup_table(
        const std::vector<int> &abstraction_mapping) override;
    virtual int get_value(const State &state) const override;
    virtual bool is_total() const override;
    virtual void dump(utils::LogProxy &log) const override;

    // Read-only access for the width-bounded-heuristics level-set construction
    // (valid in abstract-state-id mode, i.e. before set_distances). Maps a
    // variable value to its abstract state id.
    int get_variable() const {
        return var_id;
    }
    const std::vector<int> &get_lookup_table() const {
        return lookup_table;
    }
};

class MergeAndShrinkRepresentationMerge : public MergeAndShrinkRepresentation {
    std::unique_ptr<MergeAndShrinkRepresentation> left_child;
    std::unique_ptr<MergeAndShrinkRepresentation> right_child;
    std::vector<std::vector<int>> lookup_table;
public:
    MergeAndShrinkRepresentationMerge(
        std::unique_ptr<MergeAndShrinkRepresentation> left_child,
        std::unique_ptr<MergeAndShrinkRepresentation> right_child);
    virtual ~MergeAndShrinkRepresentationMerge() = default;

    virtual void set_distances(const Distances &distances) override;
    virtual void apply_abstraction_to_lookup_table(
        const std::vector<int> &abstraction_mapping) override;
    virtual int get_value(const State &state) const override;
    virtual bool is_total() const override;
    virtual void dump(utils::LogProxy &log) const override;

    // Read-only access for the width-bounded-heuristics level-set construction
    // (valid in abstract-state-id mode, before set_distances). The lookup
    // table maps (left abstract state, right abstract state) to the merged
    // abstract state id (cascading tables of Helmert et al.).
    const MergeAndShrinkRepresentation &get_left_child() const {
        return *left_child;
    }
    const MergeAndShrinkRepresentation &get_right_child() const {
        return *right_child;
    }
    const std::vector<std::vector<int>> &get_lookup_table() const {
        return lookup_table;
    }
};
}

#endif
