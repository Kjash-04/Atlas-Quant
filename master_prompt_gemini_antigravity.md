# MASTER PROMPT — Multi-AI-Agent Self-Improving Trading Bot
## Gemini 4 Argon / Antigravity / Free Windows Edition

> Copy everything from this line downward into Antigravity (`agy` CLI or VS Code Antigravity extension).
> This version already bakes in: Windows, $0 extra budget, Google AI Pro, Gemini 4 Argon, LangGraph, MT5 paper trading.

OUTPUT_MODE = "BUILD"   # BUILD | ARTICLE | VIDEO_SCRIPT | PITCH_DECK
PROJECT_NAME = "Atlas-Quant"
RISK_DISCLAIMER = "Research/educational only. Not financial advice. Past performance does not guarantee future results. Live trading requires explicit human approval."

---

## ENVIRONMENT (hard constraints — do not override)
- OS: Windows 10/11 x64. Python 3.11+ **64-bit** (required by MetaTrader5).
- Extra budget: **$0**. No Cursor, no Claude Code, no Anthropic API, no OpenAI paid API, no BYOK inside Antigravity.
- Build-time IDE/agent: **VS Code + Antigravity VS Code extension + Antigravity CLI (`agy`)**.
- Google AI Pro (paid, non-trial) with **Gemini 4 Argon**. In Antigravity: **AI Credit Overages = Never**.
- Build-time models: **Gemini 4 Argon (High thinking)** for architecture/hard debugging; **Gemini 3.8 Flash** for routine edits.
- Runtime orchestrator: **LangGraph** (free, Python) + `google-genai` / `langchain-google-genai`.
- Runtime LLM routing (two keys):
  - `GEMINI_FREE_API_KEY` → `gemini-3.8-flash` (Project A, **no billing**, free tier). Use for Observe, regime labels, news parsing, logging, routine agent messages.
  - `GEMINI_DEEP_API_KEY` → `gemini-4-argon` (Project B, billing enabled but covered by **$10/mo AI Pro Cloud credit**, **$0 budget cap**, alert at $1). Use ONLY for Diagnose / Hypothesize / Keep-or-Revert. Max `DEEP_LLM_CALLS_PER_DAY=20`. Cache every response.
- Google Cloud: activate monthly credit at https://developers.google.com/program; set **budget cap $0** and disable paid overrun.
- Broker: `MetaTrader5` Python package, **Windows-native**, demo/paper account only. `LIVE_TRADING=false`, `PAPER_TRADING=true`, `HUMAN_APPROVAL_REQUIRED=true`.
- Secrets: `.env` only. Never hardcode, never log, never send to free-tier Gemini API (free-tier prompts may be used to improve Google products).
- LLM may propose code diffs but **NEVER** places MT5 orders. Only deterministic `RiskEngine` + `ExecutionAgent` talk to MT5.
- All timestamps UTC. Store original exchange timezone alongside.
- Include `RISK_DISCLAIMER` in README and dashboard footer.

## ROLE
You are a senior quantitative researcher, AI multi-agent systems architect, Python backend engineer, and risk-aware algorithmic-trading developer. Build a complete, auditable, self-improving trading research-and-execution system. Optimize for data integrity, deterministic rules, statistical validity, capital preservation, and controlled automation — not hype.

## HARD CONSTRAINTS (never violate)
1. No look-ahead bias, survivorship bias, or train/test leakage. Every feature uses only information available at the decision timestamp.
2. The LLM / Reasoning Engine must NEVER bypass the deterministic Risk Engine and must NEVER place an order directly.
3. Paper trading is default. Live trading disabled unless `LIVE_TRADING=true` AND a signed human approval record exists in DB.
4. Risk limits immutable to self-improvement loop. Only `strategies/` and `research/` may be auto-modified; `risk_engine/` and `execution/` require human review.
5. Every hypothesis, code diff, parameter set, backtest result, decision, trade, LLM call, and health event is persisted with timestamp, version id, parent id, hashes, and `model_id` + `token_count` + `estimated_cost_usd` (must be 0.00 for free tier).
6. Fail closed: if data feed, news feed, broker connection, DB, Gemini API, or model health is degraded, Execution Agent halts new orders.
7. Secrets from `.env` / secret manager; never hardcode or log them.
8. Never claim profitability. Always report uncertainty, overfitting risk, and out-of-sample degradation.
9. Include regulatory, broker-terms, and tax cautions in README.
10. Include `RISK_DISCLAIMER` in README and dashboard footer.
11. Never exceed $0 net spend: free Flash key for routine work, Argon only within monthly credit, with hard budget cap and call counter.

## ASSUMPTIONS (state them, then proceed)
- Markets: forex / CFDs / crypto via MetaTrader 5 (MT5), Windows terminal installed.
- Data sources: TradingView webhooks, MT5 historical + live ticks, news APIs / economic calendar, alternative data (vol index, funding rates, sentiment) where available.
- Stack: Python 3.11+ 64-bit, FastAPI, Pydantic v2, pandas/numpy, SQLAlchemy, Redis, Celery/RQ, pytest, Streamlit or Grafana, Docker Compose, SQLite locally / Postgres+TimescaleDB in prod, LangGraph, google-genai.
- Antigravity is ONLY a build-time tool; it is not part of the deployed runtime.

---

## 1. SYSTEM OVERVIEW (User item 1 — The Architecture)
Design a central **AI Orchestrator** that ingests market data (TradingView, MT5, News, Alternative Data), normalizes it into a `MarketSnapshot` event stream, and coordinates:

| Agent | Responsibility | LLM |
|---|---|---|
| `DataIngestionAgent` | Fetch, clean, deduplicate, align timestamps, handle gaps | none (deterministic) |
| `RegimeAgent` | Label market state: trending / ranging / high-vol / low-vol / news-shock | `gemini-3.8-flash` (free) for optional NLP news tagging |
| `ResearchAgent` | Generate trading hypotheses from data + stored learnings | `gemini-3.8-flash` (free) |
| `StrategyCoderAgent` | Turn hypotheses into strict, deterministic Python `StrategySpec` + code | `gemini-4-argon` (deep, scarce) only when hypothesis is complex; otherwise Flash |
| `BacktestAgent` | IS/OOS/Test validation, walk-forward, robustness heatmaps, cost model | none (local compute) |
| `ReasoningEngine` (LLM Critic) | Observe failures, diagnose, hypothesize fixes, compare versions, decide keep/revert | `gemini-4-argon` for Diagnose/Hypothesize/Keep-or-Revert; `gemini-3.8-flash` for Observe/Store |
| `MemoryAgent` | Experiment DB, learning store, champion/challenger registry, LLM response cache | none |
| `RiskEngine` | Deterministic pre-trade gate (NOT an LLM) | none |
| `ExecutionAgent` | MT5 bridge, paper or live, reconciliation | none |
| `MonitorAgent` | Health checks, metrics, alerts, kill switch, **LLM budget alerts** | none |
| `HumanApprovalGate` | Required for live enablement, risk-rule changes, capital increases | none |

Deliver for this section:
- A Mermaid `flowchart TD` diagram: `Data sources → Ingestion → LangGraph Orchestrator → Research/Coder/Backtest/Reasoning/Memory → Risk Engine → Execution (Paper MT5 on Windows) → Monitor → Alerts → back into Memory`. Mark Gemini 4 Argon / Gemini 3.8 Flash on the LLM nodes.
- A repo file tree.
- A one-paragraph description of the continuous loop: `data → research → code → backtest → critique → keep/revert → deploy(paper) → monitor → data`.
- A `src/llm_router.py` implementing the two-key router described in ENVIRONMENT.

---

## 2. USER STEP 1 — BUILD THE RESEARCH ENGINE
Build a structured pipeline that feeds the AI real market data.

1. `MarketSnapshot` schema (Pydantic + SQLAlchemy):
   - `symbol, timestamp_utc, timeframe, open, high, low, close, volume, spread`
   - `indicators: {ema_20, ema_50, rsi_14, atr_14, atr_percentile_100, realized_vol_20, session}`
   - `news_events: [{time_utc, currency, impact, title, minutes_until}]`
   - `alt_data: {vol_index, funding_rate, sentiment_score, ...}`
   - `regime_label, data_hash, ingested_at`
2. Adapters: `TradingViewWebhookAdapter`, `MT5Adapter`, `NewsCalendarAdapter`, `AlternativeDataAdapter`. Each writes snapshots to `market_snapshots` and publishes to event bus.
3. Indicator module: RSI, EMA, ATR, ATR percentile, realized volatility, rolling regime, session tags — computed causally (no future bars).
4. `ResearchAgent` reads snapshots + learnings and emits `Hypothesis`:
   `id, natural_language_idea, rationale, regime_scope, proposed_indicators, expected_edge, risk_notes, created_at, parent_learning_ids, status`. Use `gemini-3.8-flash` free key; cache prompt+response.
5. Experiment DB tables: `hypotheses, experiments, strategy_versions, backtest_runs, learnings, trades, llm_calls, system_health, approvals`. Status funnel: `IDEA → SPEC → CODED → BACKTESTING → VALIDATED → IMPROVED → REJECTED → CHAMPION → RETIRED`.
6. Every experiment logs: `code_hash, param_hash, data_hash, version_id, parent_version_id, metrics_json, decision, reason, created_at`. Every LLM call logs `model_id, prompt_hash, token_count, estimated_cost_usd, cache_hit`.

Deliver: schemas, adapter stubs, indicator functions, SQL migration, `llm_router.py`, and an example run converting raw OHLCV + calendar into a `Hypothesis`.

---

## 3. USER STEP 2 — FROM IDEA TO EXECUTABLE STRATEGY
Convert vague trading hypotheses into **strict, deterministic, machine-readable Python rules with zero human interpretation at runtime**.

Define `StrategySpec` with fields:
- `strategy_id, version, parent_version, hypothesis_id, status`
- `universe, timeframe, required_indicators`
- `entry_rules: list[Rule]`, `exit_rules: list[Rule]`, where `Rule = {feature, operator, value, lookback, weight}` combined by explicit `logic: "AND" | "OR" | "WEIGHTED_THRESHOLD"`.
- `stop_loss_atr_mult, take_profit_rr, trailing_stop_atr_mult`
- `position_sizing: {model: "fixed_fractional", risk_per_trade: 0.01, max_position_pct: 0.05, lot_step}`
- `risk_controls: {max_daily_trades, news_blackout_minutes, max_spread_pips, allowed_sessions, max_correlated_positions, max_open_positions}`
- `parameter_ranges` with realistic bounds, e.g. `ema_fast: [10,15,20,25,30]`, `ema_slow: [40,50,60,70,80]`, `rsi_period: [10,14,18]`, `atr_filter_percentile: [60,70,80,90]`, `atr_stop_mult: [1.5,2.0,2.5]`.
- `invalidation_rules`, `created_at, code_hash`.

`StrategyCoderAgent` must:
- Take `Hypothesis` → produce `StrategySpec` → generate a `BaseStrategy` subclass with `compute_indicators(df)`, `generate_signals(df)`, `size_position(equity, atr, symbol_info)`, `risk_filters(snapshot)`.
- Use `gemini-4-argon` (High) only for ambiguous/complex hypotheses; otherwise `gemini-3.8-flash`. Emit deterministic diff; no free-form English in execution path.
- Reject ambiguous hypotheses as `REJECTED` with reason.

Example hypothesis to convert (include it):
> "Go long when short EMA crosses above long EMA and RSI is not overbought, but skip trades when volatility is extreme or a high-impact news event is within 30 minutes. Risk 1% per trade with a 2R target and an ATR-based stop."

Deliver: example `StrategySpec` JSON, generated Python strategy class, determinism unit test, validator rejecting missing risk controls/unbounded params, and a `google-genai` call wrapper that records cost.

---

## 4. USER STEP 3 — BACKTEST WITHOUT FOOLING YOURSELF
Implement rigorous validation — **all local compute, zero LLM cost**:

1. Chronological split: **In-Sample 60% / Out-of-Sample 20% / Held-out Test 20%**. Test set touched once, after all improvements.
2. Walk-forward analysis: rolling/anchored windows (e.g., 12-month train → 3-month validate), re-optimize only on train, report parameter stability across folds.
3. Parameter robustness heatmaps: vary two params at a time; plot Sharpe / profit-factor surface; flag isolated "profitability islands".
4. Realistic costs: commission per lot, symbol/time-dependent spread, slippage (fixed + volatility-proportional), swap/overnight financing, partial fills, latency.
5. Purge/embargo around train/validation boundaries and high-impact news to avoid leakage.
6. Metrics: net return, CAGR, Sharpe, Sortino, max drawdown, Calmar, profit factor, expectancy, win rate, avg trade, turnover, trade count, OOS degradation %, slippage sensitivity, worst day, capacity estimate.
7. `CHAMPION` acceptance criteria (pre-registered, configurable):
   - Positive expectancy after costs on IS **and** OOS.
   - OOS Sharpe ≥ 70% of IS Sharpe; OOS max DD within limit.
   - Max drawdown < 15%; min 30 trades per regime; stable across ≥ 4 walk-forward folds.
   - Robust parameter neighborhood (no single-point island).
   - Test-set result reported separately and never used for tuning.
8. `BacktestReport`: metrics table, equity curve, drawdown curve, heatmap, walk-forward fold table, cost breakdown, red-flags section.

Deliver: backtest engine, example report, leakage-detection tests (perturbing future bars must not change past signals).

---

## 5. USER STEP 4 — A CONTROLLED SELF-IMPROVEMENT LOOP
Implement the 7-step cycle as an auditable **LangGraph** state machine:

1. **Observe** — Monitor paper/live trades and backtest residuals; detect where champion fails (e.g., losses cluster when `atr_percentile > 85` or during high-impact news). Use `gemini-3.8-flash` free key to summarize residuals.
2. **Diagnose** — Reasoning Engine correlates failures with regime, indicators, news, spread, slippage; outputs structured `Diagnosis {evidence, confidence, affected_regimes}`. Use `gemini-4-argon` (deep key, decrement daily counter).
3. **Hypothesize** — Propose a concrete, spec-representable fix (e.g., "add `atr_percentile < 80` filter", "widen stop in high-vol regime"). Use `gemini-4-argon`.
4. **Experiment** — `StrategyCoderAgent` creates `challenger_version` from `champion_version` with only the approved diff; new version id, parent id, hashes.
5. **Validate** — `BacktestAgent` runs challenger through same IS/OOS/walk-forward/cost pipeline; compares to champion on fixed scorecard. Local compute only.
6. **Keep or Revert** — Keep only if challenger beats champion on pre-registered criteria (OOS Sharpe, max DD, profit factor, robustness), passes all risk-engine tests, and does not degrade any regime beyond tolerance. Use `gemini-4-argon` for final decision; otherwise revert and log reason.
7. **Store** — Persist `Learning {diagnosis, hypothesis, diff, metrics_before, metrics_after, decision, reason, embedding, timestamp, strategy_id}`; feed back to `ResearchAgent`. Use `gemini-3.8-flash` to generate embedding/summary if needed, cached.

Guardrails:
- Max N cycles/day, max M pending challengers, cooldown after K consecutive reverts.
- `DEEP_LLM_CALLS_PER_DAY=20`; if counter exhausted, skip Diagnose/Hypothesize and log `BUDGET_EXHAUSTED` instead of calling paid API.
- Champion/challenger registry; one champion per strategy family.
- Auto-modification limited to `strategies/` and `research/`; `risk_engine/` and `execution/` read-only to agents.
- Every cycle emits audit event; any decision replayable.
- Alert and halt auto-promotion if Test set reused or if `estimated_cost_usd > 0` unexpectedly.

Deliver: LangGraph orchestrator code, `Learning` schema, example cycle transcript, keep/revert unit tests, and `llm_budget.py` guard.

---

## 6. USER STEP 5 — EXECUTE WITH RISK CONTROLS
Place a strict **Risk Engine** between strategy signals and the MT5 broker API.

`RiskEngine.check(intent, account, snapshot, recent_trades) -> Approval | Rejection` enforces, in order:
- Circuit-breaker state `ACTIVE | PAUSED | HALTED`; kill switch.
- Data freshness, broker heartbeat, clock sync.
- Max daily loss (e.g., 3% equity) → `PAUSED`.
- Max drawdown (e.g., 10% peak-to-trough) → `HALTED`.
- Max daily trades, max open positions, max correlated exposure.
- Spread / slippage thresholds, news blackout, allowed sessions.
- Margin / free-margin check, max lot, symbol limits.
- Fixed fractional sizing: risk exactly `risk_per_trade = 0.01` of equity based on stop distance and ATR; round to broker lot step.
- Idempotency key; reject duplicate intents.

`ExecutionAgent`:
- `MT5Adapter` using `MetaTrader5` package (Windows x64 native): `initialize`, `symbol_info_tick`, `order_send`, deal/position reconciliation, partial fills, retry with backoff, heartbeat.
- `PaperAdapter`: simulated fills with spread + slippage, no real orders.
- Circuit breaker: on disconnect, rejection, drawdown breach, or stale data → `HALTED`, cancel pendings, alert, manual reset.
- Emergency endpoint `POST /admin/kill` flattens/cancels and blocks new orders.
- Order lifecycle events persisted to `trades` and `system_health`.

Testing: unit tests for every rejection reason; integration test proving no order reaches MT5 when risk rejects; 2-week paper soak test before any live flag.

Deliver: `RiskEngine`, `MT5Adapter`, `PaperAdapter`, kill-switch API, tests, pre-live checklist. Note in README: `MetaTrader5` is Windows-only; we are already on Windows, so no VPS/Wine needed for development.

---

## 7. USER STEP 6 — TURN IT INTO A REAL-WORLD SYSTEM
Wire into production:

- **Control plane (FastAPI):** `/health`, `/snapshots`, `/hypotheses`, `/strategies`, `/backtests`, `/experiments`, `/learnings`, `/llm-calls`, `/orders`, `/metrics`, `/admin/kill`, `/admin/approve-live`.
- **Data plane:** SQLAlchemy models for all tables; Redis/event bus for snapshots + agent messages; Celery/RQ workers for backtests and improvement cycles; object storage for reports.
- **Dashboard (Streamlit/Grafana):** equity curve, drawdown, open positions, agent status, champion/challenger versions, experiment funnel, system health, alert feed, cost breakdown, **LLM call counter + estimated spend (must stay $0.00)**.
- **Alerts (Telegram/Slack/email):** broker disconnect, stale data, order rejection, drawdown breach, daily loss limit, kill switch, agent crash, Test-set reuse, consecutive reverts, **Gemini API error, free-tier rate limit hit, deep-LLM budget exhausted, any `estimated_cost_usd > 0`**.
- **Health checks:** data freshness < N sec, broker ping, DB connectivity, agent heartbeat, Gemini API latency, queue depth, clock drift, disk space, monthly credit remaining.
- **Scaling path:** 1 paper strategy → 3–5 uncorrelated paper strategies → small live capital with human approval → multi-strategy portfolio with correlation-aware capital allocator. Increase capital only after M consecutive stable weeks and zero Sev-1 incidents.
- Include Docker Compose, `.env.example`, `requirements.txt`, `setup_windows.ps1`, README, runbook, incident response, backup/restore, migrations.

Deliver: FastAPI stub, dashboard panel spec, alert-rule table, `docker-compose.yml`, README with roadmap, go-live approval checklist, and the Windows/Gemini setup files.

---

## FINAL DELIVERABLES CHECKLIST (return in this order)
1. Executive summary + ENVIRONMENT + assumptions + `RISK_DISCLAIMER`.
2. Mermaid architecture diagram (mark Gemini 4 Argon / Gemini 3.8 Flash nodes).
3. Repo file tree.
4. All Pydantic + SQLAlchemy schemas (include `llm_calls` table).
5. Research engine, adapters, indicators, `src/llm_router.py`.
6. `StrategySpec`, example generated strategy, hypothesis conversion, `google-genai` wrapper.
7. Backtest engine, splits, walk-forward, heatmap, cost model, example report (local, $0).
8. LangGraph 7-step self-improvement orchestrator, learning store, keep/revert logic, `llm_budget.py`.
9. Risk Engine, `MT5Adapter` (Windows), `PaperAdapter`, kill switch, tests.
10. FastAPI control plane, dashboard, alerts (incl. LLM budget), health checks.
11. Docker Compose, `.env.example`, `requirements.txt`, `setup_windows.ps1`, README, runbook.
12. Tests: unit, integration, leakage detection, risk rejection, replay, **LLM budget guard**.
13. Final safety checklist: "Human approval required before `LIVE_TRADING=true`", "AI Credit Overages = Never", "Google Cloud budget cap $0", regulatory caution, and exact `RISK_DISCLAIMER`.

If `OUTPUT_MODE` is `ARTICLE`, `VIDEO_SCRIPT`, or `PITCH_DECK`, keep every section's substance but replace code with explanations, diagrams, tables, and narration. Do not skip any of the 6 user steps or the architecture overview. End with the same safety checklist.

---

## OFFICIAL REFERENCES (for README)
- Antigravity download / CLI / extensions: https://antigravity.google/download/
- Antigravity models (Argon availability): https://antigravity.google/docs/models.md
- Antigravity plans / AI Credit Overages: https://antigravity.google/docs/plans.md
- Gemini API plans (AI Pro ≠ API key): https://ai.google.dev/gemini-api/docs/google-ai-plans
- Gemini 4 Argon model card: https://ai.google.dev/gemini-api/docs/models/gemini-4-argon
- Free API keys: https://aistudio.google.com/apikey
- Google Developer Program $10/mo credit: https://developers.google.com/program
- Code Assist → Antigravity deprecation: https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals
- MetaTrader5 PyPI (Windows wheels): https://pypi.org/project/metatrader5/

---
*End of master prompt — Gemini 4 Argon / Antigravity / Free Windows Edition.*
