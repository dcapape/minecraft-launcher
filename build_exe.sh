#!/bin/bash

echo "Building Minecraft Launcher executable..."
echo ""

# Verificar que PyInstaller esté instalado
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller no está instalado. Instalando..."
    pip install pyinstaller
fi

echo ""
echo "Limpiando builds anteriores..."
rm -rf build dist

echo ""
echo "Generando ejecutable con PyInstaller..."
pyinstaller launcher.spec

echo ""
if [ -f "dist/MinecraftLauncher" ]; then
    echo ""
    echo "========================================"
    echo "¡Ejecutable generado exitosamente!"
    echo "========================================"
    echo ""
    echo "El ejecutable se encuentra en: dist/MinecraftLauncher"
    echo ""
else
    echo ""
    echo "========================================"
    echo "Error al generar el ejecutable"
    echo "========================================"
    echo ""
    echo "Revisa los mensajes de error arriba."
    echo ""
fi

