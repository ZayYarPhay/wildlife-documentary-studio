@echo off
setlocal EnableExtensions
title Wildlife Documentary Studio Launcher

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "APP_URL=http://localhost:3200"

echo.
echo ============================================================
echo   Wildlife Documentary Studio
echo ============================================================
echo.

if not exist "%BACKEND_DIR%\app\main.py" goto :bad_root
if not exist "%FRONTEND_DIR%\package.json" goto :bad_root

set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto :python_ready
where python >nul 2>nul
if errorlevel 1 goto :missing_python
set "PYTHON_EXE=python"

:python_ready
where npm.cmd >nul 2>nul
if errorlevel 1 goto :missing_node

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [WARNING] FFmpeg was not found in PATH.
  echo           The app can open, but video generation and final export will fail.
  echo.
)

echo [1/5] Checking backend dependencies...
"%PYTHON_EXE%" -c "import fastapi, sqlalchemy, alembic, PIL, pydantic_settings, multipart" >nul 2>nul
if not errorlevel 1 goto :backend_dependencies_ready
echo       Installing backend dependencies for the first run...
"%PYTHON_EXE%" -m pip install -r "%BACKEND_DIR%\requirements-dev.txt"
if errorlevel 1 goto :backend_install_failed

:backend_dependencies_ready
echo [2/5] Checking frontend dependencies...
if exist "%FRONTEND_DIR%\node_modules\next\package.json" goto :frontend_dependencies_ready
echo       Installing frontend dependencies for the first run...
pushd "%FRONTEND_DIR%"
call npm.cmd install
set "NPM_INSTALL_EXIT=%ERRORLEVEL%"
popd
if not "%NPM_INSTALL_EXIT%"=="0" goto :frontend_install_failed

:frontend_dependencies_ready
echo [3/5] Preparing local configuration and database...
if not exist "%BACKEND_DIR%\.env" (
  copy /Y "%ROOT%.env.example" "%BACKEND_DIR%\.env" >nul
  echo       Created backend\.env from .env.example
)
pushd "%BACKEND_DIR%"
"%PYTHON_EXE%" -m alembic upgrade head
set "MIGRATION_EXIT=%ERRORLEVEL%"
popd
if not "%MIGRATION_EXIT%"=="0" goto :migration_failed

if /I "%~1"=="--check" (
  echo [CHECK] Launcher prerequisites and database migration passed.
  exit /b 0
)

echo [4/5] Starting backend and frontend...
powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
if errorlevel 1 (
  start "WDS Backend" /min /D "%BACKEND_DIR%" cmd /k ""%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
) else (
  echo       Backend is already running on port 8000.
)

powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3200' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; exit 1" >nul 2>nul
if errorlevel 1 (
  start "WDS Frontend" /min /D "%FRONTEND_DIR%" cmd /k "npm.cmd run dev -- -p 3200"
) else (
  echo       Frontend is already running on port 3200.
)

echo [5/5] Waiting for the app to become ready...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(60); do { try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3200' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Milliseconds 750 } while ((Get-Date) -lt $deadline); exit 1" >nul 2>nul
if errorlevel 1 goto :startup_timeout

echo.
echo App is ready: %APP_URL%
echo Backend API: http://localhost:8000/docs
echo.
echo The backend and frontend are running in separate minimized windows.
echo Close those two windows when you want to stop the app.
start "" "%APP_URL%"
timeout /t 3 /nobreak >nul
exit /b 0

:bad_root
echo [ERROR] RunWDS.bat must stay in the wildlife-documentary-studio folder.
goto :failed

:missing_python
echo [ERROR] Python was not found. Install Python 3.12 or newer and enable PATH.
goto :failed

:missing_node
echo [ERROR] Node.js/npm was not found. Install a current Node.js LTS release.
goto :failed

:backend_install_failed
echo [ERROR] Backend dependency installation failed.
goto :failed

:frontend_install_failed
echo [ERROR] Frontend dependency installation failed.
goto :failed

:migration_failed
echo [ERROR] Database migration failed. Review the message above.
goto :failed

:startup_timeout
echo [ERROR] The frontend did not become ready within 60 seconds.
echo         Check the WDS Backend and WDS Frontend windows for details.
goto :failed

:failed
echo.
pause
exit /b 1
