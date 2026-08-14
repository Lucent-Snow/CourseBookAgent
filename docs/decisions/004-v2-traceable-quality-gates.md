# ADR-004: V2 可追溯生成与严格质量门禁

## Status

Superseded — 门禁核心已并入主流程（见 ADR-006），v2.py 试点已删除。

## Context

V1 successfully generated a 14-lecture book, but its `--force` run reused an old fallback BookPlan. The reused plan lacked component definitions and writer guidance. LLM review could report missing coverage while the workflow still marked a chapter successful. Several output failures followed:

- ASR uncertainty was silently normalized or turned into unsupported numerical claims.
- Example objects were converted to Python-dict text in Markdown.
- Unknown component names leaked into the reader.
- Topic, method, mixed, and review chapters were written with one unconstrained shape.
- Derived files were overwritten in shared cache locations, obscuring provenance.

## Decision

V2 adds a profile-driven, isolated workflow.

### Versioned course profile

A checked-in profile under `coursebook_agent/profiles/` defines the course theme, target reader, teaching goal, canonical terms with ASR aliases, a conservative ASR policy, and templates for `core`, `guest`, `review`, and `mixed` chapters.

### Traceable normalization

The source transcript remains immutable. V2 writes raw chunks, normalized chunks, and one correction record per automatic alias replacement. Only explicit aliases in the Profile may be normalized automatically. Uncertain values, formulae, and names must be flagged instead of guessed.

### Isolated runs

Every V2 run writes to `data/runs/<course>-<profile-version>-<timestamp>/`, including profile snapshot, raw/normalized chunks, corrections, digests, plan, chapter drafts, reviews, outputs, and a quality report. V2 never reads V1 chapter or plan caches.

### Chapter templates and gates

Profiles set section ranges, body length ranges, required components, and intended structure per chapter type. Deterministic gates validate source links, time ranges, components, length, section count, learning goals, mistakes, and machine-residue. An LLM reviewer receives the contract, source evidence, and draft; unsupported claims, missing coverage, and ASR uncertainty reject the draft. A rejected chapter is revised at most twice and never marked accepted merely because it rendered.

## Consequences

- A full run costs more LLM calls and may surface more rejected chapters initially.
- A successful process status is no longer a quality claim; only `accepted` chapters may enter a final V2 book.
- Profile maintenance becomes a deliberate editorial task and is versioned alongside code.
- V1 endpoints continue serving the prior demo book until a full V2 book has passed its gates.
