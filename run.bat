@echo off
title BLS Italy Bot
echo --------------------------------------------------
echo           Starting BLS Italy Bot App
echo --------------------------------------------------
if not exist "env\Scripts\python.exe" (
    echo [ERROR] Virtual environment 'env' not found in the current directory!
    echo Please make sure you are running this from the project root directory where 'env' is located.
    pause
    exit /b 1
)

echo Activating environment and launching app...
env\Scripts\python.exe app.py
if %errorlevel% neq 0 (
    echo [ERROR] The application exited with code %errorlevel%.
    pause
)
