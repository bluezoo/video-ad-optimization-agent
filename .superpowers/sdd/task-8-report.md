# Task 8: Demo Scenario F5.2 + Phase-Doc Bookkeeping — Implementation Report

**BASE SHA:** 1bee8f1

## Overview

Task 8 is the final task of workstream 09. It consists of two steps:
1. Append Scene F5.2 (non-fashion video generation scenario) to `docs/demo-scenarios/fashion.md`
2. Add a provenance note to the 09 phase doc marking the xfail narrowing (Task 7 / DISCOVERY 3) as complete

## Implementation

### Step 1: Append Scene F5.2

Adding the non-fashion video generation scenario to `docs/demo-scenarios/fashion.md`:

```markdown
### Scene F5.2 — non-fashion video generation (workstream 09)

**Query:** "Generate a video for the Aurora cold brew using a studio setting"

**Expected tool calls:**
- `generate_video_from_product` or `generate_video_with_variation` for the
  aurora-cold-brew-330ml product (campaign resolved from F5.1's campaign or
  created on the fly). Stage 1 + Stage 2 run (~1-4 min).

**Pass criteria (check the trace, not prose):**
- The scene/creative prompt visible in the trace (or the tool's debug output)
  contains NONE of: "fashion", "garment", "wearing", "model wearing",
  "she is" (case-insensitive) — it must read as a product-centric hero shot
  (condensation/appetite cues for the beverage archetype).
- The tool response surfaces `reference_image_used: false` with a warning that
  no product image exists (retail SKUs ship without images until Phase 14a/15)
  — generation still succeeds from the text description.
- Video registered with status generated/pending review; filename derives from
  a product-centric variation name (e.g. `beverage-studio-elegant`), NOT an
  ethnicity-prefixed name.
- FAIL if: a human model appears in the prompt text, any exception in the
  trace, or the old fashion preamble ("model wearing this exact garment")
  appears anywhere.
```

### Step 2: Phase-Doc Provenance Note

Adding a line to mark DISCOVERY 3's xfail narrowing as complete in the 09 phase doc.
The discovery was that Phase 2's xfail narrowing didn't happen initially, but is now
folded into this workstream (Task 7).

## Test Execution

Running the exact commands from the task:
