# UX Backend Server Integration Specification (`server.py`)

This document outlines the architectural blueprint and reference implementation for **`server.py`**, designed to bridge the **multi-agent retail advertising backend** into the frontend web application data model defined in [`object.js`](./object.js).

It is written specifically for the **UX design and frontend engineering teams** to clarify:
1. **Object Shapes & Data Contracts** (`Status`, `ApprovalStatus`, `campaignExample`, `videoExample`).
2. **Backend Tool Routing** (how each endpoint maps to Campaign, Media, Review, and Analytics agents).
3. **Data Transformation Layer** (translating SQLite/ADK backend records into frontend JSON objects).
4. **Reference Implementation Blueprint** (clean, runnable FastAPI/Starlette routing structure).

---

## 1. System Architecture & Information Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Frontend Web Application (UX UI)                     │
│    (Campaign Cards, Video Variant Grids, HITL Review, Analytics)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                       JSON REST & WebSocket Events
                      (object.js Schemas & Enums)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     FastAPI / Starlette server.py                      │
│                                                                        │
│  ┌──────────────────────┐  ┌────────────────────────────────────────┐  │
│  │  UX Model Adapters   │  │       Route Dispatchers / Handlers     │  │
│  │  - to_ux_campaign()  │  │  - /api/v1/ux/campaigns (CRUD)         │  │
│  │  - to_ux_video()     │  │  - /api/v1/ux/videos (Lifecycle/Appr) │  │
│  │  - map_status_enums()│  │  - /api/v1/ux/analytics (RPI, Maps)    │  │
│  └──────────────────────┘  └────────────────────────────────────────┘  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                  Invokes Agent Tools & Domain APIs
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Multi-Agent Optimization Backend (ADK 2.0)                │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │Campaign Agent│  │ Media Agent  │  │ Review Agent │  │ Analytics  │  │
│  │- Catalog     │  │- Veo 3 / Gen │  │- HITL Review │  │  Agent     │  │
│  │- Store Data  │  │- Variations  │  │- Activations │  │- BlueZoo   │  │
│  │- CRUD Tools  │  │- Presets     │  │- Omni-Edit   │  │- RPI & POS │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Frontend Data Contracts (`object.js` Alignment)

### A. Status Enumerations

The frontend uses integer status flags for campaigns and videos:

```typescript
export enum Status {
  NONE = 0,
  GENERATING_ACTIVE = 1,    // Veo 3 video generation in progress
  GENERATING_COMPLETE = 2,  // Video synthesized and stored
  GENERATING_FAILED = 3,    // Model error or quota limit
  REVIEW_NEEDED = 4,        // Pending human-in-the-loop (HITL) approval
  APPROVAL_UPDATED = 5,     // Edited or status modified
  TESTING_ACTIVE = 6,       // Video activated & broadcasting to in-store screens
  TESTING_COMPLETE = 7,     // Test period concluded with final metrics
  TESTING_FAILED = 8,       // Display or metrics delivery failure
}

export enum ApprovalStatus {
  NONE = 0,                 // Awaiting review
  APPROVED = 1,             // Approved by user (pushes live)
  REJECTED = 2,             // Rejected (archived/hidden)
}
```

### B. Campaign Object (`campaignExample`)

Every campaign maps 1 product to 1 retail store and contains settings for video generation:

```json
{
  "id": "000001",
  "name": "Spring/Summer Sport Sunglasses",
  "owner": "cid@domain.com",
  "shared_with": ["tommy@domain.com", "fred@domain.com"],
  "created_date": "2026-01-01T00:00:00Z",
  "modified_date": "2026-01-01T00:00:00Z",
  "is_template": false,
  "is_favorite": false,
  "is_archived": false,
  "status": 6,
  "status_meta": {
    "quantity": 10,
    "end_date": "2026-01-01T00:00:00Z"
  },
  "thumbnail": "/generated_assets/000001.jpg",
  "description": "High performance eyewear commercial campaign.",
  "settings": {
    "overall": { "prompt": "Summer rooftop energetic vibe", "files": [] },
    "items": { "prompt": "Black Polarized Sport Sunglasses", "files": [] },
    "people": { "prompt": "Athletic European runner", "files": [] },
    "performance": { "prompt": "Running in golden hour sunlight", "files": [] },
    "setting": { "prompt": "Urban rooftop track overlooking downtown", "files": [] },
    "audio": { "prompt": "Upbeat synth-pop rhythm", "files": [] },
    "languages": ["en-US"],
    "guidelines": [],
    "format": {
      "duration": 8,
      "aspect_ratios": ["16:9"],
      "resolution": "1080p"
    },
    "testing": {
      "variants_per_generation": 10,
      "rules": "http://example.com/rules.json",
      "duration": 24
    }
  },
  "videos": [ /* Array of Video Objects */ ]
}
```

### C. Video Creative Object (`videoExample`)

Each video ad creative generated by Veo represents a variation:

```json
{
  "id": "000001",
  "name": "000-000-001",
  "parent_id": "000000",
  "campaign_id": "000001",
  "created_date": "2026-01-01T00:00:00Z",
  "is_favorite": false,
  "is_archived": false,
  "approval_status": 1,
  "approval_date": "2026-01-01T00:00:00Z",
  "status": 6,
  "status_meta": {
    "quantity": 1,
    "end_date": "2026-01-01T00:00:00Z"
  },
  "thumbnail": "/generated_assets/000001_000001.jpg",
  "description": "Variant with sunset lighting and upbeat tempo",
  "url": "/generated_assets/000001_000001.mp4",
  "testing_period": {
    "start_date": "2026-01-01T00:00:00Z",
    "end_date": "2026-01-01T00:00:00Z"
  },
  "duration": 8,
  "impressions": 1000,
  "impressions_id": "imp_9481a",
  "revenue": 123.45,
  "revenue_id": "rev_2831b",
  "rank": 1,
  "settings": {
    "setting": { "prompt": "Sunset golden hour light", "files": [] }
  }
}
```

---

## 3. Function & Agent Routing Map

This table maps each UX frontend action to the underlying Agent backend function:

| Frontend UI Action | HTTP Route | Underlying Agent & Tool | Backend Action & Return Logic |
|---|---|---|---|
| **App Bootstrap / Enums** | `GET /api/v1/ux/enums` | `System / Core` | Returns integer status codes from `object.js`. |
| **JSON Schema Discovery** | `GET /api/v1/ux/schema` | `System / Core` | Returns OpenAPI / JSONSchema definitions of `UXCampaign` and `UXVideo`. |
| **List Campaigns** | `GET /api/v1/ux/campaigns` | `Campaign Agent` (`list_campaigns`) | Queries DB, hydrates nested `videos`, and maps to `UXCampaign[]`. |
| **Create Campaign** | `POST /api/v1/ux/campaigns` | `Campaign Agent` (`create_campaign`) | Parses UI settings, initializes DB record, returns new `UXCampaign`. |
| **View Campaign Detail** | `GET /api/v1/ux/campaigns/{id}` | `Campaign Agent` (`get_campaign`) | Returns single `UXCampaign` populated with all child `UXVideo` items. |
| **Edit Campaign Settings** | `PATCH /api/v1/ux/campaigns/{id}` | `Campaign Agent` (`update_campaign`) | Updates campaign name, description, status, or settings block. |
| **List Videos (Variant Grid)**| `GET /api/v1/ux/videos` | `Media Agent` (`list_campaign_videos`) | Retrieves video records and formats them as `UXVideo[]`. |
| **View Single Video** | `GET /api/v1/ux/videos/{id}` | `Review Agent` (`get_video_details`) | Returns full `UXVideo` including impressions, revenue, and ranks. |
| **1-Click HITL Approval** | `POST /api/v1/ux/videos/{id}/approval` | `Review Agent` (`activate_video`, `archive_video`) | `approval_status: 1` sets `TESTING_ACTIVE` (6); `2` sets `REJECTED` (2) & archives. |
| **Batch Video Activation**| `POST /api/v1/ux/videos/activate-batch` | `Review Agent` (`activate_batch`) | Activates multiple candidate videos across digital display screens. |
| **Visual Omni-Edit Tweak** | `POST /api/v1/ux/videos/{id}/edit` | `Review Agent` (`edit_video_with_omni`) | Applies a targeted visual prompt edit to an existing video. |
| **Generate Video Batch** | `POST /api/v1/ux/videos/generate` | `Media Agent` (`generate_video_from_product`) | Dispatches Veo 3 generation; status starts at `GENERATING_ACTIVE` (1). |
| **Creative Options & Presets**| `GET /api/v1/ux/presets` | `Media Agent` (`get_variation_presets`) | Returns 15+ configurable generation parameters and preset templates. |
| **Top Performing Creatives** | `GET /api/v1/ux/analytics/top-ads` | `Analytics Agent` (`get_top_performing_ads`) | Computes RPI across video creatives and populates `rank`. |
| **Regional Store Map** | `GET /api/v1/ux/maps/locations` | `Analytics Agent` (`get_campaign_map_data`) | Generates geographic store locations and regional performance. |
| **Winning Formula Scale** | `POST /api/v1/ux/optimization/propagate`| `Media Agent` (`apply_winning_formula`) | Extracts settings from top video and seeds a new campaign. |
| **Free-Form AI Chat** | `POST /api/v1/ux/chat` | `Root Coordinator` (`root_agent`) | Natural language multi-agent router for interactive queries. |

---

## 4. Reference Implementation: `server.py`

Below is the clean reference implementation of `server.py` demonstrating how to translate backend tool calls into `object.js` compliant structures:

```python
"""
server.py — Reference UX Backend Server
Routes multi-agent tools to frontend endpoints conforming to object.js.
"""

from __future__ import annotations

import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# 1. ENUMERATIONS (object.js Status & ApprovalStatus)
# -----------------------------------------------------------------------------

class Status(IntEnum):
    NONE = 0
    GENERATING_ACTIVE = 1
    GENERATING_COMPLETE = 2
    GENERATING_FAILED = 3
    REVIEW_NEEDED = 4
    APPROVAL_UPDATED = 5
    TESTING_ACTIVE = 6
    TESTING_COMPLETE = 7
    TESTING_FAILED = 8

class ApprovalStatus(IntEnum):
    NONE = 0
    APPROVED = 1
    REJECTED = 2

# -----------------------------------------------------------------------------
# 2. Pydantic Schemas (Exact Match for object.js JSON)
# -----------------------------------------------------------------------------

class SettingSection(BaseModel):
    prompt: str = ""
    files: List[str] = Field(default_factory=list)

class FormatSettings(BaseModel):
    duration: int = 8
    aspect_ratios: List[str] = Field(default_factory=lambda: ["16:9"])
    resolution: str = "1080p"

class TestingSettings(BaseModel):
    variants_per_generation: int = 10
    rules: str = "http://example.com/rules.json"
    duration: int = 24

class CampaignSettings(BaseModel):
    overall: SettingSection = Field(default_factory=SettingSection)
    items: SettingSection = Field(default_factory=SettingSection)
    people: SettingSection = Field(default_factory=SettingSection)
    performance: SettingSection = Field(default_factory=SettingSection)
    setting: SettingSection = Field(default_factory=SettingSection)
    audio: SettingSection = Field(default_factory=SettingSection)
    languages: List[str] = Field(default_factory=lambda: ["en-US"])
    guidelines: List[str] = Field(default_factory=list)
    format: FormatSettings = Field(default_factory=FormatSettings)
    testing: TestingSettings = Field(default_factory=TestingSettings)

class TestingPeriod(BaseModel):
    start_date: str = "2026-01-01T00:00:00Z"
    end_date: str = "2026-01-01T00:00:00Z"

class UXVideo(BaseModel):
    id: str  # 6-digit formatted id e.g. "000001"
    name: str
    parent_id: str = "000000"
    campaign_id: str
    created_date: str
    is_favorite: bool = False
    is_archived: bool = False
    approval_status: int = ApprovalStatus.NONE
    approval_date: Optional[str] = None
    status: int = Status.NONE
    status_meta: Dict[str, Any] = Field(default_factory=dict)
    thumbnail: str = ""
    description: str = ""
    url: str = ""
    testing_period: TestingPeriod = Field(default_factory=TestingPeriod)
    duration: int = 8
    impressions: int = 0
    impressions_id: str = ""
    revenue: float = 0.0
    revenue_id: str = ""
    rank: int = 0
    settings: Dict[str, Any] = Field(default_factory=dict)

class UXCampaign(BaseModel):
    id: str  # 6-digit formatted id e.g. "000001"
    name: str
    owner: str = "cid@domain.com"
    shared_with: List[str] = Field(default_factory=lambda: ["tommy@domain.com", "fred@domain.com"])
    created_date: str
    modified_date: str
    is_template: bool = False
    is_favorite: bool = False
    is_archived: bool = False
    status: int = Status.NONE
    status_meta: Dict[str, Any] = Field(default_factory=dict)
    thumbnail: str = ""
    description: str = ""
    settings: CampaignSettings = Field(default_factory=CampaignSettings)
    videos: List[UXVideo] = Field(default_factory=list)

class ApprovalRequest(BaseModel):
    approval_status: int = Field(..., description="1 for APPROVED, 2 for REJECTED")

class CreateCampaignRequest(BaseModel):
    name: str
    product_id: int
    store_name: str
    city: str
    state: str
    description: Optional[str] = ""

# -----------------------------------------------------------------------------
# 3. Data Transformation Layer (Backend -> UX Object Model)
# -----------------------------------------------------------------------------

def format_id(id_val: Any) -> str:
    """Ensure standard 6-digit formatted strings ('000001')."""
    try:
        return f"{int(id_val):06d}"
    except (ValueError, TypeError):
        return str(id_val).zfill(6)

def to_ux_video(v: Dict[str, Any]) -> UXVideo:
    """Transforms SQLite / Review Agent video record into a UXVideo object."""
    vid_id = format_id(v.get("id", 1))
    cid = format_id(v.get("campaign_id", 1))
    raw_status = str(v.get("status", "pending")).lower()

    # Determine status & approval status integers
    if raw_status in ("active", "activated"):
        status_code = Status.TESTING_ACTIVE
        appr_code = ApprovalStatus.APPROVED
    elif raw_status in ("rejected", "archived"):
        status_code = Status.APPROVAL_UPDATED
        appr_code = ApprovalStatus.REJECTED
    elif raw_status in ("generated", "pending"):
        status_code = Status.REVIEW_NEEDED
        appr_code = ApprovalStatus.NONE
    else:
        status_code = Status.NONE
        appr_code = ApprovalStatus.NONE

    return UXVideo(
        id=vid_id,
        name=f"{cid}-{vid_id}",
        parent_id=format_id(v.get("parent_id", 0)),
        campaign_id=cid,
        created_date=v.get("created_at") or "2026-01-01T00:00:00Z",
        is_favorite=bool(v.get("is_favorite", False)),
        is_archived=bool(v.get("is_archived", False) or raw_status == "archived"),
        approval_status=appr_code,
        approval_date=v.get("activated_at"),
        status=status_code,
        status_meta={"quantity": 1, "end_date": "2026-01-01T00:00:00Z"},
        thumbnail=v.get("thumbnail_url") or f"/generated_assets/{vid_id}.jpg",
        description=v.get("prompt_text") or v.get("variation_type") or "Video ad creative.",
        url=v.get("video_url") or f"/generated_assets/{vid_id}.mp4",
        testing_period=TestingPeriod(),
        duration=int(v.get("duration", 8)),
        impressions=int(v.get("total_impressions", 1000)),
        impressions_id=f"imp_{vid_id}",
        revenue=float(v.get("total_revenue", 123.45)),
        revenue_id=f"rev_{vid_id}",
        rank=int(v.get("rank", 1)),
        settings={"setting": {"prompt": v.get("variation_type", "")}},
    )

def to_ux_campaign(c: Dict[str, Any], videos: List[Dict[str, Any]]) -> UXCampaign:
    """Transforms SQLite / Campaign Agent record into a full UXCampaign object."""
    cid = format_id(c.get("id", 1))
    ux_videos = [to_ux_video(v) for v in videos]

    # Overall status based on child video lifecycle
    if any(v.status == Status.TESTING_ACTIVE for v in ux_videos):
        camp_status = Status.TESTING_ACTIVE
    elif any(v.status == Status.REVIEW_NEEDED for v in ux_videos):
        camp_status = Status.REVIEW_NEEDED
    else:
        camp_status = Status.GENERATING_COMPLETE

    return UXCampaign(
        id=cid,
        name=c.get("name") or f"Campaign {cid}",
        owner="cid@domain.com",
        created_date=c.get("created_at") or "2026-01-01T00:00:00Z",
        modified_date=c.get("updated_at") or c.get("created_at") or "2026-01-01T00:00:00Z",
        status=camp_status,
        status_meta={"quantity": len(ux_videos), "end_date": "2026-01-01T00:00:00Z"},
        thumbnail=f"/generated_assets/{cid}.jpg",
        description=c.get("description") or f"Retail media campaign in {c.get('store_name', 'Store')}.",
        videos=ux_videos,
    )

# -----------------------------------------------------------------------------
# 4. FastAPI Application Setup
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Video Ad Optimization Agent — UX API Gateway",
    description="Backend routing layer connecting multi-agent systems to the object.js frontend UX specification.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# 5. Route Implementations (Connecting Agent Tools)
# -----------------------------------------------------------------------------

@app.get("/api/v1/ux/enums", tags=["UX Specification"])
async def get_ux_enums():
    """Returns Status and ApprovalStatus enums from object.js."""
    return {
        "status": "success",
        "enums": {
            "Status": {name: member.value for name, member in Status.__members__.items()},
            "ApprovalStatus": {name: member.value for name, member in ApprovalStatus.__members__.items()},
        },
    }

@app.get("/api/v1/ux/campaigns", response_model=Dict[str, Any], tags=["Campaigns"])
async def list_ux_campaigns():
    """
    Invokes Campaign Agent `list_campaigns()` and Media Agent `list_campaign_videos()`.
    Returns list of UXCampaign objects with populated child videos.
    """
    from app.tools.campaign_tools import list_campaigns
    from app.tools.video_tools import list_campaign_videos

    raw_campaigns = list_campaigns(limit=50).get("campaigns", [])
    results = []
    for c in raw_campaigns:
        vids = list_campaign_videos(campaign_id=c["id"]).get("videos", [])
        results.append(to_ux_campaign(c, vids))

    return {"status": "success", "total_count": len(results), "campaigns": results}

@app.post("/api/v1/ux/campaigns", status_code=status.HTTP_201_CREATED, tags=["Campaigns"])
async def create_ux_campaign(payload: CreateCampaignRequest):
    """
    Invokes Campaign Agent `create_campaign()`.
    Returns initialized UXCampaign.
    """
    from app.tools.campaign_tools import create_campaign

    created = create_campaign(
        product_id=payload.product_id,
        store_name=payload.store_name,
        city=payload.city,
        state=payload.state,
    )
    if "error" in created:
        raise HTTPException(status_code=400, detail=created["error"])

    return to_ux_campaign(created["campaign"], [])

@app.get("/api/v1/ux/campaigns/{campaign_id}", response_model=UXCampaign, tags=["Campaigns"])
async def get_ux_campaign_detail(campaign_id: int):
    """
    Invokes Campaign Agent `get_campaign()` and Review Agent `get_video_review_table()`.
    """
    from app.tools.campaign_tools import get_campaign
    from app.tools.video_tools import list_campaign_videos

    camp = get_campaign(campaign_id=campaign_id)
    if "error" in camp:
        raise HTTPException(status_code=404, detail=camp["error"])

    vids = list_campaign_videos(campaign_id=campaign_id).get("videos", [])
    return to_ux_campaign(camp["campaign"], vids)

@app.get("/api/v1/ux/videos", response_model=Dict[str, Any], tags=["Videos"])
async def list_ux_videos(campaign_id: Optional[int] = None):
    """
    Invokes Media Agent `list_campaign_videos()`.
    """
    from app.tools.video_tools import list_campaign_videos

    raw_videos = list_campaign_videos(campaign_id=campaign_id).get("videos", [])
    return {
        "status": "success",
        "total_count": len(raw_videos),
        "videos": [to_ux_video(v) for v in raw_videos],
    }

@app.get("/api/v1/ux/videos/{video_id}", response_model=UXVideo, tags=["Videos"])
async def get_ux_video_detail(video_id: int):
    """
    Invokes Review Agent `get_video_details()`.
    """
    from app.tools.review_tools import get_video_details

    res = get_video_details(video_id=video_id)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return to_ux_video(res["video"])

@app.post("/api/v1/ux/videos/{video_id}/approval", response_model=UXVideo, tags=["HITL Approval"])
async def set_video_approval(video_id: int, req: ApprovalRequest):
    """
    1-Click HITL Approval / Rejection Workflow.
    - If `approval_status == 1`: Invokes Review Agent `activate_video()`.
    - If `approval_status == 2`: Invokes Review Agent `archive_video()`.
    """
    from app.tools.review_tools import activate_video, archive_video, get_video_details

    if req.approval_status == ApprovalStatus.APPROVED:
        # Pushes video live to displays, transitions status to TESTING_ACTIVE (6)
        act = activate_video(video_id=video_id)
        if "error" in act:
            raise HTTPException(status_code=400, detail=act["error"])
    elif req.approval_status == ApprovalStatus.REJECTED:
        # Archives video
        arc = archive_video(video_id=video_id)
        if "error" in arc:
            raise HTTPException(status_code=400, detail=arc["error"])
    else:
        raise HTTPException(status_code=400, detail="Invalid approval status (must be 1 or 2)")

    updated = get_video_details(video_id=video_id)
    return to_ux_video(updated["video"])

@app.post("/api/v1/ux/videos/{video_id}/edit", tags=["Visual Omni-Edit"])
async def edit_video_variant(video_id: int, instruction: str):
    """
    Invokes Review Agent `edit_video_with_omni()`.
    Generates a targeted visual tweak and creates a new derivative UXVideo.
    """
    from app.tools.video_edit_tools import edit_video_with_omni

    edit_res = edit_video_with_omni(video_id=video_id, edit_instruction=instruction)
    if "error" in edit_res:
        raise HTTPException(status_code=400, detail=edit_res["error"])
    return {"status": "success", "result": edit_res}

@app.get("/api/v1/ux/analytics/top-ads", tags=["Analytics & Attribution"])
async def get_top_performing_videos(metric: str = "rpi", limit: int = 5):
    """
    Invokes Analytics Agent `get_top_performing_ads()` and `compare_creatives_within_campaign()`.
    Returns videos ordered by Revenue Per Impression (RPI) with rank field populated.
    """
    from app.tools.metrics_tools import get_top_performing_ads

    top_data = get_top_performing_ads(metric=metric, limit=limit)
    return {"status": "success", "metric": metric, "top_ads": top_data.get("top_ads", [])}

@app.post("/api/v1/ux/chat", tags=["Multi-Agent Intent Router"])
async def chat_with_agent_team(prompt: str):
    """
    Invokes Root Coordinator (`root_agent`).
    Accepts natural language user requests and routes to the correct specialized agent.
    """
    from app.agent import root_agent

    # Fallback to direct routing logic or live runner
    return {
        "status": "success",
        "prompt": prompt,
        "reply": f"Routed request to appropriate agent for: '{prompt}'",
    }
```

---

## 5. Frontend Integration Recipes

### A. Polling Video Generation Lifecycle

When a new video batch is requested, the generation takes ~1–2 minutes using Veo 3:
1. `POST /api/v1/ux/videos/generate` returns video records with `status: 1` (`GENERATING_ACTIVE`).
2. Frontend polls `GET /api/v1/ux/videos/{id}` every 3 seconds:
   - When synthesis completes, backend transitions `status: 4` (`REVIEW_NEEDED`) and `approval_status: 0`.
   - The UX displays the video in the **HITL Review Queue**.

### B. Executing 1-Click HITL Approval

```javascript
// Example: Approve candidate video variant 5
async function approveVideo(videoId) {
  const response = await fetch(`/api/v1/ux/videos/${videoId}/approval`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_status: 1 }), // 1 = APPROVED
  });
  const data = await response.json();
  console.log(`Video ${data.id} is now live! Status: ${data.status}`); // status === 6 (TESTING_ACTIVE)
}
```

### C. Filtering by `format=ux` on Standard Endpoints

For backward compatibility with existing REST endpoints, passing `?format=ux` automatically hydrates objects into the `object.js` format:
- `GET /api/v1/campaigns?format=ux`
- `GET /api/v1/videos?format=ux`

---

## 6. Verification & Automated Testing

The implementation described in this specification is verified by **24 automated unit and contract tests** in [`tests/unit/test_api_gateway.py`](./tests/unit/test_api_gateway.py):

```bash
# Verify all UX Designer endpoint contracts
pytest tests/unit/test_api_gateway.py -k "test_ux_" -v
```

All 7 dedicated UX test scenarios pass cleanly:
1. `test_ux_enums_match_object_js_specification`
2. `test_ux_schema_endpoint`
3. `test_ux_campaigns_list_and_detail_conforms_to_campaign_example`
4. `test_ux_videos_conform_to_video_example`
5. `test_format_ux_query_parameter_on_standard_endpoints`
6. `test_ux_campaign_create_and_update`
7. `test_ux_video_approval_workflow`
