# Workstream 15: Product Onboarding (from-scratch, local-first) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local-first storage (GCS becomes explicit opt-in; product images get a full local path; tool responses never emit unchecked `storage.googleapis.com` URLs), `DEMO_DATASET=fashion|none` gated seeding, three onboarding tools on the Campaign agent + CLI wrapper, and a Drive-bundle installer/builder for demo assets.

**Architecture:** Extend `app/storage.py` in place (its per-function `get_storage_mode()` branching already IS the seam — this phase adds the missing product-image halves and existence-checked URL helpers). Seeding moves out of `init_database()` into a `seed_demo_data()` gate read from config at call time. Onboarding tools wrap `db.insert_product(Product)` and route all bytes through storage.

**Tech Stack:** Python 3.12, ADK, sqlite3, google-genai (image gen), gdown (new dep, Drive download), pytest.

## Global Constraints

- **ws09 bar (owner directive):** in local mode (GCS_BUCKET unset) nothing reads from or writes to GCS — videos, thumbnails, and charts included — and tool responses NEVER contain `storage.googleapis.com` URLs. In GCS mode, emitted URLs must be existence-checked (no dead links).
- GCS mode stays fully supported as the explicit opt-in (set `GCS_BUCKET`); charts' ADK-artifact path is already compliant — do not touch `metrics_tools.py`.
- `APP_MODE` remains the ONLY user-facing *mode* knob (config.py:23-24 comment). `DEMO_DATASET` is a demo-scoped *dataset selector* — amend that comment exactly as shown in Task 2, never frame DEMO_DATASET as a mode.
- `DEMO_DATASET` values: `fashion` (default; preserves today's behavior exactly: 22 fashion products + 6 retail core products + 4 demo campaigns) | `none` (schema only, empty catalog). Invalid value → `ValueError` at config load, mirroring APP_MODE's style.
- Existing tests stay green **unmodified**, except the exact `tests/conftest.py` edits named in Task 2 (fixture call-site updates + one new fixture) — nothing else in existing test files changes.
- Validation: `grep -rn "kaggle-on-gcp" app/ --exclude=.env` → zero hits (app/.env is untracked/personal — never commit or edit it).
- Repo rules: relative imports inside `app/`; ruff-clean on touched files (`ruff check <files>`; repo-wide lint is red pre-existing — do not fix unrelated files); tool return convention `{status, message, <data-key>, next_steps}`; no `Co-Authored-By`/AI-attribution trailers in commits; `README.md` untouched.
- A `PostToolUse` hook auto-runs `make test-unit` after edits to `app/**/*.py` — treat its failures as your own.

---

### Task 1: Local-first config + product-image storage seam

**Files:**
- Modify: `app/config.py:70-86` (GCS opt-in, LOCAL_ASSETS_DIR, PRODUCT_IMAGES_DIR)
- Modify: `app/storage.py:171-225` (product-image local branches), `app/storage.py:351-397` (URL helpers)
- Modify: `app/tools/image_tools.py:270` (raw env read → config)
- Modify: `app/database/mock_data.py:77` (scrub bucket name from comment)
- Test: `tests/unit/test_storage_local.py` (new)

**Interfaces:**
- Consumes: existing `get_storage_mode()`, `_get_bucket()`, `get_public_url()`.
- Produces (later tasks rely on these exact signatures):
  - `storage.save_product_image(filename: str, data: bytes) -> str` (returns local path or `gs://` URL)
  - `storage.product_image_exists(filename: str) -> bool` (no longer raises in local mode)
  - `storage.read_product_image(filename: str) -> bytes`, `storage.get_product_image_path(filename: str) -> str` (local branches)
  - `storage.get_product_image_public_url(filename: str, check_exists: bool = True) -> Optional[str]`
  - `storage.get_thumbnail_public_url(filename: str, check_exists: bool = True) -> Optional[str]` (signature gains param, default True — Task 3 relies on it)
  - `config.PRODUCT_IMAGES_DIR: str`, `config.LOCAL_ASSETS_DIR: str`, `config.GCS_BUCKET: str | None` (no default bucket; `DEFAULT_GCS_BUCKET` deleted)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_storage_local.py`:

```python
"""Phase 15: local-first storage — product-image local branches + URL policy.

Local mode = GCS_BUCKET None. conftest pins GCS_BUCKET=test-bucket session-wide,
so every local-mode test monkeypatches app.config.GCS_BUCKET to None (storage
functions read config at call time via function-level imports).
"""

import json
from unittest.mock import MagicMock

import pytest

from app import storage


@pytest.fixture
def local_mode(tmp_path, monkeypatch):
    """Force local storage mode with a temp product-images root."""
    monkeypatch.setattr("app.config.GCS_BUCKET", None)
    monkeypatch.setattr("app.config.PRODUCT_IMAGES_DIR", str(tmp_path / "product-images"))
    return tmp_path


@pytest.fixture
def gcs_mode(monkeypatch):
    """Force GCS mode with a mocked bucket (no real client construction)."""
    monkeypatch.setattr("app.config.GCS_BUCKET", "test-bucket")
    bucket = MagicMock()
    monkeypatch.setattr("app.storage._get_bucket", lambda: bucket)
    return bucket


class TestLocalProductImages:
    def test_save_read_exists_path_roundtrip(self, local_mode):
        path = storage.save_product_image("widget.png", b"\x89PNG-fake-bytes")
        assert path.startswith(str(local_mode))
        assert storage.product_image_exists("widget.png") is True
        assert storage.read_product_image("widget.png") == b"\x89PNG-fake-bytes"
        assert storage.get_product_image_path("widget.png") == path

    def test_exists_false_when_missing(self, local_mode):
        assert storage.product_image_exists("nope.png") is False

    def test_no_gcs_client_touched_in_local_mode(self, local_mode, monkeypatch):
        def boom():
            raise AssertionError("GCS client constructed in local mode")
        monkeypatch.setattr("app.storage._get_bucket", boom)
        storage.save_product_image("a.png", b"x")
        storage.product_image_exists("a.png")
        storage.read_product_image("a.png")
        storage.get_product_image_path("a.png")

    def test_public_urls_none_in_local_mode(self, local_mode):
        storage.save_product_image("here.png", b"x")
        assert storage.get_public_url("product-images/here.png") is None
        assert storage.get_product_image_public_url("here.png") is None
        assert storage.get_thumbnail_public_url("thumb.png") is None


class TestGcsProductImages:
    def test_public_url_none_when_blob_missing(self, gcs_mode):
        gcs_mode.blob.return_value.exists.return_value = False
        assert storage.get_product_image_public_url("gone.png") is None

    def test_public_url_when_blob_exists(self, gcs_mode):
        gcs_mode.blob.return_value.exists.return_value = True
        url = storage.get_product_image_public_url("real.png")
        assert url == "https://storage.googleapis.com/test-bucket/product-images/real.png"

    def test_save_content_type_by_extension(self, gcs_mode):
        storage.save_product_image("photo.jpg", b"jpegbytes")
        _, kwargs = gcs_mode.blob.return_value.upload_from_file.call_args
        assert kwargs["content_type"] == "image/jpeg"
        storage.save_product_image("photo.png", b"pngbytes")
        _, kwargs = gcs_mode.blob.return_value.upload_from_file.call_args
        assert kwargs["content_type"] == "image/png"


class TestConfigOptIn:
    def test_default_bucket_deleted(self):
        from app import config
        assert not hasattr(config, "DEFAULT_GCS_BUCKET")

    def test_product_images_dir_under_local_assets(self):
        from app import config
        assert config.PRODUCT_IMAGES_DIR.startswith(config.LOCAL_ASSETS_DIR)
        assert config.PRODUCT_IMAGES_DIR.endswith("product-images")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_storage_local.py -v`
Expected: FAIL — `save_product_image`/`get_product_image_public_url` don't exist; `DEFAULT_GCS_BUCKET` still exists; `product_image_exists` raises `RuntimeError` in local mode.

- [ ] **Step 3: Implement config changes**

In `app/config.py`, replace lines 70-73 (`# GCS configuration...` through `GCS_BUCKET = ...`) with:

```python
# GCS configuration — explicit OPT-IN (Phase 15 local-first).
# Unset (or empty) GCS_BUCKET means local mode: all assets (product images,
# videos, thumbnails) live under LOCAL_ASSETS_DIR and tool responses carry
# no public storage URLs. Cloud deploys set GCS_BUCKET explicitly.
GCS_BUCKET = os.environ.get("GCS_BUCKET") or None
```

Replace lines 80-86 (`# Paths ...` through `GENERATED_DIR = ...`) with:

```python
# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# Local asset root (Phase 15): single knob for where local-mode assets live.
# Defaults to the project root so the pre-existing selected/ and generated/
# locations are unchanged; product images join them under product-images/.
# Override with the LOCAL_ASSETS_DIR env var.
LOCAL_ASSETS_DIR = os.environ.get("LOCAL_ASSETS_DIR") or PROJECT_DIR
SELECTED_DIR = os.path.join(LOCAL_ASSETS_DIR, "selected")
GENERATED_DIR = os.path.join(LOCAL_ASSETS_DIR, "generated")
PRODUCT_IMAGES_DIR = os.path.join(LOCAL_ASSETS_DIR, "product-images")
```

- [ ] **Step 4: Implement storage changes**

In `app/storage.py`, replace the whole "Product Image Storage Functions (GCS only - no local fallback)" section (lines 171-225) with:

```python
# =============================================================================
# Product Image Storage Functions
# =============================================================================

def _product_image_content_type(filename: str) -> str:
    return "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"


def product_image_exists(filename: str) -> bool:
    """Check if a product image exists (GCS product-images/ or local dir)."""
    from .config import PRODUCT_IMAGES_DIR
    if get_storage_mode() == "gcs":
        bucket = _get_bucket()
        blob = bucket.blob(f"product-images/{filename}")
        return blob.exists()
    return os.path.exists(os.path.join(PRODUCT_IMAGES_DIR, filename))


def read_product_image(filename: str) -> bytes:
    """Read product image bytes from storage."""
    from .config import PRODUCT_IMAGES_DIR
    if get_storage_mode() == "gcs":
        bucket = _get_bucket()
        blob = bucket.blob(f"product-images/{filename}")
        return blob.download_as_bytes()
    with open(os.path.join(PRODUCT_IMAGES_DIR, filename), "rb") as f:
        return f.read()


def save_product_image(filename: str, data: bytes) -> str:
    """Save a product image, return the local path or gs:// URL."""
    from .config import GCS_BUCKET, PRODUCT_IMAGES_DIR
    if get_storage_mode() == "gcs":
        bucket = _get_bucket()
        blob = bucket.blob(f"product-images/{filename}")
        blob.upload_from_file(
            io.BytesIO(data),
            content_type=_product_image_content_type(filename),
            rewind=True,
        )
        return f"gs://{GCS_BUCKET}/product-images/{filename}"
    os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)
    path = os.path.join(PRODUCT_IMAGES_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


def get_product_image_path(filename: str) -> str:
    """Get the full local path or gs:// URL for a product image."""
    from .config import GCS_BUCKET, PRODUCT_IMAGES_DIR
    if get_storage_mode() == "gcs":
        return f"gs://{GCS_BUCKET}/product-images/{filename}"
    return os.path.join(PRODUCT_IMAGES_DIR, filename)
```

In the "Public URL Functions" section, replace `get_thumbnail_public_url` (lines 388-397) with, and add `get_product_image_public_url` after it:

```python
def get_thumbnail_public_url(filename: str, check_exists: bool = True) -> Optional[str]:
    """Public URL for a video thumbnail (generated/ prefix), or None.

    None when not in GCS mode, or (by default) when the file doesn't exist —
    tool responses must never carry dead storage URLs (ws09 bar).
    """
    if check_exists and not video_exists(filename):
        return None
    return get_public_url(f"generated/{filename}")


def get_product_image_public_url(filename: str, check_exists: bool = True) -> Optional[str]:
    """Public URL for a product image, or None.

    None when not in GCS mode, or (by default) when the blob doesn't exist —
    tool responses must never carry dead storage URLs (ws09 bar).
    """
    if get_storage_mode() != "gcs":
        return None
    if check_exists and not product_image_exists(filename):
        return None
    return get_public_url(f"product-images/{filename}")
```

- [ ] **Step 5: Two small scrubs**

`app/tools/image_tools.py:270` — replace the raw env read:

```python
    from ..config import GCS_BUCKET
    storage_location = SELECTED_DIR if storage.get_storage_mode() == "local" else f"gs://{GCS_BUCKET or ''}/seed-images/"
```

(Put the import at the top of the file with the other config imports if one doesn't already exist; keep it relative.)

`app/database/mock_data.py:77` — change the comment line

`# REAL Videos in GCS (gs://kaggle-on-gcp-ad-campaign-assets/generated/)` → `# REAL demo videos (generated/ prefix in whatever GCS bucket is configured)`

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_storage_local.py -v` → all PASS.
Run: `make test-unit` → all PASS (existing suites unmodified).
Run: `grep -rn "kaggle-on-gcp" app/ --exclude=.env` → zero output.
Run: `ruff check app/config.py app/storage.py app/tools/image_tools.py app/database/mock_data.py tests/unit/test_storage_local.py` → clean.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/storage.py app/tools/image_tools.py app/database/mock_data.py tests/unit/test_storage_local.py
git commit -m "feat: local-first storage seam — product-image local branches, GCS opt-in (no default bucket)"
```

---

### Task 2: DEMO_DATASET gated seeding

**Files:**
- Modify: `app/config.py` (add `DemoDataset` enum + `DEMO_DATASET` after the APP_MODE block; amend the APP_MODE comment)
- Modify: `app/database/db.py:259-261` (remove the two seeding calls from `init_database()`)
- Modify: `app/database/mock_data.py` (add `seed_demo_data()`)
- Modify: `app/agent.py:111-118` (call `seed_demo_data()` instead of `populate_mock_data()`)
- Modify: `tests/conftest.py` (`_ensure_main_db_exists`, `fresh_test_db` → use `seed_demo_data()`; add `empty_test_db` fixture)
- Test: `tests/unit/test_demo_dataset_gate.py` (new)

**Interfaces:**
- Consumes: `populate_products()`, `populate_retail_test_products()` (db.py), `populate_mock_data()` (mock_data.py) — all already idempotent (count guards / INSERT OR IGNORE).
- Produces:
  - `config.DemoDataset` (StrEnum: `FASHION = "fashion"`, `NONE = "none"`), `config.DEMO_DATASET: DemoDataset`
  - `mock_data.seed_demo_data() -> dict` — reads `config.DEMO_DATASET` **at call time** (monkeypatchable); returns `{"seeded": False}` for `none`, `{"seeded": True, ...populate_mock_data counts}` for `fashion`
  - conftest fixture `empty_test_db` — schema-only temp DB (Tasks 4/5 use it)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_demo_dataset_gate.py`:

```python
"""Phase 15: DEMO_DATASET=fashion|none gates ALL demo seeding — including the
product seeding that used to live inside init_database() (db.py:259-261)."""

import importlib

import pytest


class TestConfigParsing:
    def test_default_is_fashion(self):
        from app.config import DEMO_DATASET, DemoDataset
        assert DEMO_DATASET is DemoDataset.FASHION

    def test_invalid_value_raises_at_load(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATASET", "bogus")
        import app.config
        with pytest.raises(ValueError, match="Invalid DEMO_DATASET"):
            importlib.reload(app.config)
        monkeypatch.delenv("DEMO_DATASET")
        importlib.reload(app.config)  # restore clean module state for later tests


class TestGate:
    def test_init_database_no_longer_seeds(self, empty_test_db):
        from app.database.db import get_db_cursor
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM products")
            assert cursor.fetchone()[0] == 0

    def test_none_yields_empty_catalog(self, empty_test_db, monkeypatch):
        from app.config import DemoDataset
        monkeypatch.setattr("app.config.DEMO_DATASET", DemoDataset.NONE)
        from app.database.db import get_db_cursor
        from app.database.mock_data import seed_demo_data
        result = seed_demo_data()
        assert result["seeded"] is False
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM products")
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM campaigns")
            assert cursor.fetchone()[0] == 0

    def test_fashion_default_seeds_full_demo(self, empty_test_db):
        from app.database.db import get_db_cursor
        from app.database.mock_data import seed_demo_data
        result = seed_demo_data()
        assert result["seeded"] is True
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM products")
            assert cursor.fetchone()[0] == 28  # 22 fashion + 6 retail core
            cursor.execute("SELECT COUNT(*) FROM campaigns")
            assert cursor.fetchone()[0] == 4
        # Idempotent on re-run
        seed_demo_data()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM products")
            assert cursor.fetchone()[0] == 28
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_demo_dataset_gate.py -v`
Expected: FAIL — no `DemoDataset` in config, no `empty_test_db` fixture, no `seed_demo_data`, and `init_database()` still seeds 28 products.

- [ ] **Step 3: Implement config**

In `app/config.py`, amend the APP_MODE comment (lines 21-24): change its last sentence

`APP_MODE stays the ONLY` → keep, and extend so the block ends:

```python
# App mode (Phase 6): demo|connected, default demo. Nothing consumes this yet —
# Phase 11a resolves it internally to a data-provider selection (demo → the
# synthetic provider, connected → the live one). APP_MODE stays the ONLY
# user-facing mode knob; do not add a second mode env var. (DEMO_DATASET
# below is NOT a mode — it's a demo-scoped dataset selector: which demo
# catalog gets seeded at startup.)
```

Immediately after the APP_MODE parsing block (after line 37), add:

```python
# Demo dataset selector (Phase 15): which demo catalog to seed at startup.
# fashion (default) = today's full demo: 22 fashion products, the retail core
# test set, and 4 demo campaigns with metrics. none = schema only — an empty
# catalog for from-scratch product onboarding.
class DemoDataset(StrEnum):
    FASHION = "fashion"
    NONE = "none"


_raw_demo_dataset = (os.environ.get("DEMO_DATASET") or "").strip().lower()
try:
    DEMO_DATASET = DemoDataset(_raw_demo_dataset) if _raw_demo_dataset else DemoDataset.FASHION
except ValueError:
    raise ValueError(
        f"Invalid DEMO_DATASET={_raw_demo_dataset!r}. Allowed values: "
        f"{', '.join(d.value for d in DemoDataset)}; unset defaults to 'fashion'."
    ) from None
```

- [ ] **Step 4: Implement the gate**

`app/database/db.py`: delete lines 259-261 (the `# Populate products table` comment and the `populate_products()` / `populate_retail_test_products()` calls) from `init_database()`. `populate_products` and `populate_retail_test_products` themselves stay — `seed_demo_data` calls them.

`app/database/mock_data.py`: add at the end of the file:

```python
def seed_demo_data() -> dict:
    """Seed demo data per config.DEMO_DATASET (Phase 15 gated seeding).

    fashion: the full demo — 22 fashion products, the retail core test set,
    and 4 demo campaigns with activated videos and metrics (all idempotent).
    none: seed nothing — schema-only empty catalog for from-scratch onboarding.

    Reads config at call time so tests can monkeypatch app.config.DEMO_DATASET.
    """
    from .. import config
    from .db import populate_products, populate_retail_test_products

    if config.DEMO_DATASET is config.DemoDataset.NONE:
        print("[DB] DEMO_DATASET=none — skipping demo seeding (empty catalog)")
        return {"seeded": False}
    populate_products()
    populate_retail_test_products()
    counts = populate_mock_data()
    return {"seeded": True, **(counts or {})}
```

`app/agent.py`: change the mock_data import (grep for `populate_mock_data` near the top imports) to import `seed_demo_data` instead, and replace lines 111-113:

```python
try:
    init_database()
    seed_demo_data()
```

Check for other callers: `grep -rn "populate_mock_data\|init_database" app/ scripts/ tests/ --include="*.py"` — the only production call sites are `app/agent.py` and `db.reset_database()` (which calls `init_database()` and is itself only used by tooling; it now produces a schema-only DB, which is correct — the agent seeds on next start). Test call sites are handled in Step 5. If you find any other production caller relying on init-time seeding, STOP and report BLOCKED rather than guessing.

- [ ] **Step 5: conftest updates (the ONLY existing-test-file edits in this plan)**

In `tests/conftest.py`:

1. `_ensure_main_db_exists()` (lines 84-95): replace the import+calls so the seeded-DB behavior is preserved now that `init_database()` is schema-only:

```python
    if not MAIN_DB_PATH.exists():
        # Import and initialize if main DB doesn't exist
        from app.database.db import init_database
        from app.database.mock_data import seed_demo_data

        init_database()
        seed_demo_data()
```

2. `fresh_test_db` (lines 155-176): same substitution — `from app.database.mock_data import seed_demo_data` and call `seed_demo_data()` instead of `populate_mock_data()`.

3. Add after `fresh_test_db`:

```python
@pytest.fixture(scope="function")
def empty_test_db():
    """Schema-only database — the DEMO_DATASET=none / from-scratch state.

    Phase 15: init_database() no longer seeds, so this is just init on a
    temp file. Use for onboarding-tool and empty-catalog tests.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_empty_")
    os.close(fd)

    with patch("app.config.DB_PATH", db_path):
        from app.database.db import init_database

        init_database()
        yield db_path

    try:
        os.unlink(db_path)
    except OSError:
        pass
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_demo_dataset_gate.py -v` → PASS.
Run: `make test-unit && make test-e2e` → PASS (seeded-DB fixtures produce identical content via the new path).
Run: `ruff check app/config.py app/database/db.py app/database/mock_data.py app/agent.py tests/conftest.py tests/unit/test_demo_dataset_gate.py` → clean.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/database/db.py app/database/mock_data.py app/agent.py tests/conftest.py tests/unit/test_demo_dataset_gate.py
git commit -m "feat: DEMO_DATASET=fashion|none gated seeding (covers init_database's former unconditional seeding)"
```

---

### Task 3: URL policy — route all four emitting tools through the seam; dedupe video writes

**Files:**
- Modify: `app/tools/video_tools.py:580-587` and `:655-662` (hand-rolled local writes → `storage.save_video`), `:1771-1813` (`list_products`)
- Modify: `app/tools/review_tools.py:681-692` (`get_video_review_table` row loop), `:854-868` (`get_video_details`)
- Modify: `app/tools/maps_tools.py:479-530` (product image + video URL blocks)
- Test: `tests/unit/test_url_policy.py` (new)

**Interfaces:**
- Consumes: Task 1's `get_product_image_public_url`, `get_thumbnail_public_url(check_exists=True)`, `product_image_exists`, `save_product_image` — and existing `get_video_public_url(check_exists=...)`, `save_video`.
- Produces: `list_products` items gain `image_status: "available"|"missing"`; missing files now yield `None` URLs everywhere (the "unchecked URL for reference" fallback is removed).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_url_policy.py`:

```python
"""ws09 bar: tool responses never emit storage.googleapis.com in local mode,
and GCS-mode URLs are existence-checked (no dead links). Regression net over
list_products and the review tools; maps_tools shares the same storage
helpers and is exercised by the demo scenarios."""

import json

import pytest


@pytest.fixture
def local_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.GCS_BUCKET", None)
    monkeypatch.setattr("app.config.PRODUCT_IMAGES_DIR", str(tmp_path / "product-images"))
    return tmp_path


class TestLocalModeNeverEmitsStorageUrls:
    def test_list_products_local(self, test_db, local_mode):
        from app.tools.video_tools import list_products
        result = list_products()
        assert result["status"] == "success"
        assert "storage.googleapis.com" not in json.dumps(result)
        for product in result["products"]:
            assert product["image_status"] in ("available", "missing")
            assert "image_url" not in product  # no public URLs in local mode

    def test_review_table_local(self, test_db, local_mode):
        from app.tools.review_tools import get_video_review_table
        result = get_video_review_table()
        assert "storage.googleapis.com" not in json.dumps(result)

    def test_video_details_local(self, test_db, local_mode):
        from app.tools.review_tools import get_video_review_table, get_video_details
        table = get_video_review_table()
        video_id = table["videos"][0]["id"]
        result = get_video_details(video_id)
        assert "storage.googleapis.com" not in json.dumps(result)


class TestGcsModeUrlsAreExistenceChecked:
    def test_missing_video_yields_no_url(self, test_db, monkeypatch):
        # conftest pins GCS_BUCKET=test-bucket → GCS mode; force "nothing exists"
        monkeypatch.setattr("app.storage.video_exists", lambda p: False)
        monkeypatch.setattr("app.storage.product_image_exists", lambda f: False)
        from app.tools.review_tools import get_video_review_table
        result = get_video_review_table()
        for video in result["videos"]:
            assert video.get("video_url") is None  # no dead-link fallback

    def test_list_products_missing_image_no_url(self, test_db, monkeypatch):
        monkeypatch.setattr("app.storage.product_image_exists", lambda f: False)
        from app.tools.video_tools import list_products
        result = list_products()
        for product in result["products"]:
            assert "image_url" not in product
            assert product["image_status"] == "missing"
```

Note: `get_video_review_table`'s video dict key for the URL — confirm the exact key name in the existing row-building code (around review_tools.py:710-740, e.g. `"video_url"`) and use that key in the test.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_url_policy.py -v`
Expected: FAIL — `image_status` missing from `list_products`; GCS-mode fallback still emits unchecked URLs.

- [ ] **Step 3: Implement `list_products`**

In `app/tools/video_tools.py:1800-1804`, replace the URL block inside the loop:

```python
        # Image URL policy (ws09): existence-checked public URL in GCS mode,
        # no URL in local mode — image_status says what a UI can rely on.
        if include_urls and p.image_filename:
            image_available = False
            try:
                image_available = storage.product_image_exists(p.image_filename)
            except Exception:
                image_available = False
            product_data["image_status"] = "available" if image_available else "missing"
            if image_available:
                image_url = storage.get_product_image_public_url(
                    p.image_filename, check_exists=False
                )
                if image_url:
                    product_data["image_url"] = image_url
```

And change the return's `note` line to:

```python
        "note": "image_status shows whether each product's reference image is stored; image_url is present only in GCS mode for images that exist"
```

- [ ] **Step 4: Implement review_tools + maps_tools policy**

`app/tools/review_tools.py:682-692` (row loop in `get_video_review_table`) — remove the dead-link fallback and route the product image through the checked helper:

```python
            # Public URLs (ws09 policy): only for files that actually exist
            video_url = None
            video_exists_in_storage = False
            if row["video_filename"]:
                video_url = storage.get_video_public_url(row["video_filename"], check_exists=True)
                video_exists_in_storage = video_url is not None
            product_image_url = (
                storage.get_product_image_public_url(row["product_image"])
                if row["product_image"] else None
            )
```

`app/tools/review_tools.py:854-868` (`get_video_details`) — same shape:

```python
        # Public URLs (ws09 policy): only for files that actually exist
        video_url = None
        video_exists_in_storage = False
        if row["video_filename"]:
            video_url = storage.get_video_public_url(row["video_filename"], check_exists=True)
            video_exists_in_storage = video_url is not None

        thumbnail_url = None
        if row["thumbnail_path"]:
            # Handle both full paths and filenames
            thumb_filename = row["thumbnail_path"].split("/")[-1] if "/" in row["thumbnail_path"] else row["thumbnail_path"]
            thumbnail_url = storage.get_thumbnail_public_url(thumb_filename)
```

(`get_thumbnail_public_url` now existence-checks by default — no call-site change needed beyond leaving it as-is.)

`app/tools/maps_tools.py:480-484` — product image through the checked helper:

```python
                product_image_url = None
                if camp["product_image"]:
                    product_image_url = storage.get_product_image_public_url(
                        camp["product_image"]
                    )
```

`app/tools/maps_tools.py:512-522` — remove the dead-link fallback:

```python
                    video_url = None
                    video_exists = False
                    if vid["video_filename"]:
                        video_url = storage.get_video_public_url(
                            vid["video_filename"], check_exists=True
                        )
                        video_exists = video_url is not None
```

(The video_list entry at :535 already emits `video_url if video_exists else None` — it simplifies to `video_url`; make that simplification.)

- [ ] **Step 5: Dedupe video writes**

`app/tools/video_tools.py:580-587` — replace the thumbnail branch:

```python
            # Save scene image as thumbnail (storage seam handles local vs GCS)
            thumbnail_path = storage.save_video(thumbnail_filename, scene_image_bytes)
            print(f"[DEBUG generate_video_from_product] Saved thumbnail: {thumbnail_path}")
```

`app/tools/video_tools.py:655-662` — replace the video branch:

```python
        # Save video (storage seam handles local vs GCS)
        video_path = storage.save_video(video_filename, video_bytes)
        print(f"[DEBUG generate_video_from_product] Saved video: {video_path}")
```

(Yes, `save_video` uploads thumbnails with `content_type="video/mp4"` in GCS mode — that is byte-for-byte today's behavior at line 582; do not "fix" it in this task.)

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_url_policy.py -v` → PASS.
Run: `make test-unit` → PASS. If any existing test pinned the removed dead-link fallback or the old `note` text, STOP and report it (existing tests must not be modified in this task).
Run: `ruff check app/tools/video_tools.py app/tools/review_tools.py app/tools/maps_tools.py tests/unit/test_url_policy.py` → clean.

- [ ] **Step 7: Commit**

```bash
git add app/tools/video_tools.py app/tools/review_tools.py app/tools/maps_tools.py tests/unit/test_url_policy.py
git commit -m "feat: existence-checked URL policy across all four emitting tools; dedupe video writes through storage.save_video"
```

---

### Task 4: Onboarding tools + Campaign agent wiring

**Files:**
- Create: `app/tools/onboarding_tools.py`
- Modify: `app/agent.py` (import, `CAMPAIGN_AGENT_INSTRUCTION`, `campaign_agent.tools`)
- Test: `tests/unit/test_onboarding_tools.py` (new)

**Interfaces:**
- Consumes: `db.insert_product(Product) -> Product` (raises `sqlite3.IntegrityError` on duplicate name), `db.get_product(id)`, `db.get_product_by_name(name)`, `db.get_db_cursor()`, `storage.save_product_image/product_image_exists`, `config.IMAGE_GENERATION`.
- Produces (Task 5's CLI and Task 6's tests import these exact names from `app.tools.onboarding_tools`):
  - `create_product(name: str, category: str = "", description: str = "", attributes: dict | None = None) -> dict`
  - `import_products_from_folder(folder_path: str, category: str = "") -> dict`
  - `async generate_product_image(product_id: int = 0, product_name: str = "", style_hint: str = "", tool_context: ToolContext = None) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_onboarding_tools.py`:

```python
"""Phase 15 onboarding tools: create_product / import_products_from_folder /
generate_product_image — all against the empty-catalog fixture, local mode."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def local_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.GCS_BUCKET", None)
    monkeypatch.setattr("app.config.PRODUCT_IMAGES_DIR", str(tmp_path / "product-images"))
    return tmp_path


class TestCreateProduct:
    def test_create_success_pending_image(self, empty_test_db, local_mode):
        from app.tools.onboarding_tools import create_product
        result = create_product(
            name="Aurora Cold Brew 330ml",
            category="beverage",
            description="Nitro cold brew in a slim can",
            attributes={"volume_ml": 330, "caffeine_mg": 120},
        )
        assert result["status"] == "success"
        assert result["product"]["id"] is not None
        assert result["product"]["image_filename"] == "aurora-cold-brew-330ml.png"
        assert result["product"]["image_status"] == "pending"
        assert "next_steps" in result

    def test_attributes_roundtrip(self, empty_test_db, local_mode):
        from app.database.db import get_product_by_name
        from app.tools.onboarding_tools import create_product
        create_product(name="Trail Shoe X", category="footwear",
                       attributes={"waterproof": True, "weight_grams": 240})
        stored = get_product_by_name("Trail Shoe X")
        assert stored.attributes["weight_grams"] == 240

    def test_duplicate_name_translated(self, empty_test_db, local_mode):
        from app.tools.onboarding_tools import create_product
        create_product(name="Dup Widget", category="electronics")
        result = create_product(name="Dup Widget", category="electronics")
        assert result["status"] == "error"
        assert "already exists" in result["message"]

    def test_empty_name_rejected(self, empty_test_db, local_mode):
        from app.tools.onboarding_tools import create_product
        assert create_product(name="   ")["status"] == "error"


class TestImportFromFolder:
    def _folder(self, tmp_path):
        src = tmp_path / "vendor-images"
        src.mkdir()
        (src / "Red Mug.png").write_bytes(b"\x89PNG" + b"x" * 20000)
        (src / "blue-bottle.jpg").write_bytes(b"\xff\xd8" + b"y" * 20000)
        (src / "tiny-icon.png").write_bytes(b"\x89PNG" + b"z" * 100)  # tiny → warn
        (src / "notes.txt").write_text("not an image")
        return src

    def test_import_creates_products_and_saves_images(self, empty_test_db, local_mode, tmp_path):
        from app.tools.onboarding_tools import import_products_from_folder
        result = import_products_from_folder(str(self._folder(tmp_path)), category="homeware")
        assert result["status"] == "success"
        assert len(result["created"]) == 3          # txt ignored
        assert len(result["warnings"]) == 1          # tiny image warned, not blocked
        names = {p["name"] for p in result["created"]}
        assert names == {"red-mug", "blue-bottle", "tiny-icon"}
        from app import storage
        assert storage.product_image_exists("red-mug.png")
        assert storage.product_image_exists("blue-bottle.jpg")

    def test_reimport_skips_duplicates(self, empty_test_db, local_mode, tmp_path):
        from app.tools.onboarding_tools import import_products_from_folder
        folder = str(self._folder(tmp_path))
        import_products_from_folder(folder)
        result = import_products_from_folder(folder)
        assert len(result["created"]) == 0
        assert len(result["skipped"]) == 3

    def test_missing_folder(self, empty_test_db, local_mode):
        from app.tools.onboarding_tools import import_products_from_folder
        assert import_products_from_folder("/no/such/dir")["status"] == "error"


class TestGenerateProductImage:
    def _mock_genai(self, monkeypatch, image_bytes=b"generated-png-bytes"):
        part = SimpleNamespace(inline_data=SimpleNamespace(data=image_bytes))
        response = SimpleNamespace(candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=[part]))
        ])
        client = MagicMock()
        client.models.generate_content.return_value = response
        monkeypatch.setattr("app.tools.onboarding_tools.genai.Client", lambda: client)
        return client

    def test_generates_and_stores(self, empty_test_db, local_mode, monkeypatch):
        from app.database.db import get_product
        from app.tools.onboarding_tools import create_product, generate_product_image
        client = self._mock_genai(monkeypatch)
        created = create_product(name="Aurora Cold Brew 330ml", category="beverage")
        product_id = created["product"]["id"]
        result = asyncio.run(generate_product_image(product_id=product_id))
        assert result["status"] == "success"
        assert result["product"]["image_status"] == "available"
        from app import storage
        assert storage.product_image_exists("aurora-cold-brew-330ml.png")
        assert get_product(product_id).local_path is not None
        prompt = client.models.generate_content.call_args.kwargs["contents"][0]
        assert "beverage" in prompt  # category-aware prompt

    def test_by_name_and_style_hint(self, empty_test_db, local_mode, monkeypatch):
        from app.tools.onboarding_tools import create_product, generate_product_image
        client = self._mock_genai(monkeypatch)
        create_product(name="Trail Shoe X", category="footwear")
        result = asyncio.run(generate_product_image(product_name="Trail Shoe X",
                                                    style_hint="warm morning light"))
        assert result["status"] == "success"
        prompt = client.models.generate_content.call_args.kwargs["contents"][0]
        assert "warm morning light" in prompt

    def test_unknown_product(self, empty_test_db, local_mode):
        from app.tools.onboarding_tools import generate_product_image
        result = asyncio.run(generate_product_image(product_id=999))
        assert result["status"] == "error"

    def test_no_image_in_response(self, empty_test_db, local_mode, monkeypatch):
        from app.tools.onboarding_tools import create_product, generate_product_image
        part = SimpleNamespace(inline_data=None)
        response = SimpleNamespace(candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=[part]))
        ])
        client = MagicMock()
        client.models.generate_content.return_value = response
        monkeypatch.setattr("app.tools.onboarding_tools.genai.Client", lambda: client)
        created = create_product(name="Ghost Product", category="misc")
        result = asyncio.run(generate_product_image(product_id=created["product"]["id"]))
        assert result["status"] == "error"


class TestAgentWiring:
    def test_campaign_agent_has_onboarding_tools(self):
        from app.agent import campaign_agent
        from app.tools.onboarding_tools import (
            create_product, generate_product_image, import_products_from_folder,
        )
        assert create_product in campaign_agent.tools
        assert import_products_from_folder in campaign_agent.tools
        assert generate_product_image in campaign_agent.tools
```

Note: if `client.models.generate_content` is called with positional args in your implementation, `call_args.kwargs["contents"]` fails — call it with keyword args (`model=`, `contents=`, `config=`) exactly like `generate_scene_image` does at video_tools.py:248.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_onboarding_tools.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `app/tools/onboarding_tools.py`**

```python
"""Product onboarding tools (Phase 15): create products conversationally,
bulk-import from a local folder, and generate reference product images.

All three wrap db.insert_product(Product) — the typed write path — and route
image bytes through app.storage (the local-first seam). Wired to the Campaign
agent: onboarding is campaign-setup activity; catalog browsing stays on the
Media agent's list_products.
"""

import os
import re
import sqlite3

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from .. import storage
from ..config import IMAGE_GENERATION
from ..database.db import (
    get_db_cursor,
    get_product,
    get_product_by_name,
    insert_product,
)
from ..models.product import Product

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_TINY_IMAGE_BYTES = 10 * 1024  # below this, warn (likely icon/corrupt) but import anyway


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "product"


def _image_status(filename: str) -> str:
    try:
        return "available" if storage.product_image_exists(filename) else "pending"
    except Exception:
        return "pending"


def _product_payload(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "description": product.description,
        "image_filename": product.image_filename,
        "image_status": _image_status(product.image_filename),
        "attributes": product.attributes,
    }


def create_product(name: str, category: str = "", description: str = "",
                   attributes: dict | None = None) -> dict:
    """Create a single product in the catalog.

    The product is browse-ready immediately; its reference image starts as
    'pending' until an image is imported (import_products_from_folder) or
    generated (generate_product_image).

    Args:
        name: Unique product name (e.g. "Aurora Cold Brew 330ml").
        category: Vertical/category (e.g. beverage, footwear, dress).
        description: Short marketing-relevant description.
        attributes: Vertical-specific attributes (e.g. {"volume_ml": 330}).

    Returns:
        Dict with status, message, product (including image_status), next_steps.
    """
    if not name or not name.strip():
        return {"status": "error", "message": "Product name is required."}
    clean_name = name.strip()
    filename = f"{_slugify(clean_name)}.png"
    product = Product(
        name=clean_name,
        category=category or "",
        description=description or "",
        image_filename=filename,
        attributes=attributes or {},
    )
    try:
        stored = insert_product(product)
    except sqlite3.IntegrityError:
        return {
            "status": "error",
            "message": f"A product named '{clean_name}' already exists. Product names must be unique.",
        }
    return {
        "status": "success",
        "message": f"Product '{stored.name}' created (id={stored.id}).",
        "product": _product_payload(stored),
        "next_steps": (
            "Add a reference image: import_products_from_folder for existing photos, "
            f"or generate_product_image(product_id={stored.id}) to generate one. "
            f"Then create_campaign(product_id={stored.id}, store_name=..., city=..., state=...)."
        ),
    }


def import_products_from_folder(folder_path: str, category: str = "") -> dict:
    """Bulk-import products from a local folder of images.

    Each image file becomes one product: the filename stem (slugified) is the
    product name and the image is stored through the storage seam. Non-image
    files are ignored; duplicates are skipped; unusually small images are
    imported with a warning.

    Args:
        folder_path: Local folder containing .png/.jpg/.jpeg/.webp files.
        category: Category assigned to every imported product.

    Returns:
        Dict with status, message, created, skipped, warnings, next_steps.
    """
    folder = os.path.expanduser(folder_path)
    if not os.path.isdir(folder):
        return {"status": "error", "message": f"Folder not found: {folder_path}"}

    created, skipped, warnings = [], [], []
    for entry in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(entry)
        if ext.lower() not in _IMAGE_EXTENSIONS:
            continue
        with open(os.path.join(folder, entry), "rb") as f:
            data = f.read()
        if len(data) < _TINY_IMAGE_BYTES:
            warnings.append(
                f"{entry}: unusually small image ({len(data)} bytes) — imported anyway; verify it renders"
            )
        slug = _slugify(stem)
        filename = f"{slug}{ext.lower()}"
        product = Product(name=slug, category=category or "", image_filename=filename)
        try:
            stored = insert_product(product)
        except sqlite3.IntegrityError:
            skipped.append(f"{entry}: product '{slug}' already exists")
            continue
        path = storage.save_product_image(filename, data)
        _record_image_location(stored.id, path)
        created.append({"id": stored.id, "name": stored.name, "image_filename": filename})

    return {
        "status": "success",
        "message": f"Imported {len(created)} products from {folder_path} "
                   f"({len(skipped)} skipped, {len(warnings)} warnings).",
        "created": created,
        "skipped": skipped,
        "warnings": warnings,
        "next_steps": "Products are browse-ready with stored images. "
                      "Create campaigns with create_campaign(product_id=...).",
    }


def _record_image_location(product_id: int, path: str) -> None:
    """Record where the stored image landed (gcs_path or local_path column)."""
    column = "gcs_path" if storage.get_storage_mode() == "gcs" else "local_path"
    with get_db_cursor() as cursor:
        cursor.execute(f"UPDATE products SET {column} = ? WHERE id = ?", (path, product_id))


async def generate_product_image(product_id: int = 0, product_name: str = "",
                                 style_hint: str = "",
                                 tool_context: ToolContext = None) -> dict:
    """Generate a reference product photo for a product with no image yet.

    Produces a clean, neutral-background catalog reference shot (category-aware
    prompt; deliberately NOT a creative scene — creative variation belongs to
    the video pipeline's archetype system). Stores the image through the
    storage seam under the product's image_filename.

    Args:
        product_id: Product ID (preferred lookup).
        product_name: Product name (used when product_id is 0).
        style_hint: Optional styling nudge (e.g. "warm morning light").
        tool_context: ADK tool context (injected) — used to render the image
            as an artifact in the chat UI.

    Returns:
        Dict with status, message, product (with image_status), next_steps.
    """
    product = get_product(product_id) if product_id else None
    if product is None and product_name:
        product = get_product_by_name(product_name)
    if product is None:
        return {
            "status": "error",
            "message": f"Product not found (product_id={product_id}, product_name={product_name!r}). "
                       "Use list_products to browse the catalog.",
        }

    fragments = [f"Professional product photography of {product.name}"]
    if product.category:
        fragments.append(f"a {product.category}")
    if product.description:
        fragments.append(product.description)
    attr_text = ", ".join(
        f"{key}: {value}" for key, value in list(product.attributes.items())[:6]
    )
    prompt = ". ".join(fragments) + ". "
    if attr_text:
        prompt += f"Key attributes: {attr_text}. "
    if style_hint:
        prompt += f"Style: {style_hint}. "
    prompt += (
        "Clean neutral studio background, soft even lighting, the product centered "
        "and fully visible, catalog reference shot, no people, no text overlays."
    )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=IMAGE_GENERATION,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["image", "text"]),
        )
        image_bytes = None
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None):
                image_bytes = part.inline_data.data
                break
    except Exception as e:
        return {"status": "error", "message": f"Image generation failed: {e}"}

    if not image_bytes:
        return {
            "status": "error",
            "message": "Image model returned no image — try again, or adjust style_hint.",
        }

    path = storage.save_product_image(product.image_filename, image_bytes)
    _record_image_location(product.id, path)

    if tool_context:
        artifact = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        await tool_context.save_artifact(filename=product.image_filename, artifact=artifact)

    refreshed = get_product(product.id)
    return {
        "status": "success",
        "message": f"Reference image generated and stored for '{product.name}'.",
        "product": _product_payload(refreshed),
        "next_steps": f"create_campaign(product_id={product.id}, ...) to run this product, "
                      "then generate_video_from_product for ad videos.",
    }
```

- [ ] **Step 4: Wire into the Campaign agent**

In `app/agent.py`:

1. Add the import near the other tool imports:

```python
from .tools.onboarding_tools import (
    create_product,
    generate_product_image,
    import_products_from_folder,
)
```

2. In `CAMPAIGN_AGENT_INSTRUCTION`, insert this section between "## Your Responsibilities" and "## Creating Campaigns" — and add one bullet `- Onboard new products into the catalog (create, bulk-import, generate reference images)` to the responsibilities list:

```
## Onboarding New Products (Phase 15)
Any vendor can bring their own product — the catalog is not fixed:
- create_product(name, category, description, attributes) — add one product conversationally
- import_products_from_folder(folder_path, category) — bulk-import a folder of product photos
- generate_product_image(product_id) — generate a clean reference photo for a product without one
A product needs a stored reference image (image_status "available") before video
generation can use it as a visual reference; "pending" products can still get
campaigns, and videos fall back to text-only scene descriptions with a warning.
```

3. Append the three tools to `campaign_agent`'s `tools=[...]` list (after `get_location_demographics`):

```python
        # Product onboarding (Phase 15)
        create_product,
        import_products_from_folder,
        generate_product_image,
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_onboarding_tools.py -v` → PASS.
Run: `make test-unit` → PASS.
Run: `ruff check app/tools/onboarding_tools.py app/agent.py tests/unit/test_onboarding_tools.py` → clean.

- [ ] **Step 6: Commit**

```bash
git add app/tools/onboarding_tools.py app/agent.py tests/unit/test_onboarding_tools.py
git commit -m "feat: product onboarding tools (create/import/generate-image) on the Campaign agent"
```

---

### Task 5: Analytics-attach test (onboard → campaign → deterministic RPI)

**Files:**
- Test: `tests/unit/test_onboarding_analytics_attach.py` (new; no production code — this is doc 15 step 5's proof that an onboarded product flows into attribution with zero fixture changes)

**Interfaces:**
- Consumes: `create_product` (Task 4), `campaign_tools.create_campaign`, `demo_data.derive.derive_video_metrics_rows(ad_campaign_id, video_ids, date_from, date_to, windows=None)`, `metrics_shared.compute_rpi(total_revenue, total_impressions)`.

- [ ] **Step 1: Write the test**

Create `tests/unit/test_onboarding_analytics_attach.py`:

```python
"""Doc 15 step 5: a product onboarded via the new tools attaches to the
analytics chain with NO fixture data — campaign-id-keyed attribution derives
deterministic metrics and a finite RPI for a never-before-seen vertical."""

from datetime import date

import pytest


@pytest.fixture
def local_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.GCS_BUCKET", None)
    monkeypatch.setattr("app.config.PRODUCT_IMAGES_DIR", str(tmp_path / "product-images"))
    return tmp_path


def test_onboarded_product_flows_to_rpi(empty_test_db, local_mode):
    from app.database.db import get_db_cursor
    from app.demo_data.derive import derive_video_metrics_rows
    from app.tools.campaign_tools import create_campaign
    from app.tools.metrics_shared import compute_rpi
    from app.tools.onboarding_tools import create_product

    created = create_product(name="Aurora Cold Brew 330ml", category="beverage",
                             description="Nitro cold brew in a slim can")
    assert created["status"] == "success"
    product_id = created["product"]["id"]

    campaign = create_campaign(product_id=product_id, store_name="Demo Store",
                               city="Austin", state="TX")
    assert campaign["status"] == "success"
    campaign_id = campaign["campaign"]["id"]

    with get_db_cursor() as cursor:
        cursor.execute('''
            INSERT INTO campaign_videos
            (campaign_id, product_id, video_filename, status)
            VALUES (?, ?, 'aurora-demo.mp4', 'activated')
        ''', (campaign_id, product_id))
        video_id = cursor.lastrowid

    date_from, date_to = date(2026, 6, 1), date(2026, 6, 7)
    rows_a = derive_video_metrics_rows(campaign_id, [video_id], date_from, date_to)
    rows_b = derive_video_metrics_rows(campaign_id, [video_id], date_from, date_to)
    assert rows_a, "expected derived metric rows for the onboarded product's video"
    assert rows_a == rows_b, "derivation must be deterministic"

    total_impressions = sum(r["impressions"] for r in rows_a)
    total_revenue = sum(r["revenue"] for r in rows_a)
    assert total_impressions > 0
    rpi = compute_rpi(total_revenue, total_impressions)
    assert rpi > 0
```

Note: confirm `create_campaign`'s result shape (`campaign["campaign"]["id"]`) against `app/tools/campaign_tools.py:32`'s actual return before running; `test_retail_products.py:75-79` shows `result["campaign"]` exists. Also confirm the `campaign_videos` insert's NOT NULL columns against the schema in db.py — add any required columns (e.g. `variation_name`) with literal values if the insert fails.

- [ ] **Step 2: Run**

Run: `pytest tests/unit/test_onboarding_analytics_attach.py -v` → PASS (this test should pass immediately — it proves existing plumbing, it doesn't drive new code; if it fails, the failure is a real integration gap: report it, don't massage the test).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_onboarding_analytics_attach.py
git commit -m "test: onboarded product attaches to campaign-keyed attribution and yields deterministic RPI"
```

---

### Task 6: CLI wrapper `scripts/onboard_products.py`

**Files:**
- Create: `scripts/onboard_products.py`
- Test: `tests/unit/test_onboard_products_cli.py` (new)

**Interfaces:**
- Consumes: the three Task-4 functions, imported from `app.tools.onboarding_tools` — the CLI adds NO logic of its own (parity by construction; the test pins the dispatch).
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `create`, `import-folder`, `generate-image`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_onboard_products_cli.py`:

```python
"""CLI parity: scripts/onboard_products.py dispatches to the SAME functions the
Campaign agent's tools use, with the same arguments — no logic drift."""


def test_create_dispatch(monkeypatch, capsys):
    import scripts.onboard_products as cli
    calls = {}

    def fake_create(**kwargs):
        calls.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(cli, "create_product", fake_create)
    rc = cli.main(["create", "--name", "Aurora Cold Brew 330ml",
                   "--category", "beverage", "--description", "nitro",
                   "--attr", "volume_ml=330", "--attr", "caffeine_mg=120"])
    assert rc == 0
    assert calls == {
        "name": "Aurora Cold Brew 330ml",
        "category": "beverage",
        "description": "nitro",
        "attributes": {"volume_ml": "330", "caffeine_mg": "120"},
    }
    assert '"status": "success"' in capsys.readouterr().out


def test_import_folder_dispatch(monkeypatch):
    import scripts.onboard_products as cli
    calls = {}
    monkeypatch.setattr(cli, "import_products_from_folder",
                        lambda **kw: calls.update(kw) or {"status": "success"})
    rc = cli.main(["import-folder", "/tmp/imgs", "--category", "homeware"])
    assert rc == 0
    assert calls == {"folder_path": "/tmp/imgs", "category": "homeware"}


def test_generate_image_dispatch(monkeypatch):
    import scripts.onboard_products as cli
    calls = {}

    async def fake_generate(**kwargs):
        calls.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(cli, "generate_product_image", fake_generate)
    rc = cli.main(["generate-image", "--product-id", "3",
                   "--style-hint", "warm morning light"])
    assert rc == 0
    assert calls == {"product_id": 3, "product_name": "",
                     "style_hint": "warm morning light"}


def test_error_result_returns_nonzero(monkeypatch):
    import scripts.onboard_products as cli
    monkeypatch.setattr(cli, "create_product", lambda **kw: {"status": "error", "message": "nope"})
    assert cli.main(["create", "--name", "X"]) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_onboard_products_cli.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `scripts/onboard_products.py`**

```python
"""CLI for product onboarding — thin wrapper over the SAME functions the
Campaign agent's tools use (app/tools/onboarding_tools.py). No logic here
beyond argument parsing; parity is by construction and pinned by
tests/unit/test_onboard_products_cli.py.

Usage:
  python -m scripts.onboard_products create --name "Aurora Cold Brew 330ml" \
      --category beverage --description "nitro cold brew" --attr volume_ml=330
  python -m scripts.onboard_products import-folder /path/to/images --category homeware
  python -m scripts.onboard_products generate-image --product-id 3 --style-hint "warm light"

Environment: same as the app (app/.env). Leave GCS_BUCKET unset for
local-first mode; set DEMO_DATASET=none for an empty from-scratch catalog.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.onboarding_tools import (  # noqa: E402
    create_product,
    generate_product_image,
    import_products_from_folder,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Onboard products into the catalog")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create one product")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--category", default="")
    p_create.add_argument("--description", default="")
    p_create.add_argument("--attr", action="append", default=[],
                          metavar="KEY=VALUE", help="Repeatable vertical-specific attribute")

    p_import = sub.add_parser("import-folder", help="Bulk-import a folder of product images")
    p_import.add_argument("folder_path")
    p_import.add_argument("--category", default="")

    p_gen = sub.add_parser("generate-image", help="Generate a reference product photo")
    p_gen.add_argument("--product-id", type=int, default=0)
    p_gen.add_argument("--product-name", default="")
    p_gen.add_argument("--style-hint", default="")

    args = parser.parse_args(argv)

    if args.command == "create":
        attributes = {}
        for pair in args.attr:
            key, _, value = pair.partition("=")
            if not key or not _:
                parser.error(f"--attr must be KEY=VALUE, got {pair!r}")
            attributes[key] = value
        result = create_product(name=args.name, category=args.category,
                                description=args.description, attributes=attributes)
    elif args.command == "import-folder":
        result = import_products_from_folder(folder_path=args.folder_path,
                                             category=args.category)
    else:  # generate-image
        result = asyncio.run(generate_product_image(
            product_id=args.product_id, product_name=args.product_name,
            style_hint=args.style_hint))

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_onboard_products_cli.py -v` → PASS.
Run: `ruff check scripts/onboard_products.py tests/unit/test_onboard_products_cli.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/onboard_products.py tests/unit/test_onboard_products_cli.py
git commit -m "feat: onboard_products CLI — same functions as the agent tools, dispatch pinned by parity test"
```

---

### Task 7: Demo-asset Drive bundle (build / verify / install)

**Files:**
- Create: `scripts/demo_assets.py`
- Modify: `app/requirements.txt` (add `gdown>=5.2.0` after the google-* block)
- Test: `tests/unit/test_demo_assets.py` (new)

**Interfaces:**
- Consumes: `app.config.LOCAL_ASSETS_DIR`; `DEMO_ASSETS_DRIVE_ID` env var (NOT a config.py constant — it's setup tooling, not app runtime).
- Produces: `build_bundle(source_dir: str, out_path: str) -> dict`, `verify_and_extract(zip_path: str, dest_dir: str) -> dict` (raises `ValueError` on manifest mismatch/tamper/zip-slip), `install(from_file: str | None = None, dest_dir: str | None = None) -> dict`, `main(argv=None) -> int`. Bundle format: zip containing `manifest.json` (`{"version": 1, "files": {relpath: "sha256:<hex>"}, "expected_count": N}`) plus the files at their relpaths (e.g. `product-images/red-mug.png` → installs under `LOCAL_ASSETS_DIR/product-images/`). Marker file `<dest>/.demo-assets-installed` makes install idempotent.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_demo_assets.py`:

```python
"""Phase 15 demo-asset bundle: sha256-manifest build/verify/install, no GCS
anywhere. Network download (gdown) is NOT tested — install is exercised via
--from-file, the same code path minus the fetch."""

import json
import zipfile

import pytest


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "assets-src"
    (src / "product-images").mkdir(parents=True)
    (src / "product-images" / "red-mug.png").write_bytes(b"\x89PNG" + b"a" * 500)
    (src / "product-images" / "blue-bottle.jpg").write_bytes(b"\xff\xd8" + b"b" * 500)
    return src


def test_build_writes_manifest_and_files(source_dir, tmp_path):
    from scripts.demo_assets import build_bundle
    out = tmp_path / "demo-assets.zip"
    result = build_bundle(str(source_dir), str(out))
    assert result["status"] == "success"
    assert result["file_count"] == 2
    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["version"] == 1
    assert manifest["expected_count"] == 2
    assert manifest["files"]["product-images/red-mug.png"].startswith("sha256:")


def test_verify_and_extract_roundtrip(source_dir, tmp_path):
    from scripts.demo_assets import build_bundle, verify_and_extract
    out = tmp_path / "demo-assets.zip"
    build_bundle(str(source_dir), str(out))
    dest = tmp_path / "installed"
    result = verify_and_extract(str(out), str(dest))
    assert result["installed_count"] == 2
    assert (dest / "product-images" / "red-mug.png").read_bytes() == b"\x89PNG" + b"a" * 500


def test_tampered_file_rejected(source_dir, tmp_path):
    from scripts.demo_assets import build_bundle, verify_and_extract
    out = tmp_path / "demo-assets.zip"
    build_bundle(str(source_dir), str(out))
    # Rewrite one payload file with different bytes, keep the old manifest
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(tampered, "w") as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "product-images/red-mug.png":
                data = b"EVIL" + data
            zout.writestr(item, data)
    with pytest.raises(ValueError, match="sha256 mismatch"):
        verify_and_extract(str(tampered), str(tmp_path / "dest2"))


def test_zip_slip_rejected(tmp_path):
    from scripts.demo_assets import verify_and_extract
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", json.dumps(
            {"version": 1, "files": {"../escape.txt": "sha256:00"}, "expected_count": 1}))
        zf.writestr("../escape.txt", b"pwn")
    with pytest.raises(ValueError, match="unsafe path"):
        verify_and_extract(str(evil), str(tmp_path / "dest"))


def test_install_from_file_and_idempotence(source_dir, tmp_path, capsys):
    from scripts.demo_assets import build_bundle, install
    out = tmp_path / "demo-assets.zip"
    build_bundle(str(source_dir), str(out))
    dest = tmp_path / "assets-root"
    first = install(from_file=str(out), dest_dir=str(dest))
    assert first["status"] == "success"
    assert (dest / ".demo-assets-installed").exists()
    second = install(from_file=str(out), dest_dir=str(dest))
    assert second["status"] == "skipped"  # marker → idempotent


def test_install_without_drive_id_skips_gracefully(tmp_path, monkeypatch):
    from scripts.demo_assets import install
    monkeypatch.delenv("DEMO_ASSETS_DRIVE_ID", raising=False)
    result = install(dest_dir=str(tmp_path / "dest"))
    assert result["status"] == "skipped"
    assert "not configured" in result["message"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_demo_assets.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `scripts/demo_assets.py`**

```python
"""Demo asset bundle: build, verify, install (Phase 15).

Local-first replacement for pulling demo product images from a personal GCS
bucket: assets ship as an owner-hosted Google Drive zip, auto-downloadable at
setup. No GCS anywhere in this path (ws09 directive).

  python -m scripts.demo_assets build --source DIR --out demo-assets.zip
  python -m scripts.demo_assets install [--from-file demo-assets.zip]

install resolves the bundle from --from-file, else downloads by the
DEMO_ASSETS_DRIVE_ID env var (gdown); with neither, it skips gracefully.
Contents are verified against the bundled manifest.json (sha256 per file)
before landing in LOCAL_ASSETS_DIR; a marker file makes re-runs no-ops.

Owner workflow to (re)publish the bundle: collect the demo product images
into a folder tree (product-images/<file>...), run `build`, upload the zip to
Google Drive (anyone-with-link), set DEMO_ASSETS_DRIVE_ID to the file ID.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import LOCAL_ASSETS_DIR  # noqa: E402

MANIFEST_NAME = "manifest.json"
MARKER_NAME = ".demo-assets-installed"
BUNDLE_VERSION = 1


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_bundle(source_dir: str, out_path: str) -> dict:
    """Zip every file under source_dir (relative paths preserved) + manifest."""
    source = Path(source_dir)
    if not source.is_dir():
        return {"status": "error", "message": f"Source folder not found: {source_dir}"}
    files = {}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source).as_posix()
            data = path.read_bytes()
            files[rel] = _sha256(data)
            zf.writestr(rel, data)
        manifest = {"version": BUNDLE_VERSION, "files": files, "expected_count": len(files)}
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
    return {"status": "success", "bundle": out_path, "file_count": len(files)}


def verify_and_extract(zip_path: str, dest_dir: str) -> dict:
    """Verify every bundled file against manifest.json, then extract to dest.

    Raises ValueError on a missing manifest, count mismatch, sha256
    mismatch, or unsafe (absolute / ..) paths. Nothing is written unless the
    whole bundle verifies.
    """
    dest = Path(dest_dir)
    with zipfile.ZipFile(zip_path) as zf:
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except KeyError:
            raise ValueError(f"Bundle has no {MANIFEST_NAME}") from None
        files = manifest.get("files", {})
        if len(files) != manifest.get("expected_count"):
            raise ValueError("manifest expected_count does not match its file map")
        verified = {}
        for rel, expected in files.items():
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ValueError(f"unsafe path in bundle: {rel}")
            data = zf.read(rel)
            actual = _sha256(data)
            if actual != expected:
                raise ValueError(f"sha256 mismatch for {rel}: {actual} != {expected}")
            verified[rel] = data
    for rel, data in verified.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"status": "success", "installed_count": len(verified), "dest": str(dest)}


def _download_from_drive(drive_id: str, out_path: str) -> str:
    import gdown  # lazy: only the download path needs it
    return gdown.download(id=drive_id, output=out_path, quiet=False)


def install(from_file: str | None = None, dest_dir: str | None = None) -> dict:
    """Install the demo asset bundle into dest_dir (default LOCAL_ASSETS_DIR)."""
    dest = Path(dest_dir or LOCAL_ASSETS_DIR)
    marker = dest / MARKER_NAME
    if marker.exists():
        return {"status": "skipped",
                "message": f"Demo assets already installed ({marker}). Delete the marker to force reinstall."}

    if from_file:
        zip_path = from_file
    else:
        drive_id = os.environ.get("DEMO_ASSETS_DRIVE_ID", "").strip()
        if not drive_id:
            return {"status": "skipped",
                    "message": "Demo asset bundle not configured (DEMO_ASSETS_DRIVE_ID unset "
                               "and no --from-file). Skipping — the app works without it; "
                               "seeded products will show image_status=missing locally."}
        fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="demo-assets-")
        os.close(fd)
        _download_from_drive(drive_id, zip_path)

    result = verify_and_extract(zip_path, str(dest))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": BUNDLE_VERSION,
                                  "installed_count": result["installed_count"]}))
    return {"status": "success",
            "message": f"Installed {result['installed_count']} demo asset files into {dest}."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or install the demo asset bundle")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build a bundle zip from a source folder")
    p_build.add_argument("--source", required=True)
    p_build.add_argument("--out", required=True)

    p_install = sub.add_parser("install", help="Verify + install a bundle")
    p_install.add_argument("--from-file", default=None,
                           help="Use a local bundle zip instead of downloading from Drive")
    p_install.add_argument("--dest", default=None,
                           help="Install root (default: LOCAL_ASSETS_DIR)")

    args = parser.parse_args(argv)
    if args.command == "build":
        result = build_bundle(args.source, args.out)
    else:
        result = install(from_file=args.from_file, dest_dir=args.dest)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in ("success", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `app/requirements.txt` (after `google-cloud-storage>=2.19.0`):

```
gdown>=5.2.0
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_demo_assets.py -v` → PASS (no network — gdown is imported only inside `_download_from_drive`, which no test calls).
Run: `ruff check scripts/demo_assets.py tests/unit/test_demo_assets.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_assets.py app/requirements.txt tests/unit/test_demo_assets.py
git commit -m "feat: demo-asset Drive bundle — sha256-manifest build/verify/install, graceful skip when unconfigured"
```

---

### Task 8: Docs — SETUP_INSTRUCTIONS local-first section + from-scratch demo scenario

**Files:**
- Modify: `SETUP_INSTRUCTIONS.md` (append a new section)
- Create: `docs/demo-scenarios/from-scratch-onboarding.md`

**Interfaces:** none (docs). Root `DEMO_GUIDE.md` journeys and any phase-doc amendments are handled at the verify/finish steps of the workstream lifecycle, NOT in this task.

- [ ] **Step 1: Append to `SETUP_INSTRUCTIONS.md`**

Append this section (adjust the heading level to match the file's existing structure):

```markdown
## Local-first mode (Phase 15)

The app is local-first: with `GCS_BUCKET` **unset**, every asset (product
images, videos, thumbnails) lives under the local assets root and tool
responses never contain `storage.googleapis.com` URLs. GCS is an explicit
opt-in for cloud deploys (`GCS_BUCKET=<bucket>`); the old hardcoded default
bucket is gone.

**Check your `app/.env`:** older dev `.env` files set `GCS_BUCKET` — as long
as that line is present you are in GCS mode. Comment it out (or delete it)
for local-first mode.

- `LOCAL_ASSETS_DIR` (optional): local asset root; defaults to the project
  root, giving the pre-existing `selected/` and `generated/` folders plus the
  new `product-images/`.
- `DEMO_DATASET=fashion|none` (default `fashion`): which demo catalog gets
  seeded at startup. `fashion` = today's full demo (22 fashion + 6 retail
  core products, 4 campaigns). `none` = empty catalog — the from-scratch
  onboarding path (`docs/demo-scenarios/from-scratch-onboarding.md`).
  This is a demo-scoped dataset selector, NOT a mode knob — `APP_MODE`
  remains the only mode env var.

### Demo asset bundle (product images without GCS)

Demo product images ship as an owner-hosted Google Drive zip:

```bash
python -m scripts.demo_assets install                     # uses DEMO_ASSETS_DRIVE_ID
python -m scripts.demo_assets install --from-file x.zip   # or a local bundle
```

Unset `DEMO_ASSETS_DRIVE_ID` → the installer skips gracefully; the app still
works, seeded products just report `image_status: missing` locally.

**Owner: publishing/refreshing the bundle** — collect the demo images into a
folder tree (`<src>/product-images/<file>...`), then:

```bash
python -m scripts.demo_assets build --source <src> --out demo-assets.zip
# upload demo-assets.zip to Google Drive (anyone-with-link), then set
# DEMO_ASSETS_DRIVE_ID=<drive-file-id> in app/.env
```

### Onboarding products from the CLI

Same functions as the Campaign agent's tools:

```bash
python -m scripts.onboard_products create --name "Aurora Cold Brew 330ml" --category beverage --attr volume_ml=330
python -m scripts.onboard_products import-folder /path/to/images --category homeware
python -m scripts.onboard_products generate-image --product-id 3
```
```

- [ ] **Step 2: Create `docs/demo-scenarios/from-scratch-onboarding.md`**

Follow `docs/demo-scenarios/fashion.md`'s conventions exactly (Scenario/Scene structure, named expected tool calls, Pass/Fail criteria per scene). Content:

```markdown
# Demo Scenario: From-Scratch Product Onboarding

Proves the Phase 15 from-scratch path: an EMPTY catalog (`DEMO_DATASET=none`),
local-first storage (`GCS_BUCKET` unset), conversational onboarding, campaign
creation, and the no-GCS-URL guarantee.

**Server env (required):** start `make dev` with `DEMO_DATASET=none` set and
`GCS_BUCKET` unset (comment it out of `app/.env` first), after `make reset-db`.

**Global pass condition (every scene):** no tool response anywhere in the
session contains the string `storage.googleapis.com`.

## Scenario 1: Empty catalog

### Scene 1.1 — catalog starts empty
Query: "Show me all products in the catalog"
Expected tool call: `list_products` (Media agent)
Pass: response reports 0 products; no error. Fail: any seeded product appears.

## Scenario 2: Conversational onboarding

### Scene 2.1 — create a product
Query: "Add a new product: Aurora Cold Brew 330ml, category beverage, a nitro
cold brew in a slim can, 330ml volume"
Expected tool call: `create_product` (Campaign agent) with name="Aurora Cold
Brew 330ml", category="beverage"
Pass: status success, image_status "pending", next_steps mention image
generation. Fail: routed to a different tool, or error.

### Scene 2.2 — generate its reference image
Query: "Generate a product image for Aurora Cold Brew"
Expected tool call: `generate_product_image` (Campaign agent)
Pass: status success, image_status "available", image rendered as an artifact
in the chat. Fail: no image artifact, or a storage.googleapis.com URL anywhere.

### Scene 2.3 — product is browse-ready
Query: "Show me the catalog now"
Expected tool call: `list_products`
Pass: exactly 1 product, image_status "available", NO image_url field (local
mode). Fail: image_url present or status wrong.

## Scenario 3: Campaign on the onboarded product

### Scene 3.1 — create the campaign
Query: "Create a campaign for Aurora Cold Brew at Demo Store in Austin, Texas"
Expected tool call: `create_campaign` (Campaign agent) with the new product_id
Pass: campaign created, name contains product + store. Fail: error, or product
not found.

## Scenario 4 (OPTIONAL — slow, real Veo call): video on the onboarded product

### Scene 4.1 — generate a video
Query: "Generate a video ad for the Aurora Cold Brew campaign"
Expected tool call: `generate_video_from_product`
Pass: status success with reference_image_used=true (the generated image was
found through the local seam) and NO warning about missing product image.
Fail: warning "No product image found" despite Scene 2.2 having passed.
```

- [ ] **Step 3: Commit**

```bash
git add SETUP_INSTRUCTIONS.md docs/demo-scenarios/from-scratch-onboarding.md
git commit -m "docs: local-first setup section + from-scratch onboarding demo scenario"
```

---

## Post-task verification (workstream lifecycle, not plan tasks)

After all 8 tasks: `make test-unit && make test-e2e` green; validation greps (`grep -rn "kaggle-on-gcp" app/ --exclude=.env` → zero; `grep -rn "storage.googleapis.com" app/ | grep -v storage.py` → only the single construction site in storage.py remains); then `verifying-with-demo-scenarios` runs `from-scratch-onboarding.md` (server: `DEMO_DATASET=none`, `GCS_BUCKET` unset) **plus** fashion F1+F3 regression under default settings; root `DEMO_GUIDE.md` gets the ws15 journeys; final whole-branch review; PR per `finishing-a-development-branch`.
