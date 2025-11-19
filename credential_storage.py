"""
Módulo para almacenar credenciales de forma segura
"""
import json
import os
from cryptography.fernet import Fernet
from typing import Optional, Dict
from config import CREDENTIALS_FILE, KEY_FILE

class CredentialStorage:
    """Gestiona el almacenamiento seguro de credenciales"""
    
    def __init__(self, storage_file: Optional[str] = None, key_file: Optional[str] = None):
        # Usar rutas de config.py si no se especifican
        self.storage_file = str(storage_file) if storage_file else str(CREDENTIALS_FILE)
        self.key_file = str(key_file) if key_file else str(KEY_FILE)
        self._cipher = None
        self._load_or_create_key()
    
    def _load_or_create_key(self):
        """Carga o crea una clave de cifrado"""
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                key = f.read()
        else:
            # Generar nueva clave Fernet directamente
            # Fernet genera claves seguras de 32 bytes en formato base64
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
        
        self._cipher = Fernet(key)
    
    def save_credentials(self, credentials: Dict) -> bool:
        """
        Guarda las credenciales de forma cifrada
        """
        try:
            # Convertir a JSON y cifrar
            json_data = json.dumps(credentials)
            encrypted_data = self._cipher.encrypt(json_data.encode())
            
            # Guardar en archivo
            with open(self.storage_file, "wb") as f:
                f.write(encrypted_data)
            
            return True
        except Exception as e:
            print(f"Error guardando credenciales: {str(e)}")
            return False
    
    def load_credentials(self) -> Optional[Dict]:
        """
        Carga las credenciales descifradas
        """
        try:
            if not os.path.exists(self.storage_file):
                return None
            
            with open(self.storage_file, "rb") as f:
                encrypted_data = f.read()
            
            # Descifrar
            decrypted_data = self._cipher.decrypt(encrypted_data)
            credentials = json.loads(decrypted_data.decode())
            
            return credentials
        except Exception as e:
            print(f"Error cargando credenciales: {str(e)}")
            return None
    
    def has_credentials(self) -> bool:
        """Verifica si existen credenciales guardadas"""
        return os.path.exists(self.storage_file) and os.path.getsize(self.storage_file) > 0
    
    def clear_credentials(self) -> bool:
        """Elimina las credenciales guardadas"""
        try:
            if os.path.exists(self.storage_file):
                os.remove(self.storage_file)
            return True
        except Exception as e:
            print(f"Error eliminando credenciales: {str(e)}")
            return False

