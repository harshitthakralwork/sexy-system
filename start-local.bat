@echo off
title SparkXFlow Nexus - Launcher
echo =======================================================
echo         Starting SparkXFlow Nexus Stack
echo =======================================================
echo.

cd /d "D:\SPARKXFLOWSCAPPER\sparkxflow-nexus"

echo [1/3] Checking Docker Containers (Postgres, Redis, SearXNG)...
docker start sparkx-postgres sparkx-redis sparkx-searxng sparkx-worker sparkx-beat >nul 2>&1
echo       Docker containers started!
echo.

echo [2/3] Using Docker Backend API (Port 8000)...
echo       Compose already started sparkx-api on http://localhost:8000

echo [3/3] Starting Frontend Dashboard (Port 3000)...
start "SparkX Frontend (Next.js)" cmd /k "npm --prefix frontend run dev"

echo.
echo =======================================================
echo   All services are launching!
echo   Frontend : http://localhost:3000
echo   Backend  : http://localhost:8000
echo   SearXNG  : http://localhost:8080
echo =======================================================
echo Opening browser in 5 seconds...
timeout /t 5 >nul
start http://localhost:3000/dashboard
exit

