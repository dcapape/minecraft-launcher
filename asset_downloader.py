"""
Módulo para descargar y verificar assets de Minecraft
"""
import os
import json
import hashlib
import requests
from typing import Optional, Dict, Callable


class AssetDownloader:
    """Gestiona la descarga y verificación de assets de Minecraft"""
    
    def __init__(self, assets_dir: str, progress_callback: Optional[Callable[[int, int, str], None]] = None):
        """
        Inicializa el descargador de assets
        
        Args:
            assets_dir: Directorio donde se almacenarán los assets (ej: .minecraft/assets o profiles/xxx/assets)
            progress_callback: Función opcional para reportar progreso (porcentaje, total, mensaje)
        """
        self.assets_dir = assets_dir
        self.progress_callback = progress_callback
        self.objects_dir = os.path.join(assets_dir, "objects")
        self.indexes_dir = os.path.join(assets_dir, "indexes")
        os.makedirs(self.objects_dir, exist_ok=True)
        os.makedirs(self.indexes_dir, exist_ok=True)
    
    def _calculate_sha1(self, file_path: str) -> str:
        """Calcula el hash SHA-1 de un archivo"""
        sha1 = hashlib.sha1()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha1.update(chunk)
            return sha1.hexdigest()
        except Exception as e:
            print(f"[ERROR] Error calculando SHA-1 de {file_path}: {e}")
            return ""
    
    def _verify_hash(self, file_path: str, expected_hash: str) -> bool:
        """Verifica que el hash SHA-1 del archivo coincida con el esperado"""
        if not os.path.exists(file_path):
            return False
        actual_hash = self._calculate_sha1(file_path)
        return actual_hash.lower() == expected_hash.lower()
    
    def _download_file(self, url: str, file_path: str, expected_hash: Optional[str] = None) -> bool:
        """Descarga un archivo desde una URL y opcionalmente verifica su hash"""
        try:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Si el archivo existe y el hash coincide, no descargar
            if expected_hash and self._verify_hash(file_path, expected_hash):
                return True
            
            # Descargar el archivo
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verificar hash si se proporcionó
            if expected_hash:
                if not self._verify_hash(file_path, expected_hash):
                    print(f"[ERROR] Hash no coincide para {file_path}")
                    os.remove(file_path)
                    return False
            
            return True
        except Exception as e:
            print(f"[ERROR] Error descargando {url}: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return False
    
    def download_asset_index(self, version_json: Dict) -> Optional[Dict]:
        """
        Descarga el índice de assets para una versión
        
        Args:
            version_json: JSON de la versión de Minecraft
            
        Returns:
            Diccionario con los assets o None si hay error
        """
        asset_index_info = version_json.get("assetIndex")
        if not asset_index_info:
            print("[WARN] No se encontró assetIndex en el JSON de la versión")
            return None
        
        asset_index_id = asset_index_info.get("id")
        asset_index_url = asset_index_info.get("url")
        asset_index_sha1 = asset_index_info.get("sha1")
        
        if not asset_index_id or not asset_index_url:
            print("[WARN] assetIndex incompleto en el JSON")
            return None
        
        # Ruta donde se guardará el índice
        index_path = os.path.join(self.indexes_dir, f"{asset_index_id}.json")
        
        # Descargar el índice si no existe o si el hash no coincide
        if not self._download_file(asset_index_url, index_path, asset_index_sha1):
            print(f"[ERROR] No se pudo descargar el índice de assets: {asset_index_id}")
            return None
        
        # Leer y retornar el índice
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Error leyendo índice de assets: {e}")
            return None
    
    def download_assets(self, version_json: Dict, force: bool = False) -> tuple[int, int]:
        """
        Descarga todos los assets necesarios para una versión
        
        Args:
            version_json: JSON de la versión de Minecraft
            force: Si es True, re-descarga assets incluso si ya existen
            
        Returns:
            Tupla (assets_descargados, assets_totales)
        """
        # Descargar el índice de assets
        if self.progress_callback:
            self.progress_callback(0, 100, "Descargando índice de assets...")
        
        asset_index = self.download_asset_index(version_json)
        if not asset_index:
            return (0, 0)
        
        # Obtener la lista de objetos
        objects = asset_index.get("objects", {})
        total_assets = len(objects)
        
        if total_assets == 0:
            print("[WARN] El índice de assets está vacío")
            return (0, 0)
        
        downloaded = 0
        skipped = 0
        failed = 0
        
        # Descargar cada asset
        for idx, (asset_name, asset_info) in enumerate(objects.items()):
            if self.progress_callback:
                progress = int((idx / total_assets) * 100)
                self.progress_callback(progress, 100, f"Descargando assets ({idx + 1}/{total_assets}): {asset_name}")
            
            asset_hash = asset_info.get("hash")
            asset_size = asset_info.get("size", 0)
            
            if not asset_hash:
                print(f"[WARN] Asset sin hash: {asset_name}")
                failed += 1
                continue
            
            # Construir ruta del asset (primeros 2 caracteres del hash como subdirectorio)
            hash_prefix = asset_hash[:2]
            asset_path = os.path.join(self.objects_dir, hash_prefix, asset_hash)
            
            # Si el archivo existe y el hash coincide, saltar
            if not force and self._verify_hash(asset_path, asset_hash):
                skipped += 1
                continue
            
            # Construir URL del asset
            asset_url = f"https://resources.download.minecraft.net/{hash_prefix}/{asset_hash}"
            
            # Descargar el asset
            if self._download_file(asset_url, asset_path, asset_hash):
                downloaded += 1
            else:
                failed += 1
        
        if self.progress_callback:
            self.progress_callback(100, 100, f"Assets descargados: {downloaded}, saltados: {skipped}, fallidos: {failed}")
        
        print(f"[INFO] Assets procesados: {downloaded} descargados, {skipped} saltados, {failed} fallidos de {total_assets} totales")
        
        return (downloaded, total_assets)
    
    def verify_assets(self, version_json: Dict) -> tuple[int, int]:
        """
        Verifica que todos los assets necesarios estén presentes y sean válidos
        
        Args:
            version_json: JSON de la versión de Minecraft
            
        Returns:
            Tupla (assets_válidos, assets_totales)
        """
        asset_index = self.download_asset_index(version_json)
        if not asset_index:
            return (0, 0)
        
        objects = asset_index.get("objects", {})
        total_assets = len(objects)
        valid_assets = 0
        
        for asset_name, asset_info in objects.items():
            asset_hash = asset_info.get("hash")
            if not asset_hash:
                continue
            
            hash_prefix = asset_hash[:2]
            asset_path = os.path.join(self.objects_dir, hash_prefix, asset_hash)
            
            if self._verify_hash(asset_path, asset_hash):
                valid_assets += 1
        
        return (valid_assets, total_assets)

