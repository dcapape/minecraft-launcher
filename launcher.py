"""
Launcher principal de Minecraft Java Edition
"""
import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QMessageBox, QProgressBar, QDialog, QDialogButtonBox,
                             QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QPoint
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush
from java_downloader import JavaDownloader
from PyQt5.QtWebEngineWidgets import QWebEngineView
import webbrowser
import urllib.parse
import re
from auth_manager import AuthManager
from credential_storage import CredentialStorage
from minecraft_launcher import MinecraftLauncher

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

class JavaDownloadDialog(QDialog):
    """Diálogo con barra de progreso para descargar Java"""
    def __init__(self, java_version, minecraft_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Descargando Java {java_version}")
        self.setModal(True)
        self.java_path = None
        
        layout = QVBoxLayout()
        
        info_label = QLabel(f"Descargando Java {java_version} desde Adoptium...\nEsto puede tardar varios minutos.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Iniciando descarga...")
        layout.addWidget(self.status_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
        # Iniciar descarga
        from java_downloader import JavaDownloader
        downloader = JavaDownloader(minecraft_path)
        self.download_thread = JavaDownloadThread(downloader, java_version)
        self.download_thread.progress.connect(self.on_progress)
        self.download_thread.finished.connect(self.on_finished)
        self.download_thread.error.connect(self.on_error)
        self.download_thread.message.connect(self.on_message)
        self.download_thread.start()
    
    def on_progress(self, downloaded, total):
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress_bar.setValue(percent)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(f"Descargado: {mb_downloaded:.1f} MB / {mb_total:.1f} MB ({percent}%)")
        else:
            self.progress_bar.setRange(0, 0)  # Modo indeterminado
    
    def on_finished(self, java_path):
        self.java_path = java_path
        self.status_label.setText("Descarga completada!")
        self.progress_bar.setValue(100)
        self.accept()
    
    def on_error(self, error_msg):
        self.status_label.setText(f"Error: {error_msg}")
        QMessageBox.critical(self, "Error", f"No se pudo descargar Java:\n{error_msg}")
        self.reject()
    
    def on_message(self, message):
        self.status_label.setText(message)
    
    def get_java_path(self):
        return self.java_path

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
        self.setWindowTitle("Autenticación de Microsoft")
        self.setGeometry(100, 100, 800, 600)
        self.redirect_url = None
        
        layout = QVBoxLayout()
        
        # Información
        info_label = QLabel(
            "Completa la autenticación en el navegador de abajo.\n"
            "Serás redirigido automáticamente después de autenticarte."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Navegador embebido
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl(auth_url))
        
        # Interceptar cambios de URL para capturar la redirección
        self.web_view.urlChanged.connect(self.on_url_changed)
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        layout.addWidget(self.web_view)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.status_label = QLabel("Cargando...")
        button_layout.addWidget(self.status_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
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
                self.status_label.setText("✓ Autenticación exitosa! Cerrando...")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                # Cerrar el diálogo automáticamente después de un breve delay
                QApplication.processEvents()
                self.accept()
            elif "error" in params:
                # Error en la autenticación
                error = params.get("error", ["Error desconocido"])[0]
                error_desc = params.get("error_description", [""])[0]
                self.status_label.setText(f"Error: {error} - {error_desc}")
                self.status_label.setStyleSheet("color: red;")
            else:
                # URL de redirección sin código (puede ser una página intermedia)
                # Intentar leer el código desde el contenido de la página
                self.web_view.page().toPlainText(self._check_page_content)
                self.status_label.setText("Verificando autenticación...")
    
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
            self.status_label.setText("✓ Código encontrado! Cerrando...")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            QApplication.processEvents()
            self.accept()
        elif "removed" in self.web_view.url().toString():
            self.status_label.setText("⚠ La URL de redirección no contiene el código.\nEsto puede indicar un problema con la autenticación.\nIntenta usar el método de copiar/pegar la URL manualmente.")
            self.status_label.setStyleSheet("color: orange;")
    
    def on_load_finished(self, success):
        """Se llama cuando termina de cargar una página"""
        if success:
            current_url = self.web_view.url().toString()
            if "login.live.com" in current_url or "microsoft.com" in current_url:
                self.status_label.setText("Por favor, inicia sesión...")
            elif "oauth20_desktop.srf" in current_url:
                # Ya estamos en la página de redirección
                self.on_url_changed(self.web_view.url())
    
    def get_redirect_url(self):
        return self.redirect_url

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
        self.auth_manager = AuthManager()
        self.credential_storage = CredentialStorage()
        self.minecraft_launcher = MinecraftLauncher()
        self.auth_thread = None
        self.old_pos = None  # Para arrastrar la ventana
        self.title_bar = None  # Referencia a la barra de título
        
        # Inicializar archivo de configuración si no existe
        self.load_last_selected_version()
        
        self.init_ui()
        self.load_saved_credentials()
    
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
        
        # Aplicar estilos gaming morados
        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
            #centralWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
                border-radius: 15px;
                border: 2px solid #8b5cf6;
            }
            QLabel {
                color: #e9d5ff;
                background: transparent;
            }
            QLabel#titleLabel {
                color: #c084fc;
                font-size: 28px;
                font-weight: bold;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
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
                background: #0f0a1a;
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
        
        # Información del usuario
        self.user_label = QLabel("No autenticado")
        self.user_label.setAlignment(Qt.AlignCenter)
        self.user_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(self.user_label)
        
        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Área de mensajes
        self.message_area = QTextEdit()
        self.message_area.setReadOnly(True)
        self.message_area.setMaximumHeight(200)  # Reducir altura
        layout.addWidget(self.message_area)
        
        # Selector de versión de Minecraft
        version_layout = QHBoxLayout()
        version_label = QLabel("Versión Minecraft:")
        version_layout.addWidget(version_label)
        
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(300)
        self.version_combo.currentTextChanged.connect(self.on_version_changed)
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        version_layout.addWidget(self.version_combo)
        
        refresh_button = QPushButton("🔄")
        refresh_button.setToolTip("Actualizar lista de versiones")
        refresh_button.clicked.connect(self.load_versions)
        refresh_button.setFixedSize(40, 40)  # Tamaño fijo cuadrado
        refresh_button.setStyleSheet("font-size: 20px; padding: 5px;")
        version_layout.addWidget(refresh_button)
        
        layout.addLayout(version_layout)
        
        # Selector de versión de Java
        java_layout = QHBoxLayout()
        java_label = QLabel("Versión Java:")
        java_layout.addWidget(java_label)
        
        self.java_combo = QComboBox()
        self.java_combo.setMinimumWidth(300)
        java_layout.addWidget(self.java_combo)
        
        # Label para mostrar la versión de Java requerida
        self.java_required_label = QLabel("")
        self.java_required_label.setStyleSheet("color: blue; font-style: italic;")
        java_layout.addWidget(self.java_required_label)
        
        refresh_java_button = QPushButton("🔄")
        refresh_java_button.setToolTip("Actualizar lista de Java")
        refresh_java_button.clicked.connect(self.load_java_versions)
        refresh_java_button.setFixedSize(40, 40)  # Tamaño fijo cuadrado
        refresh_java_button.setStyleSheet("font-size: 20px; padding: 5px;")
        java_layout.addWidget(refresh_java_button)
        
        layout.addLayout(java_layout)
        
        # Cargar versiones después de que message_area esté inicializado
        self.load_versions()
        self.load_java_versions()
        
        # Conectar save_selected_version DESPUÉS de cargar las versiones
        # para evitar que se guarde durante la carga inicial
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.login_button = QPushButton("Iniciar Sesión")
        self.login_button.clicked.connect(self.start_authentication)
        button_layout.addWidget(self.login_button)
        
        self.launch_button = QPushButton("Lanzar Minecraft")
        self.launch_button.clicked.connect(self.launch_minecraft)
        # El botón se habilita cuando hay credenciales guardadas
        button_layout.addWidget(self.launch_button)
        
        self.logout_button = QPushButton("Cerrar Sesión")
        self.logout_button.clicked.connect(self.logout)
        self.logout_button.setEnabled(False)
        button_layout.addWidget(self.logout_button)
        
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
    
    def load_versions(self):
        """Carga las versiones de Minecraft disponibles (solo las descargadas)"""
        # Bloquear signals temporalmente para evitar que se guarde durante la carga
        self.version_combo.blockSignals(True)
        
        self.version_combo.clear()
        # Solo mostrar versiones completamente descargadas
        versions = self.minecraft_launcher.get_available_versions(only_downloaded=True)
        
        if versions:
            self.version_combo.addItems(versions)
            self.add_message(f"Versiones de Minecraft disponibles: {len(versions)} (solo descargadas)")
            
            # Cargar la última versión seleccionada
            last_version = self.load_last_selected_version()
            if last_version and last_version in versions:
                index = self.version_combo.findText(last_version)
                if index >= 0:
                    self.version_combo.setCurrentIndex(index)
                    self.add_message(f"Versión restaurada: {last_version}")
            else:
                # Si no hay versión guardada o no está disponible, seleccionar la primera
                if last_version:
                    self.add_message(f"Versión guardada '{last_version}' no está disponible, seleccionando primera versión")
        else:
            self.version_combo.addItem("No hay versiones disponibles")
            self.version_combo.setEnabled(False)
            self.add_message("No se encontraron versiones de Minecraft descargadas")
        
        # Desbloquear signals después de cargar
        self.version_combo.blockSignals(False)
    
    def save_selected_version(self, version: str):
        """Guarda la versión seleccionada. Crea el archivo si no existe."""
        if not version or version == "No hay versiones disponibles":
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
            
            config['last_selected_version'] = version
            
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
                    "last_selected_version": None
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
        
        if java_installations:
            # Ordenar por versión (mayor a menor)
            sorted_versions = sorted(java_installations.items(), key=lambda x: x[0], reverse=True)
            for version, path in sorted_versions:
                display_text = f"Java {version} ({path})"
                self.java_combo.addItem(display_text, path)  # Guardar el path como data
            
            self.add_message(f"Versiones de Java disponibles: {len(java_installations)}")
            # Seleccionar la versión más reciente por defecto
            if sorted_versions:
                self.java_combo.setCurrentIndex(0)
        else:
            self.java_combo.addItem("No hay Java disponible")
            self.java_combo.setEnabled(False)
            self.add_message("No se encontraron instalaciones de Java")
    
    def on_version_changed(self, version_name: str):
        """Se llama cuando cambia la versión de Minecraft seleccionada"""
        if not version_name or version_name == "No hay versiones disponibles":
            self.java_required_label.setText("")
            return
        
        # Cargar el JSON de la versión para obtener los requisitos de Java
        version_json = self.minecraft_launcher._load_version_json(version_name)
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
    
    def start_authentication(self):
        """Inicia el proceso de autenticación"""
        self.login_button.setEnabled(False)
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
                self.login_button.setEnabled(True)
        else:
            self.add_message("Autenticación cancelada")
            self.login_button.setEnabled(True)
    
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
        self.login_button.setEnabled(True)
        
        # Guardar credenciales
        if self.credential_storage.save_credentials(credentials):
            self.add_message("Credenciales guardadas correctamente")
        
        # Actualizar UI
        username = credentials.get("username", "Usuario")
        self.user_label.setText(f"Conectado como: {username}")
        self.user_label.setStyleSheet("color: #a78bfa; font-size: 16px; font-weight: bold; margin: 10px;")
        # Habilitar el botón de lanzar cuando hay sesión
        self.launch_button.setEnabled(True)
        self.logout_button.setEnabled(True)
        
        self.add_message(f"Autenticación exitosa: {username}")
    
    def on_authentication_error(self, error: str):
        """Maneja errores de autenticación"""
        self.progress_bar.setVisible(False)
        self.login_button.setEnabled(True)
        self.add_message(f"Error: {error}")
        QMessageBox.warning(self, "Error de Autenticación", error)
    
    def load_saved_credentials(self):
        """Carga credenciales guardadas"""
        if self.credential_storage.has_credentials():
            credentials = self.credential_storage.load_credentials()
            if credentials:
                # Verificar si el token sigue siendo válido
                expires_at = credentials.get("expires_at", 0)
                if time.time() < expires_at:
                    username = credentials.get("username", "Usuario")
                    self.user_label.setText(f"Conectado como: {username}")
                    self.user_label.setStyleSheet("color: #a78bfa; font-size: 16px; font-weight: bold; margin: 10px;")
                    # Habilitar el botón de lanzar cuando hay sesión
                    self.launch_button.setEnabled(True)
                    self.logout_button.setEnabled(True)
                    self.add_message(f"Credenciales cargadas para: {username}")
                else:
                    self.add_message("Las credenciales han expirado. Por favor, inicia sesión nuevamente.")
    
    def launch_minecraft(self):
        """Lanza Minecraft con las credenciales guardadas"""
        credentials = self.credential_storage.load_credentials()
        if not credentials:
            QMessageBox.warning(self, "Error", "No hay credenciales guardadas")
            return
        
        if not self.minecraft_launcher.check_minecraft_installed():
            QMessageBox.warning(
                self, 
                "Minecraft no encontrado", 
                "No se pudo encontrar la instalación de Minecraft.\n"
                "Por favor, instala Minecraft Java Edition primero."
            )
            return
        
        # Obtener la versión seleccionada
        selected_version = self.version_combo.currentText()
        if not selected_version or selected_version == "No hay versiones disponibles":
            QMessageBox.warning(self, "Error", "Por favor, selecciona una versión de Minecraft")
            return
        
        # Verificar requisitos de Java
        version_json = self.minecraft_launcher._load_version_json(selected_version)
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
                    dialog = JavaDownloadDialog(required_java, self.minecraft_launcher.minecraft_path, self)
                    if dialog.exec_() == QDialog.Accepted:
                        selected_java_path = dialog.get_java_path()
                        self.add_message(f"Java {required_java} descargada correctamente")
                        # Recargar versiones de Java
                        self.load_java_versions()
                    else:
                        self.add_message("Descarga de Java cancelada")
                        self.launch_button.setEnabled(True)
                        return
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
        
        self.add_message(f"Lanzando Minecraft version: {selected_version}")
        if selected_java_path:
            self.add_message(f"Usando Java: {selected_java_path}")
        self.launch_button.setEnabled(False)
        
        success, detected_java_version = self.minecraft_launcher.launch_minecraft(credentials, selected_version, selected_java_path)
        
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
            version_json = self.minecraft_launcher._load_version_json(selected_version)
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
                            dialog = JavaDownloadDialog(required_java, self.minecraft_launcher.minecraft_path, self)
                            if dialog.exec_() == QDialog.Accepted:
                                downloaded_java = dialog.get_java_path()
                                self.add_message(f"Java {required_java} descargada correctamente")
                                # Recargar versiones de Java
                                self.load_java_versions()
                                # Intentar lanzar de nuevo con la Java descargada
                                self.add_message(f"Reintentando lanzar con Java {required_java}...")
                                self.launch_button.setEnabled(False)
                                success, _ = self.minecraft_launcher.launch_minecraft(credentials, selected_version, downloaded_java)
                                if success:
                                    self.add_message("Minecraft proceso iniciado correctamente")
                                    self.add_message("El juego deberia abrirse en breve...")
                                else:
                                    self.add_message("Error al lanzar Minecraft despues de descargar Java")
                                    self.launch_button.setEnabled(True)
                            else:
                                self.add_message("Descarga de Java cancelada")
                            return
                        else:
                            QMessageBox.warning(
                                self,
                                "Java Requerida",
                                f"Esta version requiere Java {required_java}.\n"
                                f"Por favor, instala Java {required_java} o selecciona una version diferente de Minecraft."
                            )
                    return
            
            QMessageBox.critical(self, "Error", "No se pudo lanzar Minecraft. Revisa los mensajes para mas detalles.")
    
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
            self.user_label.setText("No autenticado")
            self.user_label.setStyleSheet("color: #fca5a5; font-size: 16px; font-weight: bold; margin: 10px;")
            # Deshabilitar el botón de lanzar cuando no hay sesión
            self.launch_button.setEnabled(False)
            self.logout_button.setEnabled(False)
            self.add_message("Sesión cerrada")
    
    def center_window(self):
        """Centra la ventana en la pantalla principal"""
        from PyQt5.QtWidgets import QDesktopWidget
        frame_geometry = self.frameGeometry()
        screen = QApplication.desktop().screenGeometry()
        center_point = screen.center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

def main():
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

