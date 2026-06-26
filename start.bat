@echo off
docker rm -f karaoke 2>nul 1>nul
echo Building Karaoke App (first time takes a few minutes)...
docker build -t karaoke . || (echo. & echo Something went wrong. Send a screenshot to your brother. & pause & exit /b 1)
echo.
echo App is ready^^!
echo.
echo On this computer : http://localhost:7860
echo On your iPhone   : http://karaoke.local:7860
echo (iPhone must be on the same WiFi)
echo.
echo Close this window to stop the app.
echo.
docker run --name karaoke --rm -p 7860:7860 karaoke
