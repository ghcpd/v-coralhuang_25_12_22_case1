@echo off
python -m pytest test_compatibility.py -v
if %errorlevel% neq 0 exit /b %errorlevel%