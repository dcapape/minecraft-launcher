"""
Launcher principal de Minecraft Java Edition
"""
import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QMessageBox, QProgressBar, QDialog, QDialogButtonBox,
                             QComboBox, QMenu)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QPoint
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QPalette
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

class LoadVersionsThread(QThread):
    """Thread para cargar versiones de Minecraft sin bloquear la UI"""
    finished = pyqtSignal(list)  # lista de versiones
    error = pyqtSignal(str)
    
    def __init__(self, minecraft_launcher):
        super().__init__()
        self.minecraft_launcher = minecraft_launcher
    
    def run(self):
        try:
            versions = self.minecraft_launcher.get_available_versions(only_downloaded=True)
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
        self.load_versions_thread = None
        self.java_download_thread = None
        self.old_pos = None  # Para arrastrar la ventana
        self.title_bar = None  # Referencia a la barra de título
        
        # Inicializar archivo de configuración si no existe
        self.load_last_selected_version()
        
        self.init_ui()
        
        # Inicializar widget de usuario
        self.update_user_widget(None)
        
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
        if os.path.exists(bg_image_path):
            # Cargar la imagen y aplicarla con transparencia usando un QLabel de fondo
            self._bg_label = QLabel(central_widget)
            self._bg_label.setAlignment(Qt.AlignCenter)
            self._bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # No interceptar eventos del mouse
            pixmap = QPixmap(bg_image_path)
            if not pixmap.isNull():
                # Crear una versión semitransparente de la imagen mezclada con el color de fondo
                transparent_pixmap = QPixmap(pixmap.size())
                transparent_pixmap.fill(Qt.transparent)
                painter = QPainter(transparent_pixmap)
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                painter.setOpacity(0.4)  # 40% de opacidad (ajustable: 0.0 = invisible, 1.0 = opaco)
                painter.drawPixmap(0, 0, pixmap)
                painter.end()
                self._bg_label.setPixmap(transparent_pixmap)
                self._bg_label.setScaledContents(True)
                self._bg_label.lower()  # Enviar al fondo
                
                # Función para redimensionar el label de fondo cuando cambie el tamaño del widget
                def update_bg_label_size():
                    if self._bg_label:
                        self._bg_label.setGeometry(0, 0, central_widget.width(), central_widget.height())
                
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
                cursor: pointer;
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
        self.version_combo.currentTextChanged.connect(self.on_version_changed)
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        version_layout.addWidget(self.version_combo)
        
        refresh_button = QPushButton("🔄")
        refresh_button.setToolTip("Actualizar lista de versiones")
        refresh_button.clicked.connect(self.load_versions)
        refresh_button.setFixedSize(40, 40)  # Misma altura que combo y label
        refresh_button.setStyleSheet("font-size: 20px; padding: 5px;")
        version_layout.addWidget(refresh_button)
        
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
        
        # Conectar save_selected_version DESPUÉS de cargar las versiones
        # para evitar que se guarde durante la carga inicial
        self.version_combo.currentTextChanged.connect(self.save_selected_version)
        
        # Mostrar mensaje inicial mientras se cargan las versiones
        self.version_combo.addItem("Cargando versiones...")
        self.version_combo.setEnabled(False)
        
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
    
    def load_versions_async(self):
        """Inicia la carga asíncrona de versiones de Minecraft"""
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
    
    def on_versions_loaded(self, versions):
        """Se llama cuando las versiones se han cargado"""
        # Ocultar barra de progreso
        self.progress_bar.setVisible(False)
        
        # Bloquear signals temporalmente para evitar que se guarde durante la carga
        self.version_combo.blockSignals(True)
        
        self.version_combo.clear()
        
        if versions:
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
                self.version_combo.setCurrentIndex(index)
                self.add_message(f"Versión restaurada: {last_version}")
            else:
                # Si no hay versión guardada o no está disponible, seleccionar la primera
                if last_version:
                    self.add_message(f"Versión guardada '{last_version}' no está disponible, seleccionando primera versión")
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
        
        # Solo mostrar versiones completamente descargadas
        versions = self.minecraft_launcher.get_available_versions(only_downloaded=True)
        
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
                self.version_combo.setCurrentIndex(index)
                self.add_message(f"Versión restaurada: {last_version}")
            else:
                # Si no hay versión guardada o no está disponible, seleccionar la primera
                if last_version:
                    self.add_message(f"Versión guardada '{last_version}' no está disponible, seleccionando primera versión")
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
        # Obtener el ID real de la versión (sin prefijos)
        version_id = self.version_combo.currentData()
        if not version_id:
            # Fallback: intentar extraer del texto si no hay data
            version_id = version_name
        
        if not version_id or version_id == "No hay versiones disponibles":
            self.java_required_label.setText("")
            return
        
        # Cargar el JSON de la versión para obtener los requisitos de Java
        version_json = self.minecraft_launcher._load_version_json(version_id)
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
        """Carga credenciales guardadas"""
        if self.credential_storage.has_credentials():
            credentials = self.credential_storage.load_credentials()
            if credentials:
                # Verificar si el token sigue siendo válido
                expires_at = credentials.get("expires_at", 0)
                if time.time() < expires_at:
                    username = credentials.get("username", "Usuario")
                    self.update_user_widget(credentials)
                    # Habilitar el botón de lanzar cuando hay sesión
                    self.launch_button.setEnabled(True)
                    self.add_message(f"Credenciales cargadas para: {username}")
                else:
                    self.add_message("Las credenciales han expirado. Por favor, inicia sesión nuevamente.")
                    self.update_user_widget(None)
    
    def launch_minecraft(self):
        """Lanza Minecraft con las credenciales guardadas"""
        credentials = self.credential_storage.load_credentials()
        if not credentials:
            # Si no hay credenciales, iniciar sesión automáticamente
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
                    
                    def on_java_downloaded(success, java_path):
                        if success and java_path:
                            self.add_message(f"Java {required_java} descargada correctamente")
                            # Recargar versiones de Java
                            self.load_java_versions()
                            # Continuar con el lanzamiento
                            self.add_message(f"Lanzando Minecraft version: {selected_version}")
                            self.add_message(f"Usando Java: {java_path}")
                            self.launch_button.setEnabled(False)
                            success_launch, _ = self.minecraft_launcher.launch_minecraft(credentials, selected_version, java_path)
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
                            
                            def on_java_downloaded_retry(success, java_path):
                                if success and java_path:
                                    self.add_message(f"Java {required_java} descargada correctamente")
                                    # Recargar versiones de Java
                                    self.load_java_versions()
                                    # Intentar lanzar de nuevo con la Java descargada
                                    self.add_message(f"Reintentando lanzar con Java {required_java}...")
                                    self.launch_button.setEnabled(False)
                                    success_launch, _ = self.minecraft_launcher.launch_minecraft(credentials, selected_version, java_path)
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
            # Mostrar menú desplegable con opción de cerrar sesión
            menu = QMenu(self)
            logout_action = menu.addAction("Cerrar sesión")
            logout_action.triggered.connect(self.logout)
            
            # Mostrar el menú debajo del widget de usuario
            menu.exec_(self.user_widget.mapToGlobal(self.user_widget.rect().bottomLeft()))
        else:
            # Si no hay sesión, iniciar autenticación
            self.start_authentication()
    
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
                    cursor: pointer;
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
                    cursor: pointer;
                }
            """)
            self.user_avatar_label.setVisible(False)
            self.user_avatar_label.clear()
    
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

def main():
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

