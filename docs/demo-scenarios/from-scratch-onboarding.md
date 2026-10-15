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
