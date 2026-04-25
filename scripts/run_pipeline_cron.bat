@echo off
REM Wrapper invoked by Windows Task Scheduler (CatandaryPipelineDaily).
REM Keeps schtasks /TR short and lets us redirect stdout+stderr cleanly.
cd /d C:\Users\Dirk\projects\catandary-trends
echo. >> data\cycle_cron.log
echo === Cron run %DATE% %TIME% === >> data\cycle_cron.log
"C:\Users\Dirk\AppData\Local\Programs\Python\Python313\python.exe" -m pipeline.run_full_cycle --batch 600 >> data\cycle_cron.log 2>&1
exit /b %ERRORLEVEL%
