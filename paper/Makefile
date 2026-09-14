# Paper build and bibliography management.
# Bibliography files under bib/ are refreshed from a shared bibliography mirror
# via `make update-bib`; do not edit them directly (edit extra.bib for entries
# not yet in that mirror).

LATEXMK ?= latexmk
LATEXFLAGS ?= -pdf -interaction=nonstopmode -halt-on-error
PDFINFO ?= pdfinfo
PAPER_PYTHON ?= python3
# The ICAPS 2027 CFP fixes the long-paper limit at eight content pages plus
# additional reference pages and requires AAAI format.
ICAPS_TARGET_CONTENT_PAGES ?= 8
AUTHOR_KIT_STYLE := aaai2027.sty
AUTHOR_KIT_BST := aaai2027.bst
AAAI2027_STYLE_SHA256 := 391bce82815bf698b8e382dd3ae7e30c75d7ab46df140cb295b1266016bc8623
AAAI2027_BST_SHA256 := 5db7765ba99de5c1e4686f9b3940a0add9c5e702f2164514462bec130ccb6e3c
GENERATED_RESULT := generated/pdb-cap-grid-full-v1.tex
ANALYSIS_ARTIFACT_DIR := ../experiments/artifacts/pdb-cap-grid-focused-full
POSTHOC_GENERATED_RESULT := generated/pdb-cap-grid-posthoc-v1.tex
POSTHOC_ANALYSIS_ARTIFACT_DIR := \
	../experiments/artifacts/pdb-cap-grid-posthoc-review
POSTHOC_ANALYSIS_ARTIFACT := \
	$(POSTHOC_ANALYSIS_ARTIFACT_DIR)/analysis-v1.json
POSTHOC_ANALYSIS_SIDECAR := \
	$(POSTHOC_ANALYSIS_ARTIFACT_DIR)/analysis-v1.json.sha256
POSTHOC_ANALYZER := ../experiments/analyze_pdb_cap_grid_posthoc_review.py
POSTHOC_RENDERER := ../experiments/render_pdb_cap_grid_posthoc_review.py
PROFILE_GENERATED_RESULT := generated/pdb-profile-predictors-v1.tex
PROFILE_ANALYSIS_ARTIFACT_DIR := ../experiments/artifacts/pdb-profile-comparison
PROFILE_ANALYSIS_ARTIFACT := $(PROFILE_ANALYSIS_ARTIFACT_DIR)/predictors-v1.json
PROFILE_ANALYSIS_SIDECAR := $(PROFILE_ANALYSIS_ARTIFACT).sha256
PROFILE_RENDERER := ../experiments/render_pdb_profile_predictors_paper.py
SEMANTIC_UNION_GENERATED_RESULT := generated/pdb-profile-semantic-union-v1.tex
SEMANTIC_UNION_ARTIFACT_DIR := \
	../experiments/artifacts/pdb-profile-semantic-union
SEMANTIC_UNION_ARTIFACT := $(SEMANTIC_UNION_ARTIFACT_DIR)/analysis-v1.json
SEMANTIC_UNION_SIDECAR := $(SEMANTIC_UNION_ARTIFACT).sha256
SEMANTIC_UNION_RENDERER := \
	../experiments/render_pdb_profile_semantic_union_paper.py
ORDER_GENERATED_RESULT := generated/pdb-profile-order-intervention-v1.tex
ORDER_ARTIFACT_DIR := \
	../experiments/artifacts/pdb-profile-order-intervention
ORDER_ARTIFACT := $(ORDER_ARTIFACT_DIR)/analysis-v1.json
ORDER_SIDECAR := $(ORDER_ARTIFACT).sha256
ORDER_RENDERER := \
	../experiments/render_pdb_profile_order_intervention_paper.py
HOLDOUT_GENERATED_RESULT := generated/pdb-profile-certificate-holdout-v1.tex
HOLDOUT_ARTIFACT_DIR := \
	../experiments/artifacts/pdb-profile-certificate-holdout
HOLDOUT_ARTIFACT := $(HOLDOUT_ARTIFACT_DIR)/analysis-v1.json
HOLDOUT_SIDECAR := $(HOLDOUT_ARTIFACT).sha256
HOLDOUT_DENOMINATOR_AUDIT := \
	$(HOLDOUT_ARTIFACT_DIR)/denominator-audit-v1.json
HOLDOUT_DENOMINATOR_SIDECAR := $(HOLDOUT_DENOMINATOR_AUDIT).sha256
HOLDOUT_RENDERER := \
	../experiments/render_pdb_profile_certificate_holdout_paper.py
SEED_GENERATED_RESULT := generated/pdb-profile-joint-seed-validation-v1.tex
SEED_ARTIFACT_DIR := \
	../experiments/artifacts/pdb-profile-joint-seed-validation
SEED_ARTIFACT := $(SEED_ARTIFACT_DIR)/analysis-v1.json
SEED_SIDECAR := $(SEED_ARTIFACT).sha256
SEED_RENDERER := \
	../experiments/render_pdb_profile_joint_seed_validation_paper.py
TI_GENERATED_RESULT := generated/terminal-incidence-results.tex
TI_RENDERER := render_terminal_incidence_results.py
TI_EVIDENCE_READERS := terminal_incidence_evidence.py \
	terminal_incidence_selection_evidence.py

.PHONY: paper supplement author-kit-preflight submission-check submission-audit \
		submission update-bib clean

paper: paper.pdf

paper.pdf: paper.tex $(AUTHOR_KIT_STYLE) $(AUTHOR_KIT_BST) \
		$(ORDER_GENERATED_RESULT) \
		$(HOLDOUT_GENERATED_RESULT) \
		$(SEED_GENERATED_RESULT) \
		$(TI_GENERATED_RESULT) \
		$(wildcard bib/*.bib) $(wildcard extra.bib) | author-kit-preflight
	$(LATEXMK) $(LATEXFLAGS) $<

supplement: supplement.pdf

supplement.pdf: supplement.tex cap-study.tex $(GENERATED_RESULT) \
		$(POSTHOC_GENERATED_RESULT) $(PROFILE_GENERATED_RESULT) \
		$(SEMANTIC_UNION_GENERATED_RESULT) $(ORDER_GENERATED_RESULT) \
		$(HOLDOUT_GENERATED_RESULT) \
		$(SEED_GENERATED_RESULT) \
		$(TI_GENERATED_RESULT) \
		$(wildcard bib/*.bib) $(wildcard extra.bib)
	$(LATEXMK) $(LATEXFLAGS) $<

$(POSTHOC_GENERATED_RESULT): $(POSTHOC_RENDERER) \
		$(POSTHOC_ANALYSIS_ARTIFACT) $(POSTHOC_ANALYSIS_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(POSTHOC_RENDERER) \
		--analysis $(POSTHOC_ANALYSIS_ARTIFACT) --output $@ --write

$(PROFILE_GENERATED_RESULT): $(PROFILE_RENDERER) \
		$(PROFILE_ANALYSIS_ARTIFACT) $(PROFILE_ANALYSIS_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(PROFILE_RENDERER) \
		--analysis $(PROFILE_ANALYSIS_ARTIFACT) --output $@ --write

$(SEMANTIC_UNION_GENERATED_RESULT): $(SEMANTIC_UNION_RENDERER) \
		$(SEMANTIC_UNION_ARTIFACT) $(SEMANTIC_UNION_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(SEMANTIC_UNION_RENDERER) \
		--analysis $(SEMANTIC_UNION_ARTIFACT) --output $@ --write

$(ORDER_GENERATED_RESULT): $(ORDER_RENDERER) \
		$(ORDER_ARTIFACT) $(ORDER_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(ORDER_RENDERER) \
		--analysis $(ORDER_ARTIFACT) --output $@ --write

$(HOLDOUT_GENERATED_RESULT): $(HOLDOUT_RENDERER) $(HOLDOUT_ARTIFACT) \
		$(HOLDOUT_SIDECAR) $(HOLDOUT_DENOMINATOR_AUDIT) \
		$(HOLDOUT_DENOMINATOR_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(HOLDOUT_RENDERER) \
		--analysis $(HOLDOUT_ARTIFACT) \
		--denominator-audit $(HOLDOUT_DENOMINATOR_AUDIT) \
		--output $@ --write

$(SEED_GENERATED_RESULT): $(SEED_RENDERER) $(SEED_ARTIFACT) \
		$(SEED_SIDECAR)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(SEED_RENDERER) \
		--analysis $(SEED_ARTIFACT) --output $@ --write

# The renderer reads only the explicitly pinned, committed terminal branch.
# It refuses to generate prospective or synthetic production results. The
# submission checker also verifies these bytes and the outcome-specific title.
$(TI_GENERATED_RESULT): $(TI_RENDERER) $(TI_EVIDENCE_READERS)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(TI_RENDERER) --write

# The untouched AAAI 2027 files are vendored from https://aaai.org/authorkit27/.
# Fail closed if either file is missing, replaced by a link, or byte-modified.
author-kit-preflight:
	@command -v sha256sum >/dev/null || { \
		echo 'sha256sum not found; cannot attest the AAAI 2027 author kit' >&2; \
		exit 2; \
	}
	@command -v stat >/dev/null || { \
		echo 'stat not found; cannot attest the AAAI 2027 author kit' >&2; \
		exit 2; \
	}
	@style='$(AUTHOR_KIT_STYLE)'; \
	 test -f "$$style" && test ! -L "$$style" && \
	 test "$$(stat -c '%h' "$$style")" = 1 || { \
		echo 'aaai2027.sty is missing, non-regular, or linked' >&2; \
		exit 2; \
	 }; \
	 test "$$(sha256sum "$$style" | awk '{print $$1}')" = \
		'$(AAAI2027_STYLE_SHA256)' || { \
		echo 'aaai2027.sty does not match the official reviewed kit' >&2; \
		exit 2; \
	}
	@bst='$(AUTHOR_KIT_BST)'; \
	 test -f "$$bst" && test ! -L "$$bst" && \
	 test "$$(stat -c '%h' "$$bst")" = 1 || { \
		echo 'aaai2027.bst is missing, non-regular, or linked' >&2; \
		exit 2; \
	 }; \
	 test "$$(sha256sum "$$bst" | awk '{print $$1}')" = \
		'$(AAAI2027_BST_SHA256)' || { \
		echo 'aaai2027.bst does not match the official reviewed kit' >&2; \
		exit 2; \
	}

# This gate binds every reviewed result artifact used by either PDF and
# prevents a submission build from silently retaining synthetic, stale, or
# unreviewed result bytes.
submission-check: $(POSTHOC_GENERATED_RESULT) $(PROFILE_GENERATED_RESULT) \
		$(SEMANTIC_UNION_GENERATED_RESULT) $(ORDER_GENERATED_RESULT) \
		$(HOLDOUT_GENERATED_RESULT) $(SEED_GENERATED_RESULT) $(TI_GENERATED_RESULT)
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) $(TI_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/recover_pdb_profile_comparison.py --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/analyze_pdb_cap_grid_full.py --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(POSTHOC_ANALYZER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/render_pdb_cap_grid_full_paper.py --self-test
	cd $(ANALYSIS_ARTIFACT_DIR) && sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/render_pdb_cap_grid_full_paper.py --check
	cd $(POSTHOC_ANALYSIS_ARTIFACT_DIR) && \
		sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(POSTHOC_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(POSTHOC_RENDERER) --analysis $(POSTHOC_ANALYSIS_ARTIFACT) \
		--output $(POSTHOC_GENERATED_RESULT) --check
	cd $(PROFILE_ANALYSIS_ARTIFACT_DIR) && \
		sha256sum -c predictors-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(PROFILE_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(PROFILE_RENDERER) --analysis $(PROFILE_ANALYSIS_ARTIFACT) \
		--output $(PROFILE_GENERATED_RESULT) --check
	cd $(SEMANTIC_UNION_ARTIFACT_DIR) && \
		sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(SEMANTIC_UNION_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(SEMANTIC_UNION_RENDERER) --analysis $(SEMANTIC_UNION_ARTIFACT) \
		--output $(SEMANTIC_UNION_GENERATED_RESULT) --check
	cd $(ORDER_ARTIFACT_DIR) && sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(ORDER_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(ORDER_RENDERER) --analysis $(ORDER_ARTIFACT) \
		--output $(ORDER_GENERATED_RESULT) --check
	cd $(HOLDOUT_ARTIFACT_DIR) && sha256sum -c analysis-v1.json.sha256 && \
		sha256sum -c denominator-audit-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(HOLDOUT_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(HOLDOUT_RENDERER) --analysis $(HOLDOUT_ARTIFACT) \
		--denominator-audit $(HOLDOUT_DENOMINATOR_AUDIT) \
		--output $(HOLDOUT_GENERATED_RESULT) --check
	cd $(SEED_ARTIFACT_DIR) && sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(SEED_RENDERER) --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		$(SEED_RENDERER) --analysis $(SEED_ARTIFACT) \
		--output $(SEED_GENERATED_RESULT) --check

# Project review-bundle audit. The ICAPS 2027 CFP is silent about a separate
# supplementary upload, so the submission form must be checked before treating
# the supplement as a venue deliverable. The checker accepts exactly these two
# internal review outputs; private manifests, generated provenance, source,
# logs, and post-unblinding artifacts stay outside them.
# Force both documents through LaTeX here: latexmk otherwise trusts its state
# database even when a newer unrelated PDF has replaced an output file.
submission-audit: submission-check author-kit-preflight
	$(LATEXMK) $(LATEXFLAGS) -g paper.tex
	$(LATEXMK) $(LATEXFLAGS) -g supplement.tex
	@set -eu; \
	command -v $(PDFINFO) >/dev/null || { \
		echo 'pdfinfo not found; cannot audit the paper page count' >&2; \
		exit 2; \
	}; \
	target='$(ICAPS_TARGET_CONTENT_PAGES)'; \
	case "$$target" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'ICAPS_TARGET_CONTENT_PAGES must be an integer from 1 through 999' >&2; exit 2 ;; \
	esac; \
	pages="$$( $(PDFINFO) paper.pdf | \
		awk '/^Pages:/ { print $$2; exit }')"; \
	case "$$pages" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'cannot determine a bounded positive paper page count' >&2; exit 2 ;; \
	esac; \
	references_page="$$(sed -n \
		's/.*\\newlabel{paper:references-start}{{[^}]*}{\([0-9][0-9]*\)}.*/\1/p' \
		paper.aux)"; \
	case "$$references_page" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'cannot determine a unique bounded paper:references-start page' >&2; exit 2 ;; \
	esac; \
	if [ "$$references_page" -gt "$$pages" ] || [ "$$references_page" -lt 2 ]; then \
		echo "paper:references-start page $$references_page is inconsistent with $$pages PDF pages" >&2; \
		exit 2; \
	fi; \
	body_page=$$references_page; \
	if [ "$$body_page" -gt "$$target" ]; then \
		echo "AAAI-formatted content reaches page $$body_page; ICAPS target is $$target" >&2; \
		exit 2; \
	fi; \
	echo "AAAI 2027 format: body content reaches physical page $$body_page within ICAPS target; $$pages total pages including references"
	@set -eu; \
	for log in paper.log supplement.log; do \
		test -s "$$log" || { echo "$$log is missing or empty" >&2; exit 2; }; \
		if grep -En \
			'^(Overfull \\[hv]box|LaTeX Warning: (Citation|Reference).*undefined|LaTeX Warning: There were undefined (citations|references)|Package (natbib|biblatex) Warning: .*undefined|LaTeX Warning: Label\(s\) may have changed|LaTeX Warning: Label .* multiply defined|LaTeX Warning: There were multiply-defined labels)' \
			"$$log"; then \
			echo "$$log contains submission-blocking layout or reference warnings" >&2; \
			exit 2; \
		fi; \
	done
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py \
		--review-bundle paper.pdf supplement.pdf

submission: submission-audit

update-bib:
	note='DO NOT EDIT THIS FILE DIRECTLY! It is overwritten by "make update-bib".'; \
	mkdir -p bib; \
	for name in abbrv-short abbrv literatur crossref-short crossref; do \
	    file=bib/$${name}.bib; \
	    wget -q https://raw.githubusercontent.com/aibasel/bib/main/$${name}.bib -O $${file}; \
	    printf '%% %s\n\n%s\n' "$${note}" "$$(cat $${file})" > $${file}; \
	done; \
	echo "$${note}" > bib/DO_NOT_EDIT_THESE_FILES

clean:
	rm -f paper*.aux paper*.bbl paper*.blg paper*.log paper*.out paper*.pdf \
		paper*.fdb_latexmk paper*.fls \
		supplement*.aux supplement*.bbl supplement*.blg supplement*.log \
		supplement*.out supplement*.pdf supplement*.fdb_latexmk supplement*.fls
