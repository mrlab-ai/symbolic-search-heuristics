#!/usr/bin/env python3
"""Validate final paper integration and a provisional two-PDF review bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


class SubmissionReadinessError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "paper.tex"
SUPPLEMENT = ROOT / "supplement.tex"
CAP_STUDY = ROOT / "cap-study.tex"
PROXY = ROOT / "aaai2026-proxy.tex"
MANIFEST = ROOT / "reproducibility-manifest.md"
GENERATED = ROOT / "generated" / "pdb-cap-grid-full-v1.tex"
GENERATED_INPUT = r"\input{generated/pdb-cap-grid-full-v1.tex}"
CAP_STUDY_INPUT = r"\input{cap-study.tex}"
REFERENCES_START_LABEL = r"\label{paper:references-start}"

# A clearpage before this exact active suffix flushes every body float before
# the reference boundary.  The proxy gate therefore counts the physical page
# immediately preceding paper:references-start, rather than the source page on
# which a deferred table happened to be declared.
MAIN_REFERENCE_TAIL = re.compile(
    r"\\clearpage\s*"
    r"\\label\{paper:references-start\}\s*"
    r"\\ifdefined\\ICAPSAAAIProxy\s*"
    r"\\else\s*"
    r"\\bibliographystyle\{plainnat\}\s*"
    r"\\fi\s*"
    r"\\bibliography\{bib/abbrv,bib/literatur,bib/crossref\}\s*"
    r"\\end\{document\}\s*\Z"
)

PAGE_COUNTER_MUTATION = re.compile(
    r"\\(?:pagenumbering|setcounter\s*\{\s*page\s*\}"
    r"|addtocounter\s*\{\s*page\s*\}|stepcounter\s*\{\s*page\s*\})"
)

PROXY_WRAPPER = re.compile(
    r"\s*\\def\\ICAPSAAAIProxy\{1\}\s*"
    r"\\input\{paper\.tex\}\s*\Z"
)

# Provisional project audit assumption only, not an ICAPS 2027 requirement:
# audit a two-PDF review bundle until the venue publishes its rules. Changing
# this allowlist then requires an explicit reviewed edit.
REVIEW_BUNDLE_FILENAMES = (
    "aaai2026-proxy.pdf",
    "supplement.pdf",
)

REVIEW_DOCUMENT_MARKERS = {
    "aaai2026-proxy.pdf": {
        "required": ("Cofactor Width", "Anonymous submission", "Abstract"),
        "forbidden": ("Supplementary Material",),
    },
    "supplement.pdf": {
        "required": (
            "Cofactor Width",
            "Supplementary Material",
            "Anonymous for review",
            "Guide.",
        ),
        "forbidden": ("Abstract\n",),
    },
}

# Self-citations and the public system name can legitimately appear in paper
# text. These patterns instead cover direct execution, path, repository, and
# provenance identities that must not occur anywhere in a review PDF.
FORBIDDEN_REVIEW_PDF = (
    ("execution-facility codename", re.compile(r"\barrhenius\b", re.IGNORECASE)),
    (
        "identifying infrastructure token",
        re.compile(
            r"\b(?:nobackup|naiss|dfsplan|link[oö]ping|liu\.se)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "public repository identity",
        re.compile(
            r"\b(?:symbolic-search-heuristics|mrlab-ai)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "absolute private path",
        re.compile(
            r"\bfile:(?:/{1,3})(?:home|users|nobackup|proj|scratch)/"
            r"[^\s<>\"']+"
            r"|(?<![:/])/(?:home|users|nobackup|proj|scratch)/[^\s<>\"']+"
            r"|\b[A-Z]:\\Users\\[^\s<>\"']+",
            re.IGNORECASE,
        ),
    ),
    (
        "email address",
        re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Git object, revision, or private digest",
        re.compile(
            r"(?<![0-9a-f])(?=[0-9a-f]{9,64}(?![0-9a-f]))"
            r"(?=[0-9a-f]*[a-f])[0-9a-f]{9,64}"
        ),
    ),
)

ANONYMOUS_PDF_AUTHORS = {
    "",
    "anonymous",
    "anonymous submission",
    "anonymous for review",
}

XMP_IDENTITY_FIELDS = {
    "author",
    "company",
    "contributor",
    "creator",
    "lastmodifiedby",
    "manager",
    "owner",
    "publisher",
}

ALLOWED_PDFINFO_FIELDS = {
    "author",
    "creationdate",
    "creator",
    "custom metadata",
    "encrypted",
    "file size",
    "form",
    "javascript",
    "keywords",
    "metadata stream",
    "moddate",
    "optimized",
    "page rot",
    "page size",
    "pages",
    "pdf version",
    "producer",
    "subject",
    "suspects",
    "tagged",
    "title",
    "userproperties",
}

SAFE_PDF_CREATORS = re.compile(
    r"^(?:TeX|LaTeX(?: with hyperref)?|pdfTeX(?:-[0-9][0-9.]*)?|"
    r"LuaTeX(?:-[0-9][0-9.]*)?|XeTeX(?:-[0-9][0-9.]*)?)$",
    re.IGNORECASE,
)

SAFE_PDF_PRODUCERS = re.compile(
    r"^(?:pdfTeX(?:-[0-9][0-9.]*)?|LuaTeX(?:-[0-9][0-9.]*)?|"
    r"XeTeX(?:-[0-9][0-9.]*)?|xdvipdfmx(?:\s[0-9][0-9.]*)?|"
    r"GPL Ghostscript(?:\s[0-9][0-9.]*)?)$",
    re.IGNORECASE,
)

FORBIDDEN_CONTENT = (
    ("placeholder", re.compile(r"placeholder", re.IGNORECASE)),
    (
        "synthetic or rehearsal result content",
        re.compile(r"\b(?:synthetic|rehearsal)\b", re.IGNORECASE),
    ),
    ("pending P6", re.compile(r"\bpending\s+P6\b", re.IGNORECASE)),
    (
        "P6 pending",
        re.compile(r"\bP6\b[\s\S]{0,120}\bpending\b", re.IGNORECASE),
    ),
    (
        "pending P6",
        re.compile(r"\bpending\b[\s\S]{0,120}\bP6\b", re.IGNORECASE),
    ),
    (
        "full census pending",
        re.compile(
            r"\bfull(?:-suite|\s+census|\s+suite)\b[\s\S]{0,120}\bpending\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pending full census",
        re.compile(
            r"\bpending\b[\s\S]{0,120}\bfull(?:-suite|\s+census|\s+suite)\b",
            re.IGNORECASE,
        ),
    ),
    ("forecast P6", re.compile(r"\bforecast(?:s|ing)?\s+P6\b", re.IGNORECASE)),
    (
        "preliminary results",
        re.compile(r"\bpreliminary\s+results?\b", re.IGNORECASE),
    ),
    (
        "overstated structural-value blindness",
        re.compile(
            r"\bbefore\s+any\s+(?:P6\s+)?structural\s+values?\b",
            re.IGNORECASE,
        ),
    ),
)

# These tokens identify the execution environment or the private source
# history. The exact generated-file input spelling is exempt because it is a
# repository-local filename, not rendered prose. No other case or context is
# exempt.
FORBIDDEN_IDENTITY = (
    ("execution-facility codename", re.compile(r"\barrhenius\b", re.IGNORECASE)),
    (
        "identifying infrastructure token",
        re.compile(
            r"\b(?:nobackup|naiss|dfsplan|jendrik|linköping)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "public repository namespace",
        re.compile(r"\bsymbolic-search-heuristics\b", re.IGNORECASE),
    ),
    (
        "Git object or revision prefix",
        re.compile(r"(?<![0-9a-f])[0-9a-f]{9,40}(?![0-9a-f])"),
    ),
)

# The focused renderer intentionally emits scientific aggregates only. These
# names reserve the private-provenance namespace and prevent a future renderer
# change from exposing execution identities in either review-facing document.
FORBIDDEN_REVIEW_MACROS = (
    r"\CapAnalysisSha",
    r"\CapPropertiesSha",
    r"\CapPaperDataSha",
    r"\CapProtocol",
    r"\CapProtocolRevision",
    r"\CapPlannerRevision",
    r"\CapPlannerBinarySha",
    r"\CapPlannerPreprocessSha",
    r"\CapJobSha",
)

REQUIRED_MAIN = (
    GENERATED_INPUT,
    r"\CapFullContextRows",
    r"\CapPrimaryContrastRows",
    r"\CapPrimaryMechanismRows",
    r"\CapPrimarySecondaryText",
    r"\CapScopeCaveat",
)

REQUIRED_SUPPLEMENT = (
    GENERATED_INPUT,
    CAP_STUDY_INPUT,
)

REQUIRED_CAP_STUDY = (
    r"\CapCensusContrastRows",
    r"\CapPrimarySecondaryRows",
    r"\CapCensusSecondaryRows",
    r"\CapFullConstructionRows",
    r"\CapSelectorSummaryRows",
    r"\CapSelectorSourceRows",
    r"\CapEffectiveCapRows",
    r"\CapMechanismText",
    r"\CapCensoringCaveat",
)

REQUIRED_MANIFEST = (
    "experiments/pdb_cap_grid_full_protocol.py",
    "experiments/exp_pdb_cap_grid_full.py",
    "experiments/analyze_pdb_cap_grid_full.py",
    "experiments/pdb_cap_grid_full_secondary_contract.py",
    "experiments/render_pdb_cap_grid_full_paper.py",
    "experiments/artifacts/pdb-cap-grid-development-p4/analysis-v3.json",
    "`experiments/artifacts/pdb-cap-grid-focused-full/analysis-v1.json`",
    "`experiments/artifacts/pdb-cap-grid-focused-full/analysis-v1.json.sha256`",
    "paper/generated/pdb-cap-grid-full-v1.tex",
    "pdb-cap-grid-development-screen-v3",
    "pdb-cap-grid-focused-full-evaluation-v1",
    "frozen-during-active-full-execution-before-properties-fetch-or-scientific-outcome-aggregation/v2",
    "1,377 tasks x 5 configurations = 6,885 fresh cells",
    "all 984 array elements `COMPLETED` with exit `0:0`",
)

REQUIRED_MANIFEST_DIGESTS = (
    "77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa",
    "fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b",
    "94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78",
    "977a1cac30b027990c8ed5f23803032a351c9497b26a837b303ba9604fc4f775",
    "24efc07fc6fdfd19d2a7532d4e717f072b1f5a2e893b946b529aedf4158ebc81",
    "0e97eb3a18271f149874f49ec1c0efbd362ad5a863665e7a0600c0ad8cdbbc12",
    "bddc69b2eedcc1442e6a42517d4d294e9a6ae0ab7dbf4aebc49714b152c0f215",
    "fb8db53b4f5eea7306961351d110b0d331abc87fa2a31242321de429f32ad60a",
    "1df86a1255cb301ffe2b6eb0db52ba81ca7f8c511e5a011cd028d8eff2dfc862",
)

EXPECTED_GENERATED_SHA256 = (
    "6bed124d4972bb76c87739cb96bf09d65f65c0a70818072f131f794d3421fb65"
)

FORBIDDEN_MANIFEST = re.compile(
    r"\b(?:pending|placeholder|unresolved)\b", re.IGNORECASE
)


def _fingerprint(st):
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_nlink,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _read_stable_regular_bytes(
    path: Path,
    maximum_bytes: int,
    *,
    label: Optional[str] = None,
) -> bytes:
    label = label or path.name
    try:
        before = path.lstat()
    except OSError as error:
        raise SubmissionReadinessError(
            f"{label} cannot be inspected"
        ) from error
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise SubmissionReadinessError(
            f"{label} must be a single-link regular file"
        )
    if before.st_size > maximum_bytes:
        raise SubmissionReadinessError(f"{label} exceeds {maximum_bytes} bytes")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags)
    except OSError as error:
        raise SubmissionReadinessError(
            f"{label} cannot be opened safely"
        ) from error
    try:
        try:
            opened = os.fstat(descriptor)
            if _fingerprint(opened) != _fingerprint(before):
                raise SubmissionReadinessError(f"{label} changed before opening")
            chunks = []
            total = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum_bytes:
                    raise SubmissionReadinessError(
                        f"{label} exceeds {maximum_bytes} bytes"
                    )
            after_fd = os.fstat(descriptor)
        except OSError as error:
            raise SubmissionReadinessError(
                f"{label} could not be read safely"
            ) from error
    finally:
        os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as error:
        raise SubmissionReadinessError(
            f"{label} cannot be re-inspected"
        ) from error
    expected = _fingerprint(before)
    if _fingerprint(after_fd) != expected or _fingerprint(after_path) != expected:
        raise SubmissionReadinessError(f"{label} changed while being read")
    return b"".join(chunks)


def _read_stable_regular(
    path: Path,
    maximum_bytes: int = 4 * 1024 * 1024,
    *,
    label: Optional[str] = None,
) -> str:
    label = label or path.name
    raw = _read_stable_regular_bytes(path, maximum_bytes, label=label)
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise SubmissionReadinessError(f"{label} is not strict UTF-8") from error


def _strip_tex_comments(text: str) -> str:
    r"""Remove unescaped TeX comments while preserving lines and escaped \%."""
    stripped = []
    for line in text.splitlines(keepends=True):
        comment = None
        for index, character in enumerate(line):
            if character != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                comment = index
                break
        if comment is None:
            stripped.append(line)
        else:
            ending = "\n" if line.endswith("\n") else ""
            stripped.append(line[:comment] + ending)
    return "".join(stripped)


def _validate_review_bundle_names(paths) -> None:
    names = [path.name for path in paths]
    if len(names) != len(set(names)):
        raise SubmissionReadinessError(
            "review bundle contains duplicate filenames"
        )
    if sorted(names) != sorted(REVIEW_BUNDLE_FILENAMES):
        raise SubmissionReadinessError(
            "review bundle must contain exactly: {}".format(
                ", ".join(REVIEW_BUNDLE_FILENAMES)
            )
        )


def _validate_review_bundle_paths(paths) -> None:
    _validate_review_bundle_names(paths)
    if any(path.parent != ROOT for path in paths):
        raise SubmissionReadinessError(
            "review bundle PDFs must be the canonical outputs in paper/"
        )


def _register_review_pdf_digest(digests, label: str, raw: bytes) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    if digest in digests:
        raise SubmissionReadinessError(
            f"{label} duplicates the bytes of {digests[digest]}"
        )
    digests[digest] = label


def _decode_tool_output(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise SubmissionReadinessError(
            f"{label} is not strict UTF-8"
        ) from error


def _normalized_visible_text(text: str) -> str:
    text = html.unescape(text)
    for _ in range(2):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    text = text.replace("\u00ad", "")
    joined = re.sub(
        r"(?<=\w)([-\u2010\u2011])\s*\r?\n\s*(?=\w)",
        r"\1",
        text,
    )
    dehyphenated = re.sub(
        r"(?<=\w)[-\u2010\u2011]\s*\r?\n\s*(?=\w)",
        "",
        text,
    )
    return text + "\n" + joined + "\n" + dehyphenated


def _scan_review_surface(
    pdf_name: str,
    surface_name: str,
    text: str,
    *,
    include_digest_pattern: bool,
) -> None:
    # Link targets can be HTML-escaped or percent-encoded by a PDF producer.
    # Normalize both representations before applying the same identity scan.
    text = _normalized_visible_text(text)
    patterns = (
        FORBIDDEN_REVIEW_PDF
        if include_digest_pattern
        else FORBIDDEN_REVIEW_PDF[:-1]
    )
    for description, pattern in patterns:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            raise SubmissionReadinessError(
                f"{pdf_name}:{surface_name}:{line}: "
                f"identifying review content ({description})"
            )


def _document_info_fields(pdf_name: str, document_info: str):
    fields = {}
    for line in document_info.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        normalized_key = key.strip().casefold()
        fields.setdefault(normalized_key, []).append(value.strip())
    unknown = sorted(set(fields) - ALLOWED_PDFINFO_FIELDS)
    if unknown:
        raise SubmissionReadinessError(
            f"{pdf_name} has unreviewed PDF metadata fields"
        )

    def single(key: str, *, required: bool = False):
        values = fields.get(key, [])
        if len(values) > 1:
            raise SubmissionReadinessError(
                f"{pdf_name} has duplicate PDF {key} metadata"
            )
        if required and not values:
            raise SubmissionReadinessError(
                f"{pdf_name} lacks PDF {key} metadata"
            )
        return values[0] if values else None

    author = single("author")
    if author is not None and author.casefold() not in ANONYMOUS_PDF_AUTHORS:
        raise SubmissionReadinessError(
            f"{pdf_name} PDF Author metadata is not anonymous"
        )

    # The reviewed build does not set hidden Title metadata.  Visible title
    # identity is checked independently from page-one text; accepting a
    # free-form hidden title would create an unnecessary anonymity channel.
    title = single("title")
    if title:
        raise SubmissionReadinessError(
            f"{pdf_name} has nonempty hidden PDF title metadata"
        )

    creator = single("creator")
    if creator and not SAFE_PDF_CREATORS.fullmatch(creator):
        raise SubmissionReadinessError(
            f"{pdf_name} PDF Creator metadata is not an approved tool identity"
        )
    producer = single("producer")
    if producer and not SAFE_PDF_PRODUCERS.fullmatch(producer):
        raise SubmissionReadinessError(
            f"{pdf_name} PDF Producer metadata is not an approved tool identity"
        )
    custom_metadata = single("custom metadata")
    if custom_metadata is not None and custom_metadata.casefold() != "no":
        raise SubmissionReadinessError(
            f"{pdf_name} has unreviewed custom PDF metadata"
        )
    metadata_stream = single("metadata stream")
    if metadata_stream is not None and metadata_stream.casefold() != "no":
        raise SubmissionReadinessError(
            f"{pdf_name} contains an unreviewed PDF metadata stream"
        )
    for key in ("subject", "keywords"):
        value = single(key)
        if value:
            raise SubmissionReadinessError(
                f"{pdf_name} has nonempty hidden PDF {key} metadata"
            )
    for key, values in fields.items():
        compact = re.sub(r"[^a-z]", "", key)
        if compact in {"contributor", "lastmodifiedby"} and any(values):
            raise SubmissionReadinessError(
                f"{pdf_name} has hidden identity-bearing PDF metadata"
            )

    required_values = {
        "javascript": "no",
        "encrypted": "no",
        "form": "none",
        "userproperties": "no",
    }
    for key, expected in required_values.items():
        value = single(key, required=True)
        if value.casefold() != expected:
            raise SubmissionReadinessError(
                f"{pdf_name} has unsafe PDF {key} metadata"
            )
    pages = single("pages", required=True)
    if not re.fullmatch(r"[1-9][0-9]{0,5}", pages):
        raise SubmissionReadinessError(
            f"{pdf_name} has an invalid PDF page count"
        )
    return fields


def _xmp_identity_values(pdf_name: str, xmp_metadata: str):
    if not xmp_metadata.strip():
        return []
    try:
        root = ET.fromstring(xmp_metadata)
    except (ET.ParseError, RecursionError) as error:
        raise SubmissionReadinessError(
            f"{pdf_name} XMP metadata is not well-formed XML"
        ) from error
    values = []
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1].split(":")[-1].casefold()
        for attribute, value in element.attrib.items():
            attribute_name = (
                attribute.rsplit("}", 1)[-1].split(":")[-1].casefold()
            )
            if attribute_name in XMP_IDENTITY_FIELDS:
                values.append(" ".join(html.unescape(value).split()))
        if local_name not in XMP_IDENTITY_FIELDS:
            continue
        pieces = list(element.itertext())
        for descendant in element.iter():
            for attribute, value in descendant.attrib.items():
                attribute_name = (
                    attribute.rsplit("}", 1)[-1].split(":")[-1].casefold()
                )
                if attribute_name == "resource":
                    pieces.append(value)
        normalized = " ".join(html.unescape(" ".join(pieces)).split())
        values.append(normalized)
    return values


class _ActionTargetParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.targets = []

    def handle_starttag(self, _tag, attributes):
        for name, value in attributes:
            if name.casefold() in {"action", "data", "href", "src"} and value:
                self.targets.append(value)

    handle_startendtag = handle_starttag


def _extract_action_targets(pdf_name: str, action_markup: str) -> str:
    parser = _ActionTargetParser()
    try:
        parser.feed(action_markup)
        parser.close()
    except (RecursionError, ValueError) as error:
        raise SubmissionReadinessError(
            f"{pdf_name} action markup could not be parsed"
        ) from error
    return "\n".join(parser.targets)


def _validate_review_document_identity(pdf_name: str, first_page_text: str) -> None:
    contract = REVIEW_DOCUMENT_MARKERS[pdf_name]
    normalized = " ".join(first_page_text.split()).casefold()
    for token in contract["required"]:
        needle = " ".join(token.split()).casefold()
        if not re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", normalized):
            raise SubmissionReadinessError(
                f"{pdf_name} lacks its required first-page document identity"
            )
    for token in contract["forbidden"]:
        needle = " ".join(token.split()).casefold()
        if re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", normalized):
            raise SubmissionReadinessError(
                f"{pdf_name} has the wrong first-page document identity"
            )


def _validate_review_pdf_surfaces(
    pdf_name: str,
    raw: bytes,
    document_info: str,
    xmp_metadata: str,
    extracted_text: str,
    first_page_text: str,
    action_markup: str,
    javascript: str,
) -> None:
    if not raw.startswith(b"%PDF-"):
        raise SubmissionReadinessError(f"{pdf_name} lacks a PDF header")

    _document_info_fields(pdf_name, document_info)
    # The reviewed LaTeX outputs have no XMP metadata stream.  Rejecting every
    # nonempty stream is both simpler and genuinely fail-closed: otherwise an
    # identity can hide in an arbitrary namespace or free-form field that is
    # outside any finite author-tag allowlist.
    if xmp_metadata.strip():
        raise SubmissionReadinessError(
            f"{pdf_name} contains an unreviewed XMP metadata stream"
        )
    if javascript.strip():
        raise SubmissionReadinessError(f"{pdf_name} contains document JavaScript")
    _validate_review_document_identity(pdf_name, first_page_text)
    normalized_visible_text = _normalized_visible_text(extracted_text)
    for description, pattern in FORBIDDEN_CONTENT:
        if pattern.search(normalized_visible_text):
            raise SubmissionReadinessError(
                f"{pdf_name} contains unresolved review text ({description})"
            )

    # Binary streams and XMP commonly contain content-derived PDF IDs, so the
    # generic hexadecimal detector is limited to standard metadata and visible
    # text. Direct path, facility, repository, and email tokens are still
    # forbidden on every inspectable surface.
    _scan_review_surface(
        pdf_name,
        "raw-bytes",
        raw.decode("latin-1"),
        include_digest_pattern=False,
    )
    _scan_review_surface(
        pdf_name,
        "document-info",
        document_info,
        include_digest_pattern=True,
    )
    _scan_review_surface(
        pdf_name,
        "xmp-metadata",
        xmp_metadata,
        include_digest_pattern=False,
    )
    _scan_review_surface(
        pdf_name,
        "extracted-text",
        extracted_text,
        include_digest_pattern=True,
    )
    _scan_review_surface(
        pdf_name,
        "PDF-action-markup",
        _extract_action_targets(pdf_name, action_markup),
        include_digest_pattern=True,
    )


def _validate_attachment_inventory(pdf_name: str, inventory: str) -> None:
    if not re.fullmatch(r"\s*0 embedded files\s*", inventory):
        raise SubmissionReadinessError(
            f"{pdf_name} contains an embedded file or an unknown attachment inventory"
        )


def _run_pdf_tool(executable: str, arguments, pdf_name: str) -> bytes:
    try:
        result = subprocess.run(
            [executable] + list(arguments),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            env={
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.environ.get("PATH", ""),
            },
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SubmissionReadinessError(
            f"{pdf_name}: {Path(executable).name} could not inspect the PDF"
        ) from error
    if result.returncode != 0:
        raise SubmissionReadinessError(
            f"{pdf_name}: {Path(executable).name} failed with status "
            f"{result.returncode}"
        )
    if len(result.stdout) > 128 * 1024 * 1024:
        raise SubmissionReadinessError(
            f"{pdf_name}: {Path(executable).name} emitted excessive output"
        )
    return result.stdout


def audit_review_bundle(path_values) -> None:
    paths = [
        Path(os.path.abspath(os.path.expanduser(os.fspath(value))))
        for value in path_values
    ]
    _validate_review_bundle_paths(paths)
    # Independently enforce the float-flushing source boundary even when the
    # bundle-only action is invoked without the full final-result gate.
    _validate_main_reference_boundary(
        _strip_tex_comments(
            _read_stable_regular(MAIN, label="main paper source")
        )
    )
    _validate_proxy_wrapper(
        _read_stable_regular(PROXY, label="AAAI proxy wrapper")
    )
    pdfinfo = shutil.which("pdfinfo")
    pdftotext = shutil.which("pdftotext")
    pdfdetach = shutil.which("pdfdetach")
    pdftohtml = shutil.which("pdftohtml")
    if not pdfinfo or not pdftotext or not pdfdetach or not pdftohtml:
        raise SubmissionReadinessError(
            "pdfinfo, pdftotext, pdfdetach, and pdftohtml are required for the "
            "review-bundle audit"
        )

    digests = {}
    for path in sorted(paths, key=lambda item: item.name):
        label = path.name
        before = _read_stable_regular_bytes(
            path, 64 * 1024 * 1024, label=label
        )
        _register_review_pdf_digest(digests, label, before)
        document_info = _decode_tool_output(
            _run_pdf_tool(pdfinfo, [str(path)], label),
            f"{label} document info",
        )
        xmp_metadata = _decode_tool_output(
            _run_pdf_tool(pdfinfo, ["-meta", str(path)], label),
            f"{label} XMP metadata",
        )
        extracted_text = _decode_tool_output(
            _run_pdf_tool(
                pdftotext,
                ["-enc", "UTF-8", "-nopgbrk", str(path), "-"],
                label,
            ),
            f"{label} extracted text",
        )
        first_page_text = _decode_tool_output(
            _run_pdf_tool(
                pdftotext,
                [
                    "-f",
                    "1",
                    "-l",
                    "1",
                    "-enc",
                    "UTF-8",
                    "-nopgbrk",
                    str(path),
                    "-",
                ],
                label,
            ),
            f"{label} first-page text",
        )
        action_markup = _decode_tool_output(
            _run_pdf_tool(
                pdftohtml,
                ["-stdout", "-hidden", "-noframes", "-i", str(path)],
                label,
            ),
            f"{label} action markup",
        )
        javascript = _decode_tool_output(
            _run_pdf_tool(pdfinfo, ["-js", str(path)], label),
            f"{label} JavaScript inventory",
        )
        attachments = _decode_tool_output(
            _run_pdf_tool(pdfdetach, ["-list", str(path)], label),
            f"{label} embedded-file inventory",
        )
        _validate_attachment_inventory(label, attachments)
        after = _read_stable_regular_bytes(
            path, 64 * 1024 * 1024, label=label
        )
        if before != after:
            raise SubmissionReadinessError(
                f"{label} changed while external PDF checks were running"
            )
        _validate_review_pdf_surfaces(
            label,
            before,
            document_info,
            xmp_metadata,
            extracted_text,
            first_page_text,
            action_markup,
            javascript,
        )


def _validate_main_reference_boundary(active: str) -> None:
    count = active.count(REFERENCES_START_LABEL)
    if count != 1:
        raise SubmissionReadinessError(
            "paper.tex must contain exactly one active float-flushing "
            "reference boundary"
        )
    if PAGE_COUNTER_MUTATION.search(active):
        raise SubmissionReadinessError(
            "paper.tex must not manipulate the logical page counter"
        )
    if not MAIN_REFERENCE_TAIL.search(active):
        raise SubmissionReadinessError(
            "paper.tex reference boundary must be the exact active document tail"
        )


def _validate_proxy_wrapper(text: str) -> None:
    active = _strip_tex_comments(text)
    if not PROXY_WRAPPER.fullmatch(active):
        raise SubmissionReadinessError(
            "aaai2026-proxy.tex must contain only the reviewed proxy switch "
            "and paper input"
        )


def _validate_source(name: str, text: str, required) -> None:
    active = _strip_tex_comments(text)
    if name == "paper.tex":
        _validate_main_reference_boundary(active)
    for description, pattern in FORBIDDEN_CONTENT:
        match = pattern.search(active)
        if match:
            line = active.count("\n", 0, match.start()) + 1
            raise SubmissionReadinessError(
                f"{name}:{line}: unresolved submission marker ({description})"
            )
    identity_text = active.replace(GENERATED_INPUT, "")
    for description, pattern in FORBIDDEN_IDENTITY:
        match = pattern.search(identity_text)
        if match:
            line = identity_text.count("\n", 0, match.start()) + 1
            raise SubmissionReadinessError(
                f"{name}:{line}: identifying review content ({description})"
            )
    for macro in FORBIDDEN_REVIEW_MACROS:
        if macro in active:
            raise SubmissionReadinessError(
                f"{name}: private provenance macro must not be rendered: {macro}"
            )
    for token in required:
        count = active.count(token)
        if count != 1:
            raise SubmissionReadinessError(
                f"{name}: expected exactly one {token!r}, found {count}"
            )


def _validate_manifest(
    manifest_text: str,
    generated_text: str,
    *,
    expected_generated_sha256: str = EXPECTED_GENERATED_SHA256,
) -> None:
    match = FORBIDDEN_MANIFEST.search(manifest_text)
    if match:
        line = manifest_text.count("\n", 0, match.start()) + 1
        raise SubmissionReadinessError(
            "reproducibility-manifest.md:{}: unresolved finalization marker".format(
                line
            )
        )
    for token in REQUIRED_MANIFEST:
        if manifest_text.count(token) != 1:
            raise SubmissionReadinessError(
                "reproducibility-manifest.md: expected exactly one {!r}".format(
                    token
                )
            )
    for digest in REQUIRED_MANIFEST_DIGESTS:
        if manifest_text.count(digest) != 1:
            raise SubmissionReadinessError(
                "reproducibility-manifest.md: expected exactly one required "
                "audit digest"
            )
    generated_sha256 = hashlib.sha256(generated_text.encode("utf-8")).hexdigest()
    if generated_sha256 != expected_generated_sha256:
        raise SubmissionReadinessError(
            "generated TeX does not match the accepted focused-study bytes"
        )
    if manifest_text.count(generated_sha256) != 1:
        raise SubmissionReadinessError(
            "reproducibility-manifest.md must contain the exact rendered-TeX "
            "SHA-256"
        )


def validate(
    main_text: str,
    supplement_text: str,
    cap_study_text: str,
    manifest_text: str,
    generated_text: str,
    *,
    expected_generated_sha256: str = EXPECTED_GENERATED_SHA256,
) -> None:
    _validate_source("paper.tex", main_text, REQUIRED_MAIN)
    _validate_source("supplement.tex", supplement_text, REQUIRED_SUPPLEMENT)
    _validate_source("cap-study.tex", cap_study_text, REQUIRED_CAP_STUDY)
    _validate_manifest(
        manifest_text,
        generated_text,
        expected_generated_sha256=expected_generated_sha256,
    )


def check_repository() -> None:
    main_text = _read_stable_regular(MAIN, label="main paper source")
    supplement_text = _read_stable_regular(
        SUPPLEMENT, label="supplement source"
    )
    cap_study_text = _read_stable_regular(
        CAP_STUDY, label="focused-study supplement source"
    )
    _validate_proxy_wrapper(
        _read_stable_regular(PROXY, label="AAAI proxy wrapper")
    )
    manifest_text = _read_stable_regular(
        MANIFEST, label="private reproducibility manifest"
    )
    generated_text = _read_stable_regular(
        GENERATED, label="generated result source"
    )
    validate(
        main_text,
        supplement_text,
        cap_study_text,
        manifest_text,
        generated_text,
    )


def _review_bundle_self_test():
    paths = [ROOT / name for name in REVIEW_BUNDLE_FILENAMES]
    _validate_review_bundle_paths(paths)
    safe_raw = b"%PDF-1.7\n% synthetic anonymous review PDF\n"
    safe_info = (
        "Title:          \n"
        "Author:         Anonymous Submission\n"
        "Creator:        LaTeX\n"
        "Producer:       pdfTeX-1.40.18\n"
        "CreationDate:   Wed Aug 12 10:00:00 2026\n"
        "UserProperties: no\n"
        "Form:           none\n"
        "JavaScript:     no\n"
        "Metadata Stream: no\n"
        "Pages:          8\n"
        "Encrypted:      no\n"
    )
    # A prior-work author name and the public system name are legitimate in
    # visible scholarly text; anonymity is enforced through PDF metadata and
    # direct infrastructure/provenance scans, not by suppressing citations.
    safe_text = "SymK builds on prior work by Jendrik Seipp.\n"
    safe_first_page = (
        "Bounding Heuristic Fragmentation with Cofactor Width\n"
        "Anonymous submission\nAbstract\n"
    )
    safe_action_markup = "<html><body>anonymous paper</body></html>"
    _validate_review_pdf_surfaces(
        REVIEW_BUNDLE_FILENAMES[0],
        safe_raw,
        safe_info,
        "",
        safe_text,
        safe_first_page,
        safe_action_markup,
        "",
    )
    _validate_attachment_inventory(REVIEW_BUNDLE_FILENAMES[0], "0 embedded files\n")

    rejected = 0
    bad_name_sets = (
        [ROOT / REVIEW_BUNDLE_FILENAMES[0]],
        [ROOT / REVIEW_BUNDLE_FILENAMES[0]] * 2,
        paths + [ROOT / "reproducibility-manifest.md"],
    )
    for candidate in bad_name_sets:
        try:
            _validate_review_bundle_names(candidate)
        except SubmissionReadinessError:
            rejected += 1
        else:
            raise AssertionError("review-bundle filename adversary was accepted")
    try:
        _validate_review_bundle_paths(
            [Path("/tmp") / name for name in REVIEW_BUNDLE_FILENAMES]
        )
    except SubmissionReadinessError:
        rejected += 1
    else:
        raise AssertionError("out-of-tree review bundle was accepted")
    duplicate_digests = {}
    _register_review_pdf_digest(
        duplicate_digests, REVIEW_BUNDLE_FILENAMES[0], safe_raw
    )
    try:
        _register_review_pdf_digest(
            duplicate_digests, REVIEW_BUNDLE_FILENAMES[1], safe_raw
        )
    except SubmissionReadinessError:
        rejected += 1
    else:
        raise AssertionError("byte-identical review PDFs were accepted")

    surface_mutations = (
        (b"not a PDF", safe_info, "", safe_text, safe_first_page, safe_action_markup, ""),
        (
            safe_raw,
            safe_info.replace("Anonymous Submission", "Named Author"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace("Creator:        LaTeX", "Creator:        Named Author"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace("Creator:        LaTeX", "Creator:        pdfTeX-NamedAuthor"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace("Title:          ", "Title:          Named Author"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info + "Custom Metadata: yes\n",
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace(
                "Producer:       pdfTeX-1.40.18",
                "Producer:       GPL Ghostscript Named Author",
            ),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace(
                "Producer:       pdfTeX-1.40.18",
                "Producer:       pdfTeX-NamedAuthor",
            ),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info.replace("Metadata Stream: no", "Metadata Stream: yes"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw + b"/home/researcher/private",
            safe_info,
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw + b"symbolic-search-heuristics",
            safe_info,
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            'xmlns:alt="http://purl.org/dc/elements/1.1/" '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            "<alt:creator><rdf:Seq><rdf:li>Named Author</rdf:li>"
            "</rdf:Seq></alt:creator></x:xmpmeta>",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>Named Author</dc:title></x:xmpmeta>',
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            'xmlns:pdf="http://ns.adobe.com/pdf/1.3/" '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<pdf:Author rdf:resource="Named Author"/></x:xmpmeta>',
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "cluster=arrhenius",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "institution=https://liu.se",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "file:///home/researcher/private\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "owner@example.org\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "revision deadbeef0123456789abcdef0123456789abcdef\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "github.com/mrlab-ai/repo\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "pending P6\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "RESULT PLACE-\nHOLDER\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text + "symbolic-search-\nheuristics\n",
            safe_first_page,
            safe_action_markup,
            "",
        ),
        (safe_raw, safe_info, "", safe_text, "Supplementary Material", safe_action_markup, ""),
        (
            safe_raw,
            safe_info,
            "",
            safe_text,
            safe_first_page,
            '<a href="file%3A%2F%2F%2Fhome%2Fresearcher%2Fprivate">x</a>',
            "",
        ),
        (
            safe_raw,
            safe_info,
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "app.alert('x')",
        ),
        (
            safe_raw,
            safe_info.replace("Encrypted:      no", "Encrypted:      yes"),
            "",
            safe_text,
            safe_first_page,
            safe_action_markup,
            "",
        ),
    )
    for raw, info, xmp, text, first_page, action_markup, javascript in surface_mutations:
        try:
            _validate_review_pdf_surfaces(
                REVIEW_BUNDLE_FILENAMES[0],
                raw,
                info,
                xmp,
                text,
                first_page,
                action_markup,
                javascript,
            )
        except SubmissionReadinessError:
            rejected += 1
        else:
            raise AssertionError("review-PDF identity adversary was accepted")
    try:
        _validate_attachment_inventory(
            REVIEW_BUNDLE_FILENAMES[0],
            "1 embedded files\n1: private-source.zip\n",
        )
    except SubmissionReadinessError:
        rejected += 1
    else:
        raise AssertionError("embedded review-PDF file was accepted")
    return rejected


def self_test():
    reference_tail = (
        "\\clearpage\n"
        + REFERENCES_START_LABEL
        + "\n\\ifdefined\\ICAPSAAAIProxy\n"
        + "\\else\n  \\bibliographystyle{plainnat}\n\\fi\n"
        + "\\bibliography{bib/abbrv,bib/literatur,bib/crossref}\n"
        + "\\end{document}\n"
    )
    main = (
        "\n".join(REQUIRED_MAIN)
        + "\nfinal census accepted\n"
        + reference_tail
    )
    supplement = "\n".join(REQUIRED_SUPPLEMENT) + "\nfinal census accepted\n"
    cap_study = "\n".join(REQUIRED_CAP_STUDY) + "\nfinal tables accepted\n"
    generated = "\\newcommand{\\CapFixtureValue}{1}\n"
    generated_sha = hashlib.sha256(generated.encode("utf-8")).hexdigest()
    manifest = (
        "\n".join(REQUIRED_MANIFEST)
        + "\n"
        + "\n".join(REQUIRED_MANIFEST_DIGESTS)
        + "\nrendered TeX SHA-256 "
        + generated_sha
        + "\n"
    )

    def validate_fixture(candidate):
        validate(
            *candidate,
            expected_generated_sha256=generated_sha,
        )

    base = (main, supplement, cap_study, manifest, generated)
    validate_fixture(base)
    rejected = 0
    _validate_proxy_wrapper(
        "% reviewed wrapper\n\\def\\ICAPSAAAIProxy{1}\n"
        "\\input{paper.tex}\n"
    )
    for bad_wrapper in (
        "\\setcounter{page}{1}\n\\def\\ICAPSAAAIProxy{1}\n"
        "\\input{paper.tex}\n",
        "\\def\\ICAPSAAAIProxy{1}\n\\input{other.tex}\n",
    ):
        try:
            _validate_proxy_wrapper(bad_wrapper)
        except SubmissionReadinessError:
            rejected += 1
        else:
            raise AssertionError("proxy-wrapper adversary was accepted")
    mutations = [
        (main + "RESULT PLACEHOLDER\n", supplement, cap_study, manifest, generated),
        (main + "synthetic results\n", supplement, cap_study, manifest, generated),
        (main + "pending P6\n", supplement, cap_study, manifest, generated),
        (main + "preliminary results\n", supplement, cap_study, manifest, generated),
        (
            main + "before any structural value was inspected\n",
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (main + "Arrhenius\n", supplement, cap_study, manifest, generated),
        (main + "ARRHENIUS\n", supplement, cap_study, manifest, generated),
        (main + "arrhenius\n", supplement, cap_study, manifest, generated),
        (main + "nobackup\n", supplement, cap_study, manifest, generated),
        (
            main + "symbolic-search-heuristics\n",
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (main, supplement + "revision deadbeef0\n", cap_study, manifest, generated),
        (main, supplement, cap_study + "rehearsal values\n", manifest, generated),
        (main, supplement, cap_study + "revision deadbeef0\n", manifest, generated),
        (
            main + "The pending\n1,377-task full-suite census remains unresolved\n",
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            "\n".join("% " + line for line in REQUIRED_MAIN) + "\n",
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            main,
            "\n".join("% " + line for line in REQUIRED_SUPPLEMENT) + "\n",
            cap_study,
            manifest,
            generated,
        ),
        (
            main,
            supplement,
            "\n".join("% " + line for line in REQUIRED_CAP_STUDY) + "\n",
            manifest,
            generated,
        ),
        (main, supplement, cap_study, manifest + "pending\n", generated),
        (
            main,
            supplement,
            cap_study,
            manifest.replace(generated_sha, "3" * 64),
            generated,
        ),
        (main, supplement, cap_study, manifest, generated + "% drift\n"),
        (
            main,
            supplement,
            cap_study,
            manifest.replace(REQUIRED_MANIFEST[2], "0" * 64),
            generated,
        ),
        (
            main,
            supplement,
            cap_study,
            manifest.replace(REQUIRED_MANIFEST_DIGESTS[0], "0" * 64),
            generated,
        ),
        (
            main.replace("\\clearpage\n", "", 1),
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            main.replace(
                REFERENCES_START_LABEL,
                REFERENCES_START_LABEL + "\nbody after boundary",
                1,
            ),
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            main.replace("\\end{document}", "body after bibliography\n\\end{document}"),
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            main.replace(
                "\\clearpage",
                "\\setcounter{page}{1}\n\\clearpage",
                1,
            ),
            supplement,
            cap_study,
            manifest,
            generated,
        ),
        (
            main.replace(
                REFERENCES_START_LABEL,
                REFERENCES_START_LABEL + "\n" + REFERENCES_START_LABEL,
                1,
            ),
            supplement,
            cap_study,
            manifest,
            generated,
        ),
    ]
    mutations.extend(
        (main.replace(token, ""), supplement, cap_study, manifest, generated)
        for token in REQUIRED_MAIN
    )
    mutations.extend(
        (main, supplement.replace(token, ""), cap_study, manifest, generated)
        for token in REQUIRED_SUPPLEMENT
    )
    mutations.extend(
        (main, supplement, cap_study.replace(token, ""), manifest, generated)
        for token in REQUIRED_CAP_STUDY
    )
    mutations.extend(
        (main, supplement, cap_study, manifest.replace(token, ""), generated)
        for token in REQUIRED_MANIFEST
    )
    mutations.extend(
        (main, supplement, cap_study, manifest.replace(digest, ""), generated)
        for digest in REQUIRED_MANIFEST_DIGESTS
    )
    mutations.extend(
        (main + macro + "\n", supplement, cap_study, manifest, generated)
        for macro in FORBIDDEN_REVIEW_MACROS
    )
    mutations.extend(
        (main, supplement + macro + "\n", cap_study, manifest, generated)
        for macro in FORBIDDEN_REVIEW_MACROS
    )
    mutations.extend(
        (main, supplement, cap_study + macro + "\n", manifest, generated)
        for macro in FORBIDDEN_REVIEW_MACROS
    )
    for candidate in mutations:
        try:
            validate_fixture(candidate)
        except SubmissionReadinessError:
            rejected += 1
        else:
            raise AssertionError("submission-readiness adversary was accepted")
    review_rejected = _review_bundle_self_test()
    return {
        "self_test": "PASS",
        "adversaries_rejected": rejected,
        "review_bundle_adversaries_rejected": review_rejected,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--self-test", action="store_true")
    actions.add_argument(
        "--review-bundle",
        nargs="+",
        metavar="PDF",
        help="Audit the provisional two-PDF double-blind review bundle.",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True, separators=(",", ":")))
        return 0
    if args.review_bundle is not None:
        try:
            audit_review_bundle(args.review_bundle)
        except (OSError, SubmissionReadinessError) as error:
            print(f"review bundle: BLOCKED: {error}", file=sys.stderr)
            return 2
        print(
            "review bundle: READY ({})".format(
                ", ".join(REVIEW_BUNDLE_FILENAMES)
            )
        )
        return 0
    try:
        check_repository()
    except (OSError, SubmissionReadinessError) as error:
        print(f"submission readiness: BLOCKED: {error}", file=sys.stderr)
        return 2
    print("submission readiness: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
