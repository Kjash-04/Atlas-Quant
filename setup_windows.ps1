# ==============================================================================
# Atlas-Quant Windows Setup & Initialization Script
# Architecture: 64-bit Windows AMD64 | Python 3.11+
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ATLAS-QUANT: WINDOWS ENVIRONMENT SETUP" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Python & Architecture
Write-Host "`n[1/5] Checking Python architecture..." -ForegroundColor Yellow
$pyArch = python -c "import platform; print(platform.architecture()[0])"
if ($pyArch -ne "64bit") {
    Write-Host "ERROR: MetaTrader5 requires 64-bit Python. Found: $pyArch" -ForegroundColor Red
    Exit 1
}
Write-Host "  -> Verified 64-bit Python." -ForegroundColor Green

# 2. Check and Create .env
Write-Host "`n[2/5] Checking environment configuration (.env)..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Write-Host "  -> Copying .env.example to .env..." -ForegroundColor White
    Copy-Item ".env.example" ".env"
    Write-Host "  -> Created default .env file. Update your GEMINI_FREE_API_KEY when ready." -ForegroundColor Green
} else {
    Write-Host "  -> .env file already exists." -ForegroundColor Green
}

# 3. Install Python Dependencies
Write-Host "`n[3/5] Installing dependencies via pip..." -ForegroundColor Yellow
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Pip returned non-zero exit code. Please review errors above." -ForegroundColor Yellow
} else {
    Write-Host "  -> Python dependencies installed successfully." -ForegroundColor Green
}

# 4. Generate Sample Market Data & Seed DB
Write-Host "`n[4/5] Generating initial market data & seeding database..." -ForegroundColor Yellow
python scripts/generate_sample_data.py
python -c "from src.database.connection import init_db; init_db(); print('Database tables initialized.')"
Write-Host "  -> Database initialized." -ForegroundColor Green

# 5. Run Validation Test Suite
Write-Host "`n[5/5] Running test suite to verify system integrity..." -ForegroundColor Yellow
python -m pytest tests -v
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "  SETUP COMPLETE: All tests passed!" -ForegroundColor Green
    Write-Host "  Start FastAPI:   uvicorn src.api.main:app --reload --port 8000" -ForegroundColor White
    Write-Host "  Start Dashboard: streamlit run src/dashboard/app.py" -ForegroundColor White
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed or encountered warnings. Check logs." -ForegroundColor Yellow
}
