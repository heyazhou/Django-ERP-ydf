@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "PY=%~dp0.venv\Scripts\python.exe"
set "MYSQLD=%~dp0.mysql\mysql-8.4.11-winx64\bin\mysqld.exe"
set "INI=%~dp0.mysql\my.ini"

if not exist "%PY%" (
  echo 未找到项目解释器 .venv\Scripts\python.exe
  exit /b 1
)
if not exist "%MYSQLD%" (
  echo 未找到项目数据库程序
  exit /b 1
)

call :dbup
if errorlevel 1 (
  echo 正在启动数据库 127.0.0.1:3307
  start "项目数据库" /MIN "%MYSQLD%" --defaults-file="%INI%"
)
set N=0
:waitdb
call :dbup
if not errorlevel 1 goto dbok
set /a N+=1
if !N! GEQ 40 (
  echo 数据库没有在 40 秒内启动，请查看 .mysql\error.log
  exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto waitdb
:dbok
echo 数据库已就绪
echo 网站 http://127.0.0.1:8000    后台 /admin/    手机 /m/
echo 登录账号 admin    密码 admin
"%PY%" manage.py runserver 127.0.0.1:8000
exit /b %ERRORLEVEL%

:dbup
"%PY%" -c "import socket;s=socket.socket();s.settimeout(0.5);r=s.connect_ex(('127.0.0.1',3307));s.close();raise SystemExit(0 if r==0 else 1)"
exit /b %ERRORLEVEL%
