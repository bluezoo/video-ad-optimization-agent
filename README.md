# video-ad-optimization-agent

# Higher performance in-store advertising starts with accurate audience data

Creating compelling video advertisements has never been easier. Knowing **which advertisements actually drive sales** is the harder problem.

The video advertising optimization agent, developed in collaboration between Google and BlueZoo, demonstrates how privacy-first audience measurement can be combined with the latest generative AI technologies to make in-store digital advertising deliver maximum lift at point-of-sale.

Using Google’s Veo3 AI tool for video synthesis, retailers can create multiple candidate video advertisements for every product in every demographic for less than the cost of a single studio-recorded video shoot. BlueZoo makes it possible to measure which advertisement performs best by allowing retailers to calculate “revenue per impression” (RPI) for each video creative. Retailers use BlueZoo impressions counts delivered for each video advertisement to normalize point-of-sale (POS) revenue by dividing advertised product revenue by the number of impressions delivered for that store’s ad during a day.

<p align="center">
  <a href="./assets/high-level-system.png">
    <img src="./assets/high-level-system.png" alt="Ad Campaign Agent" width="700">
  </a>
</p>

The best-performing creative becomes the seed for the next generation of Veo3-generated content, establishing a continuous optimization loop that delivers a more effective creative with every campaign cycle. Instead of relying on assumptions or lengthy creative cycles, retailers can rapidly generate, evaluate, and refine advertising using measurable business outcomes. The result is a faster, data-driven approach to creating more effective in-store advertising.

**Why This Matters**  
Traditional in-store advertising campaigns require significant time, creative resources, and production costs. Creating multiple versions of a product advertisement for different locations, audiences, or promotions is expensive and time-consuming, making it impractical to test which version works best.

Generative AI changes that by making it possible to create multiple targeted video campaigns for every product and store location in minutes, not weeks. Instead of investing heavily in a single creative concept, retailers can rapidly generate multiple variations, each tailored to specific products, promotions, locations, demographics, or customer segments. However, determining which creative actually influences purchasing behavior has traditionally required expensive manual testing or subjective decision-making.

By measuring real-time campaign performance, retailers can identify which creative delivers the greatest business impact. Those performance insights can then be fed back into the AI to generate even stronger creative, enabling a virtuous cycle of create-multiple-candidates → deploy-in-store → measure-performance → select-the-best → repeat. The result is faster campaign deployment, continuous improvement, and advertising that becomes more effective and cost-efficient over time.

**How It Works**  
The optimization workflow establishes a feedback loop:

1. Human specialist (from retailer or advertiser) uploads one or more seed images and video descriptors (setting, music, model, etc.) to create initial video iterations. (Submit videos for human review or submit to a “review agent”.)  
2. Automated campaign manager deploys video advertising in-store (one creative per store for one or more days) across in-store digital displays.  
3. BlueZoo sensors measure audience impressions (for one or more days).  
4. Retailers calculate revenue per impression by dividing each store’s POS revenue for each advertised product by the number of impressions delivered   
5. Agent identifies the highest-performing video advertisements.  
6. Agent generates new creative variations using Google's Veo3 video generation based on the highest performing advertisements.  
7. Continue at step 2 to improve campaigns over time through progressive optimization.

Instead of making creative decisions based on opinion, retailers can select advertising based on data.

<p align="center">
  <a href="./assets/executive-journey.png">
    <img src="./assets/executive-journey.png" alt="Ad Campaign Agent" width="700">
  </a>
</p>

**Why Google Veo3 Video Synthesis**  
Google Veo 3 video synthesis enables the rapid creation of studio-quality video advertisements, making it possible to generate personalized campaigns for every store location, promotion, or audience in minutes rather than weeks.

Google's AI ecosystem also provides tools to review content for brand compliance and corporate standards, automatically generate alternative creative variations, and orchestrate intelligent workflows that continuously improve campaign performance.

Without in-expensive, scalable content generation, testing multiple creative concepts would be too time-consuming and costly. Google's AI technologies make continuous creative optimization practical at enterprise scale.

**Why BlueZoo Audience Measurement**  
BlueZoo provides the impressions measurement capability that provides the data to the feedback loop, making optimization possible.

Our audience measurement platform delivers:

* Privacy-first impression and dwell time measurement  
* Scalable infrastructure for deployment across tens of thousands of digital screens  
* Mobile applications for measurement auditing that ensures data accuracy

Without reliable audience measurement, AI has no objective way to determine whether newly generated creative is actually performing better. BlueZoo closes that feedback loop.

**Demonstrated at InfoComm 2026**  
This project was developed collaboratively by BlueZoo and Google engineers as a technology demonstration for InfoComm 2026, building on the earlier demonstration first showcased at NRF 2026\.

The goal of the demonstration is to illustrate how audience measurement and generative AI can work together to create a continuous optimization cycle for in-store video advertising, helping retailers maximize advertising effectiveness while maintaining consumer privacy. While the demo at InfoComm 2026 used cached BlueZoo audience data and cached Veo3-generated video advertisements, this agent delivers the code for live connectivity to the Veo3 engine and BlueZoo’s BigQuery database recording real time audience analytics.

Although this repository demonstrates a specific implementation (clothing/fashion brands with human models), the underlying approach can be extended to a wide variety of retail media, digital signage, and in-store advertising applications.

**Learn More**  
To learn more about how to connect BlueZoo's audience measurement platform with this agent, visit [www.bluezoo.io](http://www.bluezoo.io).

For additional background on this demonstration, see the [accompanying announcement](https://www.bluezoo.io/bluezoo-demonstrates-how-googles-latest-ai-technologies-can-improve-the-sales-performance-of-in-store-video-advertising/).

```bash
# 1. Install dependencies
make install

# 2. Run the interactive ADK Agent Web UI (:8501)
make dev

# 3. Or run the REST API Gateway for Web Apps (:8000)
make api
```

---

## Architecture & Multi-Agent System

Built on **Google ADK 2.0** (`google-adk>=2.0.0`), the platform coordinates four specialized domain agents under a unified root coordinator (`app/agent.py`):

```
┌─────────────────────────────────────────────────────────────┐
│                    Root Coordinator Agent                   │
│             (Directs tasks to specialized agents)           │
└──────────────┬──────────────┬──────────────┬────────────────┘
               │              │              │
       ┌───────┴──────┐ ┌─────┴───────┐ ┌────┴────────┐ ┌────────────────┐
       │Campaign Agent│ │ Media Agent │ │Review Agent │ │Analytics Agent │
       │- Catalog     │ │- Veo 3 /    │ │- HITL Queue │ │- BlueZoo RPI   │
       │- Stores      │ │  Nano Banana│ │- Approvals  │ │- POS Revenue   │
       │- Campaigns   │ │- Presets    │ │- Omni-Edit  │ │- Regional Maps │
       └──────────────┘ └─────────────┘ └─────────────┘ └────────────────┘
```

1. **Campaign Agent**: Manages multi-category product onboarding, store locations, and campaign metadata.
2. **Media Agent**: Generates candidate video creative via Google Veo 3 and product imagery via Nano Banana, supporting 15+ configurable parameters and creative presets.
3. **Review Agent**: Provides human-in-the-loop (HITL) review queue management, batch activations/pauses, and targeted video tweaks via Omni-Edit.
4. **Analytics Agent**: Computes BlueZoo audience metrics, POS revenue-per-impression (RPI), creative performance rankings, and geographic comparisons.

---

## 6-Step Poster Workflow Blueprint

The end-to-end workflow matches the architectural poster blueprint ([`assets/use-case-poster.jpeg`](assets/use-case-poster.jpeg)):

| Step | Focus | Responsible Agent | Key Capabilities & Endpoints |
|---|---|---|---|
| **1. Discover Your AI Team** | Catalog & Campaigns | `All Agents` | Inspect available agents, browse multi-category products, view campaigns (`/api/v1/discover`, `/api/v1/agents`, `/api/v1/campaigns`). |
| **2. Generate Creative at Scale** | Video Synthesis | `Media Agent` | Configure 15+ creative parameters (subjects, setting, lighting, mood, audio, props) and generate video variants (`/api/v1/videos/options`, `/api/v1/videos/generate`). |
| **3. You Stay in Control** | HITL Verification | `Review Agent` | Review candidate videos, approve/reject variants, and push live to digital displays (`/api/v1/review/table`, `/api/v1/videos/{id}/activate`). |
| **4. Measure What Matters** | Attribution & Lift | `Analytics Agent` | Correlate BlueZoo sensor dwell/impressions with POS revenue to calculate RPI (`/api/v1/analytics/top-ads`, `/api/v1/analytics/campaigns/{id}/metrics`). |
| **5. See the Big Picture** | Geographic Intelligence | `Analytics Agent` | Compare regional performance (e.g. West Coast vs. East Coast) and render store map visualizations (`/api/v1/maps/regions`, `/api/v1/maps/static`). |
| **6. Scale What Works** | Creative Optimization | `Media Agent` | Extract winning creative attributes from top performers and apply them to subsequent campaign iterations (`/api/v1/optimization/winning-formula`). |

---

## REST API Gateway & Web Application Interface

For integrating frontend web applications, content management systems (CMS), and custom dashboards, the repository provides a standalone **REST API Gateway** (`app/api_gateway.py`):

```bash
# Launch on http://localhost:8000 (override port with PORT=8080 make api)
make api
```

- **Interactive Documentation**: `http://localhost:8000/docs` (Swagger UI via FastAPI)
- **Zero-Dependency Fallback**: Automatically falls back to a built-in multi-threaded HTTP server with full CORS support if `fastapi`/`uvicorn` are absent.
- **Dataset Explorer**: Paginated access and seed/reset controls for all 12 system datasets under `/api/v1/datasets`.
- **Multi-Agent Natural Language Chat**: Real-time intent routing via `POST /api/v1/agents/chat`.

---

## Frontend UX Designer Specification (`object.js`)

The gateway natively implements the frontend UX object specification defined in [`object.js`](object.js):

- **Status & Approval Enums (`GET /api/v1/ux/enums`)**:
  - `Status`: `0: NONE`, `1: GENERATING_ACTIVE`, `2: GENERATING_COMPLETE`, `3: GENERATING_FAILED`, `4: REVIEW_NEEDED`, `5: APPROVAL_UPDATED`, `6: TESTING_ACTIVE`, `7: TESTING_COMPLETE`, `8: TESTING_FAILED`
  - `ApprovalStatus`: `0: NONE`, `1: APPROVED`, `2: REJECTED`
- **UX Campaign Object (`UXCampaign`)**: Formatted 6-digit IDs (`"000001"`), nested status metadata, granular settings blocks (`overall`, `items`, `people`, `performance`, `setting`, `audio`, `format`, `testing`), and populated `videos` collections.
- **UX Video Object (`UXVideo`)**: Formatted IDs, approval states, timestamps, impressions, revenue, test period dates, and rank.
- **Dedicated UX Endpoints**:
  - `GET /api/v1/ux/enums` & `GET /api/v1/ux/schema`
  - `GET /api/v1/ux/campaigns` & `POST /api/v1/ux/campaigns`
  - `GET /api/v1/ux/campaigns/{id}` & `PATCH /api/v1/ux/campaigns/{id}`
  - `GET /api/v1/ux/videos` & `GET /api/v1/ux/videos/{id}`
  - `POST /api/v1/ux/videos/{id}/approval` (1-click approve/reject)
  - `?format=ux` query parameter available across standard `/api/v1/campaigns` and `/api/v1/videos` endpoints.

---

## Documentation Directory

| Document | Purpose |
|---|---|
| [`UX_SERVER_SPEC.md`](UX_SERVER_SPEC.md) | Technical handover specification outlining the rough `server.py` router for UX designers. |
| [`docs/API_GATEWAY.md`](docs/API_GATEWAY.md) | Comprehensive REST API Gateway specification, endpoint catalog, and UX integration guide. |
| [`object.js`](object.js) | Frontend UX object model and status enumeration reference. |
| [`docs/METRICS.md`](docs/METRICS.md) | Single source of truth for BlueZoo audience metrics, dwell times, and POS revenue attribution. |
| [`SETUP_INSTRUCTIONS.md`](SETUP_INSTRUCTIONS.md) | Local environment setup, API keys, Vertex AI / AI Studio configurations, and DB seeding. |
| [`DEMO_GUIDE.md`](DEMO_GUIDE.md) | Step-by-step walkthrough for customer presentations and live demonstrations. |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Cloud Run and Google Cloud Vertex AI Agent Engine deployment instructions. |
| [`tests/README.md`](tests/README.md) | Testing architecture, test levels, markers, and verification suites. |
