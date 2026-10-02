@echo off
pushd "%~dp0.."
if not exist "tmp\emulator\pc-settings.json" (
    echo Najpierw uruchom Uruchom-TUI.cmd.
    pause
) else (
    start "Guido PC - emulator" "output\pc\ShadokProjektory-RPi.exe" --settings "%CD%\tmp\emulator\pc-settings.json"
)
popd
