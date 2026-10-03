@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "GAME_ROOT=%REPO_ROOT%.."
set "RYUNET_ROOT=%REPO_ROOT%RyuNET-core-master"
set "TRACKER_SCORE_LOG=%REPO_ROOT%score_log.txt"

start "SDVX EA Proxy" /D "%RYUNET_ROOT%" "%ComSpec%" /k node -r "%RYUNET_ROOT%\node_modules\ts-node\register" "%REPO_ROOT%proxy\ea_proxy.ts"
start "SDVX Discord Bot" /D "%REPO_ROOT%" "%ComSpec%" /k python "%REPO_ROOT%bot.py"

endlocal
