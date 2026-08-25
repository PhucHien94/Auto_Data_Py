@echo off
start "" code --user-data-dir "%USERPROFILE%\.vscode-default" "D:\Testing\Project\2026_MartRenew\Auto_Data_Py"
timeout /t 2 >nul
start "" code --password-store="basic" --user-data-dir "%USERPROFILE%\.vscode-company" "D:\Testing\Project\2026_MartRenew\Auto_Data_Py"