# Workstream 14 (combined): Model Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Documented image-model comparison (14a), consolidated+tested Veo polling plus a prototype-gated Omni Flash evaluation (14b), and the agent default flipped to `gemini-3.6-flash` (pulled forward from Phase 16 step 3) — three independently verified, sequentially committed tracks on one branch.

**Architecture:** Evaluation-first for 14a (scripts only, no app code unless the owner approves a default change on the evidence). For 14b, a pure refactor extracts one shared async poll/extract helper pair used by all three Veo call sites (exception-raising helper; `generate_video_ad` maps exceptions to its existing DB-update semantics at the call site), then a real Interactions-API prototype gates whether any Omni backend code gets built. Task C is a config-default flip with its documented touch-points.

**Tech Stack:** google-genai SDK (worktree venv: 2.14.0), Vertex AI (`GOOGLE_CLOUD_LOCATION=global`), pytest, PIL.

## Global Constraints

- Golden prompt files stay **byte-identical**: `tests/unit/data/golden_scene_prompt_product1_asian.txt`, `tests/unit/data/golden_creative_prompt_product1_asian.txt`; `app/tools/prompt_builders.py` is untouched by every task. `tests/unit/test_product_adapter.py::TestGoldenPrompts` green at every commit.
- Veo stays the default video backend: `VIDEO_GEN_MODEL = os.environ.get("VIDEO_GEN_MODEL", "veo-3.1-generate-001")` (app/config.py:71) is not changed by any task.
- `IMAGE_GENERATION` default (`gemini-3-pro-image`, app/config.py:70) is not changed by any task — a switch is an owner decision on Task 1's evidence, outside this plan.
- Existing tests are unmodified EXCEPT the one authorized edit: `tests/unit/test_config.py:23` `"gemini-3.5-flash"` → `"gemini-3.6-flash"` (Task 5). Any other existing-test change requires controller authorization first.
- `generate_video_ad`'s local-mode save path (raw `open()` into `GENERATED_DIR`, video_tools.py:1077-1082) is preserved byte-for-byte — the Task 2 refactor stops at poll+extract.
- No `Co-Authored-By`/AI-attribution trailers in commits or PR bodies. `README.md` untouched. Relative imports inside `app/`. Ruff-clean on touched files only.
- Live runs (comparison, prototype, scenarios): `set -a; source app/.env; set +a` then `export GCS_BUCKET=` (empty) for anything exercising app tool paths in demo mode; scripts that only call the SDK directly may run with the env as-is. All media outputs go under gitignored dirs (`generated/`, `/tmp`) — never committed.
- STATUS.md is edited only in the main checkout (controller does this); WORK_LOG.md is branch-side (`.docs/version2-plan/working-docs/14-model-upgrades/WORK_LOG.md`).
- New/adjusted manual-testing journeys go in root `DEMO_GUIDE.md` under a new `### Workstream 14` heading (ws11a owner rule).

---

### Task 1: Image-model side-by-side comparison (14a)

**Files:**
- Create: `scripts/compare_image_models.py`
- Create: `.docs/version2-plan/working-docs/14-model-upgrades/image-model-comparison.md`
- Modify: `.docs/version2-plan/working-docs/14-model-upgrades/WORK_LOG.md` (append Q14 evidence)

**Interfaces:**
- Consumes: `app.tools.prompt_builders.build_scene_image_prompt(product: dict, variation: CreativeVariation) -> str`; `app.models.variation.CreativeVariation(name=...)`; `google.genai.Client().models.generate_content(...)`.
- Produces: `generated/model-comparison/<model>/<case>.png` + `generated/model-comparison/metrics.json` (local only, gitignored), and the committed comparison doc. No app code changes.

- [ ] **Step 1: Write the comparison script**

```python
"""Side-by-side image-model comparison for Phase 14a.

Compares gemini-3-pro-image (current default) vs gemini-3.1-flash-lite-image
(Nano Banana 2 Lite) across the call shapes that share the IMAGE_GENERATION
knob: Stage-1 scene images (fashion wearable + retail-core non-wearable) and
the chart/infographic shape (IMAGE-only modalities, 16:9) used by
metrics_tools/maps_tools.

Run from the repo root with app/.env loaded:

    set -a; source app/.env; set +a
    .venv/bin/python scripts/compare_image_models.py

Outputs PNGs + metrics.json under generated/model-comparison/ (gitignored).
"""

import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from PIL import Image  # noqa: E402

from app.models.variation import CreativeVariation  # noqa: E402
from app.tools.prompt_builders import build_scene_image_prompt  # noqa: E402

MODELS = ["gemini-3-pro-image", "gemini-3.1-flash-lite-image"]
OUT_DIR = Path(__file__).resolve().parent.parent / "generated" / "model-comparison"

FASHION_PRODUCT = {
    "name": "sage-satin-camisole",
    "details": "A sage green satin camisole with delicate lace trim",
    "category": "summer",
    "color": "sage green",
    "fabric": "satin",
}
RETAIL_PRODUCT = {
    "name": "aurora-cold-brew-330ml",
    "details": "A sleek 330ml can of Aurora cold brew coffee, matte black with aurora-gradient accents",
    "category": "beverage",
    "color": "matte black",
}
CHART_PROMPT = (
    "A clean 16:9 infographic for a retail dashboard titled 'RPI Across Creatives'. "
    "A horizontal bar chart with three bars labeled studio-minimalist (0.0605), "
    "golden-hour-rooftop (0.0595), urban-street (0.0589), axis label "
    "'Revenue per Impression (USD)', legible sans-serif text, light background."
)


def scene_case(product: dict) -> tuple[str, dict]:
    variation = CreativeVariation(name="model-comparison")
    prompt = build_scene_image_prompt(product, variation)
    return prompt, {"response_modalities": ["image", "text"]}


def chart_case() -> tuple[str, dict]:
    return CHART_PROMPT, {
        "response_modalities": ["IMAGE"],
        "image_config": types.ImageConfig(aspect_ratio="16:9"),
    }


CASES = {
    "fashion-scene": scene_case(FASHION_PRODUCT),
    "retail-scene": scene_case(RETAIL_PRODUCT),
    "chart-16x9": chart_case(),
}


def reference_case() -> tuple[list, dict] | None:
    """Fashion scene WITH a reference product image, mirroring
    generate_scene_image's wearable branch (video_tools.py:233-254). Returns
    None when no reference image is reachable (local-first with no bundle) —
    then both models are compared referenceless, symmetrically, and the doc
    must say so."""
    try:
        from app import storage

        filename = "sage-satin-camisole.png"
        if not storage.product_image_exists(filename):
            return None
        image_bytes = storage.read_product_image(filename)
    except Exception:
        return None
    prompt, cfg = scene_case(FASHION_PRODUCT)
    preamble = (
        "Use the provided image as the exact visual reference for the garment. "
        "The model must be wearing this exact garment.\n\n"
    )
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        preamble + prompt,
    ]
    return contents, cfg


_ref = reference_case()
if _ref is not None:
    CASES["fashion-scene-with-reference"] = _ref
else:
    print("NOTE: no reference product image reachable — with-reference case skipped, "
          "comparison is referenceless for both models (record this in the doc)")


def extract_image_bytes(response) -> bytes | None:
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    return None


def main() -> int:
    client = genai.Client()
    metrics: dict[str, dict] = {}
    for model in MODELS:
        (OUT_DIR / model).mkdir(parents=True, exist_ok=True)
        for case, (prompt, cfg) in CASES.items():
            t0 = time.monotonic()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg),
            )
            latency = round(time.monotonic() - t0, 1)
            image_bytes = extract_image_bytes(response)
            if image_bytes is None:
                metrics[f"{model}/{case}"] = {"error": "no image returned", "latency_s": latency}
                print(f"FAIL  {model} {case}: no image ({latency}s)")
                continue
            out_path = OUT_DIR / model / f"{case}.png"
            out_path.write_bytes(image_bytes)
            with Image.open(io.BytesIO(image_bytes)) as im:
                resolution = f"{im.width}x{im.height}"
            metrics[f"{model}/{case}"] = {
                "bytes": len(image_bytes),
                "resolution": resolution,
                "latency_s": latency,
                "path": str(out_path),
            }
            print(f"OK    {model} {case}: {resolution}, {len(image_bytes)} bytes, {latency}s")
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nMetrics written to {OUT_DIR / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the real API**

Run: `set -a; source app/.env; set +a; .venv/bin/python scripts/compare_image_models.py`
Expected: 6 `OK` lines (2 models × 3 cases) — 8 when a reference product image is reachable and the with-reference case activates — and `metrics.json` written. (Pricing note per phase doc: link-check current per-image pricing at evaluation time rather than pinning dollar figures.)

- [ ] **Step 3: Visually inspect all six PNGs** (Read tool on each `generated/model-comparison/<model>/<case>.png`) and grade per case: subject correctness, text legibility (chart case especially), artifacting.

- [ ] **Step 4: Write the comparison doc**

Create `.docs/version2-plan/working-docs/14-model-upgrades/image-model-comparison.md` containing: the metrics table (model × case: resolution, bytes, latency), the visual-inspection notes per case, a pricing-page link and observed cost framing, and a **recommendation section** ending in one of: "keep `gemini-3-pro-image` default" / "switch default" / "split the knob (charts stay pro)" — with reasons. Do not change any default in code regardless of the recommendation.

- [ ] **Step 5: Append Q14 evidence to WORK_LOG**

Append to `WORK_LOG.md`: the observed resolutions per model/case (Q14 asks whether 1K output is acceptable for in-store screens/dashboard previews) and a pointer to the comparison doc.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/ruff check scripts/compare_image_models.py` → clean.
```bash
git add scripts/compare_image_models.py .docs/version2-plan/working-docs/14-model-upgrades/
git commit -m "feat(14a): image-model side-by-side comparison harness + documented results"
```

---

### Task 2: Consolidate Veo polling + result extraction (14b step 1)

**Files:**
- Modify: `app/tools/video_tools.py` (add helpers after `generate_scene_image`, i.e. around line 270; convert three call sites at :320-362, :615-642, :998-1071; add `import asyncio` to the stdlib import block at :35-39)
- Test: `tests/unit/test_veo_polling.py` (new)

**Interfaces:**
- Consumes: existing call sites' `client` (google-genai `Client`) and `operation` objects from `client.models.generate_videos(...)`.
- Produces (used by Task 4's positive branch as the Veo-side normalization point):
  - `async def _wait_for_veo_operation(client, operation, *, max_wait_time: int = 600, poll_interval: int = 20, debug_label: str = "veo")` → returns the completed operation; raises `TimeoutError` on timeout, `ValueError` when the operation completes with no `result.generated_videos`.
  - `def _extract_video_bytes(client, generated_video) -> bytes` → Vertex inline bytes or Developer-API download; raises `ValueError` if Vertex returns empty bytes.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the consolidated Veo polling/extraction helpers (Phase 14b step 1).

These are the first tests ever covering the polling paths — previously
triplicated inline with zero coverage.
"""

import sqlite3

import pytest

import app.tools.video_tools as video_tools


class FakeVideo:
    def __init__(self, video_bytes=b"mp4-bytes"):
        self.video_bytes = video_bytes


class FakeGeneratedVideo:
    def __init__(self, video_bytes=b"mp4-bytes"):
        self.video = FakeVideo(video_bytes)


class FakeResult:
    def __init__(self, videos):
        self.generated_videos = videos


class FakeOperation:
    """Completes after `completes_after` polls; result set on completion."""

    def __init__(self, completes_after=0, result="ok"):
        self._polls_remaining = completes_after
        self._result_kind = result
        self.done = completes_after == 0

    @property
    def result(self):
        if self._result_kind == "ok":
            return FakeResult([FakeGeneratedVideo()])
        if self._result_kind == "empty":
            return FakeResult([])
        return None


class FakeClient:
    def __init__(self):
        self.polls = 0
        self.operations = None  # installed by make_client


def make_client(op: FakeOperation) -> FakeClient:
    client = FakeClient()

    class Ops:
        @staticmethod
        def get(operation):
            client.polls += 1
            op._polls_remaining -= 1
            if op._polls_remaining <= 0:
                op.done = True
            return op

    client.operations = Ops()
    return client


@pytest.fixture(autouse=True)
def instant_sleep(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(video_tools.asyncio, "sleep", _no_sleep)


class TestWaitForVeoOperation:
    @pytest.mark.asyncio
    async def test_success_after_polls(self):
        op = FakeOperation(completes_after=3)
        client = make_client(op)
        done = await video_tools._wait_for_veo_operation(client, op)
        assert done.done is True
        assert client.polls == 3
        assert done.result.generated_videos

    @pytest.mark.asyncio
    async def test_already_done_no_polls(self):
        op = FakeOperation(completes_after=0)
        client = make_client(op)
        done = await video_tools._wait_for_veo_operation(client, op)
        assert client.polls == 0
        assert done is op

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        op = FakeOperation(completes_after=10_000)
        client = make_client(op)
        with pytest.raises(TimeoutError, match="timed out after 600"):
            await video_tools._wait_for_veo_operation(client, op)
        # 600s budget / 20s interval = 30 polls exactly
        assert client.polls == 30

    @pytest.mark.asyncio
    async def test_empty_result_raises_valueerror(self):
        op = FakeOperation(completes_after=1, result="empty")
        client = make_client(op)
        with pytest.raises(ValueError, match="no result"):
            await video_tools._wait_for_veo_operation(client, op)

    @pytest.mark.asyncio
    async def test_none_result_raises_valueerror(self):
        op = FakeOperation(completes_after=1, result="none")
        client = make_client(op)
        with pytest.raises(ValueError, match="no result"):
            await video_tools._wait_for_veo_operation(client, op)


class TestExtractVideoBytes:
    def test_vertex_inline_bytes(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        out = video_tools._extract_video_bytes(object(), FakeGeneratedVideo(b"abc"))
        assert out == b"abc"

    def test_vertex_empty_bytes_raises(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        with pytest.raises(ValueError, match="No video_bytes"):
            video_tools._extract_video_bytes(object(), FakeGeneratedVideo(b""))


class TestGenerateVideoAdTimeoutSemantics:
    """generate_video_ad must keep its DB-update + error-dict timeout behavior
    (it maps the helper's exceptions at the call site instead of raising)."""

    @pytest.mark.asyncio
    async def test_timeout_marks_ad_failed_and_returns_error(
        self, fresh_test_db, monkeypatch
    ):
        import io as _io

        from PIL import Image as PILImage

        # Minimal valid PNG for the PIL sniff in generate_video_ad
        buf = _io.BytesIO()
        PILImage.new("RGB", (4, 4)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaigns (name, city, state, category) VALUES (?, ?, ?, ?)",
                ("veo-timeout-test", "Los Angeles", "CA", "holiday"),
            )
            campaign_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO campaign_images (campaign_id, image_path, metadata) VALUES (?, ?, ?)",
                (campaign_id, "veo-timeout-test.png", "{}"),
            )

        monkeypatch.setattr(video_tools.storage, "get_storage_mode", lambda: "local")
        monkeypatch.setattr(video_tools.storage, "get_image_path", lambda f: f"/tmp/{f}")
        monkeypatch.setattr(video_tools.storage, "image_exists", lambda f: True)
        monkeypatch.setattr(video_tools.storage, "read_image", lambda f: png_bytes)

        never_done = FakeOperation(completes_after=10_000)
        fake_client = make_client(never_done)
        fake_client.models = type(
            "M", (), {"generate_videos": staticmethod(lambda **kw: never_done)}
        )()
        monkeypatch.setattr(video_tools.genai, "Client", lambda: fake_client)

        result = await video_tools.generate_video_ad(
            campaign_id=campaign_id, custom_prompt="test prompt", duration_seconds=4
        )

        assert result["status"] == "error"
        assert "timed out" in result["message"]
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT status FROM campaign_ads WHERE id = ?", (result["ad_id"],)
            )
            assert cursor.fetchone()["status"] == "failed"
```

(If `fresh_test_db` in `tests/conftest.py` turns out not to be the right isolation fixture for direct inserts, use `test_db` — check the fixture docstrings; do NOT modify conftest.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_veo_polling.py -v`
Expected: FAIL / ERROR with `AttributeError: module 'app.tools.video_tools' has no attribute '_wait_for_veo_operation'` (and no `asyncio` attribute).

- [ ] **Step 3: Implement the helpers**

In `app/tools/video_tools.py`: add `import asyncio` as the first line of the stdlib import block (before `import io`). Then insert after `generate_scene_image` (after current line ~271, before `animate_scene_with_veo`):

```python
async def _wait_for_veo_operation(
    client,
    operation,
    *,
    max_wait_time: int = 600,
    poll_interval: int = 20,
    debug_label: str = "veo",
):
    """Poll a Veo generate_videos operation to completion (consolidates three
    formerly-duplicated loops — Phase 14b step 1).

    Returns the completed operation. Raises TimeoutError after max_wait_time,
    ValueError if the operation completes without generated videos. Callers
    that must not raise (generate_video_ad) map these at the call site.
    """
    waited = 0
    while not operation.done:
        if waited >= max_wait_time:
            raise TimeoutError(f"Video generation timed out after {max_wait_time} seconds")
        print(f"[DEBUG {debug_label}] Waiting... ({waited}s elapsed)")
        await asyncio.sleep(poll_interval)
        waited += poll_interval
        operation = client.operations.get(operation)
    print(f"[DEBUG {debug_label}] Operation completed after {waited}s")
    if operation.result is None or not operation.result.generated_videos:
        raise ValueError("Video generation completed but returned no result")
    return operation


def _extract_video_bytes(client, generated_video) -> bytes:
    """Extract video bytes from a generated video (consolidates the
    triplicated Vertex-inline vs Developer-API-download branch)."""
    is_vertex_ai = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    if is_vertex_ai:
        video_bytes = generated_video.video.video_bytes
        if not video_bytes:
            raise ValueError("No video_bytes in Vertex AI response")
        return video_bytes
    # Gemini Developer API: must download first, then save to temp to get bytes
    client.files.download(file=generated_video.video)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_path = tmp.name
    generated_video.video.save(temp_path)
    with open(temp_path, "rb") as f:
        video_bytes = f.read()
    os.unlink(temp_path)
    return video_bytes
```

- [ ] **Step 4: Convert call site 1 — `animate_scene_with_veo`**

Replace current lines 320-362 (from `# Poll for completion` through `return video_bytes, video_prompt`, inclusive of the extraction block) with:

```python
    # Poll for completion + extract bytes (shared helpers, Phase 14b step 1)
    operation = await _wait_for_veo_operation(
        client, operation, debug_label="animate_scene_with_veo"
    )
    video_bytes = _extract_video_bytes(client, operation.result.generated_videos[0])

    print(f"[DEBUG animate_scene_with_veo] Video generated: {len(video_bytes)} bytes")
    return video_bytes, video_prompt
```

- [ ] **Step 5: Convert call site 2 — single-stage branch of `generate_video_from_product`**

Replace current lines 615-642 (from `# Poll for completion` through the `os.unlink(temp_path)` end of the extraction block, keeping the following `thumbnail_path = None` lines) with:

```python
            operation = await _wait_for_veo_operation(
                client, operation, debug_label="generate_video_from_product"
            )
            video_bytes = _extract_video_bytes(
                client, operation.result.generated_videos[0]
            )
```

- [ ] **Step 6: Convert call site 3 — `generate_video_ad` (exception-mapped, semantics preserved)**

Replace current lines 998-1071 (from `# Poll for completion (20 second intervals per official docs)` through the end of the Developer-API extraction block `print(f"[DEBUG generate_video_ad] Video bytes size: {len(video_data)}")`) with:

```python
        # Poll for completion; this call site maps helper exceptions to the
        # legacy behavior (mark ad failed in DB + return an error dict).
        try:
            operation = await _wait_for_veo_operation(
                client, operation, debug_label="generate_video_ad"
            )
        except TimeoutError:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    UPDATE campaign_ads SET status = 'failed' WHERE id = ?
                ''', (ad_id,))
            return {
                "status": "error",
                "message": "Video generation timed out after 10 minutes",
                "ad_id": ad_id
            }
        except ValueError:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    UPDATE campaign_ads SET status = 'failed' WHERE id = ?
                ''', (ad_id,))
            return {
                "status": "error",
                "message": "Video generation completed but returned no result. Check API quota and permissions.",
                "ad_id": ad_id,
                "prompt_used": prompt
            }

        generated_video = operation.result.generated_videos[0]
        timestamp = int(time.time())
        output_filename = f"campaign_{campaign_id}_ad_{ad_id}_{timestamp}.mp4"
        video_data = _extract_video_bytes(client, generated_video)
        print(f"[DEBUG generate_video_ad] Video bytes size: {len(video_data)}")
```

Leave everything from `# Save video - handle both local and GCS storage modes` onward **unchanged** (Global Constraints: the local-mode raw-`open()` save path is preserved).

- [ ] **Step 7: Run the new tests and the full fast suites**

Run: `.venv/bin/pytest tests/unit/test_veo_polling.py -v` → all PASS.
Run: `make test-unit && make test-e2e` → green (306+new unit, 25 e2e).

- [ ] **Step 8: Lint and commit**

Run: `.venv/bin/ruff check app/tools/video_tools.py tests/unit/test_veo_polling.py` → clean.
```bash
git add app/tools/video_tools.py tests/unit/test_veo_polling.py
git commit -m "refactor(14b): consolidate Veo polling + video-bytes extraction into shared async helpers"
```

---

### Task 3: Interactions API prototype (14b step 3 — findings before any schema)

**Files:**
- Create: `scripts/probe_omni_interactions.py`
- Create: `.docs/version2-plan/working-docs/14-model-upgrades/omni-prototype-findings.md`

**Interfaces:**
- Consumes: installed google-genai SDK (worktree venv 2.14.0), `client.interactions.{create,get,cancel,delete}`.
- Produces: a findings doc that Task 4's gate reads. No app code.

Context the prototype must honor (ws01 probe, phase doc amendment): `gemini-omni-flash-preview` 404s on `generate_videos`; raw-dict `interactions.create(request={"body": ...})` failed with `400: value 'UNKNOWN' is not supported for 'type'` — use the SDK's **typed** request path. Supported-type hint list from that error: text, image, video, document, content, user_input, model_output, function_call/result.

- [ ] **Step 1: Write the probe script**

```python
"""Bounded Interactions API prototype for Phase 14b step 3.

Goal: establish, with the SDK's TYPED request path (raw dicts proven broken,
ws01), (a) the working request/response shape for text_to_video and
image_to_video on gemini-omni-flash-preview, (b) polling mechanics via
client.interactions.get(), and (c) what previous_interaction_id actually
needs for a meaningful edit. Read-only against the API except for the
interactions it creates. Every attempt prints its full outcome; nothing is
asserted — findings go to omni-prototype-findings.md.

Run: set -a; source app/.env; set +a
     GOOGLE_CLOUD_LOCATION=global .venv/bin/python scripts/probe_omni_interactions.py
"""

import inspect
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

MODEL = "gemini-omni-flash-preview"


def show(label, fn):
    print(f"\n=== {label} ===")
    try:
        out = fn()
        print(f"OK: {out!r}"[:2000])
        return out
    except Exception as e:  # noqa: BLE001 - prototype records everything
        print(f"FAIL [{type(e).__name__}]: {e}"[:2000])
        return None


def main() -> int:
    client = genai.Client()

    # 0. Discover the typed surface before calling anything.
    print("interactions.create signature:")
    print(inspect.signature(client.interactions.create))
    typed = [n for n in dir(types) if "interaction" in n.lower()]
    print(f"types.*Interaction*: {typed}")

    # 1. text_to_video with typed params (adjust to the signature printed above).
    interaction = show(
        "create text_to_video",
        lambda: client.interactions.create(
            model=MODEL,
            input="A 4-second product hero shot of a matte black cold brew can rotating slowly on a marble counter, soft studio light.",
        ),
    )
    if interaction is None:
        print("\ntext_to_video creation failed — record and stop.")
        return 1

    # 2. Poll via interactions.get until terminal state (10 min budget).
    def poll():
        latest = client.interactions.get(interaction_id=interaction.id)
        waited = 0
        while getattr(latest, "status", None) in (None, "in_progress", "processing", "queued"):
            if waited >= 600:
                raise TimeoutError("interaction poll timed out")
            time.sleep(10)
            waited += 10
            latest = client.interactions.get(interaction_id=interaction.id)
        return latest

    final = show("poll to completion", poll)
    if final is not None:
        show("inspect outputs", lambda: [type(o).__name__ for o in getattr(final, "outputs", [])])

    # 3. Edit via previous_interaction_id: text delta alone.
    show(
        "edit via previous_interaction_id (text delta only)",
        lambda: client.interactions.create(
            model=MODEL,
            input="Same video, but make the lighting warm golden hour.",
            previous_interaction_id=interaction.id,
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**The exact keyword names above are the first thing the prototype validates** (step 0 prints the real signature); if `input=`/`interaction_id=`/`previous_interaction_id=` differ in the installed SDK, adjust the script to the printed signature, re-run, and record what worked — that discovery IS the deliverable. If `image_to_video` has a typed entry point (per the printed signature/types), add one attempt for it using the fashion scene PNG from Task 1's output dir.

- [ ] **Step 2: Run it**

Run: `set -a; source app/.env; set +a; GOOGLE_CLOUD_LOCATION=global .venv/bin/python scripts/probe_omni_interactions.py 2>&1 | tee /tmp/omni-probe.log`
Expected: full per-attempt output, success or failure. Failures are valid findings, not blockers.

- [ ] **Step 3: Write the findings doc**

`omni-prototype-findings.md` must answer, with evidence quoted from the run log: (1) does typed `interactions.create` accept a video-generation request for `gemini-omni-flash-preview`, and with exactly which parameters; (2) what does polling look like (states seen, time to completion, output object shape); (3) what does `previous_interaction_id` need for a meaningful edit — text delta alone, or re-attached assets; (4) minimum working SDK version (2.14.0 tested — note whether the surface looks stable); (5) a GO / NO-GO recommendation for building the `omni_flash` backend now, per the phase doc's "evaluate, not adopt" framing.

- [ ] **Step 4: Lint and commit**

Run: `.venv/bin/ruff check scripts/probe_omni_interactions.py` → clean.
```bash
git add scripts/probe_omni_interactions.py .docs/version2-plan/working-docs/14-model-upgrades/omni-prototype-findings.md
git commit -m "spike(14b): Interactions API prototype + documented findings"
```

---

### Task 4: Omni Flash gate — act on the prototype findings

This task is a decision fork; the controller (not a subagent) executes it, because both branches touch plan/phase docs.

- [ ] **Step 1: Read `omni-prototype-findings.md` and take exactly one branch.**

**Branch NO-GO (prototype shows the surface immature/unusable/blocked):**

- [ ] Append a `DISCOVERY` entry to `WORK_LOG.md` quoting the blocking evidence.
- [ ] Amend `.docs/version2-plan/14b-video-model-upgrade-omni-flash.md` — under "Current state", add:
  `> **Amended (workstream 14, 2026-07-XX):** step-3 prototype executed against google-genai <version> — <one-line outcome>. Findings: working-docs/14-model-upgrades/omni-prototype-findings.md. Steps 4-6 (backend toggle, revision tool, SDK pin) deferred until <specific unblocking condition>; step 1 (polling consolidation) and step 3 (prototype) are done.`
- [ ] Amend `99-open-questions.md` #15 the same way (provenance format), recording the wait-for-GA recommendation.
- [ ] Commit: `git commit -m "docs(14b): prototype findings — omni_flash backend deferred (evidence in working docs)"`. Task B is then complete (consolidation landed, evaluation documented — the phase's own exit criteria for a negative result).

**Branch GO (prototype proves the mechanics):**

- [ ] STOP — do not write backend code from this plan. Draft a plan amendment (appended to this file as `### Task 4G`) specifying, from the prototype's ACTUAL confirmed shapes: `VIDEO_MODEL_BACKEND` config (`veo` default / `omni_flash` opt-in, ValueError on invalid — mirror the `DEMO_DATASET` enum pattern in app/config.py:41-47), the `GeneratedVideo` result contract both backends normalize into, the Omni polling path (separate from `_wait_for_veo_operation` — different API object), the new Review-Agent revision tool + interaction-ID/lineage storage, the SDK floor pin, and a new DEMO_GUIDE journey. Present the amendment to the owner for approval (scope gate — the approved working doc made B3 conditional), then execute it via the normal per-task subagent flow.

---

### Task 5: Agent default → `gemini-3.6-flash` (pulled forward from Phase 16 step 3)

**Files:**
- Modify: `app/config.py:64`, `tests/unit/test_config.py:23` (authorized edit), `SETUP_INSTRUCTIONS.md` (Phase-1 bullet + new ws14 bullet), `.docs/version2-plan/16-live-api-testing.md` (provenance), `app/tools/video_tools.py:99` (docstring drift), `scripts/deploy.sh:40`, `scripts/deploy_ae.sh:246`, `scripts/deploy_ae_inline.py:19` (stale comments), `DEMO_GUIDE.md` (journey 14.1)

Pre-verified this kickoff (do not re-derive): `gemini-3.6-flash` is **GA** (Google model page, released 2026-07-21) and responds on Vertex `global` — so CLAUDE.md:74's gotcha text and "GA IDs" language need **no** change.

- [ ] **Step 1: Flip the default** — `app/config.py:64`:

```python
MODEL = os.environ.get("AGENT_MODEL", "gemini-3.6-flash")  # Main agent model (GA; global region supported)
```

- [ ] **Step 2: Update the pinned test** — `tests/unit/test_config.py:23`: `assert cfg.MODEL == "gemini-3.6-flash"` (the ONE authorized existing-test edit).

- [ ] **Step 3: Run the config tests — expect green**

Run: `.venv/bin/pytest tests/unit/test_config.py -v` → PASS (also proves env-overridability unchanged).

- [ ] **Step 4: Docs.** In `SETUP_INSTRUCTIONS.md`: in the Phase-1 bullet change ``(default `gemini-3.5-flash`)`` to ``(default `gemini-3.6-flash` since workstream 14)``; append a new bullet:

```markdown
- **Phase 14a/14b (workstream 14):** agent default model is now `gemini-3.6-flash` (GA, Vertex global — pulled forward from Phase 16 step 3). Image/video generation defaults unchanged (`gemini-3-pro-image`, `veo-3.1-generate-001`); the Nano Banana 2 Lite comparison and Omni Flash prototype findings live in `.docs/version2-plan/working-docs/14-model-upgrades/`.
```

In `.docs/version2-plan/16-live-api-testing.md`, directly under step 3's text, add:

```markdown
   > **Amended (workstream 14, 2026-07-XX):** done here — default flipped to
   > `gemini-3.6-flash` (GA 2026-07-21, verified live on Vertex `global` at
   > ws14 kickoff; CLAUDE.md gotcha unchanged). Phase 16 keeps this step only
   > as a no-op re-verification when the live tier lands.
```

- [ ] **Step 5: Comment/docstring hygiene (no behavior):** `video_tools.py:99` "Uses VIDEO_ANALYSIS_MODEL from config" → "Uses MODEL from config"; `scripts/deploy.sh:40` and `scripts/deploy_ae.sh:246` stale model-name comments → "Gemini 3.x models"; `scripts/deploy_ae_inline.py:19` example "gemini-3.5-flash" → "gemini-3.6-flash".

- [ ] **Step 6: Add DEMO_GUIDE journey.** New section `### Workstream 14` with:

```markdown
#### Journey 14.1 — agent default model is gemini-3.6-flash

```bash
.venv/bin/python -c "from app import config; print(config.MODEL)"
```

**Expect:** `gemini-3.6-flash` (override still via `AGENT_MODEL` in `app/.env`).
Then in the web UI ask: **"Show me all my campaigns"** — expect routing to the
Campaign Agent's `list_campaigns` exactly as before (the flip changes the
model, not the routing contract; F1 Scene 1 is the full check).
```

- [ ] **Step 7: Full fast suites** — `make test-unit && make test-e2e` → green.

- [ ] **Step 8: Commit**

```bash
git add app/config.py tests/unit/test_config.py SETUP_INSTRUCTIONS.md .docs/version2-plan/16-live-api-testing.md app/tools/video_tools.py scripts/deploy.sh scripts/deploy_ae.sh scripts/deploy_ae_inline.py DEMO_GUIDE.md
git commit -m "feat: agent default model gemini-3.6-flash (Phase 16 step 3 pulled into ws14)"
```

---

### Task 6: Demo-scenario verification (verifying-with-demo-scenarios)

Controller-run lifecycle step (STATUS → `verify in progress` in main checkout first). Sequential `demo-scenario-verifier` dispatches, port 8501, local-first storage (`export GCS_BUCKET=` beats app/.env):

- [ ] **F1 (docs/demo-scenarios/fashion.md)** — the self-described release gate for model-config changes: routing scene + full Stage-1 image + Stage-2 Veo generation on the new agent default AND the refactored polling path (Tasks 2+5 both exercised live). Must PASS all scenes.
- [ ] **F5.2** — non-fashion (aurora-cold-brew) video path, `reference_image_used: false`, product-centric filename: exercises the consolidated helper on the two-stage path with no reference image.
- [ ] **from-scratch-onboarding Scenes 2.1 + 2.2** — routing to Campaign Agent + real `generate_product_image` call on the (unchanged) image default, under the new agent model.
- [ ] **Q15 evidence** — during F1/F5.2, record video-output notes (duration, resolution if inspectable, subjective quality on the new agent default's prompts) into `WORK_LOG.md`, alongside Task 1's Q14 resolutions.
- [ ] **WORK_LOG checkpoint 5** — pass/fail per scenario + evidence paths. A failing scenario blocks finishing; fix and re-verify.

Then: `requesting-code-review` (whole branch) → `finishing-a-development-branch` (PR into `version_2`, owner-confirmed self-merge; both STATUS rows → merged; checkpoint 6).
