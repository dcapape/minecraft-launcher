"""
Módulo para descargar Java Runtime automáticamente
"""
import os
import platform
import urllib.request
import zipfile
import json
import shutil
from pathlib import Path
from typing import Optional, Callable


class JavaDownloader:
    """Descarga Java Runtime desde Adoptium/Eclipse Temurin"""
    
    def __init__(self, minecraft_path: str):
        self.minecraft_path = minecraft_path
        self.system = platform.system()
        self.arch = platform.machine().lower()
        
        # Mapear arquitectura
        if self.arch in ['x86_64', 'amd64']:
            self.arch = 'x64'
        elif self.arch in ['aarch64', 'arm64']:
            self.arch = 'aarch64'
        else:
            self.arch = 'x64'  # Por defecto
        
        # Mapear sistema operativo
        if self.system == "Windows":
            self.os_name = "windows"
            self.ext = "zip"
        elif self.system == "Darwin":
            self.os_name = "mac"
            self.ext = "tar.gz"
        else:
            self.os_name = "linux"
            self.ext = "tar.gz"
    
    def get_download_url(self, java_version: int) -> Optional[str]:
        """Obtiene la URL de descarga desde la API de Adoptium"""
        try:
            # Usar la API v3 de Adoptium para obtener información del release
            api_url = f"https://api.adoptium.net/v3/binary/latest/{java_version}/ga/{self.os_name}/{self.arch}/jdk/hotspot/normal/adoptium"
            
            # La API redirige directamente a la URL de descarga
            # Hacer una petición para seguir la redirección
            req = urllib.request.Request(api_url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            
            # Abrir la URL (sigue redirecciones automáticamente)
            with urllib.request.urlopen(req) as response:
                # Obtener la URL final después de las redirecciones
                download_url = response.geturl()
                return download_url
        except Exception as e:
            print(f"[ERROR] No se pudo obtener URL de descarga: {e}")
            # Intentar construir URL directa como fallback
            # Formato: https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/adoptium
            try:
                fallback_url = f"https://api.adoptium.net/v3/binary/latest/{java_version}/ga/{self.os_name}/{self.arch}/jdk/hotspot/normal/adoptium"
                return fallback_url
            except:
                return None
    
    def download_java(self, java_version: int, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        """
        Descarga e instala Java Runtime
        
        Args:
            java_version: Versión de Java a descargar (ej: 8, 11, 17, 21)
            progress_callback: Función callback(descargado, total) para mostrar progreso
        
        Returns:
            Ruta al ejecutable de Java o None si falla
        """
        # Verificar si ya está descargado
        runtime_dir = os.path.join(self.minecraft_path, "runtime", f"java-runtime-{java_version}")
        java_exe = os.path.join(runtime_dir, "bin", "java.exe" if self.system == "Windows" else "java")
        
        if os.path.exists(java_exe):
            print(f"[INFO] Java {java_version} ya esta descargada en {runtime_dir}")
            return java_exe
        
        # Obtener URL de descarga
        download_url = self.get_download_url(java_version)
        if not download_url:
            return None
        
        print(f"[INFO] Descargando Java {java_version} desde {download_url}")
        
        # Crear directorio temporal
        temp_dir = os.path.join(self.minecraft_path, "runtime", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Nombre del archivo descargado
        filename = download_url.split("/")[-1]
        if "?" in filename:
            filename = filename.split("?")[0]
        download_path = os.path.join(temp_dir, filename)
        
        try:
            # Descargar archivo
            def report_hook(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    downloaded = block_num * block_size
                    progress_callback(downloaded, total_size)
            
            urllib.request.urlretrieve(download_url, download_path, report_hook)
            
            print(f"[INFO] Descarga completada. Extrayendo...")
            
            # Extraer archivo
            extract_dir = os.path.join(temp_dir, f"java-{java_version}")
            os.makedirs(extract_dir, exist_ok=True)
            
            if self.ext == "zip":
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            else:
                import tarfile
                with tarfile.open(download_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(extract_dir)
            
            # Encontrar el directorio raíz de Java (puede estar en un subdirectorio)
            java_root = None
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path):
                    test_java = os.path.join(item_path, "bin", "java.exe" if self.system == "Windows" else "java")
                    if os.path.exists(test_java):
                        java_root = item_path
                        break
            
            if not java_root:
                # Buscar recursivamente
                for root, dirs, files in os.walk(extract_dir):
                    test_java = os.path.join(root, "java.exe" if self.system == "Windows" else "java")
                    if os.path.exists(test_java) and "bin" in root:
                        java_root = os.path.dirname(os.path.dirname(test_java))
                        break
            
            if not java_root:
                print(f"[ERROR] No se pudo encontrar el directorio raiz de Java")
                return None
            
            # Mover a la ubicación final
            if os.path.exists(runtime_dir):
                shutil.rmtree(runtime_dir)
            os.makedirs(os.path.dirname(runtime_dir), exist_ok=True)
            shutil.move(java_root, runtime_dir)
            
            # Limpiar archivos temporales
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            
            # Verificar que el ejecutable existe
            if os.path.exists(java_exe):
                print(f"[OK] Java {java_version} instalada correctamente en {runtime_dir}")
                return java_exe
            else:
                print(f"[ERROR] Java instalada pero no se encontro el ejecutable en {java_exe}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Error descargando Java: {e}")
            import traceback
            traceback.print_exc()
            return None

