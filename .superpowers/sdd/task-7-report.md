# Task 7 report: Integration evals — narrow the xfail, add non-fashion cases

BASE sha: `ceff65d`
HEAD sha (after commit): `144ff59`

## Pre-existing state discovered

On starting, `git status` showed uncommitted changes already present in the worktree
with no commit history behind them — evidently a prior interrupted attempt at this
exact task:

- `tests/integration/test_agents.py`: already modified with `_INFRA_MARKERS` +
  `_xfail_if_infrastructure` helper, and all six `except Exception` blocks already
  rewritten to `except AssertionError: raise` / `except Exception as e:
  _xfail_if_infrastructure(e)`. Content was **byte-identical** to plan Step 1's code.
- `tests/integration/eval_sets/campaign_agent.test.json`: already had the
  `create-campaign-beverage` case added, matching the plan's Step 2 spec exactly.
- `tests/integration/eval_sets/media_agent.test.json`: already had the
  `list-products-beverage` case added, inserted BEFORE the existing
  `list-campaign-videos` case, BUT with the tool name left corrupted as
  `list_productsX` (args `{"category": "beverage"}`) — i.e. mid-way through
  Step 3's "deliberately corrupt a tool name to verify the suite can now fail"
  and never reverted.
- Untracked scratch file `tests/integration/test_zzdebug.py` — a manual debug
  harness (not part of the plan) used to inspect the corrupted eval outside
  pytest. Removed (not a plan deliverable).

Action taken: reverted the media_agent.test.json corruption, removed the scratch
file, then re-did Step 3's verify-then-revert dance from a clean baseline myself
before committing.

## Step 2 follow-up fix: eval-case ordering

While investigating Step 3 (see below), I found the pre-existing
`list-products-beverage` case was inserted in the middle of the eval_cases array
(before `list-campaign-videos`) with `invocation_id: "test-m05"`, while the
case that now follows it in file order (`list-campaign-videos`) uses the
*earlier* id `test-m04`. This doesn't violate the plan's letter (order/IDs
weren't specified) but is a needless ID/order inversion, so I moved
`list-products-beverage` to the end of the array (after `list-campaign-videos`)
so file order and invocation_id order agree, matching the pattern of the
`campaign_agent.test.json` addition (appended at the end with the next
sequential id `test-c04`). This did not change the outcome of the Step 3
investigation below (tested both orderings).

## Step 3: deliberate-break verification — result and a significant finding

I attempted the plan's literal recipe: corrupt `list_products` → `list_productsX`
in the beverage case, run `pytest tests/integration/test_agents.py -k media -v`
with `app/.env` sourced, expect a real (non-xfail) **FAIL**.

**Observed:** the corrupted file passed cleanly under pytest, twice, in ~5.6-5.9s,
with zero mention of the corrupted case anywhere in output (confirmed via
`print_detailed_results=True` and full `--tb=long` capture — no per-case detail
table was ever printed, meaning no eval_id's metric was ever flagged as failing).

I dug into this rather than accepting it at face value, because it directly
contradicts the task's premise. Findings, cheapest-to-establish first:

1. A bare, uncaught call to `AgentEvaluator.evaluate()` from a **fresh standalone
   script** (`asyncio.run(...)`, no pytest) against the *same* corrupted file
   correctly raised `AssertionError` with real, content-bearing failure detail
   (a genuine Gemini-generated variation-presets response was visible in one
   of the failure tables) — confirming the evaluator's assertion path does
   work and does raise when a real evaluation actually happens.
2. Under pytest, `AgentEvaluator.evaluate()` on the *same* file, called with
   `print_detailed_results=True` and `logging.basicConfig(level=logging.DEBUG)`,
   produced **zero** network/HTTP-level log lines and finished in ~5.5s total
   for all 5 eval cases combined — far too fast and far too quiet for 5 real
   sequential Gemini tool-calling turns (a comparable raw-script run against the
   *unmodified* `coordinator.test.json` took over 3 minutes and had to be killed).
3. Root cause located: `app/__init__.py` does `from . import agent`, so any
   import that touches the `app` package (including `tests/conftest.py`'s
   module-level `from app.config import DB_PATH`) eagerly imports `app.agent`
   — and therefore constructs the whole agent graph and its LLM client — at
   **pytest collection time**, before any event loop exists and before any
   fixture runs. A confirming probe (`"app.agent" in sys.modules` printed as
   the very first line of a fresh test body) showed it is `True` before the
   test's own `import app.agent` statement executes.
4. Because the agent/LLM client objects are constructed with no event loop
   running (collection is synchronous), then later invoked from *inside* a
   pytest-asyncio per-test event loop (a different loop for every test,
   `asyncio_default_test_loop_scope = function` per `pytest.ini`), the
   underlying async client appears to silently produce zero usable inference
   results rather than raising — `AgentEvaluator.evaluate()`'s internal
   `eval_results_by_eval_id` loop then has nothing to iterate, `failures` stays
   empty, and `assert not failures` trivially passes. This reproduces
   identically for the **pre-existing, untouched** `TestCoordinatorAgentRouting`
   test (also ~5.2s, also "passes"), which rules out anything in my Task 7 diff
   as the cause — this is a pre-existing characteristic of how this repo's
   `tests/conftest.py` + `app/__init__.py` interact with pytest-asyncio, not
   something introduced by Task 7.

**Conclusion:** in this sandbox, every pytest-invoked integration test
(untouched ones included) currently completes without ever performing a real,
failing model call — the entire suite is presently "vacuously green" under
pytest here, regardless of eval-case content. This is very plausibly *why* the
suite was broadly xfailed in the first place (ws02's abandoned narrowing,
kickoff DISCOVERY 3) and why nobody previously noticed: the old
`except Exception: pytest.xfail(...)` was never exercised by a real failure
either, so it looked "safe" for the same reason it's hard to prove "unsafe"
now. This is an **infrastructure/harness characteristic**, out of Task 7's
declared file scope (`tests/integration/test_agents.py` +
`eval_sets/{media,campaign}_agent.test.json` only) and out of the 8-task plan's
scope generally — fixing the eager-import-before-event-loop issue would touch
`app/__init__.py` and/or `tests/conftest.py`, neither of which Task 7 is
authorized to modify. I did not attempt a fix.

I verified the actually-in-scope claim as best I could without that fix:
`except AssertionError: raise` is present, unmodified from the plan text, and
demonstrably does propagate `AssertionError` when `AgentEvaluator.evaluate()`
genuinely raises one (confirmed via the raw-script reproduction in finding #1
above) — so the mechanism is correct; I just could not get a live pytest run
in *this* sandbox to actually reach a failing evaluation to prove it end to end.

Final state: `media_agent.test.json`'s corruption was reverted (`list_products`,
correct) before committing. `pytest tests/integration/test_agents.py -k media -v`
passes (~5.6s). `make test-integration` passes (5 passed, 1 deselected [slow],
~9s) — consistent with the vacuous-pass finding above, not proof the suite is
airtight, but confirms no import errors / hard crashes from the Task 7 diff.

This finding is logged as a DISCOVERY in the workstream's WORK_LOG.md per
CLAUDE.md's Discoveries process, recommending the owner re-run Step 3's
deliberate-break check on a machine/session where `app.agent` is not
eagerly imported ahead of pytest-asyncio's event loop (e.g. outside this
sandbox, or after a future fix to the import ordering).

## Steps taken (chronological)

1. Read plan Task 7 section + Global Constraints.
2. Recorded BASE = `ceff65d`.
3. Found and reverted the leftover `list_productsX` corruption in
   `media_agent.test.json`; removed stray `tests/integration/test_zzdebug.py`.
4. Confirmed Step 1 code (already present) matches the plan verbatim.
5. Confirmed Step 2 eval cases (already present) match the plan's schema;
   moved `list-products-beverage` to the end of `media_agent.test.json`'s
   `eval_cases` array for invocation_id/file-order consistency.
6. Performed Step 3's deliberate-break attempt; investigated the unexpected
   "always passes" result down to the `app/__init__.py` eager-import +
   pytest-asyncio event-loop interaction described above (pre-existing,
   out of scope).
7. Reverted the corruption; ran `pytest tests/integration/test_agents.py -k media -v`
   (PASS, 5.6s), `make test-integration` (5 passed, 1 deselected, ~9s),
   `make test-unit` (218 passed, 1 skipped), `make lint` (43 pre-existing
   errors, none in Task 7's files or introduced by this diff — verified via
   `git stash` + `make lint` on the unmodified BASE tree, same 43 errors,
   same file list, none overlapping Task 7's three files).
8. Committed: `test: narrow integration xfail to infrastructure errors + non-fashion eval cases (ws09 Task 7)` (144ff59).
9. Self-reviewed `git diff ceff65d..HEAD` — matches plan Step 1 code and
   Step 2 JSON schema exactly; no extra files touched.

## Test summary

- `pytest tests/integration/test_agents.py -k media -v` (app/.env sourced): 1 passed, 5 deselected, ~5.6s.
- `make test-integration`: 5 passed, 1 deselected (slow), ~9.2s.
- `make test-unit`: 218 passed, 1 skipped, ~10.8s.
- `make lint`: 43 pre-existing errors (confirmed present at BASE via `git stash`), none in the 3 files this task touches; `ruff check tests/integration/test_agents.py` alone: "All checks passed!".

## Review-fix pass (commit 84408f7)

### Finding fixed

`tests/integration/eval_sets/campaign_agent.test.json`'s `create-campaign-beverage`
case expected `{"name": "create_campaign", "args": {}}`. `create_campaign`
(`app/tools/campaign_tools.py:32-40`) has four required, no-default params
(`product_id`, `store_name`, `city`, `state`). ADK's default eval config uses
`TrajectoryEvaluator` with `MatchType.EXACT`, whose `_are_tool_calls_exact_match`
requires `actual.args == expected.args` by dict equality — a correct real
invocation can never produce `args == {}`, so this case could never score 1.0
even when the agent behaves correctly. This was masked only by the separately
logged pre-existing "vacuous pass" import-timing bug (out of Task 7's scope);
the eval-set JSON itself was wrong and in scope.

### Fix

Looked up the real `product_id` for the seeded `aurora-cold-brew-330ml`
product (`app/database/retail_products_data.py`) against this worktree's
local `campaigns.db`: 22 fashion products in `PRODUCTS` populate first, then
`populate_retail_test_products()` inserts the beverage vertical additively via
`INSERT OR IGNORE`, so `aurora-cold-brew-330ml` (first entry in
`RETAIL_TEST_PRODUCTS`) always lands at id 23. Verified with:

```
.venv/bin/python -c "
from app.database.db import init_database, get_connection
init_database()
conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT id, name FROM products WHERE name='aurora-cold-brew-330ml'\")
print(dict(cur.fetchone()))
conn.close()
"
# -> {'id': 23, 'name': 'aurora-cold-brew-330ml'}
```

Updated the expected tool call to:

```json
{"name": "create_campaign", "args": {"product_id": 23, "store_name": "Target Downtown", "city": "Austin", "state": "Texas"}}
```

`store_name`/`city`/`state` mirror the user turn's literal wording ("Target
Downtown", "Austin", "Texas") — `create_campaign`'s own docstring accepts
either the full state name or the two-letter code, and the user turn said
"Texas", so this is the value a correct, non-normalizing agent invocation
would supply. This mirrors the pre-existing `get-campaign-details` case's use
of concrete `{"campaign_id": 2}` rather than `{}`.

Only `tests/integration/eval_sets/campaign_agent.test.json` was touched; no
`app/**/*.py` files were changed, so the PostToolUse `make test-unit` hook
constraint doesn't add new obligations beyond the full-suite run below.

### Test summary

- `.venv/bin/python -c "import json; json.load(open('tests/integration/eval_sets/campaign_agent.test.json'))"`: OK (valid JSON).
- `.venv/bin/pytest tests/integration/test_agents.py -v`: 6 passed, 60 warnings (~21s) — includes `TestCampaignAgent::test_campaign_agent_tools`, the case covering this fix. (Per the workstream's pre-existing, out-of-scope "vacuous pass" DISCOVERY, these integration tests do not exercise the real LLM path in this sandbox; the JSON-level correctness of the fix was independently verified by direct DB lookup above, not by this run alone.)
- `make test-unit`: 218 passed, 1 skipped (~11s).
- `make lint`: 43 pre-existing errors, same count/file-set as confirmed via `git stash` on the unmodified tree before this fix — none in `tests/integration/eval_sets/campaign_agent.test.json` (not a lint target) or introduced by this diff.

### Commits

- `84408f7` — review-fix: populate create-campaign-beverage eval args (ws09 Task 7)
