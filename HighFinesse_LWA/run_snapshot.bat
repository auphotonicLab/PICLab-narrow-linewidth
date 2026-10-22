@echo off
rem Read-only: saves what the GUI last published to diag_out\snapshot_*.csv
cd /d "%~dp0"
if not exist diag_out mkdir diag_out
set PY=py -3
py -3 -c "import sys" >nul 2>&1 || set PY=python
cd diag_out
%PY% ..\lwa_utils.py snapshot > snapshot_log.txt 2>&1
