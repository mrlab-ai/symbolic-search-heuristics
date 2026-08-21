# Paper build and bibliography management.
# Bibliography files under bib/ are refreshed from a shared bibliography mirror
# via `make update-bib`; do not edit them directly (edit extra.bib for entries
# not yet in that mirror).

LATEXMK ?= latexmk
LATEXFLAGS ?= -pdf -interaction=nonstopmode -halt-on-error
PDFINFO ?= pdfinfo
PAPER_PYTHON ?= python3
# Provisional stress-test threshold; replace it with the published ICAPS 2027
# rule when the official author kit becomes available. Reference pages do not
# count against this body-page target.
PROXY_TARGET_CONTENT_PAGES ?= 8
GENERATED_RESULT := generated/pdb-cap-grid-full-v1.tex
ANALYSIS_ARTIFACT_DIR := ../experiments/artifacts/pdb-cap-grid-focused-full

.PHONY: paper supplement proxy proxy-preflight submission-check submission-audit \
	submission update-bib clean

paper: paper.pdf

paper.pdf: paper.tex $(GENERATED_RESULT) $(wildcard bib/*.bib)
	$(LATEXMK) $(LATEXFLAGS) $<

supplement: supplement.pdf

supplement.pdf: supplement.tex cap-study.tex $(GENERATED_RESULT) $(wildcard bib/*.bib)
	$(LATEXMK) $(LATEXFLAGS) $<

# ICAPS 2027 has not published its author kit.  This target deliberately uses
# the preceding conference's AAAI 2026 format only as a page/layout stress
# test.  Put aaai2026.sty on TEXINPUTS and aaai2026.bst on BSTINPUTS; do not
# vendor or silently substitute either reviewed file.
proxy: aaai2026-proxy.pdf

proxy-preflight:
	@command -v sha256sum >/dev/null || { \
		echo 'sha256sum not found; cannot attest the reviewed proxy kit' >&2; \
		exit 2; \
	}
	@style="$$(kpsewhich aaai2026.sty)"; \
	test -n "$$style" || { \
		echo 'aaai2026.sty not found; add the reviewed author kit to TEXINPUTS' >&2; \
		exit 2; \
	}; \
	test "$$(sha256sum "$$style" | awk '{print $$1}')" = \
		'6f90c4d7a36f4a038daf187fdd6cec9fe578aba819733b49551574a37feecd35' || { \
		echo 'aaai2026.sty does not match the reviewed provisional kit' >&2; \
		exit 2; \
	}
	@bst="$$(kpsewhich aaai2026.bst)"; \
	test -n "$$bst" || { \
		echo 'aaai2026.bst not found; add the reviewed author kit to BSTINPUTS' >&2; \
		exit 2; \
	}; \
	test "$$(sha256sum "$$bst" | awk '{print $$1}')" = \
		'ac26e2c66047435c0ed25f21ae36ad42d731cf3d794c4a8b5f05a62141a27294' || { \
		echo 'aaai2026.bst does not match the reviewed provisional kit' >&2; \
		exit 2; \
	}

aaai2026-proxy.pdf: proxy-preflight aaai2026-proxy.tex paper.tex \
		$(GENERATED_RESULT) $(wildcard bib/*.bib)
	$(LATEXMK) $(LATEXFLAGS) aaai2026-proxy.tex

# This gate binds the accepted focused full-study artifact and prevents a
# submission build from silently retaining synthetic, stale, or unreviewed
# result bytes.
submission-check:
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/analyze_pdb_cap_grid_full.py --self-test
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/render_pdb_cap_grid_full_paper.py --self-test
	cd $(ANALYSIS_ARTIFACT_DIR) && sha256sum -c analysis-v1.json.sha256
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) \
		../experiments/render_pdb_cap_grid_full_paper.py --check

# Provisional project audit assumption only, not an ICAPS 2027 requirement:
# audit a two-PDF review bundle until the venue publishes its rules. The
# checker accepts exactly these two outputs; private manifests, generated
# provenance, source, logs, and post-unblinding artifacts stay outside it.
# Force both documents through LaTeX here: latexmk otherwise trusts its state
# database even when a newer unrelated PDF has replaced an output file.
submission-audit: submission-check proxy-preflight
	$(LATEXMK) $(LATEXFLAGS) -g aaai2026-proxy.tex
	$(LATEXMK) $(LATEXFLAGS) -g supplement.tex
	@set -eu; \
	command -v $(PDFINFO) >/dev/null || { \
		echo 'pdfinfo not found; cannot audit the proxy page count' >&2; \
		exit 2; \
	}; \
	target='$(PROXY_TARGET_CONTENT_PAGES)'; \
	case "$$target" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'PROXY_TARGET_CONTENT_PAGES must be an integer from 1 through 999' >&2; exit 2 ;; \
	esac; \
	pages="$$( $(PDFINFO) aaai2026-proxy.pdf | \
		awk '/^Pages:/ { print $$2; exit }')"; \
	case "$$pages" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'cannot determine a bounded positive proxy page count' >&2; exit 2 ;; \
	esac; \
	references_page="$$(sed -n \
		's/.*\\newlabel{paper:references-start}{{[^}]*}{\([0-9][0-9]*\)}.*/\1/p' \
		aaai2026-proxy.aux)"; \
	case "$$references_page" in \
		[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; \
		*) echo 'cannot determine a unique bounded paper:references-start page' >&2; exit 2 ;; \
	esac; \
	if [ "$$references_page" -gt "$$pages" ] || [ "$$references_page" -lt 2 ]; then \
		echo "paper:references-start page $$references_page is inconsistent with $$pages PDF pages" >&2; \
		exit 2; \
	fi; \
	body_page=$$((references_page - 1)); \
	if [ "$$body_page" -gt "$$target" ]; then \
		echo "AAAI proxy content reaches page $$body_page; provisional target is $$target" >&2; \
		exit 2; \
	fi; \
	echo "AAAI proxy: body content reaches physical page $$body_page within provisional target; $$pages total pages including references"
	@set -eu; \
	for log in aaai2026-proxy.log supplement.log; do \
		test -s "$$log" || { echo "$$log is missing or empty" >&2; exit 2; }; \
		if grep -En \
			'^(Overfull \\[hv]box|LaTeX Warning: (Citation|Reference).*undefined|LaTeX Warning: There were undefined (citations|references)|Package (natbib|biblatex) Warning: .*undefined|LaTeX Warning: Label\(s\) may have changed|LaTeX Warning: Label .* multiply defined|LaTeX Warning: There were multiply-defined labels)' \
			"$$log"; then \
			echo "$$log contains submission-blocking layout or reference warnings" >&2; \
			exit 2; \
		fi; \
	done
	PYTHONDONTWRITEBYTECODE=1 $(PAPER_PYTHON) check_submission_ready.py \
		--review-bundle aaai2026-proxy.pdf supplement.pdf

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
		supplement*.out supplement*.pdf supplement*.fdb_latexmk supplement*.fls \
		aaai2026-proxy.aux aaai2026-proxy.bbl aaai2026-proxy.blg \
		aaai2026-proxy.fdb_latexmk aaai2026-proxy.fls \
		aaai2026-proxy.log aaai2026-proxy.out aaai2026-proxy.pdf
