"""
Launcher principal de Minecraft Java Edition
"""
import sys
import time
import platform
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QMessageBox, QProgressBar, QDialog, QDialogButtonBox,
                             QComboBox, QMenu, QGraphicsOpacityEffect, QListWidget, QListWidgetItem,
                             QCheckBox, QGroupBox, QScrollArea, QInputDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QPalette, QRegion, QPainterPath
from PyQt5.QtCore import QRect
import requests
from io import BytesIO
from typing import Optional
import os
import json
from java_downloader import JavaDownloader
from PyQt5.QtWebEngineWidgets import QWebEngineView
import webbrowser
import urllib.parse
import re
from auth_manager import AuthManager
from credential_storage import CredentialStorage
from minecraft_launcher import MinecraftLauncher
from server_manager import ServerManagerDialog, fetch_profiles_json

class LoadVersionsThread(QThread):
    """Thread para cargar versiones de Minecraft sin bloquear la UI"""
    finished = pyqtSignal(list)  # lista de versiones
    error = pyqtSignal(str)
    
    def __init__(self, minecraft_launcher):
        super().__init__()
        self.minecraft_launcher = minecraft_launcher
    
    def run(self):
        try:
            # Usar strict_check=False para incluir versiones recién descargadas (solo con JSON y JAR)
            versions = self.minecraft_launcher.get_available_versions(only_downloaded=True, strict_check=False)
            self.finished.emit(versions)
        except Exception as e:
            self.error.emit(str(e))

class JavaDownloadThread(QThread):
    """Thread para descargar Java sin bloquear la UI"""
    progress = pyqtSignal(int, int)  # descargado, total
    finished = pyqtSignal(str)  # ruta al ejecutable
    error = pyqtSignal(str)
    message = pyqtSignal(str)
    
    def __init__(self, downloader, java_version):
        super().__init__()
        self.downloader = downloader
        self.java_version = java_version
    
    def run(self):
        try:
            def progress_callback(downloaded, total):
                self.progress.emit(downloaded, total)
            
            self.message.emit(f"Descargando Java {self.java_version}...")
            java_path = self.downloader.download_java(self.java_version, progress_callback)
            
            if java_path:
                self.finished.emit(java_path)
            else:
                self.error.emit("No se pudo descargar Java")
        except Exception as e:
            self.error.emit(str(e))

class LoadVersionManifestThread(QThread):
    """Thread para cargar el manifest de versiones desde Mojang"""
    finished = pyqtSignal(dict)  # manifest completo
    error = pyqtSignal(str)
    
    def run(self):
        try:
            response = requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=30)
            response.raise_for_status()
            manifest = response.json()
            self.finished.emit(manifest)
        except Exception as e:
            self.error.emit(str(e))

class DownloadVersionThread(QThread):
    """Thread para descargar una versión de Minecraft"""
    progress = pyqtSignal(int, int, str)  # descargado, total, mensaje
    finished = pyqtSignal(str)  # version_id
    error = pyqtSignal(str)
    
    def __init__(self, version_id, version_url, minecraft_path):
        super().__init__()
        self.version_id = version_id
        self.version_url = version_url
        self.minecraft_path = minecraft_path
        self.system = platform.system()
    
    def _should_include_library(self, library):
        """Verifica si una librería debe incluirse según las reglas del OS"""
        if "rules" not in library:
            return True
        
        for rule in library.get("rules", []):
            action = rule.get("action", "allow")
            if "os" in rule:
                os_rule = rule["os"]
                os_name = os_rule.get("name", "").lower()
                current_os = self.system.lower()
                
                # Mapear nombres de OS
                if current_os == "windows":
                    current_os = "windows"
                elif current_os == "darwin":
                    current_os = "osx"
                elif current_os == "linux":
                    current_os = "linux"
                
                if os_name and os_name != current_os:
                    if action == "allow":
                        return False
                    continue
            
            if action == "disallow":
                return False
        
        return True
    
    def _maven_name_to_path(self, name):
        """Convierte un nombre Maven (group:artifact:version) a ruta de archivo"""
        parts = name.split(':')
        if len(parts) < 3:
            return None
        
        group_id = parts[0].replace('.', '/')
        artifact_id = parts[1]
        version = parts[2]
        
        # Construir ruta: group/artifact/version/artifact-version.jar
        path = f"{group_id}/{artifact_id}/{version}/{artifact_id}-{version}.jar"
        return path
    
    def _download_library(self, library, libraries_dir, progress_base, progress_max):
        """Descarga una librería individual"""
        # Verificar reglas
        if not self._should_include_library(library):
            return True  # Librería excluida por reglas, no es un error
        
        # Obtener información de descarga
        downloads = library.get("downloads", {})
        artifact = downloads.get("artifact")
        
        if not artifact:
            # Si no hay artifact en downloads, intentar construir desde name
            lib_name = library.get("name", "")
            if not lib_name:
                return True  # No hay información de descarga, saltar
            
            # Construir path desde name
            lib_path = self._maven_name_to_path(lib_name)
            if not lib_path:
                return True  # No se pudo construir path, saltar
            
            # Verificar si ya existe
            full_path = os.path.join(libraries_dir, lib_path)
            if os.path.exists(full_path):
                return True  # Ya existe, no descargar
            
            # No hay URL disponible, no podemos descargarla
            return True  # Saltar librerías sin URL
        
        # Obtener URL y path
        lib_url = artifact.get("url")
        lib_path = artifact.get("path")
        
        if not lib_url or not lib_path:
            return True  # No hay URL o path, saltar
        
        # Verificar si ya existe
        full_path = os.path.join(libraries_dir, lib_path)
        if os.path.exists(full_path):
            return True  # Ya existe, no descargar
        
        # Crear directorio si no existe
        lib_dir = os.path.dirname(full_path)
        os.makedirs(lib_dir, exist_ok=True)
        
        # Descargar la librería
        try:
            response = requests.get(lib_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            return True
        except Exception as e:
            print(f"[WARN] Error descargando librería {lib_path}: {e}")
            # Si falla, eliminar archivo parcial
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except:
                    pass
            return False  # Error al descargar
    
    def run(self):
        try:
            # Paso 1: Descargar el JSON de la versión
            self.progress.emit(0, 100, f"Descargando JSON de {self.version_id}...")
            response = requests.get(self.version_url, timeout=30)
            response.raise_for_status()
            version_json = response.json()
            
            # Paso 2: Crear directorio de la versión
            version_dir = os.path.join(self.minecraft_path, "versions", self.version_id)
            os.makedirs(version_dir, exist_ok=True)
            
            # Paso 3: Guardar el JSON
            json_path = os.path.join(version_dir, f"{self.version_id}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(version_json, f, indent=2)
            
            self.progress.emit(5, 100, f"JSON guardado. Descargando client.jar...")
            
            # Paso 4: Descargar el client.jar
            downloads = version_json.get("downloads", {})
            client_info = downloads.get("client")
            if not client_info:
                self.error.emit("No se encontró información del client.jar en el JSON")
                return
            
            jar_url = client_info.get("url")
            if not jar_url:
                self.error.emit("No se encontró URL del client.jar")
                return
            
            jar_path = os.path.join(version_dir, f"{self.version_id}.jar")
            
            # Descargar el JAR con progreso (5-30%)
            response = requests.get(jar_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(jar_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 25) + 5  # 5-30%
                            self.progress.emit(percent, 100, f"Descargando client.jar: {downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB")
            
            self.progress.emit(30, 100, f"Client.jar descargado. Descargando librerías...")
            
            # Paso 5: Descargar todas las librerías
            libraries_dir = os.path.join(self.minecraft_path, "libraries")
            os.makedirs(libraries_dir, exist_ok=True)
            
            libraries = version_json.get("libraries", [])
            total_libraries = len(libraries)
            libraries_downloaded = 0
            libraries_skipped = 0
            libraries_errors = 0
            
            for idx, library in enumerate(libraries):
                # Actualizar progreso (30-95%)
                progress_percent = 30 + int((idx / total_libraries) * 65) if total_libraries > 0 else 30
                lib_name = library.get("name", "desconocida")
                self.progress.emit(progress_percent, 100, f"Descargando librerías ({idx + 1}/{total_libraries}): {lib_name.split(':')[-2] if ':' in lib_name else lib_name}")
                
                result = self._download_library(library, libraries_dir, 30, 95)
                if result:
                    libraries_downloaded += 1
                else:
                    libraries_errors += 1
            
            self.progress.emit(100, 100, f"Descarga completada ({libraries_downloaded} librerías)")
            self.finished.emit(self.version_id)
            
        except Exception as e:
            self.error.emit(str(e))

class AuthThread(QThread):
    """Thread para realizar autenticación sin bloquear la UI"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    message = pyqtSignal(str)
    need_redirect_url = pyqtSignal(str)  # Emite la URL de autorización
    
    def __init__(self, auth_manager):
        super().__init__()
        self.auth_manager = auth_manager
        self.redirect_url = None
    
    def set_redirect_url(self, url: str):
        """Establece la URL de redirección para completar la autenticación"""
        self.redirect_url = url
    
    def run(self):
        try:
            if self.redirect_url:
                # Paso 2: Completar autenticación con la URL de redirección
                self.message.emit("Intercambiando código por token...")
                credentials = self.auth_manager.authenticate(self.redirect_url)
                if credentials:
                    self.finished.emit(credentials)
                else:
                    self.error.emit("Error en la autenticación")
            else:
                # Paso 1: Obtener URL de autorización
                self.message.emit("Iniciando autenticación...")
                auth_result = self.auth_manager.authenticate()
                if not auth_result or "auth_url" not in auth_result:
                    self.error.emit("Error obteniendo URL de autorización")
                    return
                
                auth_url = auth_result["auth_url"]
                self.need_redirect_url.emit(auth_url)
        except Exception as e:
            self.error.emit(str(e))

class RedirectUrlDialog(QDialog):
    """Diálogo con navegador embebido para autenticación"""
    redirect_captured = pyqtSignal(str)  # Emite cuando se captura la URL de redirección
    
    def __init__(self, auth_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Autenticación")
        
        # Ventana sin barra de título (frameless) e independiente
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Tamaño fijo
        self.resize(800, 600)
        self.redirect_url = None
        
        # Centrar en la pantalla donde está la ventana principal
        self._center_on_parent_screen(parent)
        
        # Widget central con estilo gaming
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 5, 20, 5)
        layout.setSpacing(10)
        
        # Barra de título personalizada
        title_bar = TitleBar(self)
        title_bar.setFixedHeight(35)
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(5)
        title_bar.setLayout(title_bar_layout)
        
        # Título
        title = QLabel("Autenticación")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_bar_layout.addWidget(title, 1)
        
        # Botones de ventana
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.reject)
        title_bar_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)
        
        # Navegador embebido
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl(auth_url))
        
        # Interceptar cambios de URL para capturar la redirección
        self.web_view.urlChanged.connect(self.on_url_changed)
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        layout.addWidget(self.web_view)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setVisible(False)
        button_layout.addWidget(self.status_label)
        
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
        
        # Layout principal del diálogo
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(central_widget)
        self.setLayout(main_layout)
        
        # Aplicar estilos gaming morados
        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
            #centralWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border-radius: 15px;
                border: 2px solid #8b5cf6;
            }
            #titleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2d1b4e, stop:1 #1a0d2e);
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
                border-bottom: 1px solid #8b5cf6;
            }
            QLabel {
                color: #e9d5ff;
                background: transparent;
            }
            QLabel#titleLabel {
                color: #c084fc;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
                border: 2px solid #a78bfa;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5b21b6, stop:1 #4c1d95);
            }
            QPushButton#closeButton {
                background: #dc2626;
                border: 1px solid #ef4444;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#closeButton:hover {
                background: #ef4444;
                border: 1px solid #f87171;
            }
            QPushButton#minimizeButton {
                background: #6b7280;
                border: 1px solid #9ca3af;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#minimizeButton:hover {
                background: #9ca3af;
                border: 1px solid #d1d5db;
            }
            QWebEngineView {
                background: #1a0d2e;
                border-radius: 8px;
            }
        """)
    
    def on_url_changed(self, url):
        """Se llama cuando cambia la URL del navegador"""
        url_str = url.toString()
        
        # Verificar si es la URL de redirección (contiene el código de autorización)
        if "oauth20_desktop.srf" in url_str:
            parsed = urllib.parse.urlparse(url_str)
            params = urllib.parse.parse_qs(parsed.query)
            
            # Si tiene el parámetro 'code', es la redirección exitosa
            if "code" in params:
                self.redirect_url = url_str
                # Cerrar el diálogo automáticamente después de un breve delay
                QApplication.processEvents()
                self.accept()
            elif "error" in params:
                # Error en la autenticación
                error = params.get("error", ["Error desconocido"])[0]
                error_desc = params.get("error_description", [""])[0]
                self.status_label.setText(f"Error: {error}")
                self.status_label.setStyleSheet("color: #fca5a5; font-weight: bold;")
                self.status_label.setVisible(True)
            else:
                # URL de redirección sin código (puede ser una página intermedia)
                # Intentar leer el código desde el contenido de la página
                self.web_view.page().toPlainText(self._check_page_content)
    
    def _check_page_content(self, content):
        """Verifica el contenido de la página en busca del código"""
        # Buscar el código en el contenido HTML/JavaScript
        # A veces Microsoft lo incluye en el HTML
        code_match = re.search(r'code=([^&\s"\']+)', content)
        if code_match:
            code = code_match.group(1)
            # Reconstruir la URL con el código
            current_url = self.web_view.url().toString()
            if "?" in current_url:
                self.redirect_url = f"{current_url.split('?')[0]}?code={code}"
            else:
                self.redirect_url = f"{current_url}?code={code}"
            QApplication.processEvents()
            self.accept()
        elif "removed" in self.web_view.url().toString():
            self.status_label.setText("Error: No se pudo obtener el código de autenticación")
            self.status_label.setStyleSheet("color: #fca5a5; font-weight: bold;")
            self.status_label.setVisible(True)
    
    def on_load_finished(self, success):
        """Se llama cuando termina de cargar una página"""
        if success:
            current_url = self.web_view.url().toString()
            if "oauth20_desktop.srf" in current_url:
                # Ya estamos en la página de redirección
                self.on_url_changed(self.web_view.url())
    
    def _center_on_parent_screen(self, parent):
        """Centra la ventana en la pantalla donde está la ventana principal"""
        if parent:
            # Obtener la geometría de la ventana principal
            parent_geometry = parent.geometry()
            parent_center = parent_geometry.center()
            
            # Calcular la posición para centrar esta ventana
            dialog_geometry = self.frameGeometry()
            dialog_geometry.moveCenter(parent_center)
            self.move(dialog_geometry.topLeft())
        else:
            # Si no hay parent, centrar en la pantalla principal
            from PyQt5.QtWidgets import QDesktopWidget
            screen = QApplication.desktop().screenGeometry()
            center_point = screen.center()
            frame_geometry = self.frameGeometry()
            frame_geometry.moveCenter(center_point)
            self.move(frame_geometry.topLeft())
    
    def get_redirect_url(self):
        return self.redirect_url

class VersionDownloadDialog(QDialog):
    """Diálogo para seleccionar y descargar versiones de Minecraft"""
    
    def __init__(self, parent=None, minecraft_launcher=None):
        super().__init__(parent)
        self.minecraft_launcher = minecraft_launcher
        self.selected_version = None
        self.manifest_thread = None
        self.download_thread = None
        
        self.setWindowTitle("Añadir Versión")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(600, 500)
        self._center_on_parent_screen(parent)
        
        # Widget central
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 5, 20, 5)
        layout.setSpacing(10)
        
        # Barra de título
        title_bar = TitleBar(self)
        title_bar.setFixedHeight(35)
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(5)
        title_bar.setLayout(title_bar_layout)
        
        title = QLabel("Añadir Versión de Minecraft")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_bar_layout.addWidget(title, 1)
        
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.reject)
        title_bar_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)
        
        # Label de estado
        self.status_label = QLabel("Cargando versiones disponibles...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # ListWidget de versiones (en vez de ComboBox)
        self.version_list = QListWidget()
        self.version_list.setEnabled(False)
        self.version_list.setFont(self.version_list.font())  # Preparar para cambiar fuente
        font = self.version_list.font()
        font.setPointSize(font.pointSize() + 2)  # Aumentar fuente en 2 puntos
        self.version_list.setFont(font)
        layout.addWidget(self.version_list)
        
        # Checkbox para filtrar solo versiones estables
        self.stable_only_checkbox = QCheckBox("Solo versiones estables")
        self.stable_only_checkbox.setChecked(True)  # Marcado por defecto
        self.stable_only_checkbox.setStyleSheet("""
            QCheckBox {
                color: #e9d5ff;
                font-size: 12px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #6d28d9;
                border-radius: 3px;
                background: #1a0d2e;
            }
            QCheckBox::indicator:checked {
                background: #7c3aed;
                border-color: #8b5cf6;
            }
            QCheckBox::indicator:hover {
                border-color: #8b5cf6;
            }
        """)
        self.stable_only_checkbox.stateChanged.connect(self.on_filter_changed)
        layout.addWidget(self.stable_only_checkbox)
        
        # Guardar el manifest completo para poder filtrar
        self.full_manifest = None
        
        # Botones
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        self.download_button = QPushButton("Descargar")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.start_download)
        button_layout.addWidget(self.download_button)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(central_widget)
        self.setLayout(main_layout)
        
        # Aplicar estilos (mismo que RedirectUrlDialog)
        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
            #centralWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border-radius: 15px;
                border: 2px solid #8b5cf6;
            }
            #titleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2d1b4e, stop:1 #1a0d2e);
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
                border-bottom: 1px solid #8b5cf6;
            }
            QLabel {
                color: #e9d5ff;
                background: transparent;
            }
            QLabel#titleLabel {
                color: #c084fc;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
                border: 2px solid #a78bfa;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5b21b6, stop:1 #4c1d95);
            }
            QPushButton:disabled {
                background: #3f3f3f;
                color: #888888;
                border: 2px solid #555555;
            }
            QPushButton#closeButton {
                background: #dc2626;
                border: 1px solid #ef4444;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#closeButton:hover {
                background: #ef4444;
                border: 1px solid #f87171;
            }
            QPushButton#minimizeButton {
                background: #6b7280;
                border: 1px solid #9ca3af;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#minimizeButton:hover {
                background: #9ca3af;
                border: 1px solid #d1d5db;
            }
            QListWidget {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget:hover {
                border: 2px solid #8b5cf6;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3f3f3f;
            }
            QListWidget::item:selected {
                background: #7c3aed;
                color: white;
            }
            QListWidget::item:hover {
                background: #6d28d9;
            }
        """)
        
        # Cargar manifest
        self.load_manifest()
    
    def _center_on_parent_screen(self, parent):
        """Centra la ventana en la pantalla donde está la ventana principal"""
        if parent:
            parent_geometry = parent.geometry()
            parent_center = parent_geometry.center()
            dialog_geometry = self.frameGeometry()
            dialog_geometry.moveCenter(parent_center)
            self.move(dialog_geometry.topLeft())
        else:
            from PyQt5.QtWidgets import QDesktopWidget
            screen = QApplication.desktop().screenGeometry()
            center_point = screen.center()
            frame_geometry = self.frameGeometry()
            frame_geometry.moveCenter(center_point)
            self.move(frame_geometry.topLeft())
    
    def load_manifest(self):
        """Carga el manifest de versiones desde Mojang"""
        self.manifest_thread = LoadVersionManifestThread()
        self.manifest_thread.finished.connect(self.on_manifest_loaded)
        self.manifest_thread.error.connect(self.on_manifest_error)
        self.manifest_thread.start()
    
    def on_manifest_loaded(self, manifest):
        """Se llama cuando se carga el manifest"""
        # Guardar el manifest completo para poder filtrar después
        self.full_manifest = manifest
        
        # Aplicar filtro inicial
        self._apply_version_filter()
    
    def _apply_version_filter(self):
        """Aplica el filtro de versiones según el checkbox"""
        if not self.full_manifest:
            return
        
        # Obtener versiones ya descargadas
        downloaded_versions = set()
        if self.minecraft_launcher:
            try:
                downloaded = self.minecraft_launcher.get_available_versions(only_downloaded=True)
                downloaded_versions = set(downloaded)
            except:
                pass
        
        # Filtrar versiones no descargadas
        versions = self.full_manifest.get("versions", [])
        available_versions = []
        for version in versions:
            version_id = version.get("id")
            if version_id and version_id not in downloaded_versions:
                # Aplicar filtro de versiones estables si el checkbox está marcado
                if self.stable_only_checkbox.isChecked():
                    version_type = version.get("type", "release")
                    # Solo incluir versiones de tipo "release" (estables)
                    if version_type == "release":
                        available_versions.append(version)
                else:
                    # Incluir todas las versiones (release, snapshot, old_beta, old_alpha, etc.)
                    available_versions.append(version)
        
        if not available_versions:
            filter_text = "estables" if self.stable_only_checkbox.isChecked() else "disponibles"
            self.status_label.setText(f"Todas las versiones {filter_text} ya están descargadas")
            self.status_label.setStyleSheet("color: #fca5a5;")
            self.version_list.clear()
            self.version_list.setEnabled(False)
            self.download_button.setEnabled(False)
            return
        
        # Ordenar por fecha (más recientes primero)
        available_versions.sort(key=lambda v: v.get("releaseTime", ""), reverse=True)
        
        # Agregar a la lista
        self.version_list.clear()
        for version in available_versions:
            version_id = version.get("id")
            version_type = version.get("type", "release")
            display_name = f"{version_id} ({version_type})"
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, version)  # Guardar datos de la versión
            self.version_list.addItem(item)
        
        self.version_list.setEnabled(True)
        self.download_button.setEnabled(True)
        filter_text = "estables" if self.stable_only_checkbox.isChecked() else "disponibles"
        self.status_label.setText(f"{len(available_versions)} versiones {filter_text}")
        self.status_label.setStyleSheet("color: #86efac;")
    
    def on_filter_changed(self, state):
        """Se llama cuando cambia el estado del checkbox de filtro"""
        print(f"[INFO] Filtro de versiones estables: {'activado' if state == Qt.Checked else 'desactivado'}")
        self._apply_version_filter()
    
    def on_manifest_error(self, error):
        """Se llama cuando hay un error cargando el manifest"""
        self.status_label.setText(f"Error cargando versiones: {error}")
        self.status_label.setStyleSheet("color: #fca5a5;")
    
    def start_download(self):
        """Inicia la descarga de la versión seleccionada"""
        current_item = self.version_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Error", "Por favor selecciona una versión")
            return
        
        version_data = current_item.data(Qt.UserRole)
        if not version_data:
            return
        
        version_id = version_data.get("id")
        version_url = version_data.get("url")
        
        if not version_id or not version_url:
            QMessageBox.warning(self, "Error", "Versión inválida")
            return
        
        print(f"[INFO] Iniciando descarga de versión: {version_id}")
        
        # Iniciar descarga ANTES de cerrar el diálogo
        minecraft_path = self.minecraft_launcher.minecraft_path if self.minecraft_launcher else None
        if not minecraft_path:
            QMessageBox.warning(self, "Error", "No se pudo determinar la ruta de Minecraft")
            return
        
        # Crear el thread ANTES de cerrar el diálogo
        parent = self.parent()
        if not parent:
            QMessageBox.warning(self, "Error", "No se pudo obtener la ventana principal")
            return
        
        # Crear el thread con el parent como padre para que no se destruya
        self.download_thread = DownloadVersionThread(version_id, version_url, minecraft_path)
        self.download_thread.setParent(parent)  # Establecer parent para que no se destruya
        
        # Conectar señales al parent (LauncherWindow) en lugar del diálogo
        print(f"[INFO] Conectando señales del thread al parent")
        self.download_thread.progress.connect(parent.on_version_download_progress)
        self.download_thread.finished.connect(parent.on_version_download_finished)
        self.download_thread.error.connect(parent.on_version_download_error)
        
        # Guardar referencia en el parent para que no se destruya
        if hasattr(parent, 'version_download_thread'):
            # Si hay un thread anterior, esperar a que termine o cancelarlo
            if parent.version_download_thread and parent.version_download_thread.isRunning():
                print(f"[WARN] Thread de descarga anterior aún en ejecución")
        parent.version_download_thread = self.download_thread
        
        # NO conectar deleteLater aquí - el thread debe mantenerse vivo hasta que termine completamente
        # La limpieza se hará en los métodos on_version_download_finished/error después de verificar que terminó
        
        # Guardar referencia al diálogo en el parent para poder cerrarlo cuando termine
        if parent and hasattr(parent, 'version_download_dialog'):
            parent.version_download_dialog = self
        
        # Iniciar el thread
        self.download_thread.start()
        print(f"[INFO] Thread de descarga iniciado")
        
        # Cerrar el diálogo inmediatamente después de iniciar el thread
        # El thread continuará ejecutándose en segundo plano y mostrará el progreso en la ventana principal
        print(f"[INFO] Cerrando diálogo, thread continuará en segundo plano descargando librerías")
        self.accept()
    
    def on_download_progress(self, downloaded, total, message):
        """Actualiza el progreso de la descarga"""
        self.status_label.setText(message)
        # Emitir señal al parent para actualizar su barra de progreso
        if self.parent():
            if hasattr(self.parent(), 'progress_bar'):
                self.parent().progress_bar.setVisible(True)
                self.parent().progress_bar.setRange(0, 100)
                self.parent().progress_bar.setValue(downloaded)
            if hasattr(self.parent(), 'progress_label'):
                self.parent().progress_label.setVisible(True)
                self.parent().progress_label.setText(message)
    
    def on_download_finished(self, version_id):
        """Se llama cuando termina la descarga"""
        self.selected_version = version_id
        if self.parent():
            if hasattr(self.parent(), 'progress_bar'):
                self.parent().progress_bar.setVisible(False)
            if hasattr(self.parent(), 'progress_label'):
                self.parent().progress_label.setVisible(False)
            if hasattr(self.parent(), 'add_message'):
                self.parent().add_message(f"Versión {version_id} descargada correctamente")
            # Refrescar la lista de versiones en el parent
            if hasattr(self.parent(), 'load_versions_async'):
                self.parent().load_versions_async()
        # No llamar a self.accept() aquí porque la ventana ya se cerró al iniciar la descarga
    
    def on_download_error(self, error):
        """Se llama cuando hay un error en la descarga"""
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: #fca5a5;")
        self.version_list.setEnabled(True)
        self.download_button.setEnabled(True)
        if self.parent():
            if hasattr(self.parent(), 'progress_bar'):
                self.parent().progress_bar.setVisible(False)
            if hasattr(self.parent(), 'progress_label'):
                self.parent().progress_label.setVisible(False)
        QMessageBox.critical(self, "Error", f"No se pudo descargar la versión:\n{error}")

class InstallProfileThread(QThread):
    """Thread para instalar un perfil personalizado sin bloquear la UI"""
    progress = pyqtSignal(int, int, str)  # progreso, total, mensaje
    finished = pyqtSignal(str)  # id del perfil instalado
    error = pyqtSignal(str)
    
    def __init__(self, profile, hostname, minecraft_path, profiles_data=None):
        super().__init__()
        self.profile = profile
        self.hostname = hostname
        self.minecraft_path = minecraft_path
        self.profiles_data = profiles_data  # Para obtener server_url si está disponible
        self.system = platform.system()
    
    def run(self):
        try:
            profile_id = self.profile.get("id", "unknown")
            profile_name = self.profile.get("name", "Sin nombre")
            
            # Crear carpeta del perfil
            profile_dir = os.path.join(self.minecraft_path, "profiles", profile_id)
            os.makedirs(profile_dir, exist_ok=True)
            
            self.progress.emit(5, 100, f"Creando estructura de carpetas para {profile_name}...")
            
            # Crear estructura de carpetas necesaria
            for folder in ["mods", "shaderpacks", "resourcepacks", "config", "saves"]:
                os.makedirs(os.path.join(profile_dir, folder), exist_ok=True)
            
            # Paso 1: Instalar versión base
            version_base = self.profile.get("version_base", {})
            version_type = version_base.get("type", "vanilla")
            
            if version_type == "neoforge":
                self.progress.emit(10, 100, "Instalando NeoForge...")
                self._install_neoforge(version_base, profile_dir, profile_name)
            elif version_type == "vanilla":
                self.progress.emit(10, 100, "Instalando versión Vanilla...")
                self._install_vanilla(version_base, profile_dir, profile_name)
            
            # Paso 2: Descargar mods
            mods = self.profile.get("mods", [])
            if mods:
                self.progress.emit(40, 100, f"Descargando {len(mods)} mod(s)...")
                self._download_mods(mods, profile_dir)
            
            # Paso 3: Descargar shaders
            shaders = self.profile.get("shaders", [])
            if shaders:
                self.progress.emit(60, 100, f"Descargando {len(shaders)} shader(s)...")
                self._download_shaders(shaders, profile_dir)
            
            # Paso 4: Descargar resource packs
            resourcepacks = self.profile.get("resourcepacks", [])
            if resourcepacks:
                self.progress.emit(80, 100, f"Descargando {len(resourcepacks)} resource pack(s)...")
                self._download_resourcepacks(resourcepacks, profile_dir)
            
            # Paso 5: Configurar options.txt
            self.progress.emit(90, 100, "Configurando opciones...")
            self._configure_options(profile_dir)
            
            self.progress.emit(100, 100, "Instalación completada")
            self.finished.emit(profile_id)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"Error durante la instalación: {str(e)}")
    
    def _install_neoforge(self, version_base, profile_dir, profile_name):
        """Instala NeoForge usando el instalador en el perfil"""
        installer_url = version_base.get("installer_url")
        if not installer_url:
            raise Exception("No se encontró URL del instalador de NeoForge")
        
        minecraft_version = version_base.get("minecraft_version")
        neoforge_version = version_base.get("neoforge_version")
        
        # Primero instalar la versión vanilla base si es necesaria
        self.progress.emit(10, 100, "Instalando versión Vanilla base...")
        self._install_vanilla(version_base, profile_dir, profile_name)
        
        # Descargar instalador
        self.progress.emit(20, 100, "Descargando instalador de NeoForge...")
        installer_path = os.path.join(profile_dir, "neoforge-installer.jar")
        response = requests.get(installer_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(installer_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Ejecutar instalador silenciosamente apuntando a profile_dir
        # El instalador de NeoForge usa el directorio actual de trabajo como base
        java_path = self._find_java()
        if not java_path:
            raise Exception("No se encontró Java para ejecutar el instalador")
        
        # Crear estructura de carpetas necesaria en el perfil
        versions_dir = os.path.join(profile_dir, "versions")
        libraries_dir = os.path.join(profile_dir, "libraries")
        os.makedirs(versions_dir, exist_ok=True)
        os.makedirs(libraries_dir, exist_ok=True)
        
        # El instalador crea la versión con el formato: neoforge-{neoforge_version}
        expected_version_id = f"neoforge-{neoforge_version}"
        
        # Crear el archivo launcher_profiles.json que el instalador de NeoForge necesita
        # El instalador busca este archivo para verificar que es un directorio de Minecraft válido
        launcher_profiles_path = os.path.join(profile_dir, "launcher_profiles.json")
        if not os.path.exists(launcher_profiles_path):
            launcher_profiles = {
                "profiles": {
                    "profile": {
                        "name": profile_name,  # Usar el nombre del perfil del JSON del servidor
                        "lastVersionId": expected_version_id  # Usar la versión de NeoForge que se instalará
                    }
                },
                "settings": {
                    "locale": "es_ES"
                },
                "version": 2
            }
            with open(launcher_profiles_path, 'w', encoding='utf-8') as f:
                json.dump(launcher_profiles, f, indent=2)
            print(f"[INFO] Creado launcher_profiles.json en el perfil con nombre: {profile_name}")
        
        # Forzar que el instalador use el perfil como directorio base
        # El instalador de NeoForge acepta --installClient [File] donde File es el directorio de instalación
        profile_dir_abs = os.path.abspath(profile_dir)
        cmd = [
            java_path, "-jar", installer_path,
            "--installClient", profile_dir_abs
        ]
        
        # Configurar variables de entorno para forzar la instalación en el perfil
        env = os.environ.copy()
        env["MINECRAFT_DIR"] = profile_dir_abs
        env["INSTALL_DIR"] = profile_dir_abs
        env["MCP_DIR"] = profile_dir_abs
        
        print(f"[DEBUG] Ejecutando instalador de NeoForge: {' '.join(cmd)}")
        print(f"[DEBUG] Directorio de trabajo: {profile_dir_abs}")
        print(f"[DEBUG] MINECRAFT_DIR: {profile_dir_abs}")
        
        # Ejecutar el instalador desde el directorio del perfil
        self.progress.emit(30, 100, "Ejecutando instalador de NeoForge...")
        result = subprocess.run(
            cmd,
            cwd=profile_dir_abs,  # Cambiar directorio de trabajo al perfil (absoluto)
            env=env,  # Pasar variables de entorno modificadas
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if self.system == "Windows" else 0
        )
        
        print(f"[DEBUG] Código de retorno: {result.returncode}")
        if result.stdout:
            print(f"[DEBUG] stdout: {result.stdout}")
        if result.stderr:
            print(f"[DEBUG] stderr: {result.stderr}")
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout if result.stdout else "Error desconocido"
            raise Exception(f"Error ejecutando instalador de NeoForge (código {result.returncode}): {error_msg}")
        
        # Verificar que se instaló directamente en el perfil
        import shutil
        # El instalador crea la versión con el formato: neoforge-{neoforge_version}
        # Por ejemplo: neoforge-21.1.215 (no incluye la versión de Minecraft)
        expected_version_id = f"neoforge-{neoforge_version}"
        
        self.progress.emit(40, 100, "Verificando instalación en el perfil...")
        
        # Verificar que la versión se instaló en el perfil
        version_json_path = os.path.join(profile_dir, "versions", expected_version_id, f"{expected_version_id}.json")
        if not os.path.exists(version_json_path):
            raise Exception(
                f"El instalador no instaló la versión en el perfil.\n"
                f"Buscado en: {version_json_path}\n"
                f"El instalador debe usar --installClient para instalar en el perfil."
            )
        
        print(f"[INFO] JSON de versión NeoForge encontrado en perfil: {version_json_path}")
        
        # Verificar que el JAR cliente se instaló en el perfil
        client_jar_path = os.path.join(
            profile_dir, 
            "libraries", 
            "net", 
            "neoforged", 
            "neoforge", 
            neoforge_version,
            f"neoforge-{neoforge_version}-client.jar"
        )
        
        if not os.path.exists(client_jar_path):
            raise Exception(
                f"El instalador no instaló el JAR cliente en el perfil.\n"
                f"Buscado en: {client_jar_path}\n"
                f"El instalador debe usar --installClient para instalar en el perfil."
            )
        
        print(f"[INFO] JAR cliente de NeoForge encontrado en perfil: {client_jar_path}")
        
        # Leer el JSON para obtener las librerías necesarias
        with open(version_json_path, 'r', encoding='utf-8') as f:
            version_json = json.load(f)
        
        # Copiar el JAR cliente a la carpeta de versiones (formato esperado)
        target_version_dir = os.path.join(profile_dir, "versions", expected_version_id)
        os.makedirs(target_version_dir, exist_ok=True)
        
        target_jar = os.path.join(target_version_dir, f"{expected_version_id}.jar")
        shutil.copy2(client_jar_path, target_jar)
        print(f"[INFO] JAR cliente copiado a versiones: {target_jar}")
        
        # Descargar todas las librerías necesarias (incluyendo heredadas)
        self.progress.emit(60, 100, "Descargando librerías de NeoForge...")
        
        # Recopilar todas las librerías incluyendo las heredadas
        all_libraries = []
        visited_versions = set()
        
        def collect_libraries(v_json, visited):
            """Recopila librerías de forma recursiva incluyendo versiones heredadas"""
            if "inheritsFrom" in v_json:
                parent_version = v_json["inheritsFrom"]
                if parent_version not in visited:
                    visited.add(parent_version)
                    # Cargar versión padre desde el perfil
                    parent_version_dir = os.path.join(profile_dir, "versions", parent_version)
                    parent_json_path = os.path.join(parent_version_dir, f"{parent_version}.json")
                    if os.path.exists(parent_json_path):
                        with open(parent_json_path, 'r', encoding='utf-8') as f:
                            parent_json = json.load(f)
                        collect_libraries(parent_json, visited)
            
            # Agregar librerías de esta versión
            for lib in v_json.get('libraries', []):
                all_libraries.append(lib)
        
        collect_libraries(version_json, visited_versions)
        
        total_libs = len(all_libraries)
        for i, library in enumerate(all_libraries):
            progress = 60 + int((i / total_libs) * 30) if total_libs > 0 else 60
            self.progress.emit(progress, 100, f"Descargando librerías ({i + 1}/{total_libs})...")
            self._download_library(library, libraries_dir, 0, 100)
        
        # Verificar que los archivos existen
        if not os.path.exists(version_json_path):
            raise Exception(f"No se encontró el JSON de NeoForge en profile_dir")
        if not os.path.exists(target_jar):
            raise Exception(f"No se encontró el JAR cliente de NeoForge en profile_dir")
        
        # Actualizar launcher_profiles.json con el lastVersionId correcto (neoforge-21.1.215)
        launcher_profiles_path = os.path.join(profile_dir, "launcher_profiles.json")
        if os.path.exists(launcher_profiles_path):
            try:
                with open(launcher_profiles_path, 'r', encoding='utf-8') as f:
                    launcher_profiles = json.load(f)
                # Actualizar lastVersionId con la versión de NeoForge instalada
                if "profiles" in launcher_profiles:
                    for profile_key in launcher_profiles["profiles"]:
                        launcher_profiles["profiles"][profile_key]["lastVersionId"] = expected_version_id
                with open(launcher_profiles_path, 'w', encoding='utf-8') as f:
                    json.dump(launcher_profiles, f, indent=2)
                print(f"[INFO] Actualizado launcher_profiles.json con lastVersionId: {expected_version_id}")
            except Exception as e:
                print(f"[WARN] Error actualizando launcher_profiles.json: {e}")
        
        print(f"[INFO] Versión NeoForge instalada exitosamente en profile_dir")
        
        # Limpiar instalador temporal
        try:
            os.remove(installer_path)
        except:
            pass
    
    def _install_vanilla(self, version_base, profile_dir, profile_name):
        """Instala versión Vanilla en el perfil"""
        minecraft_version = version_base.get("minecraft_version")
        if not minecraft_version:
            raise Exception("No se especificó versión de Minecraft")
        
        # Crear el archivo launcher_profiles.json si no existe
        launcher_profiles_path = os.path.join(profile_dir, "launcher_profiles.json")
        if not os.path.exists(launcher_profiles_path):
            launcher_profiles = {
                "profiles": {
                    "profile": {
                        "name": profile_name,  # Usar el nombre del perfil del JSON del servidor
                        "lastVersionId": minecraft_version
                    }
                },
                "settings": {
                    "locale": "es_ES"
                },
                "version": 2
            }
            with open(launcher_profiles_path, 'w', encoding='utf-8') as f:
                json.dump(launcher_profiles, f, indent=2)
            print(f"[INFO] Creado launcher_profiles.json en el perfil con nombre: {profile_name}")
        
        # Obtener manifest de versiones
        manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        response = requests.get(manifest_url, timeout=30)
        response.raise_for_status()
        manifest = response.json()
        
        # Buscar la versión en el manifest
        version_info = None
        for version in manifest.get("versions", []):
            if version.get("id") == minecraft_version:
                version_info = version
                break
        
        if not version_info:
            raise Exception(f"Versión {minecraft_version} no encontrada en el manifest")
        
        # Descargar JSON de la versión
        version_json_url = version_info.get("url")
        response = requests.get(version_json_url, timeout=30)
        response.raise_for_status()
        version_json = response.json()
        
        # Crear directorio de versión dentro del perfil
        version_id = minecraft_version  # Usar el ID real de la versión
        versions_dir = os.path.join(profile_dir, "versions", version_id)
        os.makedirs(versions_dir, exist_ok=True)
        
        # Guardar JSON
        json_path = os.path.join(versions_dir, f"{version_id}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(version_json, f, indent=2)
        
        # Descargar client.jar
        downloads = version_json.get("downloads", {})
        client_info = downloads.get("client")
        if client_info:
            jar_url = client_info.get("url")
            jar_path = os.path.join(versions_dir, f"{version_id}.jar")
            
            response = requests.get(jar_url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(jar_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        
        # Descargar todas las librerías necesarias (incluyendo heredadas)
        libraries_dir = os.path.join(profile_dir, "libraries")
        os.makedirs(libraries_dir, exist_ok=True)
        
        # Recopilar todas las librerías incluyendo las heredadas
        all_libraries = []
        visited_versions = set()
        
        def collect_libraries(v_json, visited):
            """Recopila librerías de forma recursiva incluyendo versiones heredadas"""
            if "inheritsFrom" in v_json:
                parent_version = v_json["inheritsFrom"]
                if parent_version not in visited:
                    visited.add(parent_version)
                    # Cargar versión padre desde el perfil
                    parent_version_dir = os.path.join(profile_dir, "versions", parent_version)
                    parent_json_path = os.path.join(parent_version_dir, f"{parent_version}.json")
                    if os.path.exists(parent_json_path):
                        with open(parent_json_path, 'r', encoding='utf-8') as f:
                            parent_json = json.load(f)
                        collect_libraries(parent_json, visited)
            
            # Agregar librerías de esta versión
            for lib in v_json.get('libraries', []):
                all_libraries.append(lib)
        
        collect_libraries(version_json, visited_versions)
        
        total_libs = len(all_libraries)
        for i, library in enumerate(all_libraries):
            self._download_library(library, libraries_dir, 0, 100)
    
    def _maven_name_to_path(self, name):
        """Convierte un nombre Maven (group:artifact:version) a ruta de archivo"""
        parts = name.split(':')
        if len(parts) < 3:
            return None
        
        group_id = parts[0].replace('.', '/')
        artifact_id = parts[1]
        version = parts[2]
        
        # Construir ruta: group/artifact/version/artifact-version.jar
        path = f"{group_id}/{artifact_id}/{version}/{artifact_id}-{version}.jar"
        return path
    
    def _download_library(self, library, libraries_dir, progress_base, progress_max):
        """Descarga una librería individual (para InstallProfileThread)"""
        # Verificar reglas
        if not self._should_include_library(library):
            return True  # Librería excluida por reglas, no es un error
        
        # Obtener información de descarga
        downloads = library.get("downloads", {})
        artifact = downloads.get("artifact")
        
        lib_name = library.get("name", "")
        if not lib_name:
            return True  # No hay nombre, saltar
        
        # Construir path desde name
        lib_path = self._maven_name_to_path(lib_name)
        if not lib_path:
            return True  # No se pudo construir path, saltar
        
        # Verificar si ya existe
        full_path = os.path.join(libraries_dir, lib_path)
        if os.path.exists(full_path):
            return True  # Ya existe, no descargar
        
        # Obtener URL y path
        lib_url = None
        if artifact:
            lib_url = artifact.get("url")
            # Si hay path en artifact, usarlo (puede ser diferente al construido)
            artifact_path = artifact.get("path")
            if artifact_path:
                lib_path = artifact_path
                full_path = os.path.join(libraries_dir, lib_path)
                # Verificar de nuevo con el path del artifact
                if os.path.exists(full_path):
                    return True
        
        # Si no hay URL explícita, intentar construirla desde el nombre Maven
        if not lib_url:
            # Construir URL desde repositorios Maven
            # Intentar primero con libraries.minecraft.net (para librerías de Mojang)
            # Luego con maven.neoforged.net (para librerías de NeoForge)
            # Finalmente con repo1.maven.org (Maven Central)
            repos = [
                f"https://libraries.minecraft.net/{lib_path}",
                f"https://maven.neoforged.net/releases/{lib_path}",
                f"https://repo1.maven.org/maven2/{lib_path}"
            ]
            
            # Intentar descargar desde cada repositorio hasta que uno funcione
            for repo_url in repos:
                try:
                    # Verificar si existe haciendo un HEAD request
                    head_response = requests.head(repo_url, timeout=10, allow_redirects=True)
                    if head_response.status_code == 200:
                        lib_url = repo_url
                        print(f"[DEBUG] URL construida para {lib_name}: {lib_url}")
                        break
                except:
                    continue
            
            if not lib_url:
                print(f"[WARN] No se pudo encontrar URL para librería: {lib_name}")
                return True  # No se pudo encontrar URL, saltar
        
        if not lib_url:
            return True  # No hay URL, saltar
        
        # Crear directorio si no existe
        lib_dir = os.path.dirname(full_path)
        os.makedirs(lib_dir, exist_ok=True)
        
        # Descargar la librería
        try:
            response = requests.get(lib_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            print(f"[DEBUG] Librería descargada: {lib_name} -> {full_path}")
            return True
        except Exception as e:
            print(f"[WARN] Error descargando librería {lib_path}: {e}")
            # Si falla, eliminar archivo parcial
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except:
                    pass
            return False  # Error al descargar
    
    def _should_include_library(self, library):
        """Verifica si una librería debe incluirse según las reglas del OS"""
        if "rules" not in library:
            return True
        
        for rule in library.get("rules", []):
            action = rule.get("action", "allow")
            if "os" in rule:
                os_rule = rule["os"]
                os_name = os_rule.get("name", "").lower()
                current_os = self.system.lower()
                
                if current_os == "windows":
                    current_os = "windows"
                elif current_os == "darwin":
                    current_os = "osx"
                elif current_os == "linux":
                    current_os = "linux"
                
                if os_name and os_name != current_os:
                    if action == "allow":
                        return False
                    continue
            
            if action == "disallow":
                return False
        
        return True
    
    def _get_base_url(self):
        """Obtiene la URL base para descargar archivos"""
        # Intentar usar server_url del JSON si está disponible
        if self.profiles_data and "server_url" in self.profiles_data:
            server_url = self.profiles_data.get("server_url", "").rstrip('/')
            if server_url:
                return server_url
        
        # Fallback: usar hostname con puerto 25080
        if self.hostname:
            return f"http://{self.hostname}:25080"
        
        return ""
    
    def _download_mods(self, mods, profile_dir):
        """Descarga los mods del perfil"""
        mods_dir = os.path.join(profile_dir, "mods")
        base_url = self._get_base_url()
        
        for mod in mods:
            mod_name = mod.get("name")
            mod_url = mod.get("url")
            if not mod_name or not mod_url:
                continue
            
            # Si la URL es relativa, construirla con la URL base
            if not mod_url.startswith("http"):
                if base_url:
                    # Asegurar que la URL relativa empiece con /
                    if not mod_url.startswith("/"):
                        mod_url = f"/{mod_url}"
                    mod_url = f"{base_url}{mod_url}"
                else:
                    print(f"[WARN] No se puede construir URL para mod {mod_name}: falta hostname o server_url")
                    continue
            
            mod_path = os.path.join(mods_dir, mod_name)
            if os.path.exists(mod_path):
                continue  # Ya existe
            
            try:
                response = requests.get(mod_url, stream=True, timeout=60)
                response.raise_for_status()
                with open(mod_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                print(f"[WARN] Error descargando mod {mod_name}: {e}")
    
    def _download_shaders(self, shaders, profile_dir):
        """Descarga los shaders del perfil"""
        shaders_dir = os.path.join(profile_dir, "shaderpacks")
        base_url = self._get_base_url()
        
        for shader in shaders:
            shader_name = shader.get("name")
            shader_url = shader.get("url")
            if not shader_name or not shader_url:
                continue
            
            if not shader_url.startswith("http"):
                if base_url:
                    if not shader_url.startswith("/"):
                        shader_url = f"/{shader_url}"
                    shader_url = f"{base_url}{shader_url}"
                else:
                    print(f"[WARN] No se puede construir URL para shader {shader_name}: falta hostname o server_url")
                    continue
            
            shader_path = os.path.join(shaders_dir, shader_name)
            if os.path.exists(shader_path):
                continue
            
            try:
                response = requests.get(shader_url, stream=True, timeout=60)
                response.raise_for_status()
                with open(shader_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                print(f"[WARN] Error descargando shader {shader_name}: {e}")
    
    def _download_resourcepacks(self, resourcepacks, profile_dir):
        """Descarga los resource packs del perfil"""
        rp_dir = os.path.join(profile_dir, "resourcepacks")
        base_url = self._get_base_url()
        
        for rp in resourcepacks:
            rp_name = rp.get("name")
            rp_url = rp.get("url")
            if not rp_name or not rp_url:
                continue
            
            if not rp_url.startswith("http"):
                if base_url:
                    if not rp_url.startswith("/"):
                        rp_url = f"/{rp_url}"
                    rp_url = f"{base_url}{rp_url}"
                else:
                    print(f"[WARN] No se puede construir URL para resource pack {rp_name}: falta hostname o server_url")
                    continue
            
            rp_path = os.path.join(rp_dir, rp_name)
            if os.path.exists(rp_path):
                continue
            
            try:
                response = requests.get(rp_url, stream=True, timeout=60)
                response.raise_for_status()
                with open(rp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                print(f"[WARN] Error descargando resource pack {rp_name}: {e}")
    
    def _configure_options(self, profile_dir):
        """Configura el archivo options.txt del perfil"""
        options = self.profile.get("options", {})
        if not options:
            return
        
        options_path = os.path.join(profile_dir, "options.txt")
        options_dict = {}
        
        # Leer options.txt existente si existe
        if os.path.exists(options_path):
            with open(options_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        options_dict[key.strip()] = value.strip()
        
        # Actualizar con opciones del perfil
        if "fov" in options:
            options_dict["fov"] = str(options["fov"])
        if "renderDistance" in options:
            options_dict["renderDistance"] = str(options["renderDistance"])
        if "maxFps" in options:
            options_dict["maxFps"] = str(options["maxFps"])
        if "guiScale" in options:
            options_dict["guiScale"] = str(options["guiScale"])
        
        # Configurar shaders
        if options.get("enable_shaders", False):
            shader_pack = options.get("shader_pack", "")
            if shader_pack:
                # Remover extensión si la tiene
                shader_pack = shader_pack.replace(".zip", "").replace(".jar", "")
                options_dict["shaderPack"] = shader_pack
        else:
            options_dict["shaderPack"] = "OFF"
        
        # Configurar resource packs
        if options.get("enable_resourcepacks", False):
            resource_packs = options.get("resource_packs", [])
            if resource_packs:
                # Formato: resourcePacks:["pack1.zip","pack2.zip"]
                packs_str = "[" + ",".join([f'"{p.replace(".zip", "").replace(".jar", "")}.zip"' for p in resource_packs]) + "]"
                options_dict["resourcePacks"] = packs_str
        else:
            options_dict["resourcePacks"] = "[]"
        
        # Escribir options.txt
        with open(options_path, 'w', encoding='utf-8') as f:
            for key, value in options_dict.items():
                f.write(f"{key}:{value}\n")
    
    def _find_java(self):
        """Encuentra una instalación de Java"""
        creationflags = subprocess.CREATE_NO_WINDOW if self.system == "Windows" else 0
        
        # Buscar java en PATH
        java_names = ["java", "javaw"] if self.system == "Windows" else ["java"]
        for java_name in java_names:
            try:
                result = subprocess.run(
                    [java_name, "-version"],
                    capture_output=True,
                    timeout=5,
                    creationflags=creationflags
                )
                if result.returncode == 0 or result.returncode == 1:  # Java muestra versión en stderr
                    return java_name
            except:
                continue
        
        # Buscar en .minecraft/runtime (rutas multiplataforma)
        runtime_base = os.path.join(self.minecraft_path, "runtime")
        if os.path.exists(runtime_base):
            # Buscar en subdirectorios comunes
            for root, dirs, files in os.walk(runtime_base):
                for file in files:
                    if file in ["java.exe", "javaw.exe", "java"]:
                        java_path = os.path.join(root, file)
                        try:
                            result = subprocess.run(
                                [java_path, "-version"],
                                capture_output=True,
                                timeout=5,
                                creationflags=creationflags
                            )
                            if result.returncode == 0 or result.returncode == 1:
                                return java_path
                        except:
                            continue
        
        return None


class CustomProfileDialog(QDialog):
    """Diálogo para instalar perfiles personalizados desde URL"""
    
    def __init__(self, parent=None, minecraft_launcher=None):
        super().__init__(parent)
        self.minecraft_launcher = minecraft_launcher
        self.profiles_data = None
        self.hostname = None
        self.install_thread = None
        
        self.setWindowTitle("Instalar Perfil Personalizado")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(800, 700)
        self._center_on_parent_screen(parent)
        
        # Widget central
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet("""
            QWidget#centralWidget {
                background: rgba(26, 13, 46, 0.8);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 5, 20, 5)
        layout.setSpacing(10)
        
        # Barra de título
        title_bar = TitleBar(self)
        title_bar.setFixedHeight(35)
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(5)
        title_bar.setLayout(title_bar_layout)
        
        title = QLabel("Instalar Perfil Personalizado")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_bar_layout.addWidget(title, 1)
        
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.reject)
        title_bar_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)
        
        # Campo de Hostname/IP
        hostname_layout = QHBoxLayout()
        hostname_label = QLabel("Hostname o IP:")
        hostname_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        hostname_layout.addWidget(hostname_label)
        
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("localhost o 192.168.1.1")
        self.hostname_input.setStyleSheet("""
            QLineEdit {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8b5cf6;
            }
        """)
        hostname_layout.addWidget(self.hostname_input, 1)
        
        self.load_button = QPushButton("Cargar")
        self.load_button.clicked.connect(self.load_profiles_json)
        self.load_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                padding: 5px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
            }
            QPushButton:disabled {
                background: #3f3f3f;
                color: #888888;
                border-color: #555555;
            }
        """)
        hostname_layout.addWidget(self.load_button)
        
        layout.addLayout(hostname_layout)
        
        # Selector de perfiles
        profile_layout = QHBoxLayout()
        profile_label = QLabel("Perfil:")
        profile_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        profile_layout.addWidget(profile_label)
        
        self.profile_combo = QComboBox()
        self.profile_combo.setEnabled(False)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_selected)
        profile_layout.addWidget(self.profile_combo, 1)
        
        layout.addLayout(profile_layout)
        
        # Área de información del perfil (scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #1a0d2e;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #6d28d9;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8b5cf6;
            }
        """)
        
        info_widget = QWidget()
        info_widget.setStyleSheet("""
            QWidget {
                background: rgba(26, 13, 46, 0.6);
            }
        """)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        
        # Información básica del servidor
        self.server_name_label = QLabel("")
        self.server_name_label.setStyleSheet("color: #a78bfa; font-size: 14px; font-weight: bold;")
        self.server_name_label.setVisible(False)
        info_layout.addWidget(self.server_name_label)
        
        self.server_connection_label = QLabel("")
        self.server_connection_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        self.server_connection_label.setVisible(False)
        info_layout.addWidget(self.server_connection_label)
        
        self.server_description_label = QLabel("")
        self.server_description_label.setStyleSheet("color: #c4b5fd; font-size: 11px;")
        self.server_description_label.setWordWrap(True)
        self.server_description_label.setVisible(False)
        info_layout.addWidget(self.server_description_label)
        
        # Lista 1: Versiones necesarias
        versions_group = QGroupBox("Versiones Necesarias")
        versions_group.setStyleSheet("""
            QGroupBox {
                background: rgba(26, 13, 46, 0.8);
                color: #a78bfa;
                font-size: 12px;
                font-weight: bold;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background: rgba(26, 13, 46, 0.8);
            }
        """)
        versions_layout = QVBoxLayout()
        self.versions_list = QListWidget()
        self.versions_list.setEnabled(False)
        self.versions_list.setStyleSheet("""
            QListWidget {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 1px solid #6d28d9;
                border-radius: 3px;
                font-size: 11px;
            }
        """)
        versions_layout.addWidget(self.versions_list)
        versions_group.setLayout(versions_layout)
        info_layout.addWidget(versions_group)
        
        # Lista 2: Mods
        mods_group = QGroupBox("Mods")
        mods_group.setStyleSheet(versions_group.styleSheet())
        mods_layout = QVBoxLayout()
        self.mods_list = QListWidget()
        self.mods_list.setEnabled(False)
        self.mods_list.setStyleSheet(self.versions_list.styleSheet())
        mods_layout.addWidget(self.mods_list)
        mods_group.setLayout(mods_layout)
        info_layout.addWidget(mods_group)
        
        # Lista 3: Shaders
        shaders_group = QGroupBox("Shaders")
        shaders_group.setStyleSheet(versions_group.styleSheet())
        shaders_layout = QVBoxLayout()
        self.shaders_list = QListWidget()
        self.shaders_list.setEnabled(False)
        self.shaders_list.setStyleSheet(self.versions_list.styleSheet())
        shaders_layout.addWidget(self.shaders_list)
        shaders_group.setLayout(shaders_layout)
        info_layout.addWidget(shaders_group)
        
        # Lista 4: Resource Packs
        resourcepacks_group = QGroupBox("Resource Packs")
        resourcepacks_group.setStyleSheet(versions_group.styleSheet())
        resourcepacks_layout = QVBoxLayout()
        self.resourcepacks_list = QListWidget()
        self.resourcepacks_list.setEnabled(False)
        self.resourcepacks_list.setStyleSheet(self.versions_list.styleSheet())
        resourcepacks_layout.addWidget(self.resourcepacks_list)
        resourcepacks_group.setLayout(resourcepacks_layout)
        info_layout.addWidget(resourcepacks_group)
        
        # Lista 5: Opciones
        options_group = QGroupBox("Opciones")
        options_group.setStyleSheet(versions_group.styleSheet())
        options_layout = QVBoxLayout()
        self.options_list = QListWidget()
        self.options_list.setEnabled(False)
        self.options_list.setStyleSheet(self.versions_list.styleSheet())
        options_layout.addWidget(self.options_list)
        options_group.setLayout(options_layout)
        info_layout.addWidget(options_group)
        
        info_widget.setLayout(info_layout)
        scroll_area.setWidget(info_widget)
        layout.addWidget(scroll_area, 1)
        
        # Botones
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setStyleSheet("""
            QPushButton {
                background: #3f3f3f;
                color: #e9d5ff;
                border: 2px solid #555555;
                border-radius: 5px;
                padding: 8px 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4f4f4f;
                border-color: #666666;
            }
        """)
        button_layout.addWidget(cancel_button)
        
        # Barra de progreso para la instalación
        self.install_progress_bar = QProgressBar()
        self.install_progress_bar.setVisible(False)
        self.install_progress_bar.setStyleSheet("""
            QProgressBar {
                background: #0f0a1a;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                height: 20px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:1 #a78bfa);
                border-radius: 3px;
            }
        """)
        button_layout.addWidget(self.install_progress_bar)
        
        self.install_progress_label = QLabel("")
        self.install_progress_label.setAlignment(Qt.AlignCenter)
        self.install_progress_label.setVisible(False)
        self.install_progress_label.setStyleSheet("color: #e9d5ff; font-size: 11px;")
        button_layout.addWidget(self.install_progress_label)
        
        self.install_button = QPushButton("Instalar")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.start_installation)
        self.install_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
            }
            QPushButton:disabled {
                background: #3f3f3f;
                color: #888888;
                border-color: #555555;
            }
        """)
        button_layout.addWidget(self.install_button)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
        
        # Layout principal del diálogo
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(central_widget)
        self.setLayout(main_layout)
        
        # Aplicar estilos
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border: 2px solid #8b5cf6;
                border-radius: 10px;
            }
            QLabel#titleLabel {
                color: #a78bfa;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#closeButton {
                background: #dc2626;
                border: 1px solid #ef4444;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#closeButton:hover {
                background: #ef4444;
                border: 1px solid #f87171;
            }
            QPushButton#minimizeButton {
                background: #6b7280;
                border: 1px solid #9ca3af;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#minimizeButton:hover {
                background: #9ca3af;
                border: 1px solid #d1d5db;
            }
            QComboBox {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #8b5cf6;
            }
            QComboBox::drop-down {
                border: none;
                background: #5b21b6;
            }
            QComboBox QAbstractItemView {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #8b5cf6;
                selection-background-color: #7c3aed;
            }
        """)
    
    def _center_on_parent_screen(self, parent):
        """Centra la ventana en la pantalla donde está la ventana principal"""
        if parent:
            parent_geometry = parent.geometry()
            parent_center = parent_geometry.center()
            dialog_geometry = self.geometry()
            dialog_geometry.moveCenter(parent_center)
            self.setGeometry(dialog_geometry)
        else:
            # Centrar en la pantalla principal si no hay parent
            screen = QApplication.primaryScreen().geometry()
            dialog_geometry = self.geometry()
            dialog_geometry.moveCenter(screen.center())
            self.setGeometry(dialog_geometry)
    
    def load_profiles_json(self):
        """Carga el archivo profiles.json desde el hostname usando la función compartida"""
        hostname = self.hostname_input.text().strip()
        if not hostname:
            QMessageBox.warning(self, "Error", "Por favor, introduce un hostname o IP")
            return
        
        self.load_button.setEnabled(False)
        self.load_button.setText("Cargando...")
        
        # Usar la función compartida para obtener el JSON
        json_data, error_message = fetch_profiles_json(hostname, api_key=None)
        
        if error_message:
            QMessageBox.critical(self, "Error", error_message)
            self.load_button.setEnabled(True)
            self.load_button.setText("Cargar")
            return
        
        if not json_data:
            QMessageBox.warning(self, "Error", "No se recibieron datos del servidor")
            self.load_button.setEnabled(True)
            self.load_button.setText("Cargar")
            return
        
        try:
            self.profiles_data = json_data
            self.hostname = hostname
            
            # Llenar selector de perfiles
            self.profile_combo.clear()
            if "profiles" in self.profiles_data and self.profiles_data["profiles"]:
                for profile in self.profiles_data["profiles"]:
                    profile_name = profile.get("name", profile.get("id", "Sin nombre"))
                    self.profile_combo.addItem(profile_name, profile)
                
                self.profile_combo.setEnabled(True)
                self.profile_combo.setCurrentIndex(0)  # Seleccionar el primero
                self.on_profile_selected(0)
            else:
                QMessageBox.warning(self, "Error", "No se encontraron perfiles en el JSON")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error inesperado:\n{str(e)}")
        finally:
            self.load_button.setEnabled(True)
            self.load_button.setText("Cargar")
    
    def on_profile_selected(self, index):
        """Se llama cuando se selecciona un perfil"""
        if index < 0 or not self.profiles_data:
            return
        
        profile = self.profile_combo.itemData(index)
        if not profile:
            return
        
        # Mostrar información del servidor
        server_name = self.profiles_data.get("server_name", "Servidor desconocido")
        self.server_name_label.setText(f"Servidor: {server_name}")
        self.server_name_label.setVisible(True)
        
        # Info de conexión
        config = profile.get("config", {})
        server_ip = config.get("server_ip", "No especificado")
        server_port = config.get("server_port", 25565)
        self.server_connection_label.setText(f"Conexión: {server_ip}:{server_port}")
        self.server_connection_label.setVisible(True)
        
        # Descripción
        description = profile.get("description", "")
        if description:
            self.server_description_label.setText(f"Descripción: {description}")
            self.server_description_label.setVisible(True)
        else:
            self.server_description_label.setVisible(False)
        
        # Lista 1: Versiones necesarias
        self.versions_list.clear()
        version_base = profile.get("version_base", {})
        if version_base:
            version_type = version_base.get("type", "unknown")
            if version_type == "neoforge":
                minecraft_version = version_base.get("minecraft_version", "N/A")
                neoforge_version = version_base.get("neoforge_version", "N/A")
                self.versions_list.addItem(f"Vanilla: {minecraft_version}")
                self.versions_list.addItem(f"NeoForge: {neoforge_version}")
            elif version_type == "vanilla":
                minecraft_version = version_base.get("minecraft_version", "N/A")
                self.versions_list.addItem(f"Vanilla: {minecraft_version}")
        
        # Lista 2: Mods
        self.mods_list.clear()
        mods = profile.get("mods", [])
        for mod in mods:
            mod_name = mod.get("name", "Sin nombre")
            required = mod.get("required", False)
            required_text = " (Requerido)" if required else ""
            self.mods_list.addItem(f"{mod_name}{required_text}")
        
        # Lista 3: Shaders
        self.shaders_list.clear()
        shaders = profile.get("shaders", [])
        for shader in shaders:
            shader_name = shader.get("name", "Sin nombre")
            enabled = shader.get("enabled", False)
            enabled_text = " (Activado)" if enabled else ""
            self.shaders_list.addItem(f"{shader_name}{enabled_text}")
        
        # Lista 4: Resource Packs
        self.resourcepacks_list.clear()
        resourcepacks = profile.get("resourcepacks", [])
        for rp in resourcepacks:
            rp_name = rp.get("name", "Sin nombre")
            enabled = rp.get("enabled", False)
            enabled_text = " (Activado)" if enabled else ""
            self.resourcepacks_list.addItem(f"{rp_name}{enabled_text}")
        
        # Lista 5: Opciones
        self.options_list.clear()
        options = profile.get("options", {})
        if options:
            if options.get("enable_shaders", False):
                shader_pack = options.get("shader_pack", "No especificado")
                self.options_list.addItem(f"Shaders: Activados ({shader_pack})")
            else:
                self.options_list.addItem("Shaders: Desactivados")
            
            if options.get("enable_resourcepacks", False):
                resource_packs = options.get("resource_packs", [])
                if resource_packs:
                    self.options_list.addItem(f"Resource Packs: Activados ({', '.join(resource_packs)})")
                else:
                    self.options_list.addItem("Resource Packs: Activados (todos)")
            else:
                self.options_list.addItem("Resource Packs: Desactivados")
            
            if "fov" in options:
                self.options_list.addItem(f"FOV: {options['fov']}")
            if "renderDistance" in options:
                self.options_list.addItem(f"Distancia de renderizado: {options['renderDistance']}")
            if "maxFps" in options:
                self.options_list.addItem(f"FPS máximo: {options['maxFps']}")
        
        # Habilitar botón de instalar
        self.install_button.setEnabled(True)
    
    def start_installation(self):
        """Inicia la instalación del perfil seleccionado"""
        index = self.profile_combo.currentIndex()
        if index < 0:
            return
        
        profile = self.profile_combo.itemData(index)
        if not profile:
            return
        
        if not self.hostname:
            QMessageBox.warning(self, "Error", "No se ha cargado información del servidor")
            return
        
        # Confirmar instalación
        reply = QMessageBox.question(
            self,
            "Confirmar Instalación",
            f"¿Deseas instalar el perfil '{profile.get('name', 'Sin nombre')}'?\n\n"
            f"Se creará en: .minecraft/profiles/{profile.get('id', 'unknown')}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Deshabilitar botón durante la instalación
        self.install_button.setEnabled(False)
        self.install_progress_bar.setVisible(True)
        self.install_progress_bar.setRange(0, 100)
        self.install_progress_bar.setValue(0)
        self.install_progress_label.setVisible(True)
        self.install_progress_label.setText("Preparando instalación...")
        
        # Crear y conectar thread de instalación
        self.install_thread = InstallProfileThread(
            profile,
            self.hostname,
            self.minecraft_launcher.minecraft_path,
            self.profiles_data
        )
        self.install_thread.progress.connect(self.on_install_progress)
        self.install_thread.finished.connect(self.on_install_finished)
        self.install_thread.error.connect(self.on_install_error)
        self.install_thread.start()
    
    def on_install_progress(self, progress, total, message):
        """Actualiza el progreso de la instalación"""
        self.install_progress_bar.setValue(progress)
        self.install_progress_label.setText(message)
    
    def on_install_finished(self, profile_id):
        """Se llama cuando la instalación se completa"""
        self.install_progress_bar.setValue(100)
        self.install_progress_label.setText("Instalación completada")
        self.install_button.setEnabled(True)
        self.install_progress_bar.setVisible(False)
        self.install_progress_label.setVisible(False)
        
        # Cerrar el diálogo
        self.accept()
        
        # Recargar versiones en la ventana principal
        if self.parent():
            parent_window = self.parent()
            if hasattr(parent_window, 'load_versions_async'):
                parent_window.load_versions_async()
    
    def on_install_error(self, error):
        """Se llama cuando hay un error en la instalación"""
        self.install_progress_bar.setVisible(False)
        self.install_progress_label.setVisible(False)
        self.install_button.setEnabled(True)
        QMessageBox.critical(self, "Error de Instalación", f"Error durante la instalación:\n{error}")

# ServerManagerDialog movido a server_manager.py

class TitleBar(QWidget):
    """Barra de título personalizada que permite arrastrar la ventana"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.old_pos = None
    
    def mousePressEvent(self, event):
        """Inicia el arrastre de la ventana"""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
    
    def mouseMoveEvent(self, event):
        """Mueve la ventana cuando se arrastra"""
        if self.old_pos and self.parent_window:
            delta = event.globalPos() - self.old_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.old_pos = event.globalPos()

class TitleBar(QWidget):
    """Barra de título personalizada que permite arrastrar la ventana"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.old_pos = None
    
    def mousePressEvent(self, event):
        """Inicia el arrastre de la ventana"""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
    
    def mouseMoveEvent(self, event):
        """Mueve la ventana cuando se arrastra"""
        if self.old_pos and self.parent_window:
            delta = event.globalPos() - self.old_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.old_pos = event.globalPos()

class TitleBar(QWidget):
    """Barra de título personalizada que permite arrastrar la ventana"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.old_pos = None
    
    def mousePressEvent(self, event):
        """Inicia el arrastre de la ventana"""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
    
    def mouseMoveEvent(self, event):
        """Mueve la ventana cuando se arrastra"""
        if self.old_pos and self.parent_window:
            delta = event.globalPos() - self.old_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.old_pos = event.globalPos()

class TitleBar(QWidget):
    """Barra de título personalizada que permite arrastrar la ventana"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.old_pos = None
    
    def mousePressEvent(self, event):
        """Inicia el arrastre de la ventana"""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
    
    def mouseMoveEvent(self, event):
        """Mueve la ventana cuando se arrastra"""
        if self.old_pos and self.parent_window:
            delta = event.globalPos() - self.old_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.old_pos = event.globalPos()
    
    def mouseReleaseEvent(self, event):
        """Detiene el arrastre"""
        self.old_pos = None

class LauncherWindow(QMainWindow):
    """Ventana principal del launcher"""
    
    def __init__(self):
        super().__init__()
        # Inicializar solo lo esencial para mostrar la ventana rápido
        self.auth_manager = AuthManager()
        self.credential_storage = CredentialStorage()
        self.minecraft_launcher = MinecraftLauncher()
        self.auth_thread = None
        self.load_versions_thread = None
        self.java_download_thread = None
        self.version_download_thread = None  # Thread para descargar versiones
        self.version_download_dialog = None  # Referencia al diálogo de descarga de versiones
        self.old_pos = None  # Para arrastrar la ventana
        self.title_bar = None  # Referencia a la barra de título
        
        # Valores por defecto (se cargarán después de mostrar la ventana)
        self.developer_mode = False
        
        # Inicializar UI básica (sin cargar imágenes pesadas)
        self.init_ui()
        
        # Inicializar widget de usuario con valores por defecto
        self.update_user_widget(None)
        
        # Diferir operaciones pesadas hasta después de mostrar la ventana
        # Usar QTimer para ejecutar después de que el evento loop esté corriendo
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._deferred_initialization)
    
    def _deferred_initialization(self):
        """Inicialización diferida: operaciones que no son críticas para mostrar la ventana"""
        # Cargar configuración (operaciones de archivo rápidas)
        self.load_last_selected_version()
        self.developer_mode = self.load_developer_mode()
        
        # Cargar imagen de fondo de forma diferida
        if self._bg_label:
            self._load_background_image("default")
        
        # Cargar credenciales guardadas (puede hacer llamadas de red)
        self.load_saved_credentials()
        
        # Cargar versiones después de mostrar la ventana
        self.load_versions_async()
    
    def init_ui(self):
        """Inicializa la interfaz de usuario"""
        self.setWindowTitle("[SOMOS GAMERS] LAUNCHER")
        
        # Ventana sin barra de título (frameless)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Establecer tamaño de ventana (reducir altura para menos espacio en blanco)
        self.resize(600, 650)
        
        # Centrar la ventana en la pantalla principal
        self.center_window()
        
        # Widget central con estilo gaming
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        
        # Cargar imagen de fondo
        bg_image_path = os.path.join(os.path.dirname(__file__), "assets", "default.png")
        if not os.path.exists(bg_image_path):
            # Intentar ruta relativa desde el directorio base
            bg_image_path = os.path.join("assets", "default.png")
        
        # Aplicar imagen de fondo con transparencia
        self._bg_label = None
        self._bg_animation = None
        self._current_bg_type = "default"  # default, custom, snapshot
        
        # Crear el label de fondo primero
        if os.path.exists(bg_image_path):
            self._bg_label = QLabel(central_widget)
            self._bg_label.setAlignment(Qt.AlignCenter)
            self._bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # No interceptar eventos del mouse
            self._bg_label.setScaledContents(True)
            self._bg_label.lower()  # Enviar al fondo
            
            # Función para redimensionar el label de fondo y aplicar máscara redondeada
            def update_bg_label_size():
                if self._bg_label:
                    self._bg_label.setGeometry(0, 0, central_widget.width(), central_widget.height())
                    # Aplicar máscara redondeada para respetar los bordes del widget central
                    radius = 15  # Mismo radio que el border-radius del widget central
                    # Crear path redondeado
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, central_widget.width(), central_widget.height(), radius, radius)
                    # Convertir path a región: toFillPolygon devuelve QPolygonF, necesitamos QPolygon
                    from PyQt5.QtGui import QPolygon
                    from PyQt5.QtCore import QPoint
                    polygonF = path.toFillPolygon()
                    # Convertir QPolygonF a QPolygon (enteros)
                    polygon = QPolygon([QPoint(int(p.x()), int(p.y())) for p in polygonF])
                    region = QRegion(polygon)
                    self._bg_label.setMask(region)
            
            # Guardar referencia para poder actualizarla después
            self._update_bg_label_size = update_bg_label_size
            
            # Conectar el resize del widget central para actualizar el label de fondo
            original_resize = central_widget.resizeEvent
            def resize_with_bg(event):
                update_bg_label_size()
                if original_resize:
                    original_resize(event)
            central_widget.resizeEvent = resize_with_bg
            
            # Establecer tamaño inicial después de que el widget esté completamente inicializado
            QApplication.processEvents()
            update_bg_label_size()
        
        # Método para cargar imagen de fondo (debe definirse después de crear _bg_label)
        self._load_background_image = self._create_bg_loader()
        
        # La imagen de fondo se cargará de forma diferida en _deferred_initialization()
        
        # Aplicar estilos base
        base_style = """
            QMainWindow {
                background: transparent;
            }
            #centralWidget {
                background-color: #1a0d2e;
                border-radius: 15px;
                border: 2px solid #8b5cf6;
            }
        """
        
        # Si no hay imagen, aplicar el gradiente
        if not os.path.exists(bg_image_path):
            base_style = """
            QMainWindow {
                background: transparent;
            }
            #centralWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border-radius: 15px;
                border: 2px solid #8b5cf6;
            }
        """
        
        self.setStyleSheet(base_style + """
            QLabel {
                color: #e9d5ff;
                background: transparent;
            }
            QLabel#titleLabel {
                color: #c084fc;
                font-size: 28px;
                font-weight: bold;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
                border: 2px solid #a78bfa;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5b21b6, stop:1 #4c1d95);
            }
            QPushButton:disabled {
                background: #3f3f3f;
                color: #888888;
                border: 2px solid #555555;
            }
            QPushButton#closeButton {
                background: #dc2626;
                border: 1px solid #ef4444;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#closeButton:hover {
                background: #ef4444;
                border: 1px solid #f87171;
            }
            QPushButton#minimizeButton {
                background: #6b7280;
                border: 1px solid #9ca3af;
                border-radius: 3px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#minimizeButton:hover {
                background: #9ca3af;
                border: 1px solid #d1d5db;
            }
            #titleBar {
                background: transparent;
            }
            QComboBox {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
                min-height: 25px;
            }
            QComboBox:hover {
                border: 2px solid #8b5cf6;
            }
            QComboBox::drop-down {
                border: none;
                background: #5b21b6;
            }
            QComboBox QAbstractItemView {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #8b5cf6;
                selection-background-color: #7c3aed;
            }
            QTextEdit {
                background: rgba(15, 10, 26, 0.7);
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
            }
            QProgressBar {
                background: #0f0a1a;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                text-align: center;
                color: #e9d5ff;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:1 #a78bfa);
                border-radius: 3px;
            }
            QMessageBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border: 2px solid #8b5cf6;
                border-radius: 10px;
            }
            QMessageBox QLabel {
                color: #e9d5ff;
                background: transparent;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                min-height: 30px;
            }
            QMessageBox QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
                border: 2px solid #a78bfa;
            }
            QMessageBox QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5b21b6, stop:1 #4c1d95);
            }
        """)
        
        # Layout principal
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        layout.setContentsMargins(20, 5, 20, 5)  # Sin márgenes arriba y abajo
        layout.setSpacing(15)
        
        # Barra de título personalizada (arrastrable)
        self.title_bar = TitleBar(self)
        self.title_bar.setFixedHeight(35)
        self.title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(5)
        self.title_bar.setLayout(title_bar_layout)
        
        # Título (expandible para centrar)
        title = QLabel("[SG] LAUNCHER ")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_bar_layout.addWidget(title, 1)  # Stretch factor 1 para que ocupe el espacio
        
        # Widget de usuario (arriba a la derecha)
        self.user_widget = QWidget()
        self.user_widget.setObjectName("userWidget")
        user_widget_layout = QHBoxLayout()
        user_widget_layout.setContentsMargins(0, 0, 0, 0)
        user_widget_layout.setSpacing(5)
        
        self.user_avatar_label = QLabel()
        self.user_avatar_label.setFixedSize(32, 32)
        self.user_avatar_label.setScaledContents(True)
        self.user_avatar_label.setVisible(False)
        user_widget_layout.addWidget(self.user_avatar_label)
        
        self.user_name_label = QLabel("Iniciar sesión")
        self.user_name_label.setObjectName("userNameLabel")
        self.user_name_label.setStyleSheet("""
            QLabel#userNameLabel {
                color: #e9d5ff;
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 5px;
                background: transparent;
            }
            QLabel#userNameLabel:hover {
                background: rgba(139, 92, 246, 0.3);
            }
        """)
        self.user_name_label.setCursor(Qt.PointingHandCursor)
        self.user_name_label.mousePressEvent = lambda e: self._on_user_widget_clicked()
        user_widget_layout.addWidget(self.user_name_label)
        
        self.user_widget.setLayout(user_widget_layout)
        title_bar_layout.addWidget(self.user_widget)
        
        # Botones de ventana (más pequeños)
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.close)
        title_bar_layout.addWidget(close_btn)
        
        layout.addWidget(self.title_bar)
        
        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")  # Label para mostrar el estado de la descarga
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        
        # Área de mensajes
        self.message_area = QTextEdit()
        self.message_area.setReadOnly(True)
        self.message_area.setMaximumHeight(300)  
        layout.addWidget(self.message_area)
        
        # Selector de versión de Minecraft
        version_layout = QHBoxLayout()
        version_layout.setSpacing(5)  # Espaciado entre elementos
        version_layout.setAlignment(Qt.AlignVCenter)  # Alinear verticalmente al centro
        version_label = QLabel("Versión Minecraft:")
        version_label.setFixedHeight(40)  # Misma altura que combo y botón
        version_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Alinear texto verticalmente
        version_label.setStyleSheet("font-size: 14px;")  # Mismo tamaño de fuente
        version_layout.addWidget(version_label)
        
        version_layout.addStretch()  # Empujar el combo a la derecha
        
        self.version_combo = QComboBox()
        self.version_combo.setFixedSize(400, 40)  # Misma altura que los botones
        self.version_combo.setStyleSheet("font-size: 14px;")  # Fuente más grande
        # NO conectar signals aquí - se conectarán después de cargar las versiones
        version_layout.addWidget(self.version_combo)
        
        add_version_button = QPushButton("+")
        add_version_button.setToolTip("Añadir nueva versión")
        add_version_button.setFixedSize(40, 40)  # Misma altura que combo y label
        add_version_button.setStyleSheet("font-size: 24px; padding: 5px; font-weight: bold;")
        
        # Crear menú desplegable con opciones
        add_version_menu = QMenu(self)
        
        # Opción 1: Vanilla
        vanilla_action = add_version_menu.addAction("Vanilla")
        vanilla_action.triggered.connect(self.show_add_version_dialog)
        
        # Opción 2: NeoForge
        neoforge_action = add_version_menu.addAction("NeoForge")
        neoforge_action.triggered.connect(self.show_neoforge_dialog)
        
        # Opción 3: Custom (Perfiles remotos)
        custom_action = add_version_menu.addAction("Custom")
        custom_action.triggered.connect(self.show_custom_profile_dialog)
        
        # Conectar el botón al menú
        add_version_button.setMenu(add_version_menu)
        
        version_layout.addWidget(add_version_button)
        
        layout.addLayout(version_layout)
        
        # Selector de versión de Java
        java_container = QVBoxLayout()
        java_container.setSpacing(5)
        
        java_layout = QHBoxLayout()
        java_layout.setSpacing(5)  # Mismo espaciado que el layout de versiones
        java_layout.setAlignment(Qt.AlignVCenter)  # Alinear verticalmente al centro
        java_label = QLabel("Versión Java:")
        java_label.setFixedHeight(40)  # Misma altura que combo y botón
        java_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Alinear texto verticalmente
        java_label.setStyleSheet("font-size: 14px;")  # Mismo tamaño de fuente
        java_layout.addWidget(java_label)
        
        java_layout.addStretch()  # Empujar el combo a la derecha
        
        self.java_combo = QComboBox()
        self.java_combo.setFixedSize(400, 40)  # Misma altura que los botones
        self.java_combo.setStyleSheet("font-size: 14px;")  # Fuente más grande
        java_layout.addWidget(self.java_combo)
        
        refresh_java_button = QPushButton("🔄")
        refresh_java_button.setToolTip("Actualizar lista de Java")
        refresh_java_button.clicked.connect(self.load_java_versions)
        refresh_java_button.setFixedSize(40, 40)  # Misma altura que combo y label
        refresh_java_button.setStyleSheet("font-size: 20px; padding: 5px;")
        java_layout.addWidget(refresh_java_button)
        
        java_container.addLayout(java_layout)
        
        # Label para mostrar la versión de Java requerida (debajo del dropdown)
        self.java_required_label = QLabel("")
        self.java_required_label.setStyleSheet("color: blue; font-style: italic;")
        self.java_required_label.setContentsMargins(0, 0, 0, 0)
        java_container.addWidget(self.java_required_label)
        
        layout.addLayout(java_container)
        
        # Cargar versiones de Java inmediatamente (es rápido)
        self.load_java_versions()
        
        # Bloquear signals antes de agregar el item temporal
        self.version_combo.blockSignals(True)
        
        # Mostrar mensaje inicial mientras se cargan las versiones
        self.version_combo.addItem("Cargando versiones...")
        self.version_combo.setEnabled(False)
        
        # Conectar save_selected_version DESPUÉS de cargar las versiones
        # para evitar que se guarde durante la carga inicial
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        
        # Desbloquear signals después de conectar (las versiones se cargarán después)
        
        # Botón de lanzar
        button_layout = QHBoxLayout()
        
        self.launch_button = QPushButton("Lanzar Minecraft")
        self.launch_button.clicked.connect(self.launch_minecraft)
        # El botón se habilita cuando hay credenciales guardadas
        button_layout.addWidget(self.launch_button)
        
        layout.addLayout(button_layout)
        
        # Estado de Minecraft
        self.minecraft_status = QLabel("")
        self.minecraft_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.minecraft_status)
        
        self.check_minecraft_status()
    
    def check_minecraft_status(self):
        """Verifica si Minecraft está instalado"""
        if self.minecraft_launcher.check_minecraft_installed():
            self.minecraft_status.setText("✓ Minecraft detectado")
            self.minecraft_status.setStyleSheet("color: green;")
        else:
            self.minecraft_status.setText("✗ Minecraft no detectado")
            self.minecraft_status.setStyleSheet("color: red;")
    
    def load_versions_async(self, select_version=None):
        """Inicia la carga asíncrona de versiones de Minecraft"""
        # Guardar la versión a seleccionar después de cargar
        self._version_to_select = select_version
        if select_version:
            self._version_to_select_was_set = True  # Marcar que es una descarga nueva
        
        # Mostrar barra de progreso
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Modo indeterminado
        
        # Crear y conectar thread
        self.load_versions_thread = LoadVersionsThread(self.minecraft_launcher)
        self.load_versions_thread.finished.connect(self.on_versions_loaded)
        self.load_versions_thread.error.connect(self.on_versions_error)
        self.load_versions_thread.start()
    
    def _organize_versions_tree(self, versions):
        """Organiza las versiones en un árbol jerárquico"""
        vanilla_versions = {}  # {version_name: version_id}
        custom_versions = {}  # {parent_version: [version_id, ...]}
        snapshot_versions = {}  # {parent_version: [version_id, ...]}
        orphan_snapshots = []  # [version_id, ...]
        
        # Analizar cada versión
        for version_id in versions:
            try:
                # Leer el JSON original sin mergear para verificar inheritsFrom
                json_path = os.path.join(
                    self.minecraft_launcher.minecraft_path, 
                    "versions", 
                    version_id, 
                    f"{version_id}.json"
                )
                
                if not os.path.exists(json_path):
                    continue
                
                with open(json_path, 'r', encoding='utf-8') as f:
                    version_json_original = json.load(f)
                
                # Verificar si es snapshot
                is_snapshot = (
                    "snapshot" in version_id.lower() or
                    version_json_original.get("type", "").lower() == "snapshot" or
                    "snapshot" in version_json_original.get("id", "").lower()
                )
                
                # Verificar si tiene herencia (del JSON original, no mergeado)
                inherits_from = version_json_original.get("inheritsFrom")
                
                if is_snapshot:
                    if inherits_from:
                        # Snapshot con versión vanilla padre
                        if inherits_from not in snapshot_versions:
                            snapshot_versions[inherits_from] = []
                        snapshot_versions[inherits_from].append(version_id)
                    else:
                        # Snapshot sin versión vanilla (huérfano)
                        orphan_snapshots.append(version_id)
                elif inherits_from:
                    # Versión custom (neoforge, forge, etc.) - NO es vanilla
                    if inherits_from not in custom_versions:
                        custom_versions[inherits_from] = []
                    custom_versions[inherits_from].append(version_id)
                else:
                    # Versión vanilla (sin inheritsFrom y no snapshot)
                    vanilla_versions[version_id] = version_id
            except Exception as e:
                # Si hay error, tratar como vanilla por defecto
                print(f"Error analizando versión {version_id}: {e}")
                vanilla_versions[version_id] = version_id
        
        # Ordenar versiones vanilla (por número de versión, descendente)
        def version_sort_key(v):
            # Extraer números de versión para ordenar correctamente
            parts = v.split('.')
            try:
                major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                return (major, minor, patch)
            except:
                return (0, 0, 0)
        
        sorted_vanilla = sorted(vanilla_versions.keys(), key=version_sort_key, reverse=True)
        
        # Construir lista ordenada en árbol
        organized = []
        version_to_index = {}  # Para mapear version_id a índice en el combo
        
        # Agregar versiones vanilla con sus hijos
        for vanilla_id in sorted_vanilla:
            # Agregar versión vanilla
            display_name = f"Vanilla {vanilla_id}"
            organized.append((display_name, vanilla_id))
            version_to_index[vanilla_id] = len(organized) - 1
            
            # Agregar versiones custom hijas
            if vanilla_id in custom_versions:
                for custom_id in sorted(custom_versions[vanilla_id]):
                    display_name = f"  - Custom {custom_id}"
                    organized.append((display_name, custom_id))
                    version_to_index[custom_id] = len(organized) - 1
            
            # Agregar snapshots hijas
            if vanilla_id in snapshot_versions:
                for snapshot_id in sorted(snapshot_versions[vanilla_id]):
                    display_name = f"  - Snapshot {snapshot_id}"
                    organized.append((display_name, snapshot_id))
                    version_to_index[snapshot_id] = len(organized) - 1
        
        # Agregar snapshots huérfanos al final
        for snapshot_id in sorted(orphan_snapshots):
            display_name = f"Snapshot {snapshot_id}"
            organized.append((display_name, snapshot_id))
            version_to_index[snapshot_id] = len(organized) - 1
        
        return organized, version_to_index
    
    def _get_custom_profiles(self):
        """Obtiene la lista de perfiles custom instalados"""
        profiles = []
        profiles_dir = os.path.join(self.minecraft_launcher.minecraft_path, "profiles")
        
        if not os.path.exists(profiles_dir):
            return profiles
        
        for profile_id in os.listdir(profiles_dir):
            profile_path = os.path.join(profiles_dir, profile_id)
            if os.path.isdir(profile_path):
                # Buscar el archivo launcher_profiles.json para obtener el nombre
                launcher_profiles_path = os.path.join(profile_path, "launcher_profiles.json")
                profile_name = profile_id  # Por defecto usar el ID
                
                if os.path.exists(launcher_profiles_path):
                    try:
                        with open(launcher_profiles_path, 'r', encoding='utf-8') as f:
                            launcher_profiles = json.load(f)
                            # Intentar obtener el nombre del perfil
                            profiles_data = launcher_profiles.get("profiles", {})
                            if profiles_data:
                                # Tomar el primer perfil
                                first_profile = list(profiles_data.values())[0]
                                profile_name = first_profile.get("name", profile_id)
                    except:
                        pass
                
                # Verificar que tenga una versión instalada
                versions_dir = os.path.join(profile_path, "versions")
                if os.path.exists(versions_dir):
                    # Buscar cualquier versión instalada
                    for version_folder in os.listdir(versions_dir):
                        version_path = os.path.join(versions_dir, version_folder)
                        if os.path.isdir(version_path):
                            version_json = os.path.join(version_path, f"{version_folder}.json")
                            if os.path.exists(version_json):
                                # Este perfil tiene una versión instalada
                                profiles.append({
                                    "id": profile_id,
                                    "name": profile_name,
                                    "path": profile_path
                                })
                                break
        
        return profiles
    
    def on_versions_loaded(self, versions):
        """Se llama cuando las versiones se han cargado"""
        # Ocultar barra de progreso
        self.progress_bar.setVisible(False)
        
        # Bloquear signals temporalmente para evitar que se guarde durante la carga
        self.version_combo.blockSignals(True)
        
        # Conectar signals solo cuando ya tenemos versiones reales
        # Desconectar primero si ya estaban conectados (por si acaso)
        try:
            self.version_combo.currentTextChanged.disconnect(self.on_version_changed)
        except:
            pass
        try:
            self.version_combo.currentTextChanged.disconnect(self.save_selected_version)
        except:
            pass
        
        # Conectar signals ahora
        self.version_combo.currentTextChanged.connect(self.on_version_changed)
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        
        self.version_combo.clear()
        
        # Primero agregar perfiles custom (sin jerarquía, al principio)
        custom_profiles = self._get_custom_profiles()
        profile_count = 0
        for profile in custom_profiles:
            display_name = f"Perfil {profile['name']}"
            # Usar un formato especial para identificar perfiles custom: "profile:{profile_id}"
            profile_id = f"profile:{profile['id']}"
            self.version_combo.addItem(display_name, profile_id)
            profile_count += 1
        
        if versions:
            # Organizar versiones en árbol
            organized_versions, version_to_index = self._organize_versions_tree(versions)
            
            # Agregar versiones organizadas al combo (después de los perfiles custom)
            for display_name, version_id in organized_versions:
                self.version_combo.addItem(display_name, version_id)
            
            self.add_message(f"Versiones de Minecraft disponibles: {len(versions)} (solo descargadas)")
            
            # Determinar qué versión seleccionar
            version_to_select = None
            if hasattr(self, '_version_to_select') and self._version_to_select:
                # Si hay una versión específica a seleccionar (después de descargar)
                version_to_select = self._version_to_select
                self._version_to_select = None  # Limpiar
                print(f"[INFO] Seleccionando versión recién descargada: {version_to_select}")
            else:
                # Si no, cargar la última versión seleccionada
                version_to_select = self.load_last_selected_version()
            
            # Seleccionar la versión
            if version_to_select and version_to_select in version_to_index:
                index = version_to_index[version_to_select]
                # Bloquear signals temporalmente para evitar que on_version_changed se dispare
                self.version_combo.blockSignals(True)
                self.version_combo.setCurrentIndex(index)
                self.version_combo.blockSignals(False)
                # Determinar si es una versión recién descargada o restaurada
                # (verificamos si _version_to_select existía antes de limpiarlo)
                was_new_download = hasattr(self, '_version_to_select_was_set') and self._version_to_select_was_set
                if was_new_download:
                    self.add_message(f"Versión {version_to_select} seleccionada")
                    self._version_to_select_was_set = False  # Limpiar flag
                else:
                    self.add_message(f"Versión restaurada: {version_to_select}")
                # Actualizar el fondo según la versión seleccionada (sin hacer merge)
                display_name = self.version_combo.currentText()
                self._update_background_for_version(version_to_select, display_name)
                # Llamar manualmente a on_version_changed para cargar requisitos de Java
                # pero solo después de que todo esté listo
                QApplication.processEvents()  # Procesar eventos pendientes
                self.on_version_changed(display_name)
            else:
                # Si no hay versión guardada o no está disponible, seleccionar la primera
                if version_to_select:
                    self.add_message(f"Versión '{version_to_select}' no está disponible, seleccionando primera versión")
                # Actualizar el fondo para la primera versión seleccionada (sin hacer merge)
                if organized_versions:
                    first_version_id = organized_versions[0][1]
                    first_display_name = organized_versions[0][0]
                    # Bloquear signals temporalmente
                    self.version_combo.blockSignals(True)
                    self.version_combo.setCurrentIndex(0)
                    self.version_combo.blockSignals(False)
                    self._update_background_for_version(first_version_id, first_display_name)
                    # Llamar manualmente a on_version_changed para cargar requisitos de Java
                    QApplication.processEvents()
                    self.on_version_changed(first_display_name)
            self.version_combo.setEnabled(True)
        else:
            self.version_combo.addItem("No hay versiones disponibles")
            self.version_combo.setEnabled(False)
            self.add_message("No se encontraron versiones de Minecraft descargadas")
        
        # Desbloquear signals después de cargar
        self.version_combo.blockSignals(False)
    
    def on_versions_error(self, error_msg):
        """Se llama cuando hay un error cargando las versiones"""
        # Ocultar barra de progreso
        self.progress_bar.setVisible(False)
        
        self.version_combo.clear()
        self.version_combo.addItem("Error cargando versiones")
        self.version_combo.setEnabled(False)
        self.add_message(f"Error cargando versiones: {error_msg}")
    
    def show_add_version_dialog(self):
        """Muestra el diálogo para añadir una nueva versión Vanilla"""
        dialog = VersionDownloadDialog(self, self.minecraft_launcher)
        # Guardar referencia al diálogo
        self.version_download_dialog = dialog
        
        result = dialog.exec_()
        
        # Limpiar referencia al diálogo
        if self.version_download_dialog == dialog:
            self.version_download_dialog = None
    
    def show_neoforge_dialog(self):
        """Muestra el diálogo para añadir una nueva versión NeoForge (placeholder)"""
        # Por ahora no hace nada
        QMessageBox.information(
            self,
            "NeoForge",
            "La instalación de NeoForge estará disponible próximamente."
        )
    
    def show_custom_profile_dialog(self):
        """Muestra el diálogo para añadir perfiles personalizados desde URL"""
        dialog = CustomProfileDialog(self, self.minecraft_launcher)
        result = dialog.exec_()
    
    def load_versions(self):
        """Carga las versiones de Minecraft disponibles (solo las descargadas) - versión síncrona para el botón refresh"""
        # Bloquear signals temporalmente para evitar que se guarde durante la carga
        self.version_combo.blockSignals(True)
        
        self.version_combo.clear()
        self.version_combo.addItem("Cargando...")
        self.version_combo.setEnabled(False)
        
        # Mostrar barra de progreso
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Modo indeterminado
        
        # Forzar actualización de la UI
        QApplication.processEvents()
        
        # Solo mostrar versiones completamente descargadas (usar strict_check=False para incluir versiones recién descargadas)
        versions = self.minecraft_launcher.get_available_versions(only_downloaded=True, strict_check=False)
        
        # Ocultar barra de progreso
        self.progress_bar.setVisible(False)
        
        if versions:
            self.version_combo.clear()
            
            # Organizar versiones en árbol
            organized_versions, version_to_index = self._organize_versions_tree(versions)
            
            # Agregar versiones organizadas al combo
            for display_name, version_id in organized_versions:
                self.version_combo.addItem(display_name, version_id)
            
            self.add_message(f"Versiones de Minecraft disponibles: {len(versions)} (solo descargadas)")
            
            # Cargar la última versión seleccionada
            last_version = self.load_last_selected_version()
            if last_version and last_version in version_to_index:
                index = version_to_index[last_version]
                # Bloquear signals temporalmente para evitar que on_version_changed se dispare
                self.version_combo.blockSignals(True)
                self.version_combo.setCurrentIndex(index)
                self.version_combo.blockSignals(False)
                self.add_message(f"Versión restaurada: {last_version}")
                # Actualizar el fondo según la versión restaurada (sin hacer merge)
                display_name = self.version_combo.currentText()
                self._update_background_for_version(last_version, display_name)
                # Llamar manualmente a on_version_changed para cargar requisitos de Java
                # pero solo después de que todo esté listo
                QApplication.processEvents()  # Procesar eventos pendientes
                self.on_version_changed(display_name)
            else:
                # Si no hay versión guardada o no está disponible, seleccionar la primera
                if last_version:
                    self.add_message(f"Versión guardada '{last_version}' no está disponible, seleccionando primera versión")
                # Actualizar el fondo para la primera versión seleccionada (sin hacer merge)
                if organized_versions:
                    first_version_id = organized_versions[0][1]
                    first_display_name = organized_versions[0][0]
                    # Bloquear signals temporalmente
                    self.version_combo.blockSignals(True)
                    self.version_combo.setCurrentIndex(0)
                    self.version_combo.blockSignals(False)
                    self._update_background_for_version(first_version_id, first_display_name)
                    # Llamar manualmente a on_version_changed para cargar requisitos de Java
                    QApplication.processEvents()
                    self.on_version_changed(first_display_name)
            self.version_combo.setEnabled(True)
        else:
            self.version_combo.clear()
            self.version_combo.addItem("No hay versiones disponibles")
            self.version_combo.setEnabled(False)
            self.add_message("No se encontraron versiones de Minecraft descargadas")
        
        # Desbloquear signals después de cargar
        self.version_combo.blockSignals(False)
    
    def save_selected_version(self, version: str):
        """Guarda la versión seleccionada. Crea el archivo si no existe."""
        # Obtener el ID real de la versión (sin prefijos)
        version_id = self.version_combo.currentData()
        if not version_id:
            # Fallback: usar el texto si no hay data
            version_id = version
        
        # No guardar valores temporales o inválidos
        invalid_values = [
            "No hay versiones disponibles",
            "Cargando versiones...",
            "Cargando...",
            "Error cargando versiones"
        ]
        
        if not version_id or version_id in invalid_values:
            return
        
        try:
            import json
            from config import CONFIG_FILE
            
            config = {}
            if CONFIG_FILE.exists():
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except (json.JSONDecodeError, IOError):
                    # Si el archivo está corrupto, empezar con configuración por defecto
                    config = {}
            
            config['last_selected_version'] = version_id
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error guardando versión seleccionada: {e}")
    
    def load_last_selected_version(self) -> str:
        """Carga la última versión seleccionada. Crea el archivo con valores por defecto si no existe."""
        try:
            import json
            from config import CONFIG_FILE
            
            if not CONFIG_FILE.exists():
                # Crear archivo de configuración con valores por defecto
                default_config = {
                    "last_selected_version": None,
                    "show_full_java_path": False
                }
                try:
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(default_config, f, indent=2)
                except Exception as e:
                    print(f"Error creando archivo de configuración: {e}")
                return None
            
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            return config.get('last_selected_version')
        except Exception as e:
            print(f"Error cargando versión seleccionada: {e}")
            return None
    
    def load_java_versions(self):
        """Carga las versiones de Java disponibles"""
        self.java_combo.clear()
        java_installations = self.minecraft_launcher.find_java_installations()
        
        # Leer configuración para determinar si mostrar la ruta completa
        show_full_path = False
        try:
            import json
            from config import CONFIG_FILE
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    show_full_path = config.get('show_full_java_path', False)
        except Exception:
            pass  # Si hay error, usar valor por defecto (False)
        
        if java_installations:
            # Ordenar por versión (mayor a menor)
            sorted_versions = sorted(java_installations.items(), key=lambda x: x[0], reverse=True)
            for version, path in sorted_versions:
                if show_full_path:
                    display_text = f"Java {version} ({path})"
                else:
                    display_text = f"Java {version}"
                self.java_combo.addItem(display_text, path)  # Guardar el path como data
            
            self.add_message(f"Versiones de Java disponibles: {len(java_installations)}")
            # Seleccionar la versión más reciente por defecto
            if sorted_versions:
                self.java_combo.setCurrentIndex(0)
        else:
            self.java_combo.addItem("No hay Java disponible")
            self.java_combo.setEnabled(False)
            self.add_message("No se encontraron instalaciones de Java")
    
    def download_java_async(self, java_version: int, callback=None):
        """
        Inicia la descarga de Java de forma asíncrona usando la barra de progreso principal.
        callback: función opcional que se llama cuando termina (success: bool, java_path: str)
        """
        # Inicializar variables de estado
        self._java_download_success = False
        self._downloaded_java_path = None
        self._java_download_callback = callback
        
        # Mostrar barra de progreso
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Descargando Java {java_version}...")
        
        # Deshabilitar botones mientras descarga
        self.launch_button.setEnabled(False)
        
        # Crear y conectar thread
        downloader = JavaDownloader(self.minecraft_launcher.minecraft_path)
        self.java_download_thread = JavaDownloadThread(downloader, java_version)
        self.java_download_thread.progress.connect(self.on_java_download_progress)
        self.java_download_thread.finished.connect(self.on_java_download_finished)
        self.java_download_thread.error.connect(self.on_java_download_error)
        self.java_download_thread.message.connect(self.on_java_download_message)
        self.java_download_thread.start()
    
    def _complete_java_download(self):
        """Completa el proceso de descarga de Java"""
        # Ocultar barra de progreso
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        
        # Rehabilitar botones
        self.launch_button.setEnabled(True)
        
        # Llamar callback si existe
        if hasattr(self, '_java_download_callback') and self._java_download_callback:
            self._java_download_callback(self._java_download_success, self._downloaded_java_path)
    
    def on_java_download_progress(self, downloaded: int, total: int):
        """Actualiza la barra de progreso durante la descarga de Java"""
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress_bar.setValue(percent)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.progress_label.setText(f"Descargando Java: {mb_downloaded:.1f} MB / {mb_total:.1f} MB ({percent}%)")
        else:
            self.progress_bar.setRange(0, 0)  # Modo indeterminado
    
    def on_version_download_progress(self, downloaded: int, total: int, message: str):
        """Actualiza el progreso durante la descarga de una versión"""
        print(f"[INFO] Progreso de descarga: {downloaded}/{total} - {message}")
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(downloaded)
        if hasattr(self, 'progress_label'):
            self.progress_label.setVisible(True)
            self.progress_label.setText(message)
    
    def on_version_download_finished(self, version_id: str):
        """Se llama cuando la descarga de una versión se completa"""
        print(f"[INFO] Descarga de versión completada: {version_id}")
        try:
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)
            if hasattr(self, 'progress_label'):
                self.progress_label.setVisible(False)
            self.add_message(f"Versión {version_id} descargada correctamente")
            
            # Esperar a que el thread termine completamente antes de limpiarlo
            if hasattr(self, 'version_download_thread') and self.version_download_thread:
                # Esperar hasta que el thread termine (máximo 5 segundos)
                if self.version_download_thread.isRunning():
                    print(f"[INFO] Esperando a que el thread termine...")
                    if not self.version_download_thread.wait(5000):  # Esperar máximo 5 segundos
                        print(f"[WARN] El thread no terminó en 5 segundos, forzando limpieza")
                    else:
                        print(f"[INFO] Thread de descarga finalizado correctamente")
                
                # Limpiar el thread después de que haya terminado
                self.version_download_thread.deleteLater()
                self.version_download_thread = None
            
            # Cerrar el diálogo de descarga si está abierto
            if hasattr(self, 'version_download_dialog') and self.version_download_dialog:
                print(f"[INFO] Cerrando diálogo de descarga")
                self.version_download_dialog.accept()
                self.version_download_dialog = None
            
            # Refrescar la lista de versiones y seleccionar la nueva versión
            self.load_versions_async(select_version=version_id)
        except Exception as e:
            print(f"[ERROR] Error en on_version_download_finished: {e}")
            import traceback
            traceback.print_exc()
    
    def on_version_download_error(self, error: str):
        """Se llama cuando hay un error en la descarga de una versión"""
        print(f"[ERROR] Error descargando versión: {error}")
        try:
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)
            if hasattr(self, 'progress_label'):
                self.progress_label.setVisible(False)
            self.add_message(f"Error descargando versión: {error}")
            
            # Esperar a que el thread termine completamente antes de limpiarlo
            if hasattr(self, 'version_download_thread') and self.version_download_thread:
                # Esperar hasta que el thread termine (máximo 5 segundos)
                if self.version_download_thread.isRunning():
                    print(f"[INFO] Esperando a que el thread termine (error)...")
                    if not self.version_download_thread.wait(5000):  # Esperar máximo 5 segundos
                        print(f"[WARN] El thread no terminó en 5 segundos, forzando limpieza")
                    else:
                        print(f"[INFO] Thread de descarga finalizado (con error)")
                
                # Limpiar el thread después de que haya terminado
                self.version_download_thread.deleteLater()
                self.version_download_thread = None
            
            # Cerrar el diálogo de descarga si está abierto (aunque haya error)
            if hasattr(self, 'version_download_dialog') and self.version_download_dialog:
                print(f"[INFO] Cerrando diálogo de descarga (error)")
                self.version_download_dialog.accept()
                self.version_download_dialog = None
            
            QMessageBox.critical(self, "Error", f"No se pudo descargar la versión:\n{error}")
        except Exception as e:
            print(f"[ERROR] Error en on_version_download_error: {e}")
            import traceback
            traceback.print_exc()
    
    def on_java_download_finished(self, java_path: str):
        """Se llama cuando la descarga de Java se completa"""
        self.progress_bar.setValue(100)
        self.progress_label.setText("Descarga completada!")
        self._java_download_success = True
        self._downloaded_java_path = java_path
        self.add_message(f"Java descargada correctamente: {java_path}")
        self._complete_java_download()
    
    def on_java_download_error(self, error_msg: str):
        """Se llama cuando hay un error en la descarga de Java"""
        self.progress_label.setText(f"Error: {error_msg}")
        self._java_download_success = False
        self.add_message(f"Error descargando Java: {error_msg}")
        QMessageBox.critical(self, "Error", f"No se pudo descargar Java:\n{error_msg}")
        self._complete_java_download()
    
    def on_java_download_message(self, message: str):
        """Se llama cuando hay un mensaje de la descarga de Java"""
        self.progress_label.setText(message)
        self.add_message(message)
    
    def on_version_changed(self, version_name: str):
        """Se llama cuando cambia la versión de Minecraft seleccionada"""
        # Ignorar valores temporales o inválidos
        invalid_values = [
            "No hay versiones disponibles",
            "Cargando versiones...",
            "Cargando...",
            "Error cargando versiones"
        ]
        
        if version_name in invalid_values:
            self.java_required_label.setText("")
            return
        
        # Obtener el ID real de la versión (sin prefijos)
        version_id = self.version_combo.currentData()
        if not version_id:
            # Fallback: intentar extraer del texto si no hay data
            version_id = version_name
        
        if not version_id or version_id in invalid_values:
            self.java_required_label.setText("")
            return
        
        # Detectar si es un perfil custom
        game_dir = None
        actual_version_id = version_id
        if version_id.startswith("profile:"):
            profile_id = version_id.replace("profile:", "")
            game_dir = os.path.join(self.minecraft_launcher.minecraft_path, "profiles", profile_id)
            # Leer launcher_profiles.json para obtener lastVersionId
            launcher_profiles_path = os.path.join(game_dir, "launcher_profiles.json")
            if os.path.exists(launcher_profiles_path):
                try:
                    with open(launcher_profiles_path, 'r', encoding='utf-8') as f:
                        launcher_profiles = json.load(f)
                    profiles_data = launcher_profiles.get("profiles", {})
                    if profiles_data:
                        # Tomar el primer perfil y obtener lastVersionId
                        first_profile = list(profiles_data.values())[0]
                        last_version_id = first_profile.get("lastVersionId")
                        if last_version_id:
                            actual_version_id = last_version_id
                except Exception as e:
                    print(f"[WARN] Error leyendo launcher_profiles.json: {e}")
                    # Fallback: buscar cualquier versión instalada
                    versions_dir = os.path.join(game_dir, "versions")
                    if os.path.exists(versions_dir):
                        for version_folder in os.listdir(versions_dir):
                            version_path = os.path.join(versions_dir, version_folder)
                            if os.path.isdir(version_path):
                                version_json_file = os.path.join(version_path, f"{version_folder}.json")
                                if os.path.exists(version_json_file):
                                    actual_version_id = version_folder
                                    break
        
        # Detectar tipo de versión y cambiar fondo si es necesario
        self._update_background_for_version(actual_version_id, version_name)
        
        # Cargar el JSON de la versión para obtener los requisitos de Java
        version_json = self.minecraft_launcher._load_version_json(actual_version_id, game_dir=game_dir)
        if version_json:
            required_java = self.minecraft_launcher.get_required_java_version(version_json)
            if required_java:
                self.java_required_label.setText(f"Requiere Java {required_java} o superior")
                
                # Intentar seleccionar automáticamente la versión de Java adecuada
                self._auto_select_java(required_java)
            else:
                self.java_required_label.setText("Requisitos de Java no especificados")
        else:
            self.java_required_label.setText("")
    
    def _auto_select_java(self, required_version: int):
        """Selecciona automáticamente la versión de Java adecuada"""
        java_installations = self.minecraft_launcher.find_java_installations()
        
        if not java_installations:
            return
        
        # Buscar la versión exacta o la más cercana que cumpla el requisito
        suitable_versions = {v: path for v, path in java_installations.items() 
                           if v >= required_version}
        
        if suitable_versions:
            # Usar la versión más baja que cumpla el requisito (más compatible)
            best_version = min(suitable_versions.keys())
            best_path = suitable_versions[best_version]
            
            # Buscar el índice en el combo box
            for i in range(self.java_combo.count()):
                if self.java_combo.itemData(i) == best_path:
                    self.java_combo.setCurrentIndex(i)
                    self.add_message(f"Java {best_version} seleccionada automáticamente (requiere {required_version}+)")
                    break
        else:
            # No hay versión adecuada, mostrar advertencia
            available_versions = sorted(java_installations.keys())
            self.java_required_label.setText(
                f"⚠ Requiere Java {required_version}+ (disponibles: {', '.join(map(str, available_versions))})"
            )
            self.java_required_label.setStyleSheet("color: orange; font-style: italic;")
    
    def add_message(self, message: str):
        """Añade un mensaje al área de mensajes"""
        self.message_area.append(f"[{time.strftime('%H:%M:%S')}] {message}")
    
    def _create_bg_loader(self):
        """Crea la función para cargar imágenes de fondo"""
        def load_bg_image(bg_type: str):
            """Carga una imagen de fondo con transparencia"""
            if not hasattr(self, '_bg_label') or not self._bg_label:
                return
            
            # Determinar qué imagen cargar
            if bg_type == "custom":
                bg_file = "custom.png"
            elif bg_type == "snapshot":
                bg_file = "snapshot.png"
            else:  # default
                bg_file = "default.png"
            
            bg_image_path = os.path.join(os.path.dirname(__file__), "assets", bg_file)
            if not os.path.exists(bg_image_path):
                bg_image_path = os.path.join("assets", bg_file)
            
            if not os.path.exists(bg_image_path):
                print(f"[WARN] No se encontró imagen de fondo: {bg_file}")
                return
            
            pixmap = QPixmap(bg_image_path)
            if pixmap.isNull():
                return
            
            # Crear una versión semitransparente de la imagen
            transparent_pixmap = QPixmap(pixmap.size())
            transparent_pixmap.fill(Qt.transparent)
            painter = QPainter(transparent_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setOpacity(0.4)  # 40% de opacidad
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            
            # Si es el mismo tipo, solo actualizar sin animación
            if self._current_bg_type == bg_type:
                self._bg_label.setPixmap(transparent_pixmap)
                # Asegurar que la opacidad esté al 100%
                effect = self._bg_label.graphicsEffect()
                if effect and isinstance(effect, QGraphicsOpacityEffect):
                    effect.setOpacity(1.0)
                return
            
            # Cambiar fondo con animación fadeIn
            self._change_background_with_fade(transparent_pixmap)
            self._current_bg_type = bg_type
        
        return load_bg_image
    
    def _change_background_with_fade(self, new_pixmap: QPixmap):
        """Cambia el fondo con animación fadeIn"""
        if not hasattr(self, '_bg_label') or not self._bg_label:
            return
        
        # Detener animación anterior si existe
        if hasattr(self, '_bg_animation') and self._bg_animation and self._bg_animation.state() == QPropertyAnimation.Running:
            self._bg_animation.stop()
        
        # Usar QGraphicsOpacityEffect para la animación de opacidad
        opacity_effect = QGraphicsOpacityEffect()
        self._bg_label.setGraphicsEffect(opacity_effect)
        
        # Cambiar la imagen primero
        self._bg_label.setPixmap(new_pixmap)
        
        # Crear nueva animación de opacidad
        self._bg_animation = QPropertyAnimation(opacity_effect, b"opacity")
        self._bg_animation.setDuration(500)  # 500ms para el fade
        self._bg_animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        # Configurar valores de la animación
        self._bg_animation.setStartValue(0.0)
        self._bg_animation.setEndValue(1.0)
        
        # Iniciar animación
        self._bg_animation.start()
    
    def _update_background_for_version(self, version_id: str, version_name: str):
        """Actualiza el fondo según el tipo de versión seleccionada"""
        if not hasattr(self, '_load_background_image'):
            return
        
        # Determinar tipo de versión
        bg_type = "default"
        
        # Verificar si es snapshot (puede estar en el nombre o en el tipo del JSON)
        is_snapshot = False
        if "snapshot" in version_id.lower() or "snapshot" in version_name.lower():
            is_snapshot = True
        else:
            # Verificar en el JSON si el tipo es "snapshot" (solo leer, sin merge)
            try:
                json_path = os.path.join(
                    self.minecraft_launcher.minecraft_path,
                    "versions",
                    version_id,
                    f"{version_id}.json"
                )
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        version_json_original = json.load(f)
                    if version_json_original.get("type", "").lower() == "snapshot":
                        is_snapshot = True
            except Exception:
                pass  # Si hay error, continuar
        
        if is_snapshot:
            bg_type = "snapshot"
        else:
            # Verificar si es custom (tiene inheritsFrom) - solo leer, sin merge
            try:
                json_path = os.path.join(
                    self.minecraft_launcher.minecraft_path,
                    "versions",
                    version_id,
                    f"{version_id}.json"
                )
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        version_json_original = json.load(f)
                    if version_json_original.get("inheritsFrom"):
                        bg_type = "custom"
            except Exception:
                pass  # Si hay error, usar default
        
        # Cambiar fondo si es diferente
        if bg_type != self._current_bg_type:
            self._load_background_image(bg_type)
    
    def start_authentication(self):
        """Inicia el proceso de autenticación"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Modo indeterminado
        
        self.auth_thread = AuthThread(self.auth_manager)
        self.auth_thread.message.connect(self.add_message)
        self.auth_thread.need_redirect_url.connect(self.handle_redirect_url_request)
        self.auth_thread.finished.connect(self.on_authentication_success)
        self.auth_thread.error.connect(self.on_authentication_error)
        self.auth_thread.start()
    
    def handle_redirect_url_request(self, auth_url):
        """Maneja la solicitud de URL de redirección"""
        self.progress_bar.setVisible(False)
        
        # Mostrar diálogo para que el usuario pegue la URL
        dialog = RedirectUrlDialog(auth_url, self)
        if dialog.exec_() == QDialog.Accepted:
            redirect_url = dialog.get_redirect_url()
            if redirect_url:
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)
                self.add_message("Procesando URL de redirección...")
                # Iniciar nuevo thread con la URL de redirección
                self.complete_authentication(redirect_url)
            else:
                self.add_message("No se proporcionó URL de redirección")
        else:
            self.add_message("Autenticación cancelada")
    
    def complete_authentication(self, redirect_url):
        """Completa la autenticación con la URL de redirección"""
        # Terminar el thread anterior
        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.terminate()
            self.auth_thread.wait()
        
        # Iniciar nuevo thread con la URL de redirección
        self.auth_thread = AuthThread(self.auth_manager)
        self.auth_thread.set_redirect_url(redirect_url)
        self.auth_thread.message.connect(self.add_message)
        self.auth_thread.finished.connect(self.on_authentication_success)
        self.auth_thread.error.connect(self.on_authentication_error)
        self.auth_thread.start()
    
    def on_authentication_success(self, credentials: dict):
        """Maneja la autenticación exitosa"""
        self.progress_bar.setVisible(False)
        
        # Guardar credenciales
        if self.credential_storage.save_credentials(credentials):
            self.add_message("Credenciales guardadas correctamente")
        
        # Actualizar UI
        username = credentials.get("username", "Usuario")
        self.update_user_widget(credentials)
        # Habilitar el botón de lanzar cuando hay sesión
        self.launch_button.setEnabled(True)
        
        self.add_message(f"Autenticación exitosa: {username}")
    
    def on_authentication_error(self, error: str):
        """Maneja errores de autenticación"""
        self.progress_bar.setVisible(False)
        self.add_message(f"Error: {error}")
        QMessageBox.warning(self, "Error de Autenticación", error)
    
    def load_saved_credentials(self):
        """Carga credenciales guardadas y valida/refresca el token si es necesario"""
        if self.credential_storage.has_credentials():
            credentials = self.credential_storage.load_credentials()
            if credentials:
                username = credentials.get("username", "Usuario")
                access_token = credentials.get("access_token", "")
                expires_at = credentials.get("expires_at", 0)
                ms_refresh_token = credentials.get("ms_refresh_token")
                current_time = time.time()
                
                # Verificar si el token está cerca de expirar (menos de 1 hora restante) o ya expiró
                time_until_expiry = expires_at - current_time
                
                if time_until_expiry < 3600:  # Menos de 1 hora restante
                    # Intentar refrescar el token si tenemos refresh_token
                    if ms_refresh_token:
                        self.add_message(f"Refrescando sesión para: {username}...")
                        try:
                            new_credentials = self.auth_manager.refresh_minecraft_session(ms_refresh_token)
                            if new_credentials:
                                # Guardar las nuevas credenciales
                                if self.credential_storage.save_credentials(new_credentials):
                                    credentials = new_credentials
                                    access_token = new_credentials.get("access_token", "")
                                    expires_at = new_credentials.get("expires_at", 0)
                                    self.add_message(f"Sesión refrescada exitosamente para: {username}")
                                else:
                                    self.add_message("Error guardando credenciales refrescadas")
                            else:
                                # No se pudo refrescar, intentar validar el token actual
                                self.add_message("No se pudo refrescar la sesión, validando token actual...")
                        except Exception as e:
                            print(f"Error refrescando sesión: {e}")
                            self.add_message("Error al refrescar sesión, validando token actual...")
                
                # Verificar si el token ha expirado completamente
                if current_time >= expires_at:
                    if ms_refresh_token:
                        # Ya intentamos refrescar arriba, si llegamos aquí es que falló
                        self.add_message(f"La sesión ha expirado para: {username}. Por favor, inicia sesión nuevamente.")
                        self.update_user_widget(None)
                        self.launch_button.setEnabled(False)
                        return
                    else:
                        # No hay refresh_token, pedir reautenticación
                        self.add_message(f"La sesión ha expirado para: {username}. Por favor, inicia sesión nuevamente.")
                        self.update_user_widget(None)
                        self.launch_button.setEnabled(False)
                        return
                
                # Si el token no ha expirado, validarlo con la API
                if access_token:
                    self.add_message("Validando sesión...")
                    is_valid = self.auth_manager.validate_token(access_token)
                    if is_valid:
                        # Token válido
                        self.update_user_widget(credentials)
                        self.launch_button.setEnabled(True)
                        # Mostrar tiempo restante de forma amigable
                        hours_left = int(time_until_expiry / 3600)
                        minutes_left = int((time_until_expiry % 3600) / 60)
                        if hours_left > 0:
                            self.add_message(f"Sesión activa para: {username} ({hours_left}h {minutes_left}m restantes)")
                        else:
                            self.add_message(f"Sesión activa para: {username} ({minutes_left}m restantes)")
                    else:
                        # Token inválido (revocado), intentar refrescar si tenemos refresh_token
                        if ms_refresh_token:
                            self.add_message("Token inválido, intentando refrescar...")
                            try:
                                new_credentials = self.auth_manager.refresh_minecraft_session(ms_refresh_token)
                                if new_credentials:
                                    if self.credential_storage.save_credentials(new_credentials):
                                        credentials = new_credentials
                                        self.update_user_widget(credentials)
                                        self.launch_button.setEnabled(True)
                                        self.add_message(f"Sesión refrescada exitosamente para: {username}")
                                    else:
                                        self.add_message("Error guardando credenciales refrescadas")
                                        self.update_user_widget(None)
                                        self.launch_button.setEnabled(False)
                                else:
                                    # No se pudo refrescar
                                    self.add_message(f"La sesión no es válida para: {username}. Por favor, inicia sesión nuevamente.")
                                    self.update_user_widget(None)
                                    self.launch_button.setEnabled(False)
                                    self.credential_storage.clear_credentials()
                            except Exception as e:
                                print(f"Error refrescando sesión: {e}")
                                self.add_message(f"La sesión no es válida para: {username}. Por favor, inicia sesión nuevamente.")
                                self.update_user_widget(None)
                                self.launch_button.setEnabled(False)
                                self.credential_storage.clear_credentials()
                        else:
                            # No hay refresh_token, pedir reautenticación
                            self.add_message(f"La sesión no es válida para: {username}. Por favor, inicia sesión nuevamente.")
                            self.update_user_widget(None)
                            self.launch_button.setEnabled(False)
                            self.credential_storage.clear_credentials()
                else:
                    # No hay token, mostrar como no autenticado
                    self.add_message("No se encontró token de acceso válido")
                    self.update_user_widget(None)
                    self.launch_button.setEnabled(False)
            else:
                self.add_message("Error cargando credenciales guardadas")
                self.update_user_widget(None)
                self.launch_button.setEnabled(False)
    
    def launch_minecraft(self):
        """Lanza Minecraft con las credenciales guardadas"""
        credentials = self.credential_storage.load_credentials()
        if not credentials:
            # Si no hay credenciales, iniciar sesión automáticamente
            self.start_authentication()
            return
        
        # Verificar si el token está cerca de expirar o ya expiró
        expires_at = credentials.get("expires_at", 0)
        current_time = time.time()
        time_until_expiry = expires_at - current_time
        ms_refresh_token = credentials.get("ms_refresh_token")
        
        if time_until_expiry < 3600:  # Menos de 1 hora restante
            # Intentar refrescar el token si tenemos refresh_token
            if ms_refresh_token:
                self.add_message("Refrescando sesión antes de lanzar...")
                try:
                    new_credentials = self.auth_manager.refresh_minecraft_session(ms_refresh_token)
                    if new_credentials:
                        if self.credential_storage.save_credentials(new_credentials):
                            credentials = new_credentials
                            self.add_message("Sesión refrescada exitosamente")
                        else:
                            self.add_message("Error guardando credenciales refrescadas")
                    else:
                        # No se pudo refrescar
                        if current_time >= expires_at:
                            self.add_message("La sesión ha expirado. Por favor, inicia sesión nuevamente.")
                            self.start_authentication()
                            return
                except Exception as e:
                    print(f"Error refrescando sesión: {e}")
                    if current_time >= expires_at:
                        self.add_message("La sesión ha expirado. Por favor, inicia sesión nuevamente.")
                        self.start_authentication()
                        return
        
        # Verificar si el token ha expirado completamente
        if current_time >= expires_at:
            # Token expirado, pedir reautenticación
            self.add_message("La sesión ha expirado. Por favor, inicia sesión nuevamente.")
            self.start_authentication()
            return
        
        if not self.minecraft_launcher.check_minecraft_installed():
            QMessageBox.warning(
                self, 
                "Minecraft no encontrado", 
                "No se pudo encontrar la instalación de Minecraft.\n"
                "Por favor, instala Minecraft Java Edition primero."
            )
            return
        
        # Obtener la versión seleccionada (ID real, sin prefijos)
        selected_version = self.version_combo.currentData()
        if not selected_version:
            # Fallback: usar el texto si no hay data
            selected_version = self.version_combo.currentText()
        if not selected_version or selected_version == "No hay versiones disponibles":
            QMessageBox.warning(self, "Error", "Por favor, selecciona una versión de Minecraft")
            return
        
        # Detectar si es un perfil custom (formato: "profile:{profile_id}")
        game_dir = None
        actual_version = selected_version
        if selected_version.startswith("profile:"):
            profile_id = selected_version.replace("profile:", "")
            game_dir = os.path.join(self.minecraft_launcher.minecraft_path, "profiles", profile_id)
            print(f"[DEBUG] Perfil custom detectado: {profile_id}, game_dir: {game_dir}")
            # Leer launcher_profiles.json para obtener lastVersionId
            launcher_profiles_path = os.path.join(game_dir, "launcher_profiles.json")
            if os.path.exists(launcher_profiles_path):
                try:
                    with open(launcher_profiles_path, 'r', encoding='utf-8') as f:
                        launcher_profiles = json.load(f)
                    profiles_data = launcher_profiles.get("profiles", {})
                    print(f"[DEBUG] Perfiles encontrados en launcher_profiles.json: {list(profiles_data.keys())}")
                    if profiles_data:
                        # Buscar el perfil con lastVersionId (preferir "NeoForge" o cualquier perfil con lastVersionId)
                        last_version_id = None
                        for profile_key, profile_data in profiles_data.items():
                            if isinstance(profile_data, dict):
                                candidate_version = profile_data.get("lastVersionId")
                                if candidate_version:
                                    last_version_id = candidate_version
                                    print(f"[DEBUG] Encontrado lastVersionId en perfil '{profile_key}': {last_version_id}")
                                    break
                        
                        if last_version_id:
                            actual_version = last_version_id
                            print(f"[INFO] Usando versión del perfil: {actual_version}")
                        else:
                            print(f"[WARN] No se encontró lastVersionId en ningún perfil")
                except Exception as e:
                    print(f"[WARN] Error leyendo launcher_profiles.json: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback: buscar cualquier versión instalada
                    versions_dir = os.path.join(game_dir, "versions")
                    if os.path.exists(versions_dir):
                        for version_folder in os.listdir(versions_dir):
                            version_path = os.path.join(versions_dir, version_folder)
                            if os.path.isdir(version_path):
                                version_json_file = os.path.join(version_path, f"{version_folder}.json")
                                if os.path.exists(version_json_file):
                                    actual_version = version_folder
                                    print(f"[DEBUG] Fallback: usando versión encontrada: {actual_version}")
                                    break
            else:
                print(f"[WARN] No se encontró launcher_profiles.json en: {launcher_profiles_path}")
        
        print(f"[DEBUG] Versión final a usar: {actual_version}, game_dir: {game_dir}")
        
        # Si es un perfil custom, verificar que todas las librerías estén descargadas
        if game_dir:
            self.add_message("Verificando que todas las librerías estén descargadas...")
            if not self.minecraft_launcher.is_profile_version_downloaded(actual_version, game_dir, strict=True):
                QMessageBox.warning(
                    self,
                    "Librerías incompletas",
                    f"El perfil no tiene todas las librerías necesarias descargadas.\n\n"
                    f"Por favor, reinstala el perfil o verifica que la instalación se completó correctamente."
                )
                return
        
        # Verificar requisitos de Java
        version_json = self.minecraft_launcher._load_version_json(actual_version, game_dir=game_dir)
        required_java = None
        if version_json:
            required_java = self.minecraft_launcher.get_required_java_version(version_json)
        
        # Obtener la versión de Java seleccionada
        selected_java_path = None
        if self.java_combo.currentData():
            selected_java_path = self.java_combo.currentData()
        elif self.java_combo.currentText() != "No hay Java disponible":
            # Si no hay data, intentar extraer del texto
            java_text = self.java_combo.currentText()
            # Formato: "Java 21 (C:\path\to\java.exe)"
            import re
            match = re.search(r'\((.+)\)', java_text)
            if match:
                selected_java_path = match.group(1)
        
        # Si se requiere Java y no está disponible, intentar descargar
        if required_java:
            java_installations = self.minecraft_launcher.find_java_installations()
            suitable_java = None
            
            # Verificar si hay Java adecuada
            if required_java == 8:
                if 8 in java_installations:
                    suitable_java = java_installations[8]
            else:
                if required_java in java_installations:
                    suitable_java = java_installations[required_java]
                else:
                    # Buscar versión mayor o igual
                    suitable_versions = {v: p for v, p in java_installations.items() if v >= required_java}
                    if suitable_versions:
                        suitable_java = suitable_versions[min(suitable_versions.keys())]
            
            # Si no hay Java adecuada y no se seleccionó una manualmente, descargar
            if not suitable_java and not selected_java_path:
                reply = QMessageBox.question(
                    self,
                    "Java Requerida",
                    f"Esta version de Minecraft requiere Java {required_java}.\n\n"
                    f"Versiones de Java disponibles: {sorted(java_installations.keys()) if java_installations else 'Ninguna'}\n\n"
                    f"¿Deseas descargar Java {required_java} automaticamente?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.add_message(f"Descargando Java {required_java}...")
                    
                    def on_java_downloaded(success, java_path):
                        if success and java_path:
                            self.add_message(f"Java {required_java} descargada correctamente")
                            # Recargar versiones de Java
                            self.load_java_versions()
                            # Continuar con el lanzamiento
                            self.add_message(f"Lanzando Minecraft version: {actual_version}")
                            self.add_message(f"Usando Java: {java_path}")
                            self.launch_button.setEnabled(False)
                            success_launch, _ = self.minecraft_launcher.launch_minecraft(credentials, actual_version, java_path, game_dir=game_dir)
                            if success_launch:
                                self.add_message("Minecraft proceso iniciado correctamente")
                                self.add_message("El juego deberia abrirse en breve...")
                                self.launch_button.setEnabled(True)
                            else:
                                self.add_message("Error al lanzar Minecraft")
                                self.launch_button.setEnabled(True)
                        else:
                            self.add_message("Descarga de Java cancelada o falló")
                            self.launch_button.setEnabled(True)
                    
                    self.download_java_async(required_java, on_java_downloaded)
                    return  # Salir aquí, el callback continuará
                else:
                    QMessageBox.warning(
                        self,
                        "Java Requerida",
                        f"Esta version requiere Java {required_java}.\n"
                        f"Por favor, instala Java {required_java} o selecciona una version diferente de Minecraft."
                    )
                    self.launch_button.setEnabled(True)
                    return
            elif suitable_java:
                selected_java_path = suitable_java
        
        self.add_message(f"Lanzando Minecraft version: {actual_version}")
        if selected_java_path:
            self.add_message(f"Usando Java: {selected_java_path}")
        if game_dir:
            self.add_message(f"Usando perfil custom: {game_dir}")
        self.launch_button.setEnabled(False)
        
        success, detected_java_version = self.minecraft_launcher.launch_minecraft(credentials, actual_version, selected_java_path, game_dir=game_dir)
        
        if success:
            self.add_message("Minecraft proceso iniciado correctamente")
            self.add_message("El juego deberia abrirse en breve...")
            # Habilitar el botón de nuevo cuando el proceso se inicia correctamente
            self.launch_button.setEnabled(True)
            # NO cerrar el launcher inmediatamente - dejar que el usuario vea si hay errores
            # El launcher se puede cerrar manualmente
        else:
            self.add_message("Error al lanzar Minecraft")
            self.launch_button.setEnabled(True)
            
            # Obtener mensaje de error más específico y ofrecer descargar Java si es necesario
            version_json = self.minecraft_launcher._load_version_json(actual_version, game_dir=game_dir)
            required_java = None
            if version_json:
                required_java = self.minecraft_launcher.get_required_java_version(version_json)
            
            # Si se detectó la versión de Java desde el error, usar esa
            if detected_java_version:
                required_java = detected_java_version
            
            if required_java:
                java_installations = self.minecraft_launcher.find_java_installations()
                suitable_java = None
                
                # Verificar si hay Java adecuada
                if required_java == 8:
                    if 8 in java_installations:
                        suitable_java = java_installations[8]
                else:
                    if required_java in java_installations:
                        suitable_java = java_installations[required_java]
                    else:
                        # Buscar versión mayor o igual
                        suitable_versions = {v: p for v, p in java_installations.items() if v >= required_java}
                        if suitable_versions:
                            suitable_java = suitable_versions[min(suitable_versions.keys())]
                
                # Si no hay Java adecuada, ofrecer descargar
                if not suitable_java:
                    if required_java == 8:
                        QMessageBox.critical(
                            self, 
                            "Java 8 Requerida", 
                            f"Esta version de Minecraft requiere Java 8 exactamente.\n\n"
                            f"Java 9 o superior NO es compatible con versiones antiguas.\n\n"
                            f"Versiones de Java disponibles: {sorted(java_installations.keys())}\n\n"
                            f"Por favor:\n"
                            f"1. Instala Java 8, o\n"
                            f"2. Usa una version mas reciente de Minecraft (1.13+)"
                        )
                    else:
                        reply = QMessageBox.question(
                            self,
                            "Java Requerida",
                            f"Esta version de Minecraft requiere Java {required_java}.\n\n"
                            f"Versiones de Java disponibles: {sorted(java_installations.keys()) if java_installations else 'Ninguna'}\n\n"
                            f"¿Deseas descargar Java {required_java} automaticamente?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        
                        if reply == QMessageBox.Yes:
                            self.add_message(f"Descargando Java {required_java}...")
                            
                            def on_java_downloaded_retry(success, java_path):
                                if success and java_path:
                                    self.add_message(f"Java {required_java} descargada correctamente")
                                    # Recargar versiones de Java
                                    self.load_java_versions()
                                    # Intentar lanzar de nuevo con la Java descargada
                                    self.add_message(f"Reintentando lanzar con Java {required_java}...")
                                    self.launch_button.setEnabled(False)
                                    success_launch, _ = self.minecraft_launcher.launch_minecraft(credentials, actual_version, java_path, game_dir=game_dir)
                                    if success_launch:
                                        self.add_message("Minecraft proceso iniciado correctamente")
                                        self.add_message("El juego deberia abrirse en breve...")
                                        self.launch_button.setEnabled(True)
                                    else:
                                        self.add_message("Error al lanzar Minecraft despues de descargar Java")
                                        self.launch_button.setEnabled(True)
                                else:
                                    self.add_message("Descarga de Java cancelada o falló")
                                    self.launch_button.setEnabled(True)
                            
                            self.download_java_async(required_java, on_java_downloaded_retry)
                            return  # Salir aquí, el callback continuará
                        else:
                            QMessageBox.warning(
                                self,
                                "Java Requerida",
                                f"Esta version requiere Java {required_java}.\n"
                                f"Por favor, instala Java {required_java} o selecciona una version diferente de Minecraft."
                            )
                    return
            
            QMessageBox.critical(self, "Error", "No se pudo lanzar Minecraft. Revisa los mensajes para mas detalles.")
    
    def _on_user_widget_clicked(self):
        """Maneja el clic en el widget de usuario"""
        credentials = self.credential_storage.load_credentials()
        if credentials:
            # Mostrar menú desplegable con opciones
            menu = QMenu(self)
            
            # Opción: Modo desarrollador (checkbox)
            developer_action = menu.addAction("Modo desarrollador")
            developer_action.setCheckable(True)
            developer_action.setChecked(self.developer_mode)
            developer_action.triggered.connect(self.toggle_developer_mode)
            
            # Opción: Administrador de servidores (solo si modo desarrollador está activo)
            if self.developer_mode:
                menu.addSeparator()
                server_manager_action = menu.addAction("Administrador de servidores")
                server_manager_action.triggered.connect(self.show_server_manager)
            
            # Separador
            menu.addSeparator()
            
            # Opción: Cerrar sesión
            logout_action = menu.addAction("Cerrar sesión")
            logout_action.triggered.connect(self.logout)
            
            # Mostrar el menú debajo del widget de usuario
            menu.exec_(self.user_widget.mapToGlobal(self.user_widget.rect().bottomLeft()))
        else:
            # Si no hay sesión, iniciar autenticación
            self.start_authentication()
    
    def show_server_manager(self):
        """Muestra el diálogo de administrador de servidores"""
        dialog = ServerManagerDialog(self, self.minecraft_launcher)
        dialog.exec_()
    
    def update_user_widget(self, credentials: Optional[dict]):
        """Actualiza el widget de usuario con la información del jugador"""
        if credentials:
            username = credentials.get("username", "Usuario")
            uuid = credentials.get("uuid", "")
            
            # Mostrar avatar y nombre
            self.user_name_label.setText(username)
            self.user_name_label.setStyleSheet("""
                QLabel#userNameLabel {
                    color: #a78bfa;
                    font-size: 12px;
                    padding: 5px 10px;
                    border-radius: 5px;
                    background: transparent;
                }
                QLabel#userNameLabel:hover {
                    background: rgba(139, 92, 246, 0.3);
                }
            """)
            
            # Cargar avatar
            if uuid:
                self._load_user_avatar(uuid)
        else:
            # Mostrar "Iniciar sesión"
            self.user_name_label.setText("Iniciar sesión")
            self.user_name_label.setStyleSheet("""
                QLabel#userNameLabel {
                    color: #e9d5ff;
                    font-size: 12px;
                    padding: 5px 10px;
                    border-radius: 5px;
                    background: transparent;
                }
                QLabel#userNameLabel:hover {
                    background: rgba(139, 92, 246, 0.3);
                }
            """)
            self.user_avatar_label.setVisible(False)
            self.user_avatar_label.clear()
            self.user_name_label.setCursor(Qt.PointingHandCursor)
    
    def _load_user_avatar(self, uuid: str):
        """Carga el avatar del jugador desde la API de Minecraft"""
        try:
            # Formatear UUID (eliminar guiones si los tiene, Crafatar los acepta con o sin guiones)
            # Pero es mejor asegurarse de que tenga el formato correcto
            uuid_clean = uuid.replace('-', '') if uuid else ''
            if not uuid_clean:
                return
            
            # Usar la API de Crafatar para obtener el avatar
            # Formato: https://crafatar.com/avatars/{uuid}?size=32
            avatar_url = f"https://crafatar.com/avatars/{uuid_clean}?size=32&default=MHF_Steve"
            
            response = requests.get(avatar_url, timeout=5)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                self.user_avatar_label.setPixmap(pixmap)
                self.user_avatar_label.setVisible(True)
        except Exception as e:
            # Si falla, simplemente no mostrar avatar
            print(f"Error cargando avatar: {e}")
            self.user_avatar_label.setVisible(False)
    
    def load_developer_mode(self) -> bool:
        """Carga el estado del modo desarrollador desde la configuración"""
        try:
            import json
            from config import CONFIG_FILE
            
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('developer_mode', False)
            return False
        except Exception as e:
            print(f"Error cargando modo desarrollador: {e}")
            return False
    
    def save_developer_mode(self, enabled: bool):
        """Guarda el estado del modo desarrollador en la configuración"""
        try:
            import json
            from config import CONFIG_FILE
            
            config = {}
            if CONFIG_FILE.exists():
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except (json.JSONDecodeError, IOError):
                    config = {}
            
            config['developer_mode'] = enabled
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error guardando modo desarrollador: {e}")
    
    def toggle_developer_mode(self, checked: bool):
        """Alterna el modo desarrollador"""
        self.developer_mode = checked
        self.save_developer_mode(checked)
        if checked:
            self.add_message("Modo desarrollador activado")
        else:
            self.add_message("Modo desarrollador desactivado")
    
    def logout(self):
        """Cierra la sesión y elimina las credenciales"""
        reply = QMessageBox.question(
            self,
            "Cerrar Sesión",
            "¿Estás seguro de que quieres cerrar sesión?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.credential_storage.clear_credentials()
            self.update_user_widget(None)
            # Deshabilitar el botón de lanzar cuando no hay sesión
            self.launch_button.setEnabled(False)
            self.add_message("Sesión cerrada")
    
    def center_window(self):
        """Centra la ventana en la pantalla principal"""
        from PyQt5.QtWidgets import QDesktopWidget
        frame_geometry = self.frameGeometry()
        screen = QApplication.desktop().screenGeometry()
        center_point = screen.center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())
        
        # Asegurar que la ventana no esté minimizada
        self.setWindowState(Qt.WindowNoState)
        self.show()
        self.raise_()
        self.activateWindow()

def main():
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

