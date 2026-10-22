@echo off
rem Unattended test of lwa_measurement.py: PLAN as in the file, results in diag_out\<label>
cd /d "%~dp0"
if not exist diag_out mkdir diag_out
set PY=py -3
py -3 -c "import sys" >nul 2>&1 || set PY=python
set LWA_SAVE_FOLDER=%~dp0diag_out
set LWA_LABEL=test_run
set LWA_SHOW_PLOTS=0
set MPLBACKEND=Agg
%PY% lwa_measurement.py > diag_out\measurement_console.txt 2>&1
echo exit code %errorlevel% >> diag_out\measurement_console.txt
