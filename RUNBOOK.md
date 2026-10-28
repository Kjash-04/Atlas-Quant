# ATLAS-QUANT OPERATIONAL RUNBOOK

## 1. System Architecture & Daily Routine
Atlas-Quant is an autonomous multi-agent quantitative research and execution engine.
- **Operating Environment**: Windows 10/11 x64, 64-bit Python.
- **Net Budget**: Strictly $0.00. Gemini 3.8 Flash free tier + Gemini 4 Argon within monthly credit.
- **Broker**: MetaTrader 5 (Windows terminal native). Default mode: `PAPER_TRADING=true`.

### Morning Standup Routine (08:00 UTC)
1. Verify system telemetry via `GET /health` or Streamlit dashboard at `http://localhost:8501`.
2. Inspect Deep LLM budget counter: Ensure daily Argon calls counter has rolled over at UTC 00:00 (`0 / 20 used`).
3. Check circuit breaker state: Must be `ACTIVE`.
4. Inspect overnight paper soak deals and ensure zero Sev-1 incidents.

---

## 2. Emergency Incident Response (Sev-1 Runbooks)

### Incident 1: Unexpected LLM Spend Detected (`estimated_cost_usd > 0`)
- **Action**: IMMEDIATE SEV-1.
- **Resolution**:
  1. Inspect `data/llm_budget_state.json` and query `/llm-calls`.
  2. Verify Project B budget cap in Google Cloud Console is locked to $0.00 with overages disabled.
  3. Ensure `AI Credit Overages = Never` is configured in Antigravity settings.
  4. Ensure `GEMINI_FREE_API_KEY` is tied exclusively to Project A (free tier, no billing account attached).

### Incident 2: Circuit Breaker HALTED (Drawdown Breach >= 10%)
- **Action**:
  1. Execution agent immediately cancels all pending orders and blocks new entries.
  2. Review residual log in `learnings` and `trades` tables to identify failure mode.
  3. Manual admin reset requires `POST /admin/reset-circuit-breaker` with token `ADMIN_RESET_CONFIRMED` only after quantitative root cause analysis.

### Incident 3: Emergency Kill Switch Procedure
- **Trigger**: Broker quote anomaly, network disconnection, or unexpected market event.
- **Command Line**:
  ```powershell
  curl -X POST http://localhost:8000/admin/kill -H "Content-Type: application/json" -d "{\"reason\": \"Admin manual emergency kill\", \"admin_token\": \"EMERGENCY_KILL_AUTHORIZED\"}"
  ```
- **Dashboard**: Click `🚨 Engage Kill Switch` on the sidebar.
- **Result**: Instantly flattens all open positions and places circuit breaker into `HALTED`.

---

## 3. Backup, Restore & Replay Procedures

### Database Backup
```powershell
# SQLite local backup
Copy-Item "data/atlas_quant.db" "data/backups/atlas_quant_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
```

### Experiment Replay Procedure
Every experiment logs:
- `code_hash`
- `param_hash`
- `data_hash`
- `metrics_json`
To replay an experiment, query `/experiments` for the `experiment_id`, retrieve the snapshot range corresponding to `data_hash`, and run `scripts/run_backtest.py` with the exact historical parameters.

---

## 4. Go-Live Human Approval Checklist
Before switching `LIVE_TRADING=true` from `PAPER_TRADING=true`:
- [ ] Minimum 14 continuous days of error-free paper soak testing completed.
- [ ] Positive expectancy after costs verified across all market regimes.
- [ ] Walk-forward parameter stability confirmed across >= 4 folds.
- [ ] Maximum paper drawdown remained strictly under 8.0%.
- [ ] Signed `HumanApprovalRecord` submitted via `POST /admin/approve-live`.
- [ ] Google Cloud billing cap confirmed at $0.00 with disable alerts configured.
- [ ] Exact Risk Disclaimer accepted by the operator:
  > *"Research/educational only. Not financial advice. Past performance does not guarantee future results. Live trading requires explicit human approval."*
