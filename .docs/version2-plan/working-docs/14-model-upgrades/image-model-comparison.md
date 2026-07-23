# Image-model comparison: gemini-3-pro-image vs gemini-3.1-flash-lite-image (Phase 14a)

Run date: 2026-07-22, Vertex AI (`GOOGLE_CLOUD_LOCATION=global`), google-genai 2.14.0.
Harness: `scripts/compare_image_models.py`; raw outputs + `metrics.json` under
`generated/model-comparison/` (gitignored, local only).

Cases mirror the three call shapes sharing the `IMAGE_GENERATION` knob:

- **fashion-scene** — Stage-1 wearable scene prompt (`build_scene_image_prompt`,
  sage-satin-camisole, category `top` → wearable archetype), modalities `["image", "text"]`.
- **retail-scene** — Stage-1 non-wearable (aurora-cold-brew-330ml, `beverage` →
  consumable-hero archetype), same modalities.
- **chart-16x9** — the metrics_tools/maps_tools infographic shape: `["IMAGE"]` +
  `ImageConfig(aspect_ratio="16:9")`.
- **fashion-scene-with-reference** — the wearable branch's reference-image path
  (`video_tools.py` `generate_scene_image`): product PNG attached as a Part + fidelity
  preamble. The reference image WAS reachable this run (GCS `product-images/`
  bucket, `sage-satin-camisole.png`, 5.5 MB), so the comparison is with-reference
  on both models symmetrically — the referenceless fallback described in the
  harness docstring was not needed.

## Metrics

| Model | Case | Resolution | Bytes | Latency (s) |
|---|---|---|---|---|
| gemini-3-pro-image | fashion-scene | 768x1376 | 1,352,742 | 22.7 |
| gemini-3-pro-image | retail-scene | 768x1376 | 1,124,129 | 26.9 |
| gemini-3-pro-image | chart-16x9 | 1376x768 | 1,224,305 | 20.9 |
| gemini-3-pro-image | fashion-scene-with-reference | 768x1376 | 1,386,976 | 23.8 |
| gemini-3.1-flash-lite-image | fashion-scene | 768x1376 | 104,502 | 3.8 |
| gemini-3.1-flash-lite-image | retail-scene | 768x1376 | 109,848 | 3.1 |
| gemini-3.1-flash-lite-image | chart-16x9 | 1376x768 | 97,162 | 2.8 |
| gemini-3.1-flash-lite-image | fashion-scene-with-reference | 768x1376 | 77,945 | 6.8 |

Both models return the same resolutions (≈1MP, the "1K" pricing tier: 768x1376
portrait for scenes, 1376x768 for the 16:9 chart). Lite is 6-8x faster and its
PNGs are ~10x smaller (heavier compression / less micro-detail, see notes).

## Visual inspection notes (one generation per case — n=1, treat as directional)

**fashion-scene (referenceless).** Both correct: sage green satin camisole with
lace trim on a walking female model, studio-loft setting. Pro is more polished —
tighter framing, crisper satin sheen and lace detail, cleaner facial rendering.
Lite is softer/more diffuse (visibly lower micro-detail, consistent with the 10x
smaller file), garment reads slightly matte, and it added un-prompted props
(handbag strap, clothing rack) — coherent but busier. No text artifacts in either.

**retail-scene.** Both nail the product: matte black 330ml can, aurora-gradient
accents, condensation, coffee-bean staging. Label text is fully legible in both
("Aurora Cold Brew 330ml" pro; "AURORA COLD BREW COFFEE ... 330ml" lite — lite
invented extra label copy: "PREMIUM SMALL BATCH", "ROASTED IN LONDON"). Pro's
composition is cleaner/minimal; lite's is warmer and busier (extra cup of iced
coffee with garnish). Product-text rendering: no misspellings in either. Tie on
usability; pro closer to the prompt's minimal intent.

**chart-16x9.** Clear pro win. Pro: single title, three correctly-labeled bars,
all three values rendered exactly (0.0605 / 0.0595 / 0.0589), proportional bar
lengths, clean axis (0.0000-0.0700), legible legend — usable as-is. Lite:
duplicated title (rendered twice), inconsistent value labels ("0.0605" but
"0.0595 RPI" / "0.0589 RPI"), un-prompted thumbnail icons colliding with the
y-axis labels, stray gridline artifacts outside the plot area, odd axis
terminus (0.0650). Legible but visibly flawed — below the bar for
dashboard/chart output.

**fashion-scene-with-reference.** Mixed, and the most interesting result. The
reference PNG is a cowl-neck sage satin camisole (a top). Lite kept the garment
a camisole — correct silhouette and cowl neckline vs the reference, slightly
lighter/greyer color, added small gold strap hardware not in the reference.
Pro rendered a beautiful image but **extended the garment into a full-length
slip dress** (lace band at the hip, lace hem) — a silhouette fidelity miss
against the reference, despite the "must be wearing this exact garment"
preamble. Pro's fabric/color fidelity is otherwise the best of any output.
n=1: this is a flag to watch in Stage-1 QA, not a verdict.

## Pricing (link-checked 2026-07-22 — do not treat figures as pinned)

Source: https://cloud.google.com/vertex-ai/generative-ai/pricing (live at run time).

- **gemini-3-pro-image**: $120 / 1M output tokens (Standard only); a 1K/2K image
  is 1120 output tokens ≈ **$0.134/image**. Input $2 / 1M tokens (560 tokens per
  input image).
- **gemini-3.1-flash-lite-image**: $30 / 1M output tokens Standard ($15 batch);
  a 1K image is 1120 tokens ≈ **$0.034/image**. Input $0.25 / 1M tokens.

Observed cost framing: at both models' actual output resolution here (1K tier),
lite is ~4x cheaper per image and 6-8x faster. At this project's demo-scale
volumes the absolute difference is cents per session; latency is the more
user-visible gap (3s vs 21-27s per Stage-1 image).

## Recommendation: keep `gemini-3-pro-image` default

Reasons:

1. **Chart shape disqualifies lite as the shared-knob default.** The
   `IMAGE_GENERATION` knob feeds four call sites across three agents, including
   the metrics/maps infographic path — lite's chart output (duplicate title,
   inconsistent labels, layout artifacts) is not client-demo quality; pro's is.
2. **Pro is the overall quality ceiling** on the Stage-1 scene shapes too
   (sharper product/fabric rendering, cleaner compositions, fewer un-prompted
   additions), and Stage-1 frames seed Veo — quality compounds downstream.
3. **The cost/latency win doesn't bind at current scale.** ~$0.10/image saved
   and ~20s faster matters at production volume, not at demo volume.
4. **n=1 caveat cuts both ways**: pro's with-reference silhouette miss
   (camisole→dress) is the one quality flag against it, but a single sample
   isn't grounds to churn the default; it is worth re-checking whenever Stage-1
   fidelity QA comes up.

If image cost/latency ever becomes a binding constraint, the evidence here
supports a **split-knob** shape as the escape hatch — Stage-1 scenes to
`gemini-3.1-flash-lite-image` (acceptable quality, big latency win), charts
stay on `gemini-3-pro-image` — rather than a wholesale switch. No code change
is made from this evaluation; per the plan, any default change is an owner
decision on this evidence.
