# Paper build and bibliography management.
# Bibliography files under bib/ are refreshed from a shared bibliography mirror
# via `make update-bib`; do not edit them directly (edit extra.bib for entries
# not yet in that mirror).

LATEXMK ?= latexmk
LATEXFLAGS ?= -pdf -interaction=nonstopmode -halt-on-error
PDFINFO ?= pdfinfo
PAPER_PYTHON ?= python3
# ICAPS 2027 has not published its page rule. Keep the preceding eight-page
# content limit as an explicit project assumption until the call is available.
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

.PHONY: paper supplement author-kit-preflight submission-check submission-audit \
		submission update-bib clean

paper: paper.pdf

paper.pdf: paper.tex $(AUTHOR_KIT_STYLE) $(AUTHOR_KIT_BST) \
		$(GENERATED_RESULT) $(POSTHOC_GENERATED_RESULT) \
		$(SEMANTIC_UNION_GENERATED_RESULT) \
		$(wildcard bib/*.bib) $(wildcard extra.bib) | author-kit-preflight
	$(LATEXMK) $(LATEXFLAGS) $<

supplement: supplement.pdf

supplement.pdf: supplement.tex cap-study.tex $(GENERATED_RESULT) \
		$(POSTHOC_GENERATED_RESULT) $(PROFILE_GENERATED_RESULT) \
		$(SEMANTIC_UNION_GENERATED_RESULT) \
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

# This gate binds the accepted focused full-study artifact and prevents a
# submission build from silently retaining synthetic, stale, or unreviewed
# result bytes.
submission-check: $(POSTHOC_GENERATED_RESULT) $(PROFILE_GENERATED_RESULT) \
		$(SEMANTIC_UNION_GENERATED_RESULT)
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

# Provisional project audit assumption only, not an ICAPS 2027 requirement:
# audit a two-PDF review bundle until the venue publishes its rules. The
# checker accepts exactly these two outputs; private manifests, generated
# provenance, source, logs, and post-unblinding artifacts stay outside it.
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
