@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "GAME_ROOT=%REPO_ROOT%.."
set "RYUNET_ROOT=%REPO_ROOT%RyuNET-core-master"
set "TRACKER_SCORE_LOG=%REPO_ROOT%score_log.txt"
set "TRACKER_CUSTOM_CHARTS_ROOT=disabled"
pushd "%REPO_ROOT%"
for /f "delims=" %%P in ('python -c "from pathlib import Path; from config import CUSTOM_CHARTS_ROOT; print(Path(CUSTOM_CHARTS_ROOT).resolve() if CUSTOM_CHARTS_ROOT is not None else 'disabled')"') do set "TRACKER_CUSTOM_CHARTS_ROOT=%%P"
popd

start "SDVX EA Proxy" /D "%RYUNET_ROOT%" "%ComSpec%" /k node -r "%RYUNET_ROOT%\node_modules\ts-node\register" "%REPO_ROOT%proxy\ea_proxy.ts"
start "SDVX Discord Bot" /D "%REPO_ROOT%" "%ComSpec%" /k python "%REPO_ROOT%bot.py"

endlocal
