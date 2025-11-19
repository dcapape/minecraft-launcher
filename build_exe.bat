@echo off
echo Building Minecraft Launcher executable...
echo.

REM Verificar que PyInstaller esté instalado
python3 -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller no está instalado. Instalando...
    python3 -m pip install pyinstaller
)

echo.
echo Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo Generando ejecutable con PyInstaller...
python3 -m PyInstaller launcher.spec

echo.
if exist dist\MinecraftLauncher.exe (
    echo.
    echo ========================================
    echo ¡Ejecutable generado exitosamente!
    echo ========================================
    echo.
    echo El ejecutable se encuentra en: dist\MinecraftLauncher.exe
    echo.
) else (
    echo.
    echo ========================================
    echo Error al generar el ejecutable
    echo ========================================
    echo.
    echo Revisa los mensajes de error arriba.
    echo.
)

pause

