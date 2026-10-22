@echo off
rem Runs lwa_utils.py diagnostics and writes everything to diag_out\check_log.txt
cd /d "%~dp0"
if not exist diag_out mkdir diag_out
set LOG=diag_out\check_log.txt
echo ==== check %date% %time% ==== > "%LOG%"
set PY=py -3
py -3 -c "import sys" >nul 2>&1 || set PY=python
echo interpreter command: %PY% >> "%LOG%"
%PY% -c "import sys,struct;print(sys.executable, sys.version.split()[0], struct.calcsize('P')*8, 'bit')" >> "%LOG%" 2>&1
%PY% -c "import numpy, matplotlib;print('numpy', numpy.__version__, 'matplotlib', matplotlib.__version__)" >> "%LOG%" 2>&1
%PY% lwa_utils.py check >> "%LOG%" 2>&1
echo ---- ping ---- >> "%LOG%"
%PY% lwa_utils.py ping >> "%LOG%" 2>&1
echo ---- dump ---- >> "%LOG%"
%PY% lwa_utils.py dump >> "%LOG%" 2>&1
echo ==== done %time% ==== >> "%LOG%"
