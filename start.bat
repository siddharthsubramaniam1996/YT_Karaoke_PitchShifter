@echo off
docker rm -f karaoke 2>nul 1>nul
echo Starting Karaoke App...
docker run --pull always --name karaoke --rm -p 80:80 siddharths96/karaoke
echo.
echo On this computer : http://localhost
echo On your iPhone   : http://akshaya.local
echo (iPhone must be on the same WiFi)
echo.
echo Close this window to stop the app.
