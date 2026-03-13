# Plan: LLM Test Generation — Full System Integration

## Status: Steps 1-7 COMPLETE — Ready for Docker rebuild & testing

---

## Problem (Discovered)
The `llm_enabled` flag in `TrainLoopRequest` was **dead code** — defined but never consumed.
`test_strategy` was hardcoded as `"generated"` in both `suite_runner.py` and `scorer.py`, making LLM tests indistinguishable from registry tests in history.csv.
LLM experiments were hardcoded to H2O only.
LLM generation was not available through the dashboard, making H10 hypothesis invalid.

## Solution
Wire LLM test generation as a first-class feature across the entire system:
dashboard UI → API → suite runner → history.csv → hypothesis analysis.

---

## Implementation Steps

### Step 1: TestCase model ✅
**File**: `models/test_case.py`
- Added `test_origin: str = "registry"` — distinguishes `"registry"` vs `"llm"`
- Added `pytest_code: Optional[str] = None` — LLM tests carry standalone code

### Step 2: Suite runner ✅
**File**: `utils/suite_runner.py`
- Split test cases into LLM vs registry groups at execution start
- Added LLM test execution loop (writes .py files, runs pytest, parses output)
- Fixed `_log_test_result()` to derive `test_strategy` from `test_origin`

### Step 3: Scorer ✅
**File**: `generator/scorer.py`
- Fixed `_build_feature_dataframe()` to derive `test_strategy` from `test_origin`

### Step 4: Coverage gap detection ✅
**File**: `generator/llm_generator.py`
- Added `detect_coverage_gaps()` — analyzes per-protocol detection rates
- Added `generate_tests_for_gaps()` — generates tests targeting identified gaps

### Step 5: Train-loop adaptive generation ✅
**File**: `dashboard/backend/main.py`
- Added helper functions: `_infer_protocol()`, `_infer_port()`, `_llm_dict_to_testcase()`
- Added adaptive LLM block in `_do_loop()` — triggers every N iterations
- Uses `detect_coverage_gaps()` → `generate_tests_for_gaps()` → append to suite

### Step 6: Dashboard /api/generate + Frontend ✅
**File**: `dashboard/backend/main.py`
- Added `_generate_llm_tests_for_suite()` helper
- Wired into both CREATE and ENHANCE paths of `/api/generate`
- Added `llm_enabled` to `GenerateRequest` model
- Added `llm_tests_added` to suite metadata

**File**: `dashboard/frontend/src/components/TestGenerator.jsx`
- Added `llmEnabled` state + toggle UI (violet Sparkles icon)
- Added `llm_enabled` to POST payload
- Added LLM test count badge in success message

### Step 7: Configurable LLM experiments ✅
**File**: `run_experiments.py`
- Added `LLM_FRAMEWORKS = AUTOML_FRAMEWORKS` — all 5 frameworks
- Added `llm_generate_every_n` parameter to `run_experiment()` and API payload
- Updated `run_llm_experiments()` to loop over all frameworks

---

## Verification Status
- All 6 Python files pass `py_compile` ✅
- JSX follows existing component patterns ✅
- Git diff: 11 files, +1,412/-59 lines ✅

## Next Steps (not yet done)
- Docker rebuild and smoke test the full system
- Run a short experiment (3-5 iterations) with LLM enabled to verify end-to-end flow
- Verify history.csv contains correct `test_strategy` values for LLM tests
- Verify H10 hypothesis analysis picks up LLM vs non-LLM comparison
- Consider adding LLM toggle to train-loop UI (TestSuites.jsx) for per-experiment control

---

## Key Files Modified (for quick reference)
| File | What changed |
|------|-------------|
| `models/test_case.py` | +2 fields: test_origin, pytest_code |
| `utils/suite_runner.py` | LLM execution path, test_strategy fix |
| `generator/scorer.py` | test_strategy derivation fix |
| `generator/llm_generator.py` | Gap detection + gap-targeted generation |
| `dashboard/backend/main.py` | Helpers, /api/generate wiring, train-loop adaptive block |
| `dashboard/frontend/.../TestGenerator.jsx` | LLM toggle, payload, success badge |
| `run_experiments.py` | Multi-framework LLM experiments, llm_generate_every_n |
