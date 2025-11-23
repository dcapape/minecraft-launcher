"""
Sistema de traducción para el launcher
"""
import locale
import json
from pathlib import Path
from typing import Dict

# Diccionarios de traducción
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "es": {
        # General
        "app_title": "[SG] LAUNCHER",
        "sign_in": "Iniciar sesión",
        "sign_out": "Cerrar sesión",
        "developer_mode": "Modo desarrollador",
        "server_manager": "Administrador de servidores",
        "launch_minecraft": "Lanzar Minecraft",
        "version": "Versión",
        "java_version": "Versión Java",
        "cancel": "Cancelar",
        "accept": "Aceptar",
        "apply": "Aplicar",
        "close": "Cerrar",
        "download": "Descargar",
        "add": "Añadir",
        "reload": "Recargar",
        
        # Messages
        "initializing_launcher": "Inicializando launcher...",
        "configuration_loaded": "Configuración cargada",
        "validating_session": "Validando sesión...",
        "active_session": "Sesión activa para: {username} ({time} restantes)",
        "versions_available": "Minecraft versions available: {count} (downloaded only)",
        "version_restored": "Versión restaurada: {version}",
        "version_selected": "Versión {version} seleccionada",
        "java_auto_selected": "Java {version} seleccionada automáticamente (requiere {required}+)",
        "java_versions_available": "Versiones de Java disponibles: {count}",
        "version_not_available": "Versión '{version}' no está disponible, seleccionando primera versión",
        "no_versions_available": "No hay versiones disponibles",
        "no_versions_found": "No se encontraron versiones de Minecraft descargadas",
        "version_downloaded": "Versión {version} descargada correctamente",
        "error_downloading_version": "Error descargando versión: {error}",
        "downloading_version": "Descargando versión: {version}",
        "installing_neoforge": "Instalando NeoForge: {version}",
        "neoforge_installed": "NeoForge {version} instalado correctamente",
        
        # Version download dialog
        "add_version_title": "Añadir Versión de Minecraft",
        "add_neoforge_title": "Añadir Versión de NeoForge",
        "loading_versions": "Cargando versiones disponibles...",
        "stable_only": "Solo versiones estables",
        "all_versions_downloaded": "Todas las versiones {type} ya están {status}",
        "versions_available_count": "{count} versiones {type} disponibles",
        "select_version": "Por favor selecciona una versión",
        "invalid_version": "Versión inválida",
        "error_determining_minecraft_path": "No se pudo determinar la ruta de Minecraft",
        "error_getting_main_window": "No se pudo obtener la ventana principal",
        
        # Custom profile dialog
        "custom_profile_title": "Perfil Personalizado",
        "hostname_or_ip": "Hostname o IP",
        "server_name": "Nombre del servidor",
        "connection_info": "Info de conexión",
        "server_description": "Descripción del servidor",
        "required_versions": "Versiones requeridas",
        "mods": "Mods",
        "shaders": "Shaders",
        "resource_packs": "Resource Packs",
        "options": "Opciones",
        "install": "Instalar",
        "profile_installed": "Perfil {name} instalado correctamente",
        "error_installing_profile": "Error instalando perfil: {error}",
        
        # Server manager
        "server_manager_title": "Administrador de Servidores",
        "server": "Servidor",
        "profile": "Perfil",
        "server_name_label": "Nombre del servidor",
        "hostname_label": "Hostname/IP",
        "api_key_label": "API Key",
        "edit_connection": "Editar conexión",
        "reload_info": "Recargar INFO",
        "json_data": "Datos JSON",
        "id": "ID",
        "name": "Nombre",
        "description": "Descripción",
        "enable_shaders": "Habilitar shaders",
        "enable_resourcepacks": "Habilitar resource packs",
        "add_mod": "Añadir mod",
        "add_shader": "Añadir shader",
        "add_resourcepack": "Añadir resource pack",
        
        # Launch messages
        "starting_minecraft": "Iniciando proceso de Minecraft...",
        "launching_version": "Lanzando Minecraft versión: {version}",
        "using_java": "Usando Java: {path}",
        "using_custom_profile": "Usando perfil custom: {path}",
        "preparing_launch": "Preparando lanzamiento...",
        "minecraft_started": "✓ Proceso de Minecraft iniciado correctamente",
        "game_should_open": "El juego debería abrirse en breve...",
        "checking_profile_updates": "Verificando actualizaciones del perfil...",
        "profile_directory": "Directorio del perfil: {path}",
        "verifying_libraries": "Verificando que todas las librerías estén descargadas...",
        "all_libraries_downloaded": "✓ Todas las librerías están descargadas",
        "verifying_java_requirements": "Verificando requisitos de Java...",
        "java_required": "Java Requerida",
        "java_required_message": "Esta versión de Minecraft requiere Java {version}.\n\nVersiones de Java disponibles: {available}\n\n¿Deseas descargar Java {version} automáticamente?",
        "java_detected": "Java detectada: versión {version}",
        "none": "Ninguna",
        "libraries_incomplete_profile_message": "El perfil no tiene todas las librerías necesarias descargadas.\n\nPor favor, reinstala el perfil o verifica que la instalación se completó correctamente.",
        
        # Asset download
        "assets_incomplete": "Assets incompletos ({valid}/{total}), descargando...",
        "downloading_asset_index": "Descargando índice de assets...",
        "downloading_assets": "Descargando assets ({current}/{total}): {name}",
        "assets_downloaded": "{downloaded} assets descargados correctamente",
        "assets_skipped": "Assets descargados: {downloaded}, saltados: {skipped}, fallidos: {failed}",
        "assets_warning": "Advertencia: No se pudieron descargar los assets, el juego puede no funcionar correctamente",
        
        # Errors
        "error": "Error",
        "warning": "Advertencia",
        "info": "Información",
        "authentication_error": "Error en la autenticación",
        "java_not_found": "No se encontró Java instalado",
        "java_required_version": "Se requiere Java {version} o superior",
        "minecraft_not_detected": "Minecraft no detectado",
        "version_not_found": "No se encontró la versión {version}",
        
        # Menu items
        "vanilla": "Vanilla",
        "neoforge": "NeoForge",
        "custom": "Custom",
        "language_changed": "Idioma cambiado",
        "developer_mode_enabled": "Modo desarrollador activado",
        "developer_mode_disabled": "Modo desarrollador desactivado",
        
        # Version Download Dialog
        "no_neoforge_versions_found": "No se encontraron versiones de NeoForge",
        "all_neoforge_versions_installed": "Todas las versiones de NeoForge ya están instaladas",
        "neoforge_versions_available": "{count} versiones de NeoForge disponibles",
        "all_versions_downloaded": "Todas las versiones {type} ya están descargadas",
        "versions_available": "{count} {type} versiones",
        "error_loading_versions": "Error cargando versiones: {error}",
        "please_select_version": "Por favor selecciona una versión",
        "could_not_determine_minecraft_path": "No se pudo determinar la ruta de Minecraft",
        "could_not_get_main_window": "No se pudo obtener la ventana principal",
        "invalid_neoforge_version": "Versión de NeoForge inválida",
        "invalid_version": "Versión inválida",
        "error_downloading": "Error descargando la versión",
        "stable_versions": "estables",
        "available_versions": "disponibles",
        
        # Custom Profile Dialog
        "install_custom_profile": "Instalar Perfil Personalizado",
        "load": "Cargar",
        "hostname_placeholder": "localhost o 192.168.1.1",
        "required_versions": "Versiones Necesarias",
        "server_name_label_text": "Nombre del servidor",
        "connection_info_label": "Info de conexión",
        "server_description_label_text": "Descripción del servidor",
        
        # Server Manager Dialog
        "add_server": "Añadir Servidor",
        "add_server_tooltip": "Añadir servidor",
        "reload_info_tooltip": "Recargar información del servidor",
        "save_api_key_tooltip": "Guardar API Key",
        "profile_id_label": "ID del perfil",
        "json_data_label": "JSON del perfil",
        "please_complete_all_fields": "Por favor, completa todos los campos",
        "api_key_cannot_be_empty": "La API Key no puede estar vacía",
        "delete_server_question": "¿Estás seguro de que quieres eliminar este servidor?",
        "please_select_server_first": "Por favor, selecciona un servidor primero.",
        "warning": "Advertencia",
        "hostname_placeholder_server": "servidormc.com o 192.168.1.1",
        "api_key_placeholder": "Tu API key del servidor",
        "api_key_saved_reload_question": "API Key guardada correctamente.\n\n¿Deseas recargar la información del servidor ahora?",
        "no_server_data_received": "No se recibieron datos del servidor",
        "shaders_folder_not_found": "No se encontró la carpeta de shaders en .minecraft",
        "mods_folder_not_found": "No se encontró la carpeta de mods en .minecraft",
        "resourcepacks_folder_not_found": "No se encontró la carpeta de resource packs en .minecraft",
        
        # Authentication Dialog
        "authentication": "Autenticación",
        "error_obtaining_auth_code": "Error: No se pudo obtener el código de autenticación",
        
        # Main Window Messages
        "session_refreshed": "Sesión refrescada exitosamente para: {username}",
        "token_invalid_refreshing": "Token inválido, intentando refrescar...",
        "no_versions_available_message": "No hay versiones disponibles",
        "version_selected_message": "Versión {version} seleccionada",
        "version_downloaded_success": "Versión {version} descargada correctamente",
        "error_loading_versions_message": "Error cargando versiones: {error}",
        "java_downloaded_success": "Java descargada correctamente: {path}",
        "error_downloading_java": "Error descargando Java: {error}",
        "processing_redirect_url": "Procesando URL de redirección...",
        "no_redirect_url_provided": "No se proporcionó URL de redirección",
        "authentication_cancelled": "Autenticación cancelada",
        "credentials_saved": "Credenciales guardadas correctamente",
        "authentication_success": "Autenticación exitosa: {username}",
        "refreshing_session": "Refrescando sesión para: {username}...",
        "error_saving_refreshed_credentials": "Error guardando credenciales refrescadas",
        "could_not_refresh_validating": "No se pudo refrescar la sesión, validando token actual...",
        "error_refreshing_validating": "Error al refrescar sesión, validando token actual...",
        "session_expired": "La sesión ha expirado para: {username}. Por favor, inicia sesión nuevamente.",
        "session_not_valid": "La sesión no es válida para: {username}. Por favor, inicia sesión nuevamente.",
        "no_valid_access_token": "No se encontró token de acceso válido",
        "error_loading_credentials": "Error cargando credenciales guardadas",
        "profile_updated": "Perfil actualizado",
        "server_added_to_multiplayer": "Servidor agregado a Multiplayer: {name}",
        "nbtlib_not_installed": "Error: nbtlib no está instalado. Instala con: pip install nbtlib",
        "error_adding_server": "Error agregando servidor: {error}",
        "refreshing_session_before_launch": "Refrescando sesión antes de lanzar...",
        "session_refreshed_success": "Sesión refrescada exitosamente",
        "session_expired_please_login": "La sesión ha expirado. Por favor, inicia sesión nuevamente.",
        "custom_profile_detected": "Perfil custom detectado: {id}",
        "checking_profile_updates": "Verificando actualizaciones del perfil...",
        "profile_directory": "Directorio del perfil: {path}",
        "verifying_libraries": "Verificando que todas las librerías estén descargadas...",
        "libraries_incomplete": "Error: Librerías incompletas, no se puede lanzar",
        "all_libraries_downloaded": "✓ Todas las librerías están descargadas",
        "verifying_java_requirements": "Verificando requisitos de Java...",
        "java_required_version": "Java requerida: versión {version}",
        "downloading_java": "Descargando Java {version}...",
        "java_downloaded": "Java {version} descargada correctamente",
        "launching_minecraft_version": "Lanzando Minecraft version: {version}",
        "using_java": "Usando Java: {path}",
        "java_download_cancelled": "Descarga de Java cancelada o falló",
        "launching_minecraft": "Lanzando Minecraft versión: {version}",
        "using_custom_profile": "Usando perfil custom: {path}",
        "preparing_launch": "Preparando lanzamiento...",
        "minecraft_started_success": "✓ Proceso de Minecraft iniciado correctamente",
        "game_should_open_soon": "El juego debería abrirse en breve...",
        "no_java_installations": "No se encontraron instalaciones de Java",
    },
    "en": {
        # General
        "app_title": "[SG] LAUNCHER",
        "sign_in": "Sign In",
        "sign_out": "Sign Out",
        "developer_mode": "Developer Mode",
        "server_manager": "Server Manager",
        "launch_minecraft": "Launch Minecraft",
        "version": "Version",
        "java_version": "Java Version",
        "cancel": "Cancel",
        "accept": "Accept",
        "apply": "Apply",
        "close": "Close",
        "download": "Download",
        "add": "Add",
        "reload": "Reload",
        
        # Messages
        "initializing_launcher": "Initializing launcher...",
        "configuration_loaded": "Configuration loaded",
        "validating_session": "Validating session...",
        "active_session": "Active session for: {username} ({time} remaining)",
        "versions_available": "Minecraft versions available: {count} (downloaded only)",
        "version_restored": "Version restored: {version}",
        "version_selected": "Version {version} selected",
        "java_auto_selected": "Java {version} automatically selected (requires {required}+)",
        "java_versions_available": "Java versions available: {count}",
        "version_not_available": "Version '{version}' not available, selecting first version",
        "no_versions_available": "No versions available",
        "no_versions_found": "No downloaded Minecraft versions found",
        "version_downloaded": "Version {version} downloaded successfully",
        "error_downloading_version": "Error downloading version: {error}",
        "downloading_version": "Downloading version: {version}",
        "installing_neoforge": "Installing NeoForge: {version}",
        "neoforge_installed": "NeoForge {version} installed successfully",
        
        # Version download dialog
        "add_version_title": "Add Minecraft Version",
        "add_neoforge_title": "Add NeoForge Version",
        "loading_versions": "Loading available versions...",
        "stable_only": "Stable versions only",
        "all_versions_downloaded": "All {type} versions are already {status}",
        "versions_available_count": "{count} {type} versions available",
        "select_version": "Please select a version",
        "invalid_version": "Invalid version",
        "error_determining_minecraft_path": "Could not determine Minecraft path",
        "error_getting_main_window": "Could not get main window",
        
        # Custom profile dialog
        "custom_profile_title": "Custom Profile",
        "hostname_or_ip": "Hostname or IP",
        "server_name": "Server Name",
        "connection_info": "Connection Info",
        "server_description": "Server Description",
        "required_versions": "Required Versions",
        "mods": "Mods",
        "shaders": "Shaders",
        "resource_packs": "Resource Packs",
        "options": "Options",
        "install": "Install",
        "profile_installed": "Profile {name} installed successfully",
        "error_installing_profile": "Error installing profile: {error}",
        
        # Server manager
        "server_manager_title": "Server Manager",
        "server": "Server",
        "profile": "Profile",
        "server_name_label": "Server Name",
        "hostname_label": "Hostname/IP",
        "api_key_label": "API Key",
        "edit_connection": "Edit Connection",
        "reload_info": "Reload INFO",
        "json_data": "JSON Data",
        "id": "ID",
        "name": "Name",
        "description": "Description",
        "enable_shaders": "Enable Shaders",
        "enable_resourcepacks": "Enable Resource Packs",
        "add_mod": "Add Mod",
        "add_shader": "Add Shader",
        "add_resourcepack": "Add Resource Pack",
        
        # Launch messages
        "starting_minecraft": "Starting Minecraft process...",
        "launching_version": "Launching Minecraft version: {version}",
        "using_java": "Using Java: {path}",
        "using_custom_profile": "Using custom profile: {path}",
        "preparing_launch": "Preparing launch...",
        "minecraft_started": "✓ Minecraft process started successfully",
        "game_should_open": "The game should open shortly...",
        "checking_profile_updates": "Checking profile updates...",
        "profile_directory": "Profile directory: {path}",
        "verifying_libraries": "Verifying all libraries are downloaded...",
        "all_libraries_downloaded": "✓ All libraries are downloaded",
        "verifying_java_requirements": "Verifying Java requirements...",
        "java_required": "Java required: version {version}",
        
        # Asset download
        "assets_incomplete": "Incomplete assets ({valid}/{total}), downloading...",
        "downloading_asset_index": "Downloading asset index...",
        "downloading_assets": "Downloading assets ({current}/{total}): {name}",
        "assets_downloaded": "{downloaded} assets downloaded successfully",
        "assets_skipped": "Assets downloaded: {downloaded}, skipped: {skipped}, failed: {failed}",
        "assets_warning": "Warning: Could not download assets, game may not work correctly",
        
        # Errors
        "error": "Error",
        "warning": "Warning",
        "info": "Information",
        "authentication_error": "Authentication error",
        "java_not_found": "Java not found",
        "java_required_version": "Java {version} or higher required",
        "minecraft_not_detected": "Minecraft not detected",
        "version_not_found": "Version {version} not found",
        
        # Menu items
        "vanilla": "Vanilla",
        "neoforge": "NeoForge",
        "custom": "Custom",
        "language_changed": "Language changed",
        "developer_mode_enabled": "Developer mode enabled",
        "developer_mode_disabled": "Developer mode disabled",
        
        # Version Download Dialog
        "no_neoforge_versions_found": "No NeoForge versions found",
        "all_neoforge_versions_installed": "All NeoForge versions are already installed",
        "neoforge_versions_available": "{count} NeoForge versions available",
        "all_versions_downloaded": "All {type} versions are already downloaded",
        "versions_available": "{count} {type} versions",
        "error_loading_versions": "Error loading versions: {error}",
        "please_select_version": "Please select a version",
        "could_not_determine_minecraft_path": "Could not determine Minecraft path",
        "could_not_get_main_window": "Could not get main window",
        "invalid_neoforge_version": "Invalid NeoForge version",
        "invalid_version": "Invalid version",
        "error_downloading": "Error downloading version",
        "stable_versions": "stable",
        "available_versions": "available",
        
        # Custom Profile Dialog
        "install_custom_profile": "Install Custom Profile",
        "load": "Load",
        "hostname_placeholder": "localhost or 192.168.1.1",
        "required_versions": "Required Versions",
        "server_name_label_text": "Server Name",
        "connection_info_label": "Connection Info",
        "server_description_label_text": "Server Description",
        
        # Server Manager Dialog
        "add_server": "Add Server",
        "add_server_tooltip": "Add server",
        "reload_info_tooltip": "Reload server information",
        "save_api_key_tooltip": "Save API Key",
        "profile_id_label": "Profile ID",
        "json_data_label": "Profile JSON",
        "please_complete_all_fields": "Please complete all fields",
        "api_key_cannot_be_empty": "API Key cannot be empty",
        "delete_server_question": "Are you sure you want to delete this server?",
        "please_select_server_first": "Please select a server first.",
        "warning": "Warning",
        "hostname_placeholder_server": "servidormc.com or 192.168.1.1",
        "api_key_placeholder": "Your server API key",
        "api_key_saved_reload_question": "API Key saved successfully.\n\nDo you want to reload server information now?",
        "no_server_data_received": "No server data received",
        "shaders_folder_not_found": "Shaders folder not found in .minecraft",
        "mods_folder_not_found": "Mods folder not found in .minecraft",
        "resourcepacks_folder_not_found": "Resource packs folder not found in .minecraft",
        
        # Authentication Dialog
        "authentication": "Authentication",
        "error_obtaining_auth_code": "Error: Could not obtain authentication code",
        
        # Main Window Messages
        "session_refreshed": "Session refreshed successfully for: {username}",
        "token_invalid_refreshing": "Invalid token, attempting to refresh...",
        "no_versions_available_message": "No versions available",
        "version_selected_message": "Version {version} selected",
        "version_downloaded_success": "Version {version} downloaded successfully",
        "error_loading_versions_message": "Error loading versions: {error}",
        "java_downloaded_success": "Java downloaded successfully: {path}",
        "error_downloading_java": "Error downloading Java: {error}",
        "processing_redirect_url": "Processing redirect URL...",
        "no_redirect_url_provided": "No redirect URL provided",
        "authentication_cancelled": "Authentication cancelled",
        "credentials_saved": "Credentials saved successfully",
        "authentication_success": "Authentication successful: {username}",
        "refreshing_session": "Refreshing session for: {username}...",
        "error_saving_refreshed_credentials": "Error saving refreshed credentials",
        "could_not_refresh_validating": "Could not refresh session, validating current token...",
        "error_refreshing_validating": "Error refreshing session, validating current token...",
        "session_expired": "Session has expired for: {username}. Please sign in again.",
        "session_not_valid": "Session is not valid for: {username}. Please sign in again.",
        "no_valid_access_token": "No valid access token found",
        "error_loading_credentials": "Error loading saved credentials",
        "profile_updated": "Profile updated",
        "server_added_to_multiplayer": "Server added to Multiplayer: {name}",
        "nbtlib_not_installed": "Error: nbtlib is not installed. Install with: pip install nbtlib",
        "error_adding_server": "Error adding server: {error}",
        "refreshing_session_before_launch": "Refreshing session before launching...",
        "session_refreshed_success": "Session refreshed successfully",
        "session_expired_please_login": "Session has expired. Please sign in again.",
        "custom_profile_detected": "Custom profile detected: {id}",
        "checking_profile_updates": "Checking profile updates...",
        "profile_directory": "Profile directory: {path}",
        "verifying_libraries": "Verifying that all libraries are downloaded...",
        "libraries_incomplete": "Error: Incomplete libraries, cannot launch",
        "all_libraries_downloaded": "✓ All libraries are downloaded",
        "verifying_java_requirements": "Verifying Java requirements...",
        "java_required_version": "Java required: version {version}",
        "downloading_java": "Downloading Java {version}...",
        "java_downloaded": "Java {version} downloaded successfully",
        "launching_minecraft_version": "Launching Minecraft version: {version}",
        "using_java": "Using Java: {path}",
        "java_download_cancelled": "Java download cancelled or failed",
        "launching_minecraft": "Launching Minecraft version: {version}",
        "using_custom_profile": "Using custom profile: {path}",
        "preparing_launch": "Preparing launch...",
        "minecraft_started_success": "✓ Minecraft process started successfully",
        "game_should_open_soon": "The game should open shortly...",
        "no_java_installations": "No Java installations found",
    }
}

# Idioma actual (se establecerá al inicializar)
_current_language = "es"

def detect_system_language() -> str:
    """Detecta el idioma del sistema"""
    try:
        # Obtener el locale del sistema
        system_locale = locale.getdefaultlocale()[0]
        if system_locale:
            # Extraer el código de idioma (ej: 'es_ES' -> 'es', 'en_US' -> 'en')
            lang_code = system_locale.split('_')[0].lower()
            if lang_code in TRANSLATIONS:
                return lang_code
    except:
        pass
    # Por defecto, español
    return "es"

def load_language_from_config() -> str:
    """Carga el idioma desde la configuración"""
    try:
        from config import CONFIG_FILE
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                lang = config.get('language')
                if lang and lang in TRANSLATIONS:
                    return lang
    except:
        pass
    # Si no hay configuración, detectar del sistema
    return detect_system_language()

def set_language(lang: str):
    """Establece el idioma actual"""
    global _current_language
    if lang in TRANSLATIONS:
        _current_language = lang
    else:
        _current_language = "es"

def get_language() -> str:
    """Obtiene el idioma actual"""
    return _current_language

def save_language_to_config(lang: str):
    """Guarda el idioma en la configuración"""
    try:
        from config import CONFIG_FILE
        config = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                config = {}
        
        config['language'] = lang
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving language to config: {e}")

def tr(key: str, **kwargs) -> str:
    """
    Traduce una clave al idioma actual
    
    Args:
        key: Clave de traducción
        **kwargs: Parámetros para formatear el string (ej: {username}, {time})
    
    Returns:
        String traducido
    """
    translation = TRANSLATIONS.get(_current_language, TRANSLATIONS["es"]).get(key, key)
    
    # Formatear el string si hay parámetros
    if kwargs:
        try:
            return translation.format(**kwargs)
        except:
            return translation
    
    return translation

# Inicializar el idioma al importar el módulo
_current_language = load_language_from_config()

