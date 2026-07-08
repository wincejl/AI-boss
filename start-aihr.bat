@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" -Url "http://localhost:3000/agent/dashboard?page=dashboard"
