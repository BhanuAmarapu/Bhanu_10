@echo off
title CloudDedup Services Runner
echo ============================================================
echo Starting Hybrid ML-CNS Deduplication Services...
echo ============================================================

:: 1. Start ML Service in a new window
echo [1/3] Starting ML Service (FastAPI) on port 8000...
start "ML Service (FastAPI)" cmd /k "cd ml-service && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

:: 2. Start Backend Flask Server in a new window
echo [2/3] Starting Backend Server (Flask) on port 5000...
start "Backend Server (Flask)" cmd /k "cd backend && python run.py"

:: 3. Start Frontend Vite Server in a new window (Commented out because Flask serves templates directly)
:: echo [3/3] Starting Frontend React Server (Vite) on port 3000...
:: start "Frontend (Vite)" cmd /k "cd frontend && npm run dev"

echo ============================================================
echo All services launched!
echo  - Web Application: http://localhost:5000
echo  - ML Service: http://127.0.0.1:8000
echo ============================================================
pause

