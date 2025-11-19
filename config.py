"""
Configuración del launcher
"""
import os
from pathlib import Path

# Rutas
BASE_DIR = Path(__file__).parent
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

