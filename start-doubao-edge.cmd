@echo off
rem ============================================================
rem  豆包 PPT 专用 Edge —— 带 CDP 调试端口
rem
rem  为什么需要它：
rem    豆包 PPT 是网页，没有 API。Bridge 想自动发消息、自动读回复，
rem    只能通过 CDP（Chrome DevTools Protocol）去驱动那个页面。
rem    出于安全考虑，普通 Edge 会忽略 --remote-debugging-port，
rem    所以这里用一个独立配置目录：跟你的日常 Edge 彻底隔离，
rem    互不影响 cookie 和登录。
rem
rem  用法：
rem    1. 双击本文件
rem    2. 在弹出的窗口里登录豆包（只需一次，之后 cookie 留在专用目录里）
rem    3. 不想让机器人碰它的时候，关掉那个窗口即可
rem
rem  调试端口只绑本机 127.0.0.1，外网访问不到。
rem ============================================================

setlocal
set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set "PROFILE=%LOCALAPPDATA%\DesktopAiRobot\edge-doubao"
set "PORT=9222"

if not exist "%EDGE%" (
  echo [错误] 找不到 Edge：%EDGE%
  pause
  exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

echo 启动豆包专用 Edge...
echo   调试端口 127.0.0.1:%PORT%
echo   配置目录 %PROFILE%
echo.
echo 首次使用：请在窗口里登录豆包。登录一次即可。
echo 停止自动化：直接关掉该窗口。
echo.

start "" "%EDGE%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check "https://www.doubao.com/office/ppt"

timeout /t 10 >nul
exit /b 0
