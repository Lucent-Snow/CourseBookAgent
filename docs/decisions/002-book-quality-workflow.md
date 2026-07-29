# ADR-002: Book-quality multi-agent workflow

## Status

Accepted (experimental, iterative)

## Context

The subtitle-only MVP already produces 14 readable lecture notes, but the coursebook still feels like a stack of independent lecture summaries:

- no whole-book spine or learning path
- almost no chapter-to-chapter bridges
- no teaching-aid emphasis (learning goals, key points, common mistakes)
- glossary is a naive concept dump
- review talks / guest lectures are treated like core method chapters

A teaching-aid book (教辅) is not a transcript cleanup. It must feel intentional:

1. a learner can see the whole course map
2. each chapter knows what came before and what comes next
3. knowledge is complete enough for review, but prioritised
4. examples and pitfalls are first-class, not afterthoughts
5. terminology is stable across the book

Context limits prevent one model call from reading every transcript. Therefore quality must come from workflow, not from stuffing more text into one prompt.

## Decision

Introduce a three-layer editorial workflow:

1. **Editor-in-chief / book blueprint**
   - reads compressed lecture digests, not full transcripts
   - outputs course spine, module groups, chapter roles, bridges, canonical terms, emphasis map
2. **Chapter writer with book context**
   - still grounded in one lecture's timed chunks
   - receives the blueprint slice + previous chapter bridge/summary
   - writes a teaching-aid chapter, not a standalone lecture note
3. **Book synthesizer**
   - unifies terminology
   - writes front matter / knowledge map
   - soft-repairs remaining discontinuity
   - builds a usable glossary and key-point index

## Non-goals

- inventing textbook content not present in class
- PPT alignment in this iteration
- chat / quiz products

## Quality bar

Ask of every draft:

> If this were a real teaching-aid book for this course, would I trust it to help me revise?

Fail conditions:

- chapters could be shuffled with little damage
- key method chapters omit procedure or decision rules
- repeated concepts contradict each other
- guest/review lectures drown the core method path without role labels

## Experiment protocol

1. Keep v1 artifacts under `data/output/` as baseline.
2. Generate book plan from existing digests.
3. Regenerate a critical arc first (hypothesis testing → ANOVA entry).
4. Score v1 vs v2 with a fixed rubric before full-course regeneration.
