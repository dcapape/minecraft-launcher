"""
Módulo para el administrador de servidores y perfiles
"""
import os
import json
import requests
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextEdit, 
                             QMessageBox, QComboBox, QListWidget, QCheckBox, 
                             QGroupBox, QScrollArea, QInputDialog, QApplication)
from PyQt5.QtCore import Qt


def fetch_profiles_json(hostname, api_key=None):
    """
    Función compartida para obtener el JSON de perfiles desde un servidor.
    
    Args:
        hostname: Hostname o IP del servidor (ej: "localhost" o "192.168.1.1")
        api_key: API Key opcional para autenticación
    
    Returns:
        tuple: (json_data, error_message)
        - json_data: Diccionario con los datos del JSON si tiene éxito, None si falla
        - error_message: Mensaje de error si falla, None si tiene éxito
    """
    if not hostname:
        return None, "Hostname no puede estar vacío"
    
    # Construir URL: http://hostname:25080/profiles.json
    url = f"http://{hostname}:25080/profiles.json"
    
    try:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        json_data = response.json()
        return json_data, None
        
    except requests.exceptions.RequestException as e:
        error_msg = f"No se pudo cargar la información del servidor: {str(e)}"
        return None, error_msg
    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        return None, error_msg


class ServerManagerDialog(QDialog):
    """Diálogo para administrar servidores y perfiles (solo modo desarrollador)"""
    
    def __init__(self, parent=None, minecraft_launcher=None):
        super().__init__(parent)
        self.minecraft_launcher = minecraft_launcher
        self.servers = []  # Lista de servidores guardados
        self.current_server = None
        self.current_profile_data = None
        self.current_json_data = None
        self.api_key_input = None  # Se inicializará en init_ui
        self.save_apikey_btn = None  # Se inicializará en init_ui
        
        self.setWindowTitle("Administrador de Servidores")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1000, 800)
        self._center_on_parent_screen(parent)
        
        # Cargar servidores guardados
        self.load_servers()
        
        self.init_ui()
    
    def _center_on_parent_screen(self, parent):
        """Centra la ventana en la pantalla donde está la ventana principal"""
        if parent:
            parent_geometry = parent.geometry()
            parent_center = parent_geometry.center()
            dialog_geometry = self.geometry()
            dialog_geometry.moveCenter(parent_center)
            self.setGeometry(dialog_geometry)
        else:
            screen = QApplication.primaryScreen().geometry()
            dialog_geometry = self.geometry()
            dialog_geometry.moveCenter(screen.center())
            self.setGeometry(dialog_geometry)
    
    def init_ui(self):
        """Inicializa la interfaz de usuario"""
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
        
        # Barra de título (importación diferida para evitar circular)
        from launcher import TitleBar
        title_bar = TitleBar(self)
        title_bar.setFixedHeight(35)
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(5)
        title_bar.setLayout(title_bar_layout)
        
        title = QLabel("Administrador de Servidores")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_bar_layout.addWidget(title, 1)
        
        # Botones de control alineados a la derecha
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(5)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.clicked.connect(self.showMinimized)
        minimize_btn.setFixedSize(24, 24)
        controls_layout.addWidget(minimize_btn)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.reject)
        close_btn.setFixedSize(24, 24)
        controls_layout.addWidget(close_btn)
        
        title_bar_layout.addLayout(controls_layout)
        
        layout.addWidget(title_bar)
        
        # Selector de servidores
        server_layout = QHBoxLayout()
        server_label = QLabel("Servidor:")
        server_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        server_layout.addWidget(server_label)
        
        self.server_combo = QComboBox()
        # NO conectar la señal todavía, se conectará después de crear todos los campos
        # self.server_combo.currentIndexChanged.connect(self.on_server_selected)
        self._refresh_server_combo()
        self.server_combo.setStyleSheet("""
            QComboBox {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 24px;
            }
            QComboBox:focus {
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
        server_layout.addWidget(self.server_combo, 1)
        
        add_server_btn = QPushButton("+")
        add_server_btn.setFixedSize(28, 28)
        add_server_btn.setToolTip("Añadir servidor")
        add_server_btn.clicked.connect(self.add_server)
        add_server_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
            }
        """)
        server_layout.addWidget(add_server_btn)
        
        reload_info_btn = QPushButton("🔄")
        reload_info_btn.setFixedSize(28, 28)
        reload_info_btn.setToolTip("Recargar información del servidor")
        reload_info_btn.clicked.connect(self.reload_server_info)
        reload_info_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                font-size: 14px;
                padding: 0px;
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
        server_layout.addWidget(reload_info_btn)
        
        layout.addLayout(server_layout)
        
        # Campo para editar API KEY
        apikey_layout = QHBoxLayout()
        apikey_label = QLabel("API Key:")
        apikey_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        apikey_label.setFixedWidth(100)
        apikey_layout.addWidget(apikey_label)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("API Key del servidor")
        self.api_key_input.setEnabled(False)
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8b5cf6;
            }
            QLineEdit:disabled {
                background: #0f0519;
                color: #888888;
                border-color: #3d1a5c;
            }
        """)
        apikey_layout.addWidget(self.api_key_input, 1)
        
        # Botones para API Key (guardar y recargar)
        apikey_buttons_layout = QVBoxLayout()
        apikey_buttons_layout.setSpacing(2)
        apikey_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        save_apikey_btn = QPushButton("💾")
        save_apikey_btn.setFixedSize(28, 28)
        save_apikey_btn.setToolTip("Guardar API Key")
        save_apikey_btn.setEnabled(False)
        save_apikey_btn.clicked.connect(self.save_api_key)
        save_apikey_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                font-size: 14px;
                padding: 0px;
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
        apikey_buttons_layout.addWidget(save_apikey_btn)
        self.save_apikey_btn = save_apikey_btn
        
        apikey_layout.addLayout(apikey_buttons_layout)
        
        layout.addLayout(apikey_layout)
        
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
        
        # Área scrollable con campos de edición
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
        
        edit_widget = QWidget()
        edit_widget.setStyleSheet("""
            QWidget {
                background: rgba(26, 13, 46, 0.6);
            }
        """)
        edit_layout = QVBoxLayout()
        edit_layout.setSpacing(10)
        
        # Campos de edición del perfil
        # ID del servidor
        id_layout = QHBoxLayout()
        id_label = QLabel("ID del perfil:")
        id_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        id_label.setFixedWidth(150)
        id_layout.addWidget(id_label)
        
        self.profile_id_input = QLineEdit()
        self.profile_id_input.setStyleSheet("""
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
        self.profile_id_input.textChanged.connect(self.update_json_display)
        id_layout.addWidget(self.profile_id_input, 1)
        edit_layout.addLayout(id_layout)
        
        # Nombre
        name_layout = QHBoxLayout()
        name_label = QLabel("Nombre:")
        name_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        name_label.setFixedWidth(150)
        name_layout.addWidget(name_label)
        
        self.profile_name_input = QLineEdit()
        self.profile_name_input.setStyleSheet(self.profile_id_input.styleSheet())
        self.profile_name_input.textChanged.connect(self.update_json_display)
        name_layout.addWidget(self.profile_name_input, 1)
        edit_layout.addLayout(name_layout)
        
        # Descripción
        desc_layout = QHBoxLayout()
        desc_label = QLabel("Descripción:")
        desc_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        desc_label.setFixedWidth(150)
        desc_layout.addWidget(desc_label)
        
        self.profile_desc_input = QLineEdit()
        self.profile_desc_input.setStyleSheet(self.profile_id_input.styleSheet())
        self.profile_desc_input.textChanged.connect(self.update_json_display)
        desc_layout.addWidget(self.profile_desc_input, 1)
        edit_layout.addLayout(desc_layout)
        
        # Lista de mods
        mods_group = QGroupBox("Mods")
        mods_group.setStyleSheet("""
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
        mods_layout = QVBoxLayout()
        
        mods_list_layout = QHBoxLayout()
        self.mods_list = QListWidget()
        self.mods_list.setEnabled(False)
        self.mods_list.setStyleSheet("""
            QListWidget {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 1px solid #6d28d9;
                border-radius: 3px;
                font-size: 11px;
            }
        """)
        mods_list_layout.addWidget(self.mods_list, 1)
        
        add_mod_btn = QPushButton("+")
        add_mod_btn.setFixedSize(30, 30)
        add_mod_btn.setToolTip("Añadir mod desde .minecraft")
        add_mod_btn.clicked.connect(self.add_mod_from_minecraft)
        add_mod_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
            }
        """)
        mods_list_layout.addWidget(add_mod_btn)
        mods_layout.addLayout(mods_list_layout)
        
        mods_group.setLayout(mods_layout)
        edit_layout.addWidget(mods_group)
        
        # Lista de shaders
        shaders_group = QGroupBox("Shaders")
        shaders_group.setStyleSheet("""
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
        shaders_layout = QVBoxLayout()
        
        shaders_list_layout = QHBoxLayout()
        self.shaders_list = QListWidget()
        self.shaders_list.setEnabled(False)
        self.shaders_list.setStyleSheet("""
            QListWidget {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 1px solid #6d28d9;
                border-radius: 3px;
                font-size: 11px;
            }
        """)
        self.shaders_list.itemDoubleClicked.connect(self.toggle_shader_enabled)
        shaders_list_layout.addWidget(self.shaders_list, 1)
        
        add_shader_btn = QPushButton("+")
        add_shader_btn.setFixedSize(30, 30)
        add_shader_btn.setToolTip("Añadir shader desde .minecraft")
        add_shader_btn.clicked.connect(self.add_shader_from_minecraft)
        add_shader_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7c3aed, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 5px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
            }
        """)
        shaders_list_layout.addWidget(add_shader_btn)
        shaders_layout.addLayout(shaders_list_layout)
        
        shaders_group.setLayout(shaders_layout)
        edit_layout.addWidget(shaders_group)
        
        # Lista de resource packs
        resourcepacks_group = QGroupBox("Resource Packs")
        resourcepacks_group.setStyleSheet(shaders_group.styleSheet())
        resourcepacks_layout = QVBoxLayout()
        
        resourcepacks_list_layout = QHBoxLayout()
        self.resourcepacks_list = QListWidget()
        self.resourcepacks_list.setEnabled(False)
        self.resourcepacks_list.setStyleSheet(self.shaders_list.styleSheet())
        self.resourcepacks_list.itemDoubleClicked.connect(self.toggle_resourcepack_enabled)
        resourcepacks_list_layout.addWidget(self.resourcepacks_list, 1)
        
        add_resourcepack_btn = QPushButton("+")
        add_resourcepack_btn.setFixedSize(30, 30)
        add_resourcepack_btn.setToolTip("Añadir resource pack desde .minecraft")
        add_resourcepack_btn.clicked.connect(self.add_resourcepack_from_minecraft)
        add_resourcepack_btn.setStyleSheet(add_shader_btn.styleSheet())
        resourcepacks_list_layout.addWidget(add_resourcepack_btn)
        resourcepacks_layout.addLayout(resourcepacks_list_layout)
        
        resourcepacks_group.setLayout(resourcepacks_layout)
        edit_layout.addWidget(resourcepacks_group)
        
        # Opciones
        options_group = QGroupBox("Opciones")
        options_group.setStyleSheet(shaders_group.styleSheet())
        options_layout = QVBoxLayout()
        
        self.enable_shaders_checkbox = QCheckBox("Activar shaders")
        self.enable_shaders_checkbox.setStyleSheet("""
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
        self.enable_shaders_checkbox.stateChanged.connect(self.update_options)
        options_layout.addWidget(self.enable_shaders_checkbox)
        
        self.enable_resourcepacks_checkbox = QCheckBox("Activar resource packs")
        self.enable_resourcepacks_checkbox.setStyleSheet(self.enable_shaders_checkbox.styleSheet())
        self.enable_resourcepacks_checkbox.stateChanged.connect(self.update_options)
        options_layout.addWidget(self.enable_resourcepacks_checkbox)
        
        options_group.setLayout(options_layout)
        edit_layout.addWidget(options_group)
        
        # Textarea con JSON
        json_label = QLabel("JSON del perfil:")
        json_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        edit_layout.addWidget(json_label)
        
        self.json_textarea = QTextEdit()
        self.json_textarea.setReadOnly(True)
        self.json_textarea.setStyleSheet("""
            QTextEdit {
                background: #1a0d2e;
                color: #e9d5ff;
                border: 2px solid #6d28d9;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        self.json_textarea.setMinimumHeight(150)
        edit_layout.addWidget(self.json_textarea)
        
        edit_widget.setLayout(edit_layout)
        scroll_area.setWidget(edit_widget)
        layout.addWidget(scroll_area, 1)
        
        # Botones (orden: Aplicar, Cancelar, Aceptar)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.apply_button = QPushButton("Aplicar")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_changes)
        self.apply_button.setStyleSheet("""
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
        button_layout.addWidget(self.apply_button)
        
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
        
        self.accept_button = QPushButton("Aceptar")
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.accept_and_close)
        self.accept_button.setStyleSheet(self.apply_button.styleSheet())
        button_layout.addWidget(self.accept_button)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
        
        # Layout principal del diálogo
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(central_widget)
        self.setLayout(main_layout)
        
        # Ahora que todos los campos están inicializados, conectar la señal
        self.server_combo.currentIndexChanged.connect(self.on_server_selected)
        
        # Si hay servidores, seleccionar el primero
        if self.server_combo.count() > 0:
            self.server_combo.setCurrentIndex(0)
        
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
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #dc2626, stop:1 #b91c1c);
                color: white;
                border: 2px solid #ef4444;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#closeButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ef4444, stop:1 #dc2626);
                border-color: #f87171;
            }
            QPushButton#minimizeButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6d28d9, stop:1 #5b21b6);
                color: white;
                border: 2px solid #8b5cf6;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton#minimizeButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8b5cf6, stop:1 #6d28d9);
                border-color: #a78bfa;
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
    
    def load_servers(self):
        """Carga los servidores guardados desde la configuración"""
        try:
            from config import CONFIG_FILE
            
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.servers = config.get('servers', [])
        except Exception as e:
            print(f"Error cargando servidores: {e}")
            self.servers = []
    
    def save_servers(self):
        """Guarda los servidores en la configuración"""
        try:
            from config import CONFIG_FILE
            
            config = {}
            if CONFIG_FILE.exists():
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except:
                    config = {}
            
            config['servers'] = self.servers
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error guardando servidores: {e}")
    
    def _refresh_server_combo(self):
        """Actualiza el combo de servidores"""
        self.server_combo.clear()
        for server in self.servers:
            display_name = f"{server.get('name', server.get('hostname', 'Sin nombre'))} ({server.get('hostname', 'N/A')})"
            self.server_combo.addItem(display_name, server)
    
    def add_server(self):
        """Abre diálogo para añadir un nuevo servidor"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Añadir Servidor")
        dialog.resize(400, 200)
        
        # Widget central con fondo morado
        central_widget = QWidget()
        central_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Hostname/IP
        hostname_layout = QHBoxLayout()
        hostname_label = QLabel("Hostname/IP:")
        hostname_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        hostname_label.setFixedWidth(100)
        hostname_layout.addWidget(hostname_label)
        
        hostname_input = QLineEdit()
        hostname_input.setPlaceholderText("servidormc.com o 192.168.1.1")
        hostname_input.setStyleSheet("""
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
        hostname_layout.addWidget(hostname_input, 1)
        layout.addLayout(hostname_layout)
        
        # API Key
        apikey_layout = QHBoxLayout()
        apikey_label = QLabel("API Key:")
        apikey_label.setStyleSheet("color: #e9d5ff; font-size: 12px;")
        apikey_label.setFixedWidth(100)
        apikey_layout.addWidget(apikey_label)
        
        apikey_input = QLineEdit()
        apikey_input.setPlaceholderText("Tu API key del servidor")
        apikey_input.setStyleSheet(hostname_input.styleSheet())
        apikey_layout.addWidget(apikey_input, 1)
        layout.addLayout(apikey_layout)
        
        # Botones
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("""
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
            }
        """)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Aceptar")
        ok_btn.clicked.connect(lambda: self._save_new_server(dialog, hostname_input.text(), apikey_input.text()))
        ok_btn.setStyleSheet("""
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
        """)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(central_widget)
        dialog.setLayout(main_layout)
        
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a0d2e, stop:0.5 #2d1b4e, stop:1 #1a0d2e);
            }
        """)
        
        dialog.exec_()
    
    def _save_new_server(self, dialog, hostname, api_key):
        """Guarda un nuevo servidor"""
        if not hostname or not api_key:
            QMessageBox.warning(dialog, "Error", "Por favor, completa todos los campos")
            return
        
        new_server = {
            "hostname": hostname,
            "api_key": api_key,
            "name": hostname  # Por defecto usar hostname como nombre
        }
        
        self.servers.append(new_server)
        self.save_servers()
        self._refresh_server_combo()
        self.server_combo.setCurrentIndex(self.server_combo.count() - 1)
        dialog.accept()
    
    def save_api_key(self):
        """Guarda la API KEY editada del servidor actual"""
        if not self.current_server:
            return
        
        new_api_key = self.api_key_input.text()
        if not new_api_key:
            QMessageBox.warning(self, "Error", "La API Key no puede estar vacía")
            return
        
        # Actualizar la API KEY en el servidor actual
        self.current_server["api_key"] = new_api_key
        
        # Guardar en la configuración
        self.save_servers()
        
        # Actualizar el combo para reflejar cambios
        self._refresh_server_combo()
        
        # Mantener la selección actual
        for i in range(self.server_combo.count()):
            server_data = self.server_combo.itemData(i)
            if server_data and server_data.get("hostname") == self.current_server.get("hostname"):
                self.server_combo.setCurrentIndex(i)
                break
        
        # Preguntar si quiere recargar la información
        reply = QMessageBox.question(
            self, 
            "API Key Guardada", 
            "API Key guardada correctamente.\n\n¿Deseas recargar la información del servidor ahora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.reload_server_info()
    
    def on_server_selected(self, index):
        """Se llama cuando se selecciona un servidor"""
        print(f"[DEBUG] on_server_selected() llamado con índice: {index}")
        
        # Verificar que los campos estén inicializados
        if not self.api_key_input or not self.save_apikey_btn:
            print(f"[DEBUG] Campos no inicializados, abortando")
            return
        
        if index < 0:
            print(f"[DEBUG] Índice negativo, deshabilitando campos")
            self.api_key_input.setEnabled(False)
            self.api_key_input.setText("")
            self.save_apikey_btn.setEnabled(False)
            return
        
        server = self.server_combo.itemData(index)
        if not server:
            print(f"[DEBUG] No hay datos del servidor en el índice {index}")
            self.api_key_input.setEnabled(False)
            self.api_key_input.setText("")
            self.save_apikey_btn.setEnabled(False)
            return
        
        print(f"[DEBUG] Servidor seleccionado: {server.get('hostname', 'N/A')}")
        self.current_server = server
        # Mostrar API KEY actual y habilitar edición
        api_key = server.get("api_key", "")
        self.api_key_input.setText(api_key)
        self.api_key_input.setEnabled(True)
        self.save_apikey_btn.setEnabled(True)
        
        print(f"[DEBUG] Llamando a reload_server_info()...")
        self.reload_server_info()
    
    def reload_server_info(self):
        """Recarga la información del servidor desde el endpoint"""
        print(f"[DEBUG] reload_server_info() llamado")
        
        # Si no hay servidor actual, intentar obtenerlo del combo
        if not self.current_server:
            print(f"[DEBUG] No hay servidor actual, intentando obtener del combo...")
            current_index = self.server_combo.currentIndex()
            if current_index >= 0:
                server = self.server_combo.itemData(current_index)
                if server:
                    print(f"[DEBUG] Servidor obtenido del combo: {server.get('hostname', 'N/A')}")
                    self.current_server = server
                    # Actualizar campos de API key
                    if self.api_key_input:
                        api_key = server.get("api_key", "")
                        self.api_key_input.setText(api_key)
                        self.api_key_input.setEnabled(True)
                        if self.save_apikey_btn:
                            self.save_apikey_btn.setEnabled(True)
                else:
                    print(f"[DEBUG] No hay datos del servidor en el índice {current_index}")
                    return
            else:
                print(f"[DEBUG] No hay servidor seleccionado en el combo")
                QMessageBox.warning(self, "Advertencia", "Por favor, selecciona un servidor primero.")
                return
        
        hostname = self.current_server.get("hostname")
        api_key = self.current_server.get("api_key")
        
        print(f"[DEBUG] Hostname: {hostname}, API Key presente: {bool(api_key)}")
        
        if not hostname:
            print(f"[DEBUG] Hostname vacío, abortando")
            return
        
        # Usar la función compartida para obtener el JSON
        print(f"[DEBUG] Intentando conectar a: http://{hostname}:25080/profiles.json")
        json_data, error_message = fetch_profiles_json(hostname, api_key)
        
        if error_message:
            print(f"[DEBUG] Error: {error_message}")
            error_msg = f"{error_message}\n\n"
            error_msg += "Puedes editar la API Key arriba y hacer clic en '🔄' para recargar."
            QMessageBox.warning(self, "Advertencia", error_msg)
            # Limpiar datos si falla
            self.current_json_data = None
            self.profile_combo.clear()
            self.profile_combo.setEnabled(False)
            return
        
        if not json_data:
            print(f"[DEBUG] No se recibieron datos")
            QMessageBox.warning(self, "Advertencia", "No se recibieron datos del servidor")
            self.current_json_data = None
            self.profile_combo.clear()
            self.profile_combo.setEnabled(False)
            return
        
        try:
            self.current_json_data = json_data
            print(f"[DEBUG] JSON recibido correctamente, {len(self.current_json_data.get('profiles', []))} perfiles encontrados")
            
            # Llenar selector de perfiles
            self.profile_combo.clear()
            if "profiles" in self.current_json_data and self.current_json_data["profiles"]:
                for profile in self.current_json_data["profiles"]:
                    profile_name = profile.get("name", profile.get("id", "Sin nombre"))
                    self.profile_combo.addItem(profile_name, profile)
                
                self.profile_combo.setEnabled(True)
                if self.profile_combo.count() > 0:
                    self.profile_combo.setCurrentIndex(0)
                    self.on_profile_selected(0)
        except Exception as e:
            print(f"[DEBUG] Error inesperado: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            error_msg = f"Error inesperado:\n{str(e)}\n\n"
            error_msg += "Puedes editar la API Key arriba y hacer clic en '🔄' para recargar."
            QMessageBox.warning(self, "Advertencia", error_msg)
            # Limpiar datos si falla
            self.current_json_data = None
            self.profile_combo.clear()
            self.profile_combo.setEnabled(False)
    
    def on_profile_selected(self, index):
        """Se llama cuando se selecciona un perfil"""
        if index < 0 or not self.current_json_data:
            return
        
        profile = self.profile_combo.itemData(index)
        if not profile:
            return
        
        self.current_profile_data = profile.copy()
        
        # Llenar campos de edición
        self.profile_id_input.setText(profile.get("id", ""))
        self.profile_name_input.setText(profile.get("name", ""))
        self.profile_desc_input.setText(profile.get("description", ""))
        
        # Llenar lista de mods
        self.mods_list.clear()
        mods = profile.get("mods", [])
        for mod in mods:
            mod_name = mod.get("name", "Sin nombre")
            required = mod.get("required", False)
            required_text = " (Requerido)" if required else ""
            self.mods_list.addItem(f"{mod_name}{required_text}")
        self.mods_list.setEnabled(True)
        
        # Llenar lista de shaders
        self.shaders_list.clear()
        shaders = profile.get("shaders", [])
        for shader in shaders:
            shader_name = shader.get("name", "Sin nombre")
            enabled = shader.get("enabled", False)
            enabled_text = " (Activado)" if enabled else ""
            self.shaders_list.addItem(f"{shader_name}{enabled_text}")
        self.shaders_list.setEnabled(True)
        
        # Llenar lista de resource packs
        self.resourcepacks_list.clear()
        resourcepacks = profile.get("resourcepacks", [])
        for rp in resourcepacks:
            rp_name = rp.get("name", "Sin nombre")
            enabled = rp.get("enabled", False)
            enabled_text = " (Activado)" if enabled else ""
            self.resourcepacks_list.addItem(f"{rp_name}{enabled_text}")
        self.resourcepacks_list.setEnabled(True)
        
        # Llenar opciones
        options = profile.get("options", {})
        self.enable_shaders_checkbox.setChecked(options.get("enable_shaders", False))
        self.enable_resourcepacks_checkbox.setChecked(options.get("enable_resourcepacks", False))
        
        # Actualizar JSON
        self.update_json_display()
        
        # Habilitar botones
        self.apply_button.setEnabled(True)
        self.accept_button.setEnabled(True)
    
    def add_shader_from_minecraft(self):
        """Abre diálogo para seleccionar shader desde .minecraft/shaders"""
        shaderpacks_dir = os.path.join(self.minecraft_launcher.minecraft_path, "shaderpacks")
        if not os.path.exists(shaderpacks_dir):
            QMessageBox.warning(self, "Error", "No se encontró la carpeta de shaders en .minecraft")
            return
        
        # Obtener shaders ya añadidos a la lista (sin el sufijo " (Activado)")
        already_added = set()
        for i in range(self.shaders_list.count()):
            item_text = self.shaders_list.item(i).text()
            shader_name = item_text.replace(" (Activado)", "")
            already_added.add(shader_name)
        
        # Listar shaders disponibles (excluyendo los ya añadidos)
        available_shaders = []
        for item in os.listdir(shaderpacks_dir):
            item_path = os.path.join(shaderpacks_dir, item)
            if os.path.isfile(item_path) and item.endswith(('.zip', '.jar')):
                if item not in already_added:
                    available_shaders.append(item)
        
        if not available_shaders:
            if already_added:
                QMessageBox.information(self, "Info", "Todos los shaders disponibles ya están en la lista.")
            else:
                QMessageBox.information(self, "Info", "No hay shaders instalados en .minecraft")
            return
        
        # Diálogo simple para seleccionar shader
        shader, ok = QInputDialog.getItem(
            self,
            "Seleccionar Shader",
            "Shader:",
            available_shaders,
            0,
            False
        )
        
        if ok and shader:
            # Agregar a la lista
            self.shaders_list.addItem(shader)
            self.update_options()
            self.update_json_display()
    
    def add_mod_from_minecraft(self):
        """Abre diálogo para seleccionar mod desde .minecraft/mods"""
        mods_dir = os.path.join(self.minecraft_launcher.minecraft_path, "mods")
        if not os.path.exists(mods_dir):
            QMessageBox.warning(self, "Error", "No se encontró la carpeta de mods en .minecraft")
            return
        
        # Obtener mods ya añadidos a la lista (sin el sufijo " (Requerido)")
        already_added = set()
        for i in range(self.mods_list.count()):
            item_text = self.mods_list.item(i).text()
            mod_name = item_text.replace(" (Requerido)", "")
            already_added.add(mod_name)
        
        # Listar mods disponibles (excluyendo los ya añadidos)
        available_mods = []
        for item in os.listdir(mods_dir):
            item_path = os.path.join(mods_dir, item)
            if os.path.isfile(item_path) and item.endswith('.jar'):
                if item not in already_added:
                    available_mods.append(item)
        
        if not available_mods:
            if already_added:
                QMessageBox.information(self, "Info", "Todos los mods disponibles ya están en la lista.")
            else:
                QMessageBox.information(self, "Info", "No hay mods instalados en .minecraft")
            return
        
        # Diálogo simple para seleccionar mod
        mod, ok = QInputDialog.getItem(
            self,
            "Seleccionar Mod",
            "Mod:",
            available_mods,
            0,
            False
        )
        
        if ok and mod:
            # Agregar a la lista
            self.mods_list.addItem(mod)
            self.mods_list.setEnabled(True)
            self.update_json_display()
    
    def add_resourcepack_from_minecraft(self):
        """Abre diálogo para seleccionar resource pack desde .minecraft/resourcepacks"""
        resourcepacks_dir = os.path.join(self.minecraft_launcher.minecraft_path, "resourcepacks")
        if not os.path.exists(resourcepacks_dir):
            QMessageBox.warning(self, "Error", "No se encontró la carpeta de resource packs en .minecraft")
            return
        
        # Obtener resource packs ya añadidos a la lista (sin el sufijo " (Activado)")
        already_added = set()
        for i in range(self.resourcepacks_list.count()):
            item_text = self.resourcepacks_list.item(i).text()
            rp_name = item_text.replace(" (Activado)", "")
            already_added.add(rp_name)
        
        # Listar resource packs disponibles (excluyendo los ya añadidos)
        available_rps = []
        for item in os.listdir(resourcepacks_dir):
            item_path = os.path.join(resourcepacks_dir, item)
            if os.path.isfile(item_path) and item.endswith(('.zip', '.jar')):
                if item not in already_added:
                    available_rps.append(item)
        
        if not available_rps:
            if already_added:
                QMessageBox.information(self, "Info", "Todos los resource packs disponibles ya están en la lista.")
            else:
                QMessageBox.information(self, "Info", "No hay resource packs instalados en .minecraft")
            return
        
        # Diálogo simple para seleccionar resource pack
        rp, ok = QInputDialog.getItem(
            self,
            "Seleccionar Resource Pack",
            "Resource Pack:",
            available_rps,
            0,
            False
        )
        
        if ok and rp:
            # Agregar a la lista
            self.resourcepacks_list.addItem(rp)
            self.resourcepacks_list.setEnabled(True)
            self.update_options()
            self.update_json_display()
    
    def toggle_shader_enabled(self, item):
        """Alterna el estado activado/desactivado de un shader"""
        text = item.text()
        if " (Activado)" in text:
            item.setText(text.replace(" (Activado)", ""))
        else:
            item.setText(text + " (Activado)")
        self.update_json_display()
    
    def toggle_resourcepack_enabled(self, item):
        """Alterna el estado activado/desactivado de un resource pack"""
        text = item.text()
        if " (Activado)" in text:
            item.setText(text.replace(" (Activado)", ""))
        else:
            item.setText(text + " (Activado)")
        self.update_json_display()
    
    def keyPressEvent(self, event):
        """Maneja eventos de teclado para eliminar items de las listas"""
        if event.key() == Qt.Key_Delete:
            # Eliminar item seleccionado de mods
            if self.mods_list.hasFocus() and self.mods_list.currentItem():
                self.mods_list.takeItem(self.mods_list.currentRow())
                self.update_json_display()
            # Eliminar item seleccionado de shaders
            elif self.shaders_list.hasFocus() and self.shaders_list.currentItem():
                self.shaders_list.takeItem(self.shaders_list.currentRow())
                self.update_json_display()
            # Eliminar item seleccionado de resource packs
            elif self.resourcepacks_list.hasFocus() and self.resourcepacks_list.currentItem():
                self.resourcepacks_list.takeItem(self.resourcepacks_list.currentRow())
                self.update_json_display()
        super().keyPressEvent(event)
    
    def update_options(self):
        """Actualiza las opciones basándose en los shaders y resource packs seleccionados"""
        # Esta función se llamará cuando cambien los checkboxes
        # Las opciones se actualizarán automáticamente en update_json_display
        self.update_json_display()
    
    def update_json_display(self):
        """Actualiza el textarea con el JSON del perfil editado"""
        if not self.current_profile_data:
            return
        
        # Crear copia del perfil para editar
        edited_profile = self.current_profile_data.copy()
        
        # Actualizar campos básicos
        edited_profile["id"] = self.profile_id_input.text()
        edited_profile["name"] = self.profile_name_input.text()
        edited_profile["description"] = self.profile_desc_input.text()
        
        # Actualizar mods desde la lista
        mods = []
        for i in range(self.mods_list.count()):
            item_text = self.mods_list.item(i).text()
            mod_name = item_text.replace(" (Requerido)", "")
            required = " (Requerido)" in item_text
            mods.append({
                "name": mod_name,
                "required": required
            })
        edited_profile["mods"] = mods
        
        # Actualizar shaders desde la lista
        shaders = []
        for i in range(self.shaders_list.count()):
            item_text = self.shaders_list.item(i).text()
            shader_name = item_text.replace(" (Activado)", "")
            enabled = " (Activado)" in item_text
            shaders.append({
                "name": shader_name,
                "enabled": enabled,
                "required": False
            })
        edited_profile["shaders"] = shaders
        
        # Actualizar resource packs desde la lista
        resourcepacks = []
        for i in range(self.resourcepacks_list.count()):
            item_text = self.resourcepacks_list.item(i).text()
            rp_name = item_text.replace(" (Activado)", "")
            enabled = " (Activado)" in item_text
            resourcepacks.append({
                "name": rp_name,
                "enabled": enabled,
                "required": False
            })
        edited_profile["resourcepacks"] = resourcepacks
        
        # Actualizar opciones
        if "options" not in edited_profile:
            edited_profile["options"] = {}
        
        edited_profile["options"]["enable_shaders"] = self.enable_shaders_checkbox.isChecked()
        edited_profile["options"]["enable_resourcepacks"] = self.enable_resourcepacks_checkbox.isChecked()
        
        # Actualizar shader_pack y resource_packs en opciones
        enabled_shaders = [s["name"].replace(".zip", "").replace(".jar", "") for s in shaders if s.get("enabled")]
        enabled_rps = [rp["name"].replace(".zip", "").replace(".jar", "") for rp in resourcepacks if rp.get("enabled")]
        
        if enabled_shaders:
            edited_profile["options"]["shader_pack"] = enabled_shaders[0]
        if enabled_rps:
            edited_profile["options"]["resource_packs"] = enabled_rps
        
        # Mostrar JSON formateado
        json_str = json.dumps(edited_profile, indent=2, ensure_ascii=False)
        self.json_textarea.setPlainText(json_str)
    
    def apply_changes(self):
        """Aplica los cambios al servidor (POST con JSON y archivos)"""
        print(f"[DEBUG] apply_changes() llamado")
        
        if not self.current_server or not self.current_profile_data:
            print(f"[DEBUG] No hay servidor o perfil actual, abortando")
            return
        
        # Construir JSON final
        edited_profile = self._build_edited_profile()
        print(f"[DEBUG] Perfil editado construido: {edited_profile.get('id', 'N/A')}")
        
        # Obtener archivos nuevos (mods, shaders, resource packs) que están en cliente pero no en servidor
        files_to_upload = self._get_new_files(edited_profile)
        print(f"[DEBUG] Archivos a subir: {len(files_to_upload)}")
        for file_type, file_path in files_to_upload:
            print(f"[DEBUG]   - {file_type}: {os.path.basename(file_path)}")
        
        # Enviar POST al servidor
        hostname = self.current_server.get("hostname")
        api_key = self.current_server.get("api_key")
        url = f"http://{hostname}:25080/update"
        
        print(f"[DEBUG] ===== INICIANDO PETICIÓN POST A /update =====")
        print(f"[DEBUG] URL: {url}")
        print(f"[DEBUG] Hostname: {hostname}")
        print(f"[DEBUG] API Key presente: {bool(api_key)}")
        if api_key:
            print(f"[DEBUG] API Key (primeros 10 chars): {api_key[:10]}...")
        else:
            print(f"[DEBUG] ⚠️  ADVERTENCIA: No hay API Key configurada")
        
        try:
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key
            else:
                print(f"[DEBUG] ⚠️  ADVERTENCIA: No se agregó header X-API-Key")
            
            print(f"[DEBUG] Headers a enviar: {list(headers.keys())}")
            
            # Preparar datos multipart/form-data
            files_dict = {}
            form_data = {}
            
            # Agregar JSON del perfil
            profile_json_str = json.dumps(edited_profile, ensure_ascii=False)
            form_data["profile_json"] = profile_json_str
            print(f"[DEBUG] Tamaño del JSON del perfil: {len(profile_json_str)} caracteres")
            
            # Agregar archivos a enviar
            file_counters = {"mods": 0, "shaders": 0, "resourcepacks": 0}
            files_metadata = []
            
            for file_type, file_path in files_to_upload:
                if os.path.exists(file_path):
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    
                    # Contador específico por tipo
                    counter = file_counters[file_type]
                    file_counters[file_type] += 1
                    
                    # Nombre de campo más descriptivo: tipo_índice
                    field_name = f"{file_type}_{counter}"
                    
                    print(f"[DEBUG] Preparando archivo: {file_name} ({file_size} bytes) como {field_name}")
                    files_dict[field_name] = (file_name, open(file_path, 'rb'), 'application/octet-stream')
                    
                    # Agregar metadatos
                    files_metadata.append({
                        "field_name": field_name,
                        "type": file_type,
                        "name": file_name,
                        "size": file_size
                    })
            
            # Agregar metadatos de archivos al form_data
            if files_metadata:
                form_data["files_metadata"] = json.dumps(files_metadata, ensure_ascii=False)
                print(f"[DEBUG] Metadatos de archivos: {json.dumps(files_metadata, indent=2)}")
            
            # Si hay archivos, usar multipart/form-data, sino solo JSON
            if files_dict:
                print(f"[DEBUG] Enviando POST con multipart/form-data ({len(files_dict)} archivos)")
                print(f"[DEBUG] Form data keys: {list(form_data.keys())}")
                print(f"[DEBUG] Files dict keys: {list(files_dict.keys())}")
                print(f"[DEBUG] Headers a enviar: {headers}")
                
                # Asegurar que los headers se envíen correctamente con multipart/form-data
                # requests puede no enviar headers personalizados correctamente con files=, 
                # así que los agregamos también al form_data como alternativa
                if api_key:
                    form_data["api_key"] = api_key
                    print(f"[DEBUG] API Key también agregada al form_data como respaldo")
                
                response = requests.post(url, files=files_dict, data=form_data, headers=headers, timeout=60)
                
                # Cerrar archivos
                for file_tuple in files_dict.values():
                    if len(file_tuple) > 1 and hasattr(file_tuple[1], 'close'):
                        file_tuple[1].close()
            else:
                print(f"[DEBUG] Enviando POST solo con JSON (sin archivos)")
                headers["Content-Type"] = "application/json"
                print(f"[DEBUG] Headers finales: {headers}")
                response = requests.post(url, json=edited_profile, headers=headers, timeout=30)
            
            print(f"[DEBUG] ===== RESPUESTA RECIBIDA =====")
            print(f"[DEBUG] Status Code: {response.status_code}")
            print(f"[DEBUG] Response Headers: {dict(response.headers)}")
            print(f"[DEBUG] Response Text (primeros 500 chars): {response.text[:500]}")
            
            response.raise_for_status()
            
            print(f"[DEBUG] ✅ Petición exitosa")
            QMessageBox.information(self, "Éxito", f"Cambios aplicados correctamente al servidor.\n{len(files_to_upload)} archivo(s) enviado(s).")
            self.reload_server_info()
        except requests.exceptions.HTTPError as e:
            print(f"[DEBUG] ===== ERROR HTTP =====")
            print(f"[DEBUG] Status Code: {e.response.status_code if hasattr(e, 'response') else 'N/A'}")
            if hasattr(e, 'response'):
                print(f"[DEBUG] Response Headers: {dict(e.response.headers)}")
                print(f"[DEBUG] Response Text: {e.response.text}")
            print(f"[DEBUG] Error: {str(e)}")
            error_msg = f"No se pudo aplicar los cambios:\nHTTP {e.response.status_code if hasattr(e, 'response') else 'N/A'}: {str(e)}"
            if hasattr(e, 'response') and e.response.status_code == 401:
                error_msg += "\n\n⚠️ Error 401: No autorizado. Verifica que la API Key sea correcta."
            QMessageBox.critical(self, "Error", error_msg)
        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] ===== ERROR EN PETICIÓN =====")
            print(f"[DEBUG] Tipo de error: {type(e).__name__}")
            print(f"[DEBUG] Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"No se pudo aplicar los cambios:\n{str(e)}")
        except Exception as e:
            print(f"[DEBUG] ===== ERROR INESPERADO =====")
            print(f"[DEBUG] Tipo de error: {type(e).__name__}")
            print(f"[DEBUG] Error: {str(e)}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error inesperado:\n{str(e)}")
    
    def accept_and_close(self):
        """Aplica los cambios y cierra la ventana"""
        self.apply_changes()
        self.accept()
    
    def _build_edited_profile(self):
        """Construye el perfil editado desde los campos"""
        edited_profile = self.current_profile_data.copy()
        
        edited_profile["id"] = self.profile_id_input.text()
        edited_profile["name"] = self.profile_name_input.text()
        edited_profile["description"] = self.profile_desc_input.text()
        
        # Mods
        mods = []
        for i in range(self.mods_list.count()):
            item_text = self.mods_list.item(i).text()
            mod_name = item_text.replace(" (Requerido)", "")
            required = " (Requerido)" in item_text
            mods.append({
                "name": mod_name,
                "required": required
            })
        edited_profile["mods"] = mods
        
        # Shaders
        shaders = []
        for i in range(self.shaders_list.count()):
            item_text = self.shaders_list.item(i).text()
            shader_name = item_text.replace(" (Activado)", "")
            enabled = " (Activado)" in item_text
            shaders.append({
                "name": shader_name,
                "enabled": enabled,
                "required": False
            })
        edited_profile["shaders"] = shaders
        
        # Resource packs
        resourcepacks = []
        for i in range(self.resourcepacks_list.count()):
            item_text = self.resourcepacks_list.item(i).text()
            rp_name = item_text.replace(" (Activado)", "")
            enabled = " (Activado)" in item_text
            resourcepacks.append({
                "name": rp_name,
                "enabled": enabled,
                "required": False
            })
        edited_profile["resourcepacks"] = resourcepacks
        
        # Opciones
        if "options" not in edited_profile:
            edited_profile["options"] = {}
        
        edited_profile["options"]["enable_shaders"] = self.enable_shaders_checkbox.isChecked()
        edited_profile["options"]["enable_resourcepacks"] = self.enable_resourcepacks_checkbox.isChecked()
        
        enabled_shaders = [s["name"].replace(".zip", "").replace(".jar", "") for s in shaders if s.get("enabled")]
        enabled_rps = [rp["name"].replace(".zip", "").replace(".jar", "") for rp in resourcepacks if rp.get("enabled")]
        
        if enabled_shaders:
            edited_profile["options"]["shader_pack"] = enabled_shaders[0]
        if enabled_rps:
            edited_profile["options"]["resource_packs"] = enabled_rps
        
        return edited_profile
    
    def _get_new_files(self, edited_profile):
        """Obtiene los archivos nuevos que están en cliente pero no en servidor"""
        files_to_upload = []
        
        # Usar el perfil original del servidor para comparar (no el editado)
        original_profile = self.current_profile_data if self.current_profile_data else edited_profile
        
        # Verificar mods (solo los que están en la lista de mods seleccionados)
        client_mods_dir = os.path.join(self.minecraft_launcher.minecraft_path, "mods")
        if os.path.exists(client_mods_dir):
            server_mods = {mod.get("name") for mod in original_profile.get("mods", [])}
            # Solo incluir los mods que el usuario agregó en la lista
            for i in range(self.mods_list.count()):
                item_text = self.mods_list.item(i).text()
                mod_name = item_text.replace(" (Requerido)", "")
                if mod_name not in server_mods:
                    mod_path = os.path.join(client_mods_dir, mod_name)
                    if os.path.exists(mod_path):
                        files_to_upload.append(("mods", mod_path))
        
        # Verificar shaders (comparar con shaders del servidor original)
        client_shaders_dir = os.path.join(self.minecraft_launcher.minecraft_path, "shaderpacks")
        if os.path.exists(client_shaders_dir):
            server_shaders = {shader.get("name") for shader in original_profile.get("shaders", [])}
            # También verificar los shaders que el usuario agregó en la lista
            for i in range(self.shaders_list.count()):
                item_text = self.shaders_list.item(i).text()
                shader_name = item_text.replace(" (Activado)", "")
                if shader_name not in server_shaders:
                    shader_path = os.path.join(client_shaders_dir, shader_name)
                    if os.path.exists(shader_path):
                        files_to_upload.append(("shaders", shader_path))
        
        # Verificar resource packs (comparar con resource packs del servidor original)
        client_rp_dir = os.path.join(self.minecraft_launcher.minecraft_path, "resourcepacks")
        if os.path.exists(client_rp_dir):
            server_rps = {rp.get("name") for rp in original_profile.get("resourcepacks", [])}
            # También verificar los resource packs que el usuario agregó en la lista
            for i in range(self.resourcepacks_list.count()):
                item_text = self.resourcepacks_list.item(i).text()
                rp_name = item_text.replace(" (Activado)", "")
                if rp_name not in server_rps:
                    rp_path = os.path.join(client_rp_dir, rp_name)
                    if os.path.exists(rp_path):
                        files_to_upload.append(("resourcepacks", rp_path))
        
        return files_to_upload

