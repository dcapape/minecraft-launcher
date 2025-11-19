"""
Configuración del launcher
"""
import os
import sys
from pathlib import Path

# Rutas
BASE_DIR = Path(__file__).parent

# Determinar si estamos ejecutando desde un ejecutable compilado
if getattr(sys, 'frozen', False):
    # Ejecutándose desde un ejecutable compilado
    # Usar directorio de datos de usuario
    if os.name == 'nt':  # Windows
        appdata = os.getenv('APPDATA')
        DATA_DIR = Path(appdata) / "MinecraftLauncher"
    elif sys.platform == 'darwin':  # macOS
        DATA_DIR = Path.home() / "Library" / "Application Support" / "MinecraftLauncher"
    else:  # Linux
        DATA_DIR = Path.home() / ".minecraft-launcher"
    
    # Crear directorio si no existe
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    CREDENTIALS_FILE = DATA_DIR / "credentials.json"
    KEY_FILE = DATA_DIR / "key.key"
    CONFIG_FILE = DATA_DIR / "launcher_config.json"
else:
    # Ejecutándose desde código fuente
    CREDENTIALS_FILE = BASE_DIR / "credentials.json"
    KEY_FILE = BASE_DIR / "key.key"
    CONFIG_FILE = BASE_DIR / "launcher_config.json"

# Configuración de autenticación
MICROSOFT_CLIENT_ID = "00000000402b5328"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"

# Configuración de Minecraft
DEFAULT_MEMORY = "2G"
MIN_MEMORY = "1G"

# Configuración de la UI
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
WINDOW_TITLE = "Launcher de Minecraft Java"

