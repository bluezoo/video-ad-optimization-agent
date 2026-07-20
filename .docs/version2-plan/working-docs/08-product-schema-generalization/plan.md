# Product Schema Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A typed, vertical-agnostic `Product` model with a row↔model adapter (metadata JSON ↔ `attributes` dict), all consumers migrated, deliberate campaign-category behavior (Option A), and a multi-vertical retail core test set proving genericity.

**Architecture:** `Product` (pydantic, `from_row`/`to_row`) parses the existing `metadata` JSON column into an open `attributes` dict and folds the legacy fashion columns into it, giving one uniform access path. `get_product()`/`get_product_by_name()`/`list_products()` return `Product`; the ~15 dict-access consumer lines migrate in one task with a golden test pinning Veo prompt text. Campaign category becomes a validated, explicitly-defaulted theme taxonomy decoupled from the now-open product category.

**Tech Stack:** pydantic (already a dep), sqlite3, pytest. **No new dependencies.**

## Global Constraints

- **Owner decisions (2026-07-20 gate):** category = **Option A** — keep the CHECK + `CAMPAIGN_CATEGORIES` closed theme list, add **`always-on`**, explicit optional validated `category` param on `create_campaign`, unmapped product categories default to `always-on` (deliberate, never silent `essentials`). Fixture = **multi-vertical retail core test set** (beverage/QSR/electronics/furniture/home-appliance), attributes-first, image files referenced but NOT generated (Phase 14a/15).
- **Veo prompt text must not change for the existing fashion catalog** — `prompt_builders.py` encodes `style → category → "elegant fashion piece"` fallbacks; a golden test captured BEFORE migration must pass unchanged AFTER.
- **No products-table schema change.** Fashion columns stay (they're already nullable); no ALTER, no destructive migration, `products_data.py`'s 22 entries untouched.
- **Agent-facing `list_products` tool output contract unchanged** (same keys: id, name, category, style, color, fabric, image_filename, optional image_url).
- **`Product.id: int`** (Phase 10 pins `product_id` against it).
- **Adapter must round-trip** (`from_row(to_row(...))` lossless) — Phase 15's `create_product` writes through it.
- SQLite CHECK can't be ALTERed: the `always-on` addition applies to fresh DBs via CREATE TABLE; existing DBs need `make reset-db` — documented in SETUP_INSTRUCTIONS.md, no automated rebuild migration.
- **Self-service substrate (owner directive 2026-07-20):** the persistence adapter must support inserting a brand-new product at runtime — db-layer `insert_product(product: Product) -> Product` — and persistence/retrieval/campaign-creation must NOT require the referenced image file to exist (vendor images arrive later via upload or nano-banana generation; Phase 15's agent tools wrap this function). Agent-facing CRUD tools remain Phase 15.
- **Do NOT touch:** README.md, DEMO_GUIDE.md, `app/database/products_data.py` entries, `presentation_mode` (Phase 9), product CRUD tools (Phase 15), `DEMO_DATASET` runtime selection (Phase 15).
- Tests run against a copy of `campaigns.db` (conftest) which may predate the retail fixtures — retail-fixture tests must call `populate_retail_test_products()` themselves (it's idempotent).
- A PostToolUse hook runs `make test-unit` after `app/**/*.py` edits. No AI-attribution trailers in commits.

---

### Task 1: `Product` model with row↔model adapter

**Files:**
- Create: `app/models/product.py`
- Test: `tests/unit/test_product_model.py` (new file)

**Interfaces:**
- Produces: `app.models.product.Product` — fields `id: int | None`, `name: str`, `category: str = ""`, `description: str = ""` (maps to the `details` column), `image_filename: str`, `gcs_path/local_path/created_at: str | None`, `attributes: dict = {}`; classmethod `from_row(row: dict) -> Product`; method `to_row() -> dict` (column dict whose `metadata` is `json.dumps(attributes)`). Tasks 2–4 consume all of these exactly.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_product_model.py`:

```python
"""Tests for the generic Product model and its row adapter (Phase 8)."""

import json

from app.models.product import Product


def _fashion_row(**overrides):
    """A row shaped like the seeded fashion catalog (both seeders dump the
    full entry dict into metadata, duplicating the typed columns)."""
    entry = {
        "name": "black-high-waist-trousers",
        "category": "pants",
        "style": "tailored wide-leg trousers",
        "color": "classic black",
        "fabric": "wool blend suiting",
        "details": "high waist, pleated front, wide straight leg, side pockets",
        "occasion": "office and professional wear",
        "image_filename": "black-high-waist-trousers.png",
        "local_path": "scripts/products/black-high-waist-trousers.png",
    }
    row = {
        "id": 1,
        **{k: entry.get(k) for k in ("name", "category", "style", "color",
                                     "fabric", "details", "occasion",
                                     "image_filename", "local_path")},
        "gcs_path": None,
        "metadata": json.dumps(entry),
        "created_at": "2026-07-20 00:00:00",
    }
    row.update(overrides)
    return row


class TestFromRow:
    def test_core_fields(self):
        p = Product.from_row(_fashion_row())
        assert p.id == 1
        assert p.name == "black-high-waist-trousers"
        assert p.category == "pants"
        assert p.description == "high waist, pleated front, wide straight leg, side pockets"
        assert p.image_filename == "black-high-waist-trousers.png"

    def test_fashion_columns_fold_into_attributes(self):
        p = Product.from_row(_fashion_row())
        assert p.attributes["style"] == "tailored wide-leg trousers"
        assert p.attributes["color"] == "classic black"
        assert p.attributes["fabric"] == "wool blend suiting"
        assert p.attributes["occasion"] == "office and professional wear"

    def test_attributes_exclude_core_column_duplicates(self):
        p = Product.from_row(_fashion_row())
        for core in ("name", "category", "details", "image_filename", "local_path"):
            assert core not in p.attributes

    def test_metadata_only_key_survives(self):
        # 7 of 22 seeded products carry 'pattern' ONLY inside metadata JSON
        entry_meta = json.loads(_fashion_row()["metadata"])
        entry_meta["pattern"] = "pinstripe"
        p = Product.from_row(_fashion_row(metadata=json.dumps(entry_meta)))
        assert p.attributes["pattern"] == "pinstripe"

    def test_row_column_wins_over_metadata(self):
        row = _fashion_row(style="updated style")
        p = Product.from_row(row)
        assert p.attributes["style"] == "updated style"

    def test_null_and_invalid_metadata_tolerated(self):
        assert Product.from_row(_fashion_row(metadata=None)).attributes["style"] \
            == "tailored wide-leg trousers"
        assert Product.from_row(_fashion_row(metadata="{not json")).attributes["color"] \
            == "classic black"

    def test_attributes_first_row_no_fashion_columns(self):
        row = {
            "id": 30, "name": "aurora-cold-brew-330ml", "category": "beverage",
            "style": None, "color": None, "fabric": None, "occasion": None,
            "details": "slow-steeped single-origin cold brew",
            "image_filename": "aurora-cold-brew-330ml.png",
            "gcs_path": None, "local_path": None, "created_at": None,
            "metadata": json.dumps({"flavor": "dark chocolate notes", "volume_ml": 330}),
        }
        p = Product.from_row(row)
        assert p.attributes == {"flavor": "dark chocolate notes", "volume_ml": 330}
        assert "style" not in p.attributes


class TestToRowRoundTrip:
    def test_round_trip_is_lossless(self):
        original = Product(
            name="aurora-cold-brew-330ml",
            category="beverage",
            description="slow-steeped single-origin cold brew",
            image_filename="aurora-cold-brew-330ml.png",
            attributes={"flavor": "dark chocolate notes", "volume_ml": 330,
                        "packaging": "slim can", "dietary_tags": ["vegan"]},
        )
        row = original.to_row()
        row.update({"id": 99, "created_at": None})
        restored = Product.from_row(row)
        assert restored.name == original.name
        assert restored.category == original.category
        assert restored.description == original.description
        assert restored.attributes == original.attributes

    def test_to_row_puts_legacy_attributes_in_typed_columns(self):
        p = Product.from_row(_fashion_row())
        row = p.to_row()
        assert row["style"] == "tailored wide-leg trousers"
        assert row["color"] == "classic black"
        assert row["details"] == p.description
        assert json.loads(row["metadata"])["fabric"] == "wool blend suiting"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_product_model.py -v`
Expected: all fail with `ModuleNotFoundError: No module named 'app.models.product'`.

- [ ] **Step 3: Implement `app/models/product.py`**

```python
"""Generic product model — the vertical-agnostic representation of a product.

Backed by the products table: typed core columns plus the metadata JSON
column, which carries all vertical-specific attributes (fashion's
style/color/fabric/occasion, a beverage's flavor/volume, ...) with no fixed
schema by design (Phase 8). Phase 15's product CRUD writes through to_row().
"""

import json
from typing import Any

from pydantic import BaseModel, Field

# products columns that map to typed Product fields (or storage internals) —
# anything else found in the metadata JSON belongs in `attributes`.
_CORE_ROW_KEYS = {
    "id", "name", "category", "details", "description",
    "image_filename", "gcs_path", "local_path", "metadata", "created_at",
}
# Legacy fashion columns: still real columns for the seeded catalog, but
# exposed uniformly through `attributes` so consumers have one access path.
_LEGACY_ATTRIBUTE_COLUMNS = ("style", "color", "fabric", "occasion")


class Product(BaseModel):
    """A product advertisable on in-store screens — any retail vertical."""

    id: int | None = None
    name: str
    category: str = ""
    description: str = ""  # maps to the products.details column
    image_filename: str
    gcs_path: str | None = None
    local_path: str | None = None
    created_at: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict) -> "Product":
        """Build a Product from a products-table row dict.

        metadata JSON keys become `attributes` (minus core-column
        duplicates — both seeders dump the whole entry dict); the legacy
        fashion columns then fold in on top (row value wins), so every
        historical row shape produces the same attributes.
        """
        raw_meta = row.get("metadata")
        try:
            meta = json.loads(raw_meta) if raw_meta else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        attributes = {
            key: value for key, value in meta.items()
            if key not in _CORE_ROW_KEYS and value is not None
        }
        for column in _LEGACY_ATTRIBUTE_COLUMNS:
            if row.get(column) is not None:
                attributes[column] = row[column]
        return cls(
            id=row.get("id"),
            name=row["name"],
            category=row.get("category") or "",
            description=row.get("details") or "",
            image_filename=row["image_filename"],
            gcs_path=row.get("gcs_path"),
            local_path=row.get("local_path"),
            created_at=str(row["created_at"]) if row.get("created_at") is not None else None,
            attributes=attributes,
        )

    def to_row(self) -> dict:
        """Column dict for INSERT INTO products — the from_row round-trip.

        Legacy fashion attributes land back in their typed columns; the
        whole attributes dict is serialized into metadata, so nothing is
        lost in either direction.
        """
        return {
            "name": self.name,
            "category": self.category or None,
            "style": self.attributes.get("style"),
            "color": self.attributes.get("color"),
            "fabric": self.attributes.get("fabric"),
            "occasion": self.attributes.get("occasion"),
            "details": self.description or None,
            "image_filename": self.image_filename,
            "gcs_path": self.gcs_path,
            "local_path": self.local_path,
            "metadata": json.dumps(self.attributes),
        }
```

(Follow `CreativeVariation`'s convention: importable from the module, NOT added to `app/models/__init__.py` — that package exports only video_properties symbols.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_product_model.py -v` — all pass.

- [ ] **Step 5: Lint + unit suite**

Run: `.venv/bin/ruff check app/models/product.py tests/unit/test_product_model.py` → clean.
Run: `make test-unit` → all pass (nothing else touched yet).

- [ ] **Step 6: Commit**

```bash
git add app/models/product.py tests/unit/test_product_model.py
git commit -m "Add generic Product model with metadata<->attributes row adapter"
```

---

### Task 2: Adapter migration — typed returns and all consumers

**Files:**
- Modify: `app/database/db.py` (`get_product` :389-406, `get_product_by_name` :409-426, `list_products` :429-449 + one import)
- Modify: `app/tools/video_tools.py` (lines ~211, ~281, ~397, 483, 523, 537, 686, 711, and the `list_products` tool internals ~1749-1771)
- Modify: `app/tools/prompt_builders.py` (product access at :42-45, :144, :283-286 + type hints)
- Modify: `app/tools/campaign_tools.py` (product access at :70, :83, :88, :109)
- Create: `tests/unit/data/golden_scene_prompt_product1.txt` (captured, not hand-written)
- Test: `tests/unit/test_product_adapter.py` (new), golden test included

**Interfaces:**
- Consumes: `Product` from Task 1 (exact fields/methods above).
- Produces: `db.get_product(product_id) -> Product | None`, `db.get_product_by_name(name) -> Product | None`, `db.list_products(category=None) -> list[Product]`. Tasks 3–4 rely on these signatures.

- [ ] **Step 1: Capture the golden prompt BEFORE any change**

With the code still unmodified, run:

```bash
mkdir -p tests/unit/data
.venv/bin/python - << 'EOF'
from app.database.db import get_product
from app.models.variation import CreativeVariation
from app.tools.prompt_builders import build_scene_image_prompt, build_creative_prompt

product = get_product(1)  # black-high-waist-trousers (dict today)
variation = CreativeVariation(name="golden-baseline")
scene = build_scene_image_prompt(product, variation)
creative = build_creative_prompt(product, variation)
open("tests/unit/data/golden_scene_prompt_product1.txt", "w").write(scene)
open("tests/unit/data/golden_creative_prompt_product1.txt", "w").write(creative)
print("captured", len(scene), len(creative))
EOF
```

(If `campaigns.db` is missing in the worktree, run `.venv/bin/python -c "from app.database.db import init_database; init_database()"` first.)

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_product_adapter.py`:

```python
"""Typed-adapter regression tests: get_product/list_products return Product
and the migration does not change Veo prompt text (Phase 8)."""

from pathlib import Path

from app.database.db import get_product, get_product_by_name, list_products
from app.models.product import Product
from app.models.variation import CreativeVariation
from app.tools.prompt_builders import build_creative_prompt, build_scene_image_prompt

GOLDEN_DIR = Path(__file__).parent / "data"


class TestTypedReturns:
    def test_get_product_returns_typed(self, test_db):
        p = get_product(1)
        assert isinstance(p, Product)
        assert p.id == 1
        assert p.name == "black-high-waist-trousers"
        assert p.attributes["style"] == "tailored wide-leg trousers"

    def test_get_product_missing_returns_none(self, test_db):
        assert get_product(999999) is None

    def test_get_product_by_name_typed(self, test_db):
        p = get_product_by_name("black-high-waist-trousers")
        assert isinstance(p, Product)
        assert p.id == 1

    def test_all_seed_products_typed_and_valid(self, test_db):
        products = list_products()
        assert len(products) >= 22
        for p in products:
            assert isinstance(p, Product)
            assert p.id and p.name and p.image_filename

    def test_category_filter_typed(self, test_db):
        for p in list_products(category="dress"):
            assert p.category == "dress"

    def test_pattern_metadata_only_key_present(self, test_db):
        # 7/22 seed entries have 'pattern' only in metadata JSON
        assert sum(1 for p in list_products() if "pattern" in p.attributes) >= 1


class TestGoldenPrompts:
    """The adapter migration must not change prompt text for the fashion
    catalog (style -> category -> literal fallback preserved)."""

    def test_scene_prompt_unchanged(self, test_db):
        product = get_product(1)
        variation = CreativeVariation(name="golden-baseline")
        expected = (GOLDEN_DIR / "golden_scene_prompt_product1.txt").read_text()
        assert build_scene_image_prompt(product, variation) == expected

    def test_creative_prompt_unchanged(self, test_db):
        product = get_product(1)
        variation = CreativeVariation(name="golden-baseline")
        expected = (GOLDEN_DIR / "golden_creative_prompt_product1.txt").read_text()
        assert build_creative_prompt(product, variation) == expected


class TestToolOutputContractsUnchanged:
    def test_list_products_tool_keys(self, test_db):
        from app.tools.video_tools import list_products as list_products_tool
        result = list_products_tool(include_urls=False)
        assert result["status"] == "success"
        product = result["products"][0]
        for key in ("id", "name", "category", "style", "color", "fabric", "image_filename"):
            assert key in product

    def test_create_campaign_still_works_typed(self, test_db):
        from app.tools.campaign_tools import create_campaign
        result = create_campaign(product_id=1, store_name="Adapter Test Store",
                                 city="Austin", state="TX")
        assert result["status"] == "success"
        assert result["campaign"]["product_name"] == "black-high-waist-trousers"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_product_adapter.py -v`
Expected: `TestTypedReturns` fails (`isinstance` False — still dicts); golden tests PASS (code unchanged); contract tests pass. This confirms the golden capture is a true baseline.

- [ ] **Step 4: Migrate `app/database/db.py`**

Add `from ..models.product import Product` to db.py's imports. Replace the three read functions' bodies (keep SELECTs identical):

- `get_product` (:389): return type annotation `-> Product | None`; docstring "Get a product by ID as a typed Product (metadata parsed into attributes)."; `if row: return Product.from_row(dict(row))` / `return None`.
- `get_product_by_name` (:409): same change (`-> Product | None`).
- `list_products` (:429): `-> list[Product]`; `return [Product.from_row(dict(row)) for row in rows]`.

- [ ] **Step 5: Migrate consumers**

`app/tools/prompt_builders.py` — change the `product` parameter type hints from `Dict[str, Any]` to `Product` (add `from ..models.product import Product`; drop `Dict` from the typing import if now unused), and:

At :41-45 (in `build_scene_image_prompt`):
```python
    # Extract product details (style -> category -> literal fallback preserved
    # from the pre-Product dict era; golden test pins the output)
    garment_description = product.description
    garment_type = product.attributes.get("style") or product.category or "elegant fashion piece"
    color = product.attributes.get("color") or ""
    fabric = product.attributes.get("fabric") or ""
```
At :144: `key_features = product.description or "fabric texture and construction"`
At :282-286 (in `build_creative_prompt`):
```python
    garment_type = product.attributes.get("style") or product.category or "elegant fashion piece"
    color = product.attributes.get("color") or ""
    fabric = product.attributes.get("fabric") or ""
    garment_desc = f"{color} {fabric} {garment_type}".strip() or "elegant fashion piece"
```

`app/tools/video_tools.py`:
- :483 → `print(f"[DEBUG generate_video_from_product] Product: {product.name}")`
- :523 → `product_image_filename = product.image_filename`
- :537 → `video_filename = generate_video_filename(product.name, variation_obj.name)`
- :686 → `"product_name": product.name,`
- :711 → `"product": product.name,`
- ~:211 and ~:281 (`generate_scene_image` / `animate_scene_with_veo` debug prints reading `product.get('name')`) → `product.name`
- ~:397 (`save_video_metadata`, `product.get('name', 'unknown')`) → `product.name if product is not None else "unknown"`
- `list_products` tool (:1749-1771): keep the output dict IDENTICAL; build it from the model:
```python
    products = db_list_products(category)

    product_list = []
    for p in products:
        product_data = {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "style": p.attributes.get("style"),
            "color": p.attributes.get("color"),
            "fabric": p.attributes.get("fabric"),
            "image_filename": p.image_filename
        }

        # Add public URL for product image
        if include_urls and p.image_filename:
            image_url = storage.get_public_url(f"product-images/{p.image_filename}")
            if image_url:
                product_data["image_url"] = image_url

        product_list.append(product_data)
```

`app/tools/campaign_tools.py`:
- :70 → `product_category = (product.category or "").lower()`
- :83 → `product_name_title = product.name.replace("-", " ").title()`
- :88 → generalize the auto-description (exit criteria: no fashion literals in paths a non-fashion product exercises; fashion output stays byte-identical because all 22 seed products have style+color set):
```python
    # Auto-generate description if not provided
    if not description:
        style = product.attributes.get("style")
        color = product.attributes.get("color")
        if style or color:
            description = f"Campaign for {style or 'fashion item'} in {color or 'classic'} at {store_name}, {city}."
        else:
            product_title = product.name.replace("-", " ").title()
            description = f"Campaign for {product_title} at {store_name}, {city}."
```
- :109 → `"product_name": product.name,`

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_product_adapter.py tests/unit/test_product_model.py -v` — all pass, INCLUDING the golden tests (if a golden test fails, the migration changed prompt semantics — fix the migration, never re-capture the golden).
Run: `make test-unit` → all pass (existing video/campaign tool tests exercise the migrated paths through tool-level dict outputs).

- [ ] **Step 7: Lint + commit**

Run: `.venv/bin/ruff check app/ tests/unit/test_product_adapter.py` → no NEW errors (pre-existing errors out of scope).

```bash
git add app/database/db.py app/tools/video_tools.py app/tools/prompt_builders.py app/tools/campaign_tools.py tests/unit/test_product_adapter.py tests/unit/data/
git commit -m "Return typed Product from product reads; migrate all consumers with golden prompt guard"
```

---

### Task 3: Deliberate campaign-category behavior (Option A)

**Files:**
- Modify: `app/database/db.py` (campaigns CHECK at :73)
- Modify: `app/config.py` (`CAMPAIGN_CATEGORIES` at :110)
- Modify: `app/tools/campaign_tools.py` (signature :31-38, docstring :43-48, category block :69-78)
- Modify: `SETUP_INSTRUCTIONS.md` (reset note)
- Test: `tests/unit/test_campaign_tools.py` (new class), `tests/unit/test_config.py` (parity test covers the new value automatically — verify)

**Interfaces:**
- Consumes: `Product` typed access from Task 2 (`product.category`).
- Produces: `create_campaign(product_id, store_name, city, state, name=None, description=None, category=None)` — Task 4's fixture test and Task 5's Scenario F5 rely on: non-fashion product + no explicit category → campaign category `"always-on"`; invalid explicit category → `{"status": "error", ...}` naming valid values.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_campaign_tools.py`:

```python
class TestCampaignCategoryResolution:
    """Phase 8 Option A: themed taxonomy decoupled from open product category."""

    def test_fashion_mapping_unchanged(self, test_db):
        # product 1 is category 'pants' -> mapped theme 'professional'
        result = create_campaign(product_id=1, store_name="Category Test Store",
                                 city="Austin", state="TX")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "professional"

    def test_explicit_valid_category_wins(self, test_db):
        result = create_campaign(product_id=1, store_name="Explicit Cat Store",
                                 city="Austin", state="TX", category="holiday")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "holiday"

    def test_explicit_category_normalized(self, test_db):
        result = create_campaign(product_id=1, store_name="Normalized Cat Store",
                                 city="Austin", state="TX", category="  Always-On ")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "always-on"

    def test_explicit_invalid_category_errors(self, test_db):
        result = create_campaign(product_id=1, store_name="Bad Cat Store",
                                 city="Austin", state="TX", category="beverage")
        assert result["status"] == "error"
        assert "always-on" in result["message"]  # lists the valid values

    def test_unmapped_product_category_defaults_to_always_on(self, test_db):
        # Insert a minimal non-fashion product directly (Task 4 adds the real fixtures)
        from app.database.db import get_db_cursor
        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO products (name, category, image_filename, metadata)"
                " VALUES (?, ?, ?, ?)",
                ("category-test-widget", "gadget", "category-test-widget.png", "{}"),
            )
            product_id = cursor.lastrowid
        result = create_campaign(product_id=product_id, store_name="Fallback Store",
                                 city="Austin", state="TX")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "always-on"
        assert "fashion item" not in result["campaign"]["description"]
```

(`create_campaign` is already imported at the top of this test file — reuse; add the `get_db_cursor` import inside the test as shown.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_campaign_tools.py::TestCampaignCategoryResolution -v`
Expected: explicit-category tests fail with `TypeError: create_campaign() got an unexpected keyword argument 'category'`; the always-on tests fail on the CHECK constraint / `essentials` assertion.

- [ ] **Step 3: Implement**

`app/database/db.py:73` — extend the CHECK:
```sql
                category TEXT CHECK(category IN ('summer', 'formal', 'professional', 'essentials', 'holiday', 'always-on')),
```

`app/config.py:110`:
```python
CAMPAIGN_CATEGORIES = ["summer", "formal", "professional", "essentials", "holiday", "always-on"]
```

`app/tools/campaign_tools.py` — add `from ..config import CAMPAIGN_CATEGORIES` to imports; add the parameter `category: str | None = None` after `description` in the signature; replace the docstring's category paragraph (:43-48) with:
```
    The campaign category is a small controlled THEME taxonomy (see
    config.CAMPAIGN_CATEGORIES / the CHECK constraint in app/database/db.py),
    deliberately decoupled from the open-ended product category: pass
    `category` explicitly (validated), or omit it — fashion product
    categories map to suggested themes (dress→summer, top→essentials,
    pants→professional, skirt→formal, outerwear→essentials) and anything
    else defaults to the neutral "always-on" bucket (Phase 8 owner
    decision — replaces the old silent "essentials" fallback).
```
and add to the Args section: `category: Optional campaign theme, one of config.CAMPAIGN_CATEGORIES. Derived from the product when omitted.`

Replace the category block (:69-78) with:
```python
    # Resolve the campaign THEME category (decoupled from product category)
    if category is not None:
        category = category.strip().lower()
        if category not in CAMPAIGN_CATEGORIES:
            return {
                "status": "error",
                "message": (
                    f"Invalid campaign category '{category}'. "
                    f"Valid categories: {', '.join(CAMPAIGN_CATEGORIES)}."
                ),
            }
    else:
        product_category = (product.category or "").lower()
        category_mapping = {
            "dress": "summer",
            "top": "essentials",
            "pants": "professional",
            "skirt": "formal",
            "outerwear": "essentials"
        }
        category = category_mapping.get(product_category, "always-on")
```

`SETUP_INSTRUCTIONS.md` — add one bullet under the local-dev/setup notes:
```
- Workstream 08 added the `always-on` campaign category to the campaigns
  table's CHECK constraint. SQLite can't ALTER a CHECK, so a `campaigns.db`
  created before this change must be regenerated: `make reset-db`, then
  restart `make dev` (demo data repopulates automatically).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_campaign_tools.py tests/unit/test_config.py -v`
Expected: all pass. `test_config.py`'s parity test iterates `CAMPAIGN_CATEGORIES` against the CHECK, so it validates `always-on` automatically — confirm it ran green. NOTE: the test DB is a copy of a `campaigns.db` whose campaigns table may carry the OLD CHECK — if the parity/always-on tests fail on the copied DB's old constraint, run `make reset-db && .venv/bin/python -c "from app.database.db import init_database; init_database()"` to regenerate the source DB first, then re-run.

- [ ] **Step 5: Lint + unit suite + commit**

Run: `.venv/bin/ruff check app/ tests/unit/test_campaign_tools.py` → no new errors. `make test-unit` → all pass.

```bash
git add app/database/db.py app/config.py app/tools/campaign_tools.py SETUP_INSTRUCTIONS.md tests/unit/test_campaign_tools.py
git commit -m "Decouple campaign theme taxonomy from product category; add always-on bucket and validated category param"
```

---

### Task 4: Multi-vertical retail core test set + self-service write path

**Files:**
- Create: `app/database/retail_products_data.py`
- Modify: `app/database/db.py` (new `insert_product()` + `populate_retail_test_products()`; call the latter from `init_database()` right after the `populate_products()` call at :239)
- Modify: `app/tools/video_tools.py` `list_products` tool docstring (:1737-1747) and `app/agent.py` "Product Library" instruction line (~:194) — the "22 products" wording
- Test: `tests/unit/test_retail_products.py` (new)

**Interfaces:**
- Consumes: `Product.to_row()` (Task 1), typed reads (Task 2), always-on default (Task 3).
- Produces: `app.database.retail_products_data.RETAIL_TEST_PRODUCTS` (list of Product-kwargs dicts), `db.insert_product(product: Product) -> Product` (raises sqlite3.IntegrityError on duplicate name; returns the stored Product re-read via get_product), and `db.populate_retail_test_products()` (idempotent). Task 5's Scenario F5 uses the beverage SKU by name; Phase 15's tools wrap insert_product.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_retail_products.py`:

```python
"""The multi-vertical retail core test set proves the schema is
vertical-agnostic (Phase 8, owner decision: general retail, not one vertical)."""

import pytest

from app.database.db import get_product_by_name, populate_retail_test_products
from app.database.retail_products_data import RETAIL_TEST_PRODUCTS
from app.models.product import Product
from app.tools.campaign_tools import create_campaign

EXPECTED_VERTICALS = {"beverage", "qsr-menu-item", "electronics", "furniture", "home-appliance"}


@pytest.fixture()
def retail_db(test_db):
    populate_retail_test_products()  # idempotent; test copy may predate fixtures
    return test_db


class TestCoreTestSet:
    def test_covers_all_five_verticals(self, retail_db):
        assert {e["category"] for e in RETAIL_TEST_PRODUCTS} == EXPECTED_VERTICALS

    def test_entries_are_attributes_first(self):
        for entry in RETAIL_TEST_PRODUCTS:
            assert entry["attributes"], f"{entry['name']} has no attributes"
            for fashion_key in ("style", "color", "fabric", "occasion"):
                assert fashion_key not in entry["attributes"], (
                    f"{entry['name']} uses fashion key '{fashion_key}'")

    def test_every_fixture_retrievable_typed_with_attributes(self, retail_db):
        for entry in RETAIL_TEST_PRODUCTS:
            p = get_product_by_name(entry["name"])
            assert isinstance(p, Product), entry["name"]
            assert p.category == entry["category"]
            assert p.attributes == entry["attributes"]
            assert p.description == entry["description"]

    def test_populate_is_idempotent(self, retail_db):
        before = get_product_by_name(RETAIL_TEST_PRODUCTS[0]["name"]).id
        populate_retail_test_products()
        assert get_product_by_name(RETAIL_TEST_PRODUCTS[0]["name"]).id == before

    def test_beverage_campaign_gets_always_on(self, retail_db):
        p = get_product_by_name("aurora-cold-brew-330ml")
        result = create_campaign(product_id=p.id, store_name="Target Downtown",
                                 city="Austin", state="TX")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "always-on"
        assert "fashion item" not in result["campaign"]["description"]
        assert "Aurora Cold Brew" in result["campaign"]["description"]


class TestSelfServiceOnTheFly:
    """Owner directive: a vendor's never-before-seen product must work end to
    end (persist -> typed retrieve -> campaign) with only an image REFERENCE —
    the file may not exist yet; upload/generation land in Phase 14a/15."""

    def test_vendor_product_end_to_end(self, retail_db):
        from app.database.db import insert_product

        vendor_product = Product(
            name="vendor-demo-trail-shoe",
            category="footwear",  # a vertical NOT in the core set
            description="lightweight waterproof trail running shoe",
            image_filename="vendor-demo-trail-shoe.png",  # not on disk anywhere
            attributes={"brand": "Summit Labs", "sizes": ["8", "9", "10"],
                        "waterproof_rating": "IPX7", "weight_grams": 240},
        )
        stored = insert_product(vendor_product)
        assert stored.id is not None
        fetched = get_product_by_name("vendor-demo-trail-shoe")
        assert fetched.attributes == vendor_product.attributes
        assert fetched.description == vendor_product.description
        result = create_campaign(product_id=stored.id, store_name="Vendor Demo Store",
                                 city="Austin", state="TX")
        assert result["status"] == "success"
        assert result["campaign"]["category"] == "always-on"
        assert "fashion item" not in result["campaign"]["description"]

    def test_duplicate_name_raises_integrity_error(self, retail_db):
        import sqlite3

        from app.database.db import insert_product

        duplicate = Product(name="aurora-cold-brew-330ml", category="beverage",
                            description="dup", image_filename="x.png")
        with pytest.raises(sqlite3.IntegrityError):
            insert_product(duplicate)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_retail_products.py -v`
Expected: ImportError on `retail_products_data` / `populate_retail_test_products`.

- [ ] **Step 3: Create `app/database/retail_products_data.py`**

```python
"""Multi-vertical retail core test set (Phase 8).

Proof that the product schema is vertical-agnostic: SKUs across five
unrelated retail verticals ("anything sellable on BlueZoo in-store
screens" — owner decision at the workstream-08 gate), all attributes-first
(no fashion columns). Image files are referenced but not yet generated —
Phase 14a/15 add upload / nano-banana generation paths that grow this core
set into real imagery. Seeded additively; the fashion demo catalog in
products_data.py is untouched.
"""

from typing import Any, Dict, List

RETAIL_TEST_PRODUCTS: List[Dict[str, Any]] = [
    {
        "name": "aurora-cold-brew-330ml",
        "category": "beverage",
        "description": "slow-steeped single-origin cold brew coffee in a slim can",
        "image_filename": "aurora-cold-brew-330ml.png",
        "attributes": {
            "flavor": "dark chocolate and toasted hazelnut notes",
            "volume_ml": 330,
            "packaging": "slim aluminum can",
            "serving_temperature": "chilled",
            "caffeine_mg": 180,
            "dietary_tags": ["vegan", "zero-sugar"],
        },
    },
    {
        "name": "citrus-grove-sparkling-water-500ml",
        "category": "beverage",
        "description": "unsweetened sparkling water with real citrus zest",
        "image_filename": "citrus-grove-sparkling-water-500ml.png",
        "attributes": {
            "flavor": "grapefruit and blood orange",
            "volume_ml": 500,
            "packaging": "glass bottle",
            "serving_temperature": "chilled",
            "caffeine_mg": 0,
            "dietary_tags": ["zero-calorie", "sodium-free"],
        },
    },
    {
        "name": "smoky-brisket-stack-sandwich",
        "category": "qsr-menu-item",
        "description": "12-hour smoked brisket with pickled onions on a brioche bun",
        "image_filename": "smoky-brisket-stack-sandwich.png",
        "attributes": {
            "cuisine": "texas barbecue",
            "calories": 780,
            "spice_level": "medium",
            "key_ingredients": ["smoked brisket", "pickled red onion", "brioche bun"],
            "combo_options": ["fries + drink", "coleslaw + drink"],
            "limited_time_window": "summer 2026",
        },
    },
    {
        "name": "pulse-anc-wireless-earbuds",
        "category": "electronics",
        "description": "active noise cancelling wireless earbuds with wireless charging case",
        "image_filename": "pulse-anc-wireless-earbuds.png",
        "attributes": {
            "brand": "Pulse Audio",
            "battery_life_hours": 32,
            "connectivity": "bluetooth 5.4",
            "noise_cancellation": "adaptive ANC",
            "finish": "matte graphite",
            "warranty_months": 24,
        },
    },
    {
        "name": "nordic-oak-lounge-chair",
        "category": "furniture",
        "description": "mid-century lounge chair in solid oak with wool boucle cushions",
        "image_filename": "nordic-oak-lounge-chair.png",
        "attributes": {
            "material": "solid oak, wool boucle upholstery",
            "dimensions_cm": {"width": 72, "depth": 80, "height": 76},
            "weight_capacity_kg": 150,
            "assembly_required": True,
            "style_family": "mid-century scandinavian",
        },
    },
    {
        "name": "crispwave-air-fryer-5l",
        "category": "home-appliance",
        "description": "5-liter digital air fryer with eight one-touch presets",
        "image_filename": "crispwave-air-fryer-5l.png",
        "attributes": {
            "capacity_liters": 5,
            "wattage": 1700,
            "presets": ["fries", "wings", "roast", "bake", "reheat"],
            "dishwasher_safe_parts": True,
            "warranty_months": 12,
        },
    },
]
```

- [ ] **Step 4: Add `insert_product()` and `populate_retail_test_products()` to `app/database/db.py`**

Insert both directly after `populate_products()` (after :386):

```python
def insert_product(product: Product) -> Product:
    """Insert a new product through the typed write path (Phase 8).

    The db-layer substrate for self-service onboarding ("run MY product
    through it"): Phase 15's agent tools (create_product / import /
    generate_product_image) wrap this. The referenced image file does NOT
    need to exist yet — image_filename is a reference resolved later by
    vendor upload or image generation.

    Returns:
        The stored Product, re-read via get_product() so the caller sees
        exactly what any later retrieval will see (id populated).

    Raises:
        sqlite3.IntegrityError: if a product with this name already exists.
    """
    row = product.to_row()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO products
            (name, category, style, color, fabric, occasion, details,
             image_filename, gcs_path, local_path, metadata)
            VALUES (:name, :category, :style, :color, :fabric, :occasion,
                    :details, :image_filename, :gcs_path, :local_path, :metadata)
        ''', row)
        product_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return get_product(product_id)


def populate_retail_test_products() -> None:
    """Seed the multi-vertical retail core test set (Phase 8).

    Attributes-first products across five verticals proving the schema is
    vertical-agnostic. Additive and idempotent (INSERT OR IGNORE on the
    UNIQUE name); the fashion demo catalog is untouched. Writes go through
    Product.to_row() — the same write path Phase 15's create_product uses.
    """
    from ..models.product import Product
    from .retail_products_data import RETAIL_TEST_PRODUCTS

    conn = get_connection()
    cursor = conn.cursor()
    for entry in RETAIL_TEST_PRODUCTS:
        row = Product(**entry).to_row()
        cursor.execute('''
            INSERT OR IGNORE INTO products
            (name, category, style, color, fabric, occasion, details,
             image_filename, gcs_path, local_path, metadata)
            VALUES (:name, :category, :style, :color, :fabric, :occasion,
                    :details, :image_filename, :gcs_path, :local_path, :metadata)
        ''', row)
    conn.commit()
    conn.close()
```

In `init_database()`, directly after the `populate_products()` call (:239), add:
```python
    populate_retail_test_products()
```

- [ ] **Step 5: Update the two "22 products" surfaces**

`app/tools/video_tools.py` `list_products` docstring (:1739): change "Products are pre-loaded from the products table (22 products)." to "Products are pre-loaded from the products table (22-item fashion catalog plus the multi-vertical retail core test set)." and (:1743) the category example line to `category: Optional category filter (e.g. dress, top, pants, beverage, electronics)`.

`app/agent.py` Product Library instruction (~:194): change "22 pre-loaded products" to "28 pre-loaded products (22-item fashion catalog + 6-SKU multi-vertical retail test set)". Leave everything else in the instruction untouched (Phase 9 owns the full rewrite).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_retail_products.py tests/unit/test_video_tools.py -v`
Expected: all pass — including `TestListProducts` (its assertions are `>= 22`, dress-filter equality, and fashion-category intersection `>= 3`, all unaffected by the additive fixtures).
Run: `make test-unit` → all pass.

- [ ] **Step 7: Lint + commit**

Run: `.venv/bin/ruff check app/ tests/unit/test_retail_products.py` → no new errors.

```bash
git add app/database/retail_products_data.py app/database/db.py app/tools/video_tools.py app/agent.py tests/unit/test_retail_products.py
git commit -m "Add multi-vertical retail core test set seeded through the typed write path"
```

---

### Task 5: Doc amendments, Scenario F5, full suite

**Files:**
- Modify: `.docs/version2-plan/99-open-questions.md` (Q7 + closing tally)
- Modify: `.docs/version2-plan/08-product-schema-generalization.md` (own open questions 1–2)
- Modify: `.docs/version2-plan/02-bug-fixes-and-cleanup.md` (item 5 provenance)
- Modify: `.docs/version2-plan/09-prompt-and-agent-generalization.md` (fixture naming + new create_campaign param + description-coupling note)
- Modify: `.docs/version2-plan/10-playout-attribution.md` (Product.id type confirmation)
- Modify: `.docs/version2-plan/15-product-onboarding.md` (contract confirmation + core-set note)
- Modify: `docs/demo-scenarios/fashion.md` (append Scenario F5)

**Interfaces:**
- Consumes: everything above; no code changes in this task.

- [ ] **Step 1: Amend the phase docs (provenance-blockquote style, verbatim texts)**

`99-open-questions.md` — directly below Q7's text (lines ~41-43), add:
```
> **Answered (workstream 08, 2026-07-20):** broader than any single vertical —
> the owner wants the schema to serve *any retail vertical sellable on BlueZoo
> in-store screens*. The proof fixture is a multi-vertical **retail core test
> set** (`app/database/retail_products_data.py`: beverage, QSR menu item,
> consumer electronics, furniture, home appliance), attributes-first. Product
> images are referenced but not generated here — users will either upload
> photos or generate them via nano banana (Phase 14a model, Phase 15 tools),
> growing this core set into the standard test imagery.
```
Update the closing tally line (~:100) to count Q7 as answered.

`08-product-schema-generalization.md` — below Open questions 1 and 2 respectively:
```
> **Resolved (workstream 08, 2026-07-20):** see 99-open-questions Q7 — not one
> vertical but a multi-vertical retail core test set (beverage/QSR/electronics/
> furniture/home-appliance), attributes-first, images deferred to Phase 14a/15.
```
```
> **Resolved (workstream 08, 2026-07-20):** Option A — campaign category stays
> a small controlled THEME taxonomy (CHECK + config.CAMPAIGN_CATEGORIES, now
> including `always-on`), decoupled from the open product category.
> create_campaign gained an explicit validated `category` param; unmapped
> product categories default to `always-on` (deliberate), never a silent
> `essentials`. Existing DBs need `make reset-db` (SQLite CHECK rebuild).
```

`02-bug-fixes-and-cleanup.md` — below item 5:
```
> **Amended (workstream 08, 2026-07-20):** the deferred fallback decision
> resolved as Option A — themed campaign taxonomy with an `always-on` default
> bucket and a validated explicit `category` parameter; the silent
> `essentials` fallback is gone (app/tools/campaign_tools.py).
```

`09-prompt-and-agent-generalization.md` — below the Dependencies line:
```
> **Amended (workstream 08, 2026-07-20):** the "Phase 8 non-fashion fixture
> catalog" is the multi-vertical retail core test set in
> `app/database/retail_products_data.py` (five verticals — use the beverage
> and QSR SKUs as primary e2e inputs). Note also: (a) create_campaign now
> takes an explicit validated `category` theme param this phase's instruction
> rewrite should surface to the agent; (b) create_campaign's auto-description
> was minimally generalized in ws08 (name-based fallback when style/color are
> absent) — this phase's step 5 still owns making that text vertical-aware.
```

`10-playout-attribution.md` — below step 1 (~:40):
```
> **Amended (workstream 08, 2026-07-20):** `Product.id` is `int | None`
> (INTEGER PRIMARY KEY AUTOINCREMENT; None only pre-insert) — the
> `product_id: str | int` here should key as `int`.
```

`15-product-onboarding.md` — below step 3 (~:20):
```
> **Amended (workstream 08, 2026-07-20):** the typed model landed as
> `app/models/product.py` `Product` with exactly the expected constructor
> surface (name, category, description, attributes dict + image_filename);
> write through `Product.to_row()` (see `db.populate_retail_test_products()`
> for the reference write path). The multi-vertical retail core test set
> (`retail_products_data.py`) is the seed this phase's image tools
> (upload / nano-banana generation) grow into real imagery — consider a
> `DEMO_DATASET` value for it alongside `fashion|none`. The self-service
> vendor flow ("run MY product") has its db substrate ready:
> `db.insert_product(Product)` accepts on-the-fly products whose image files
> don't exist yet — this phase's tools are thin wrappers over it (vendor
> upload fills local_path/gcs_path; nano-banana generation writes the file
> image_filename already references).
```

- [ ] **Step 2: Append Scenario F5 to `docs/demo-scenarios/fashion.md`**

```
## Scenario F5: Non-fashion product campaign (workstream 08)

Covers Phase 8: the typed vertical-agnostic Product model and the deliberate
campaign-category behavior, exercised through the multi-vertical retail core
test set (seeded at startup alongside the fashion catalog).

### Scene F5.1 — browse and create a campaign for a beverage product

**Query 1:** "List the beverage products"

**Query 2 (follow-up turn):** "Create a campaign for the Aurora cold brew at
Target Downtown in Austin, Texas"

**Expected tool calls:**
- Query 1: `list_products(category="beverage")` → includes
  `aurora-cold-brew-330ml` (and `citrus-grove-sparkling-water-500ml`); no
  crash on the non-fashion rows (style/color/fabric are null for them).
- Query 2: `create_campaign(product_id=<resolved id>, store_name="Target
  Downtown", city="Austin", state="Texas"|"TX")` (explicit `category` may be
  present only if it is a valid theme value).

**Pass criteria (check the values, not prose):**
- Campaign created with `status: "success"`, `category: "always-on"` (the
  deliberate non-fashion default — FAIL if it is "essentials", which would
  mean the old silent fallback survived).
- The campaign description mentions the product (e.g. "Aurora Cold Brew")
  and does NOT contain "fashion item" or "classic".
- No traceback anywhere; product fields in responses are populated from the
  typed model (name/category present; no literal "None" strings).
```

- [ ] **Step 3: Full suite + forbidden-files check**

Run: `git status --porcelain` → only the seven files of this task modified; README.md/DEMO_GUIDE.md absent.
Run: `source .venv/bin/activate && make test` → all pass (unit + e2e + integration).

- [ ] **Step 4: Commit**

```bash
git add .docs/version2-plan/99-open-questions.md .docs/version2-plan/08-product-schema-generalization.md .docs/version2-plan/02-bug-fixes-and-cleanup.md .docs/version2-plan/09-prompt-and-agent-generalization.md .docs/version2-plan/10-playout-attribution.md .docs/version2-plan/15-product-onboarding.md docs/demo-scenarios/fashion.md
git commit -m "Amend plan docs for ws08 decisions (Q7 core set, Option A category); add Scenario F5"
```
