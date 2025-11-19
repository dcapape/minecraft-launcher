"""
Módulo para lanzar Minecraft con las credenciales correctas
"""
import subprocess
import os
import json
import platform
from pathlib import Path
from typing import Optional, Dict, Callable, Tuple
import urllib.request
import zipfile
import shutil
import uuid
from java_downloader import JavaDownloader

class MinecraftLauncher:
    """Gestiona el lanzamiento de Minecraft Java Edition"""
    
    def __init__(self):
        self.system = platform.system()
        self._detect_minecraft_path()
    
    def _detect_minecraft_path(self):
        """Detecta la ruta de instalación de Minecraft"""
        if self.system == "Windows":
            # Ruta típica en Windows
            appdata = os.getenv("APPDATA")
            self.minecraft_path = os.path.join(appdata, ".minecraft")
        elif self.system == "Darwin":  # macOS
            home = os.path.expanduser("~")
            self.minecraft_path = os.path.join(home, "Library", "Application Support", "minecraft")
        else:  # Linux
            home = os.path.expanduser("~")
            self.minecraft_path = os.path.join(home, ".minecraft")
    
    def get_java_version(self, java_exe: str) -> Optional[int]:
        """Obtiene la versión de Java (número mayor, ej: 8, 11, 17, 21)"""
        try:
            result = subprocess.run(
                [java_exe, "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parsear la versión del output
            output = result.stderr or result.stdout
            if output:
                # Buscar patrones como "version "1.8.0" o "version "21.0.1"
                import re
                match = re.search(r'version ["\']?(\d+)', output)
                if match:
                    major_version = int(match.group(1))
                    # Java 8 y anteriores usan 1.x, ajustar
                    if major_version == 1:
                        match_minor = re.search(r'version ["\']?1\.(\d+)', output)
                        if match_minor:
                            return int(match_minor.group(1))
                    return major_version
        except:
            pass
        return None
    
    def find_java_installations(self) -> Dict[int, str]:
        """Encuentra todas las instalaciones de Java disponibles"""
        java_installations = {}
        
        # Probar java/javaw en PATH
        for java_name in ["java", "javaw"]:
            try:
                version = self.get_java_version(java_name)
                if version:
                    java_installations[version] = java_name
            except:
                continue
        
        # Buscar en .minecraft/runtime/ (Java incluido con el launcher oficial)
        # También buscar en la ruta del launcher oficial de Minecraft
        runtime_paths = [
            os.path.join(self.minecraft_path, "runtime"),
        ]
        
        # Agregar ruta del launcher oficial de Minecraft (si existe)
        if self.system == "Windows":
            official_launcher_runtime = r"C:\Program Files (x86)\Minecraft Launcher\runtime\java-runtime-delta\windows-x64"
            if os.path.exists(official_launcher_runtime):
                runtime_paths.append(official_launcher_runtime)
        
        for runtime_base in runtime_paths:
            if os.path.exists(runtime_base):
                # Buscar en subdirectorios comunes
                for root, dirs, files in os.walk(runtime_base):
                    # Buscar java.exe o java
                    java_exe_name = "java.exe" if self.system == "Windows" else "java"
                    if java_exe_name in files:
                        java_path = os.path.join(root, java_exe_name)
                        try:
                            version = self.get_java_version(java_path)
                            if version:
                                # Usar la versión más reciente si hay múltiples de la misma versión
                                if version not in java_installations or len(java_path) < len(java_installations[version]):
                                    java_installations[version] = java_path
                        except:
                            continue
        
        # Buscar en rutas comunes del sistema
        if self.system == "Windows":
            import glob
            common_patterns = [
                "C:\\Program Files\\Java\\jdk-*\\bin\\java.exe",
                "C:\\Program Files\\Java\\jre-*\\bin\\java.exe",
                "C:\\Program Files (x86)\\Java\\jdk-*\\bin\\java.exe",
                "C:\\Program Files (x86)\\Java\\jre-*\\bin\\java.exe",
            ]
            
            for pattern in common_patterns:
                for java_path in glob.glob(pattern):
                    try:
                        version = self.get_java_version(java_path)
                        if version:
                            # Solo agregar si no existe o si esta es más específica
                            if version not in java_installations:
                                java_installations[version] = java_path
                    except:
                        continue
        
        return java_installations
    
    def get_required_java_version(self, version_json: Dict) -> Optional[int]:
        """Obtiene la versión de Java requerida del JSON de versión"""
        # Buscar en diferentes lugares donde puede estar la versión de Java
        if "javaVersion" in version_json:
            java_version = version_json["javaVersion"]
            if isinstance(java_version, dict):
                return java_version.get("majorVersion")
            elif isinstance(java_version, int):
                return java_version
        
        # Detectar versiones antiguas que usan launchwrapper (requieren Java 8 exactamente)
        main_class = version_json.get("mainClass", "")
        if "launchwrapper" in main_class.lower() or main_class == "net.minecraft.launchwrapper.Launch":
            # Versiones con launchwrapper NO funcionan con Java 9+
            # Requieren Java 8 específicamente
            return 8
        
        # Versiones muy antiguas (1.12 y anteriores) también requieren Java 8
        version_id = version_json.get("id", "")
        if version_id:
            # Extraer versión mayor (ej: "1.12.2" -> 12)
            import re
            match = re.match(r'1\.(\d+)', version_id)
            if match:
                minor_version = int(match.group(1))
                if minor_version < 13:  # Versiones 1.12 y anteriores
                    return 8
        
        # Versiones modernas (1.17+) requieren Java 16+
        # Versiones 1.18+ requieren Java 17+
        if version_id:
            import re
            match = re.match(r'1\.(\d+)', version_id)
            if match:
                minor_version = int(match.group(1))
                if minor_version >= 18:
                    return 17
                elif minor_version >= 17:
                    return 16
        
        # Por defecto, no especificar (se usará la última disponible)
        return None
    
    def _download_java_runtime(self, version: int, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        """
        Intenta descargar Java Runtime si no está disponible.
        
        Args:
            version: Versión de Java a descargar
            progress_callback: Función callback(descargado, total) para mostrar progreso
        """
        downloader = JavaDownloader(self.minecraft_path)
        return downloader.download_java(version, progress_callback)
    
    def get_java_executable(self, required_version: Optional[int] = None) -> Optional[str]:
        """Busca el ejecutable de Java, preferiblemente la versión requerida"""
        java_installations = self.find_java_installations()
        
        if not java_installations:
            # Fallback: intentar java/javaw en PATH
            for java_name in ["java", "javaw"]:
                try:
                    result = subprocess.run(
                        [java_name, "-version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 or result.stderr:
                        return java_name
                except:
                    continue
            return None
        
        # Si hay una versión requerida, buscar la más cercana
        if required_version:
            # Para Java 8 (versiones antiguas con launchwrapper), NO usar Java 9+
            # Java 8 es especial: versiones antiguas NO funcionan con Java 9+
            if required_version == 8:
                # Buscar Java 8 exactamente
                if 8 in java_installations:
                    return java_installations[8]
                else:
                    # NO usar Java 9+ para versiones que requieren Java 8
                    print(f"[ERROR] Se requiere Java 8 exactamente para esta version")
                    print(f"   Java 9+ no es compatible con launchwrapper")
                    print(f"   Versiones disponibles: {sorted(java_installations.keys())}")
                    print(f"   Por favor, instala Java 8 o usa una version mas reciente de Minecraft")
                    return None
            
            # Para otras versiones, buscar exactamente o mayor
            if required_version in java_installations:
                return java_installations[required_version]
            
            # Buscar una versión mayor o igual
            suitable_versions = {v: path for v, path in java_installations.items() 
                               if v >= required_version}
            if suitable_versions:
                # Usar la versión más baja que cumpla el requisito
                best_version = min(suitable_versions.keys())
                return suitable_versions[best_version]
            
            # Si no hay versión adecuada, intentar descargar
            print(f"[WARN] Advertencia: Se requiere Java {required_version} o superior")
            print(f"   Versiones disponibles: {sorted(java_installations.keys())}")
            
            # Intentar descargar (por ahora solo muestra mensaje)
            downloaded_java = self._download_java_runtime(required_version)
            if downloaded_java:
                return downloaded_java
            
            # Si no se pudo descargar y es crítica, no usar una versión incorrecta
            if required_version == 8:
                return None
        
        # Si no hay requisito específico o no se encontró una adecuada, usar la versión más reciente
        if java_installations:
            best_version = max(java_installations.keys())
            return java_installations[best_version]
        
        return None
    
    def launch_minecraft(self, credentials: Dict, version: str = "latest", java_path: Optional[str] = None) -> Tuple[bool, Optional[int]]:
        """
        Lanza Minecraft con las credenciales proporcionadas
        
        Args:
            credentials: Diccionario con access_token, username, uuid
            version: Versión de Minecraft a lanzar
        """
        try:
            # Usar la versión proporcionada o detectar automáticamente
            if version == "latest":
                detected_version = self._detect_minecraft_version()
                if not detected_version:
                    print("Error: No se pudo detectar la versión de Minecraft instalada")
                    return False
                selected_version = detected_version
            else:
                selected_version = version
            
            print(f"Versión seleccionada: {selected_version}")
            
            # Leer archivo de versión JSON
            version_json = self._load_version_json(selected_version)
            if not version_json:
                print(f"Error: No se pudo cargar el archivo de versión {selected_version}")
                return False
            
            # Obtener versión de Java requerida
            required_java_version = self.get_required_java_version(version_json)
            if required_java_version:
                print(f"Java requerida: {required_java_version}")
            
            # Usar Java especificado o buscar uno adecuado
            if java_path:
                java_exe = java_path
                java_version = self.get_java_version(java_exe)
                if java_version:
                    print(f"Java seleccionada: versión {java_version} ({java_exe})")
                    if required_java_version and java_version < required_java_version:
                        print(f"[WARN] Advertencia: La version de Java ({java_version}) es menor que la requerida ({required_java_version})")
                else:
                    print(f"[WARN] Advertencia: No se pudo verificar la version de Java en {java_exe}")
            else:
                # Buscar Java adecuado automáticamente
                java_exe = self.get_java_executable(required_java_version)
                if not java_exe:
                    print("Error: No se encontró Java instalado")
                    if required_java_version:
                        print(f"Se requiere Java {required_java_version} o superior")
                    return False
                
                # Verificar versión de Java encontrada
                java_version = self.get_java_version(java_exe)
                if java_version:
                    print(f"Java encontrada: versión {java_version} ({java_exe})")
                    if required_java_version and java_version < required_java_version:
                        print(f"[WARN] Advertencia: La version de Java ({java_version}) es menor que la requerida ({required_java_version})")
            
            # CRÍTICO: Extraer nativos desde JARs a directorio temporal único (como el launcher oficial)
            # Esto evita que Java escanee directorios basura en .minecraft/bin/
            natives_hash_dir = self._extract_natives_to_temp_directory(version_json, selected_version)
            if not natives_hash_dir:
                print("[WARN] No se pudo crear el directorio temporal de nativos, usando directorio estándar")
            
            # Obtener argumentos JVM y del juego
            # Pasar también selected_version y el directorio temporal de nativos
            jvm_args = self._get_jvm_arguments(version_json, selected_version, natives_hash_dir)
            game_args = self._get_game_arguments(version_json, credentials, selected_version)
            
            # Verificar si se usa módulo path (-p) en los argumentos JVM
            uses_module_path = any("-p" in str(arg) for arg in jvm_args)
            
            # Si se usa módulo path, construir SOLO con los JARs explícitos del JSON
            # CRÍTICO: No agregar carpetas ni JARs que no estén en la lista original
            if uses_module_path:
                libraries_dir = os.path.join(self.minecraft_path, "libraries")
                classpath_separator = ";" if self.system == "Windows" else ":"
                
                # DEPURACIÓN: Listar contenido del directorio de librerías
                print(f"[DEBUG] Contenido del directorio de librerías ({libraries_dir}):")
                try:
                    if os.path.exists(libraries_dir):
                        # Listar solo el primer nivel para no saturar
                        items = os.listdir(libraries_dir)
                        print(f"[DEBUG] Total de items en libraries: {len(items)}")
                        # Mostrar todos los items
                        for idx, item in enumerate(items, 1):
                            item_path = os.path.join(libraries_dir, item)
                            item_type = "DIR" if os.path.isdir(item_path) else "FILE"
                            print(f"[DEBUG]   [{idx}] [{item_type}] {item}")
                        
                        # Buscar específicamente directorios sospechosos
                        suspicious_dirs = []
                        for item in items:
                            item_lower = item.lower()
                            if "bin." in item_lower or "ce6c" in item_lower or "meta-inf" in item_lower:
                                item_path = os.path.join(libraries_dir, item)
                                if os.path.isdir(item_path):
                                    suspicious_dirs.append(item)
                        
                        if suspicious_dirs:
                            print(f"[DEBUG] [ADVERTENCIA] Directorios sospechosos encontrados en libraries:")
                            for sus_dir in suspicious_dirs:
                                print(f"[DEBUG]   - {sus_dir}")
                        else:
                            print(f"[DEBUG] No se encontraron directorios sospechosos en libraries")
                    else:
                        print(f"[DEBUG] El directorio de librerías no existe: {libraries_dir}")
                except Exception as e:
                    print(f"[DEBUG] Error al listar directorio de librerías: {e}")
                
                # Buscar el argumento -p y construir el module path desde el JSON original
                for i, arg in enumerate(jvm_args):
                    if arg == "-p" and i + 1 < len(jvm_args):
                        module_path_value = jvm_args[i + 1]
                        if isinstance(module_path_value, str):
                            # CRÍTICO: Construir el module path SOLO con los JARs listados explícitamente en el JSON
                            # Dividir por el separador para obtener la lista de JARs
                            jar_paths_raw = [j.strip() for j in module_path_value.split(classpath_separator) if j.strip()]
                            
                            print(f"[DEBUG] Module path RAW tiene {len(jar_paths_raw)} entradas (desde JSON)")
                            
                            # Construir lista de JARs válidos en el orden exacto del JSON
                            # CRÍTICO: Prevenir duplicados (el launcher oficial no incluye JARs duplicados)
                            valid_jars = []
                            seen_jars = set()  # Para detectar duplicados
            
                            for jar_path_raw in jar_paths_raw:
                                # Ignorar argumentos JVM que puedan haberse colado
                                if jar_path_raw.startswith("-"):
                                    print(f"[SKIP] Ignorando argumento JVM: {jar_path_raw}")
                                    continue
                                
                                jar_path_raw = jar_path_raw.strip()
                                if not jar_path_raw:
                                    continue
                                
                                # CRÍTICO: Verificar que sea una ruta de JAR (no una carpeta)
                                # Las rutas de JARs siempre terminan en .jar
                                if not jar_path_raw.lower().endswith(".jar"):
                                    print(f"[SKIP] No es un JAR (no termina en .jar): {jar_path_raw}")
                                    continue
                                
                                # Convertir a ruta absoluta si es relativa
                                if not os.path.isabs(jar_path_raw):
                                    # Construir desde libraries_dir
                                    jar_path = os.path.join(libraries_dir, jar_path_raw.replace("/", os.path.sep))
                                else:
                                    jar_path = jar_path_raw
                                
                                # Normalizar separadores
                                if self.system == "Windows":
                                    jar_path = os.path.normpath(jar_path)
                                
                                # CRÍTICO: Solo incluir si:
                                # 1. Termina en .jar (ya verificado arriba)
                                # 2. Es un archivo (NO un directorio)
                                # 3. Existe
                                if not os.path.exists(jar_path):
                                    print(f"[SKIP] JAR no existe: {jar_path}")
                                    continue
                                
                                if not os.path.isfile(jar_path):
                                    print(f"[SKIP] Es directorio (no archivo): {jar_path}")
                                    continue
                                
                                # Verificar que no sea un directorio disfrazado
                                if os.path.isdir(jar_path):
                                    print(f"[SKIP] Es un directorio: {jar_path}")
                                    continue
                                
                                # Filtrar patrones problemáticos
                                nombre = os.path.basename(jar_path)
                                if "bin." in nombre.lower() or "ce6c" in nombre.lower():
                                    print(f"[SKIP] Contiene patrón problemático: {nombre}")
                                    continue
                                
                                # Verificar que esté dentro del directorio de librerías (seguridad)
                                try:
                                    jar_path_real = os.path.realpath(jar_path)
                                    libraries_dir_real = os.path.realpath(libraries_dir)
                                    if not jar_path_real.startswith(libraries_dir_real):
                                        print(f"[SKIP] JAR fuera del directorio de librerías: {jar_path}")
                                        continue
                                    
                                    # CRÍTICO: Usar ruta real para detectar duplicados (case-insensitive en Windows)
                                    # El launcher oficial elimina duplicados: si el mismo JAR aparece varias veces,
                                    # solo se incluye la primera instancia
                                    jar_key = jar_path_real.lower() if self.system == "Windows" else jar_path_real
                                    if jar_key in seen_jars:
                                        print(f"[SKIP] JAR duplicado omitido en module path: {os.path.basename(jar_path)}")
                                        continue
                                    
                                    seen_jars.add(jar_key)
                                    
                                    # Convertir a forward slash para module path (como otros launchers)
                                    if self.system == "Windows":
                                        jar_path_normalized = jar_path.replace("\\", "/")
                                    else:
                                        jar_path_normalized = jar_path
                                    
                                    valid_jars.append(jar_path_normalized)
                                    print(f"[OK] JAR agregado al module path: {os.path.basename(jar_path)}")
                                except Exception as e:
                                    print(f"[WARN] Error verificando ruta real: {e}")
                                    # Fallback: usar ruta normalizada sin verificación de duplicados
                                    if self.system == "Windows":
                                        jar_path_normalized = jar_path.replace("\\", "/")
                                    else:
                                        jar_path_normalized = jar_path
                                    
                                    jar_key = jar_path_normalized.lower() if self.system == "Windows" else jar_path_normalized
                                    if jar_key not in seen_jars:
                                        seen_jars.add(jar_key)
                                        valid_jars.append(jar_path_normalized)
                                        print(f"[OK] JAR agregado al module path (fallback): {os.path.basename(jar_path)}")
                            
                            if not valid_jars:
                                print(f"[ERROR] No hay JARs válidos en el module path")
                                return False, None
                                    
                            # Construir el module path con solo los JARs válidos, en el orden original del JSON
                            module_path_str = classpath_separator.join(valid_jars)
                            jvm_args[i + 1] = module_path_str
                                
                            print(f"[INFO] Module path actualizado: {len(valid_jars)} JARs válidos (solo del JSON)")
                            print(f"[DEBUG] Module path completo ({len(module_path_str)} chars):")
                            for idx, jar in enumerate(valid_jars, 1):
                                print(f"  [{idx}] {jar}")
                        break
            
            # Verificar que no haya argumentos del juego mezclados en los argumentos JVM
            # (esto puede pasar si hay un error en el procesamiento)
            game_arg_patterns = ["--username", "--version", "--gameDir", "--assetsDir", "--assetIndex", 
                               "--uuid", "--accessToken", "--clientId", "--xuid", "--userType", 
                               "--userProperties", "--width", "--height", "--fullscreen"]
            jvm_args_filtered = []
            for arg in jvm_args:
                if isinstance(arg, str):
                    # Verificar si es un argumento del juego
                    is_game_arg = any(arg.startswith(pattern) for pattern in game_arg_patterns)
                    if is_game_arg:
                        print(f"[WARN] Filtrando argumento del juego de JVM args: {arg}")
                        continue
                jvm_args_filtered.append(arg)
            
            if len(jvm_args_filtered) != len(jvm_args):
                print(f"[INFO] Filtrados {len(jvm_args) - len(jvm_args_filtered)} argumentos del juego de JVM args")
                jvm_args = jvm_args_filtered
            
            # Construir comando completo en el orden correcto:
            # java [JVM args] [-p modulepath] [-cp classpath] [Main class] [Game args]
            args = [java_exe]
            
            # CRÍTICO: El launcher oficial pasa AMBOS argumentos -cp y -p simultáneamente
            # No debemos filtrar -cp cuando se usa -p
            # El classpath incluye TODAS las libraries + el JAR de la versión
            # El module path incluye solo los JARs específicos para el module system
            jvm_args_final = []
            
            # Si hay un -cp en los argumentos JVM del JSON, reemplazarlo con nuestro classpath completo
            # Si no hay, lo agregaremos después
            cp_index = -1
            for i, arg in enumerate(jvm_args):
                if arg == "-cp" or arg == "-classpath":
                    cp_index = i
                    break
            
            if cp_index >= 0:
                # Hay un -cp en el JSON, lo mantendremos pero reemplazaremos su valor
                print(f"[INFO] Encontrado -cp en argumentos JVM del JSON (índice {cp_index})")
                # Mantener todos los argumentos, reemplazaremos el valor después
                jvm_args_final = jvm_args
            else:
                # No hay -cp en el JSON, mantener todos los argumentos y agregaremos -cp después
                jvm_args_final = jvm_args
            
            if uses_module_path:
                print("[INFO] Usando module path (-p) - también se usará -cp con todas las libraries")
            else:
                print("[INFO] No se usa module path - se usará -cp con todas las libraries")
            
            # AGREGAR TODOS LOS ARGUMENTOS JVM (ya filtrados y expandidos)
            args += jvm_args_final
            
            # CRÍTICO: Construir y agregar -cp classpath SIEMPRE
            # El launcher oficial SIEMPRE pasa -cp con TODAS las libraries + el JAR de la versión
            # Incluso cuando se usa -p (module path), ambos se pasan simultáneamente
            print("[INFO] Construyendo classpath completo desde todas las libraries + JAR de versión")
            classpath = self._build_classpath(version_json, selected_version)
            
            if not classpath or not classpath.strip():
                print("[ERROR CRITICO] El classpath está vacío/no generado")
                return False, None
            
            # Verificar si ya existe -cp o -classpath en los argumentos JVM
            has_cp_in_jvm = any(arg in ("-cp", "-classpath") for arg in jvm_args_final)
            
            if has_cp_in_jvm:
                # Reemplazar el valor del -cp existente con nuestro classpath completo
                print("[INFO] Reemplazando valor de -cp existente con classpath completo")
                for i, arg in enumerate(args):
                    if arg == "-cp" or arg == "-classpath":
                        if i + 1 < len(args):
                            args[i + 1] = classpath
                        else:
                            # Si no hay valor, agregarlo
                            args.insert(i + 1, classpath)
                        break
            else:
                # No hay -cp en los argumentos JVM, agregarlo
                print("[INFO] Agregando -cp con classpath completo")
                args.extend(["-cp", classpath])
                
                # VERIFICACIÓN CRÍTICA: Asegurar que classpath NO es "-cp"
                if classpath == "-cp" or classpath == "-classpath":
                    print(f"[ERROR CRITICO] classpath tiene valor inválido: '{classpath}'")
                    print(f"[ERROR CRITICO] Esto causará que Java reciba '-cp -cp'")
                    return False, None
                
                print(f"[DEBUG] Classpath completo ({len(classpath)} caracteres):")
                print(classpath)
                
                # CRÍTICO: Guardar una copia del classpath antes de agregarlo para evitar modificaciones
                classpath_to_add = str(classpath)  # Crear una copia explícita
                
                # Verificar que classpath_to_add es realmente el classpath, no "-cp"
                if not classpath_to_add or not classpath_to_add.strip():
                    print(f"[ERROR CRITICO] classpath está vacío antes de agregar a args")
                    return False, None
                
                if classpath_to_add == "-cp" or classpath_to_add == "-classpath":
                    print(f"[ERROR CRITICO] classpath tiene valor inválido: '{classpath_to_add}'")
                    print(f"[ERROR CRITICO] Esto causará que Java reciba '-cp -cp'")
                    return False, None
                
                # Verificar que el classpath contiene al menos un separador de ruta o un punto y coma
                # (un classpath válido debería tener rutas de archivos)
                if ";" not in classpath_to_add and ":" not in classpath_to_add and not os.path.exists(classpath_to_add):
                    print(f"[WARN] classpath no contiene separadores y no es una ruta válida: '{classpath_to_add}'")
                
                # CRÍTICO: Verificar si -cp ya existe antes de agregarlo
                if has_cp_in_jvm:
                    print("[INFO] -cp ya existe en argumentos JVM. Buscando para actualizar o eliminar duplicados...")
                    # Buscar TODAS las instancias de -cp/-classpath y eliminarlas
                    # Luego agregar uno nuevo con el classpath correcto
                    indices_to_remove = []
                    i = 0
                    while i < len(args):
                        if args[i] in ("-cp", "-classpath"):
                            print(f"[INFO] Encontrado -cp/-classpath en índice {i}")
                            # Eliminar -cp/-classpath y su valor siguiente (si existe y no es otro -cp)
                            indices_to_remove.append(i)
                            if i + 1 < len(args) and args[i + 1] not in ("-cp", "-classpath"):
                                # El siguiente es el valor del classpath, también eliminarlo
                                print(f"[INFO] Eliminando también el valor del classpath en índice {i+1}: '{str(args[i+1])}'")
                                indices_to_remove.append(i + 1)
                                i += 2  # Saltar ambos
                            else:
                                # El siguiente es otro -cp o no existe, solo eliminar este
                                i += 1
                        else:
                            i += 1
                    
                    # Eliminar en orden inverso para no afectar los índices
                    for idx in sorted(indices_to_remove, reverse=True):
                        removed = args.pop(idx)
                        print(f"[INFO] Eliminado elemento en índice {idx}: '{removed}'")
                    
                    # Ahora agregar -cp con el classpath correcto
                    print("[INFO] Agregando -cp con classpath correcto...")
                    args.append("-cp")
                    args.append(classpath_to_add)
                else:
                    # No existe -cp, agregarlo
                    print(f"[DEBUG] Agregando -cp y classpath a args...")
                    print(f"[DEBUG] classpath_to_add (completo): {classpath_to_add}")
                    print(f"[DEBUG] classpath_to_add (longitud total): {len(classpath_to_add)} caracteres")
                    
                    args.append("-cp")
                    args.append(classpath_to_add)
                
                print(f"[DEBUG] Agregado -cp y classpath a args. Args ahora tiene {len(args)} elementos")
                
                # Verificación inmediata después de agregar: contar cuántos -cp hay
                cp_count = sum(1 for arg in args if arg in ("-cp", "-classpath"))
                if cp_count > 1:
                    print(f"[ERROR CRITICO] Se encontraron {cp_count} instancias de -cp/-classpath en args!")
                    print(f"[ERROR CRITICO] Esto causará el error 'Error: -cp requires class path specification'")
                    # Mostrar todas las instancias
                    for i, arg in enumerate(args):
                        if arg in ("-cp", "-classpath"):
                            print(f"  [ERROR] -cp/-classpath encontrado en índice {i}")
                            if i + 1 < len(args):
                                print(f"  [ERROR]   Valor siguiente: '{str(args[i + 1])}'")
                    return False, None
                elif cp_count == 1:
                    # Verificar que el único -cp tiene un valor válido
                    for i, arg in enumerate(args):
                        if arg in ("-cp", "-classpath"):
                            if i + 1 >= len(args):
                                print(f"[ERROR CRITICO] -cp en índice {i} no tiene valor después")
                                return False, None
                            cp_value = args[i + 1]
                            if cp_value == "-cp" or cp_value == "-classpath":
                                print(f"[ERROR CRITICO] -cp seguido de '{cp_value}' en lugar del classpath")
                                return False, None
                            if not cp_value or not str(cp_value).strip():
                                print(f"[ERROR CRITICO] -cp tiene valor vacío")
                                return False, None
                            print(f"[OK] -cp verificado: tiene valor válido de {len(str(cp_value))} caracteres")
                            break
            
            # Siempre, después de JVM args y (si aplica) classpath, viene la main class
            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
            if not main_class:
                print("[ERROR] No se encontró mainClass en el JSON de versión")
                return False, None
            args.append(main_class)
            
            # AGREGAR LOS ARGUMENTOS DEL JUEGO (después de la clase principal)
            args += game_args
            
            # Verificación previa al lanzamiento: evita crashes por -cp erróneo
            for i, arg in enumerate(args):
                if arg in ("-cp", "-classpath"):
                    if i + 1 >= len(args) or not args[i+1] or args[i+1] == main_class:
                        error_msg = f"[ERROR CRITICO] -cp/-classpath en posición {i} sin valor válido justo después!"
                        print(error_msg)
                        print(f"[DEBUG] Args completos: {args}")
                        return False, None
            
            # Verificación final: asegurar que el orden sea correcto
            # java [JVM args] [-p modulepath] [-cp classpath] [Main class] [Game args]
            
            # Encontrar el índice de la clase principal
            main_class_index = None
            for i, arg in enumerate(args):
                if arg == main_class:
                    main_class_index = i
                    break
            
            if main_class_index is None:
                print(f"[ERROR] No se encontró la clase principal '{main_class}' en args")
                print(f"[DEBUG] Args actuales: {args}")
                return False, None
            
            # Verificar que la main class esté después de todos los argumentos JVM
            # Los argumentos JVM deben estar antes del índice de main_class
            args_before_main = args[1:main_class_index]  # Todo entre java_exe y main class
            
            # Verificar que no haya argumentos del juego antes de la clase principal
            game_arg_patterns = ["--username", "--version", "--gameDir", "--assetsDir", "--assetIndex", 
                               "--uuid", "--accessToken", "--clientId", "--xuid", "--userType", 
                               "--userProperties", "--width", "--height", "--fullscreen"]
            game_args_before_main = [arg for arg in args_before_main if isinstance(arg, str) and any(arg.startswith(p) for p in game_arg_patterns)]
            
            if game_args_before_main:
                print(f"[ERROR] Argumentos del juego encontrados ANTES de la clase principal: {game_args_before_main}")
                print(f"[ERROR] Esto causará el error 'Unrecognized option'")
                # Filtrar argumentos del juego de la sección JVM
                filtered_before_main = [arg for arg in args_before_main if not (isinstance(arg, str) and any(arg.startswith(p) for p in game_arg_patterns))]
                # Reconstruir args correctamente
                args = [args[0]] + filtered_before_main + [main_class] + args[main_class_index + 1:]
                # Actualizar el índice de la clase principal después de reconstruir
                main_class_index = len([args[0]] + filtered_before_main)
                print(f"[INFO] Args reconstruidos correctamente. Main class ahora en índice {main_class_index}")
            
            # Verificar que no haya argumentos JVM después de la main class
            # (esto sería un error grave)
            args_after_main = args[main_class_index + 1:]
            jvm_arg_patterns = ["-X", "-D", "--add", "-p", "-cp", "-classpath"]
            jvm_args_after_main = [arg for arg in args_after_main if isinstance(arg, str) and any(arg.startswith(p) for p in jvm_arg_patterns)]
            
            if jvm_args_after_main:
                print(f"[WARN] Argumentos JVM encontrados DESPUÉS de la clase principal: {jvm_args_after_main}")
                print(f"[WARN] Esto puede causar problemas. Filtrando...")
                # Filtrar argumentos JVM de la sección de game args
                filtered_after_main = [arg for arg in args_after_main if not (isinstance(arg, str) and any(arg.startswith(p) for p in jvm_arg_patterns))]
                # Reconstruir args
                args = args[:main_class_index + 1] + filtered_after_main
            
            # Debug: verificar que los argumentos estén en el orden correcto
            final_main_class_index = None
            for i, arg in enumerate(args):
                if arg == main_class:
                    final_main_class_index = i
                    break
            
            if final_main_class_index is None:
                print(f"[ERROR] No se encontró la clase principal después de las correcciones")
                return False, None
            
            final_args_before_main = args[1:final_main_class_index]
            
            print(f"[DEBUG] Orden de argumentos final (verificado):")
            print(f"  1. Java: {java_exe}")
            print(f"  2. JVM args ({len(final_args_before_main)} args): {final_args_before_main}")
            
            # Verificar si hay -cp en los argumentos
            cp_index = None
            for i, arg in enumerate(args):
                if arg == "-cp" or arg == "-classpath":
                    cp_index = i
                    break
            
            if cp_index is not None:
                if cp_index + 1 < len(args):
                    cp_value = args[cp_index + 1]
                    print(f"  [VERIFICACIÓN] -cp encontrado en índice {cp_index}")
                    print(f"  [VERIFICACIÓN] Valor de classpath (completo): {str(cp_value)}")
                    print(f"  [VERIFICACIÓN] Longitud del classpath: {len(str(cp_value))} caracteres")
                else:
                    print(f"  [ERROR CRITICO] -cp encontrado en índice {cp_index} pero NO tiene valor después")
            elif not uses_module_path:
                print(f"  [ERROR CRITICO] Versión NO usa module path pero NO se encontró -cp en args")
                print(f"  [DEBUG] Args completos para debug: {args}")
            
            print(f"  3. Main class: {main_class} (índice {final_main_class_index})")
            print(f"  4. Game args ({len(args) - final_main_class_index - 1} args): {args[final_main_class_index + 1:]}")
            
            # Verificación final antes de ejecutar: asegurar que -cp tiene valor
            if not uses_module_path:
                # Buscar -cp en args
                found_cp = False
                for i, arg in enumerate(args):
                    if arg == "-cp" or arg == "-classpath":
                        found_cp = True
                        if i + 1 >= len(args):
                            print(f"[ERROR CRITICO] -cp encontrado en posición {i} pero NO tiene valor")
                            return False, None
                        cp_val = args[i + 1]
                        if not cp_val or not str(cp_val).strip():
                            print(f"[ERROR CRITICO] -cp tiene valor vacío en posición {i}")
                            return False, None
                        if str(cp_val).strip() == main_class:
                            print(f"[ERROR CRITICO] -cp seguido de main class (sin classpath real)")
                            return False, None
                        print(f"[OK] -cp verificado: tiene valor válido de {len(str(cp_val))} caracteres")
                        break
                
                if not found_cp:
                    print(f"[ERROR CRITICO] Versión NO usa module path pero NO se encontró -cp en args finales")
                    print(f"[DEBUG] Args completos: {args}")
                    return False, None
            
            print(f"Lanzando Minecraft para {credentials.get('username')}...")
            print(f"Java: {java_exe}")
            print(f"Versión: {selected_version}")
            
            # DEBUG: Mostrar el comando completo que se va a ejecutar
            print(f"\n[DEBUG] ========== COMANDO COMPLETO ==========")
            print(f"[DEBUG] Comando completo ({len(args)} argumentos):")
            for i, arg in enumerate(args):
                if i == 0:
                    print(f"  [{i}] {arg}")
                elif arg == "-cp" or arg == "-classpath":
                    print(f"  [{i}] {arg}")
                    if i + 1 < len(args):
                        next_arg = args[i + 1]
                        print(f"  [{i+1}] {str(next_arg)} (longitud: {len(str(next_arg))} caracteres)")
                elif arg == main_class:
                    print(f"  [{i}] {arg} <-- MAIN CLASS")
                elif isinstance(arg, str) and arg.startswith("--"):
                    print(f"  [{i}] {arg}")
                elif isinstance(arg, str) and len(arg) > 100:
                    print(f"  [{i}] {arg} (longitud: {len(arg)} caracteres)")
                else:
                    print(f"  [{i}] {arg}")
            print(f"[DEBUG] =========================================\n")
            
            # Construir el comando como string para mostrar también
            cmd_str = " ".join([f'"{arg}"' if " " in str(arg) else str(arg) for arg in args])
            print(f"{cmd_str}")

            print()
            
            # Lanzar Minecraft capturando output en archivos de log para diagnosticar
            import time
            import tempfile
            
            # Crear archivos de log temporales
            log_dir = os.path.join(self.minecraft_path, "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            stdout_log = os.path.join(log_dir, f"launcher_stdout_{timestamp}.log")
            stderr_log = os.path.join(log_dir, f"launcher_stderr_{timestamp}.log")
            
            print(f"[INFO] Logs de Minecraft:")
            print(f"  stdout: {stdout_log}")
            print(f"  stderr: {stderr_log}")
            
            # Abrir archivos de log
            stdout_file = open(stdout_log, 'w', encoding='utf-8', errors='replace')
            stderr_file = open(stderr_log, 'w', encoding='utf-8', errors='replace')
            
            try:
                process = subprocess.Popen(
                    args,
                    cwd=self.minecraft_path,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    bufsize=1,  # Line buffered
                    text=True
                )
                
                # Esperar un momento para ver si el proceso se inicia correctamente
                time.sleep(3)
                
                # Verificar si el proceso sigue corriendo
                if process.poll() is not None:
                    # El proceso terminó inmediatamente - leer los logs
                    stdout_file.close()
                    stderr_file.close()
                    
                    print(f"\n[ERROR] Minecraft se cerro inmediatamente (codigo: {process.returncode})")
                    
                    # Leer stderr para ver el error
                    try:
                        with open(stderr_log, 'r', encoding='utf-8', errors='replace') as f:
                            stderr_content = f.read()
                            if stderr_content:
                                print("\n=== Error de Minecraft (stderr) ===")
                                # Mostrar las últimas líneas
                                lines = stderr_content.strip().split('\n')
                                for line in lines[-30:]:
                                    if line.strip():
                                        print(line)
                    except:
                        pass
                    
                    # Mostrar los argumentos para debugging
                    print(f"\n=== Comando ejecutado ===")
                    print(f"Java: {java_exe}")
                    java_ver = self.get_java_version(java_exe)
                    if java_ver:
                        print(f"Java version: {java_ver}")
                    print(f"Main class: {version_json.get('mainClass', 'N/A')}")
                    print(f"JVM args count: {len(jvm_args)}")
                    print(f"Game args count: {len(game_args)}")
                    
                    return False, None
                
                # Esperar un poco más para ver si el proceso se mantiene activo
                time.sleep(5)
                
                # Verificar nuevamente
                if process.poll() is not None:
                    stdout_file.close()
                    stderr_file.close()
                    
                    print(f"\n[ERROR] Minecraft se cerro despues de iniciar (codigo: {process.returncode})")
                    print(f"[INFO] Revisa el log en: {stderr_log}")
                    
                    # Leer stderr para ver el error
                    try:
                        with open(stderr_log, 'r', encoding='utf-8', errors='replace') as f:
                            stderr_content = f.read()
                            if stderr_content:
                                print("\n=== Error de Minecraft (stderr) ===")
                                lines = stderr_content.strip().split('\n')
                                for line in lines[-30:]:
                                    if line.strip():
                                        print(line)
                    except:
                        pass
                    
                    return False, None
                
                # Si el proceso sigue corriendo, cerrar los archivos pero mantener el proceso
                # Los archivos seguirán escribiendo en segundo plano
                stdout_file.close()
                stderr_file.close()
                
                print("[OK] Minecraft proceso iniciado correctamente")
                print("[INFO] El juego deberia abrirse en breve...")
                print(f"[INFO] PID del proceso: {process.pid}")
                print(f"[INFO] Si el juego no se abre, revisa los logs en:")
                print(f"  {stderr_log}")
                
                # Guardar referencia al proceso para que no se cierre
                # El proceso seguirá corriendo en segundo plano
                
                return True, None
                
            except Exception as e:
                stdout_file.close()
                stderr_file.close()
                raise
            
        except Exception as e:
            print(f"Error lanzando Minecraft: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def is_version_downloaded(self, version: str) -> bool:
        """Verifica si una versión está completamente descargada"""
        version_dir = os.path.join(self.minecraft_path, "versions", version)
        json_path = os.path.join(version_dir, f"{version}.json")
        jar_path = os.path.join(version_dir, f"{version}.jar")
        
        if not os.path.exists(json_path) or not os.path.exists(jar_path):
            return False
        
        # Cargar JSON y verificar librerías críticas
        try:
            version_json = self._load_version_json(version)
            if not version_json:
                return False
        except:
            return False
        
        libraries_dir = os.path.join(self.minecraft_path, "libraries")
        libraries_required = 0
        libraries_found = 0
        
        for lib in version_json.get('libraries', []):
            # Verificar reglas
            if "rules" in lib:
                if not self._should_include_argument(lib):
                    continue
            
            libraries_required += 1
            lib_path = None
            if "downloads" in lib and "artifact" in lib["downloads"]:
                lib_path = lib["downloads"]["artifact"].get("path")
            if not lib_path:
                lib_name = lib.get("name", "")
                if lib_name:
                    lib_path = self._maven_name_to_path(lib_name)
            
            if lib_path:
                full_path = os.path.join(libraries_dir, lib_path)
                if os.path.exists(full_path):
                    libraries_found += 1
        
        # Considerar descargada si tiene al menos el 80% de las librerías o si no hay librerías
        if libraries_required == 0:
            return True
        return libraries_found >= (libraries_required * 0.8)
    
    def get_available_versions(self, only_downloaded: bool = True) -> list:
        """Obtiene todas las versiones de Minecraft disponibles"""
        versions_dir = os.path.join(self.minecraft_path, "versions")
        if not os.path.exists(versions_dir):
            return []
        
        versions = []
        for item in os.listdir(versions_dir):
            version_path = os.path.join(versions_dir, item)
            if os.path.isdir(version_path):
                json_path = os.path.join(version_path, f"{item}.json")
                if os.path.exists(json_path):
                    # Si only_downloaded es True, verificar que esté descargada
                    if only_downloaded:
                        if self.is_version_downloaded(item):
                            versions.append(item)
                    else:
                        versions.append(item)
        
        # Ordenar versiones (básico, podría mejorarse)
        versions.sort(reverse=True)
        return versions
    
    def _detect_minecraft_version(self) -> Optional[str]:
        """Detecta la versión de Minecraft instalada más reciente"""
        versions = self.get_available_versions()
        if not versions:
            return None
        return versions[0]
    
    def _load_version_json(self, version: str) -> Optional[Dict]:
        """Carga el archivo JSON de la versión, incluyendo herencia (inheritsFrom)"""
        return self._load_version_json_recursive(version, set())
    
    def _load_version_json_recursive(self, version: str, visited: set) -> Optional[Dict]:
        """Carga el JSON de la versión de forma recursiva, manejando herencia"""
        # Prevenir ciclos infinitos
        if version in visited:
            print(f"[WARN] Ciclo detectado en herencia de versiones: {version}")
            return None
        
        visited.add(version)
        
        json_path = os.path.join(self.minecraft_path, "versions", version, f"{version}.json")
        if not os.path.exists(json_path):
            print(f"[ERROR] No se encontró el JSON de la versión: {version}")
            return None
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                version_json = json.load(f)
        except Exception as e:
            print(f"[ERROR] Error leyendo {json_path}: {e}")
            return None
        
        # Si tiene herencia, cargar la versión padre primero
        if "inheritsFrom" in version_json:
            parent_version = version_json["inheritsFrom"]
            print(f"[INFO] Versión {version} hereda de {parent_version}")
            
            parent_json = self._load_version_json_recursive(parent_version, visited.copy())
            if not parent_json:
                print(f"[WARN] No se pudo cargar la versión padre {parent_version}, continuando sin herencia")
            else:
                # Combinar los JSONs: primero el padre, luego el hijo (el hijo sobrescribe)
                version_json = self._merge_version_jsons(parent_json, version_json)
        
        return version_json
    
    def _merge_version_jsons(self, parent: Dict, child: Dict) -> Dict:
        """
        Combina dos JSONs de versión, el child sobrescribe al parent.
        
        CRÍTICO: Replica el comportamiento del launcher oficial:
        - Combina todas las secciones (libraries, arguments, etc.)
        - Respeta el orden: parent primero, luego child
        - El child puede sobrescribir campos específicos
        """
        merged = parent.copy()
        
        # CRÍTICO: Combinar libraries (el child agrega a las del parent)
        # El launcher oficial combina todas las libraries de ambas versiones
        # PERO elimina duplicados: si la misma librería aparece en parent y child,
        # solo se incluye una vez (la del child prevalece)
        if "libraries" in parent:
            merged["libraries"] = parent["libraries"].copy()
        else:
            merged["libraries"] = []
        
        if "libraries" in child:
            # CRÍTICO: Eliminar duplicados basándose en el nombre de la librería
            # El launcher oficial registra cada librería por su nombre (group:artifact:version)
            # y solo la última instancia se incluye
            seen_lib_names = {}
            # Primero, indexar las libraries del parent por nombre
            for i, lib in enumerate(merged["libraries"]):
                if isinstance(lib, dict):
                    lib_name = lib.get("name", "")
                    if lib_name:
                        # Extraer solo group:artifact:version (sin classifier como :natives-*)
                        base_name = lib_name.split(":")[:3]  # group:artifact:version
                        if len(base_name) == 3:
                            base_name_str = ":".join(base_name)
                            seen_lib_names[base_name_str] = i
            
            # Agregar las libraries del child, reemplazando duplicados
            for lib in child["libraries"]:
                if isinstance(lib, dict):
                    lib_name = lib.get("name", "")
                    if lib_name:
                        # Extraer solo group:artifact:version (sin classifier)
                        base_name = lib_name.split(":")[:3]
                        if len(base_name) == 3:
                            base_name_str = ":".join(base_name)
                            if base_name_str in seen_lib_names:
                                # Duplicado: reemplazar la instancia del parent con la del child
                                parent_index = seen_lib_names[base_name_str]
                                merged["libraries"][parent_index] = lib
                                print(f"[DEBUG] Librería duplicada reemplazada (child prevalece): {base_name_str}")
                            else:
                                # Nueva librería, agregarla
                                merged["libraries"].append(lib)
                                seen_lib_names[base_name_str] = len(merged["libraries"]) - 1
                        else:
                            # Librería sin formato estándar, agregarla directamente
                            merged["libraries"].append(lib)
                    else:
                        # Librería sin nombre, agregarla directamente
                        merged["libraries"].append(lib)
                else:
                    # Librería no es dict, agregarla directamente
                    merged["libraries"].append(lib)
        
        # CRÍTICO: Combinar arguments (el child agrega a los del parent)
        # El launcher oficial combina argumentos JVM y del juego en orden
        if "arguments" in parent:
            merged["arguments"] = parent["arguments"].copy()
        else:
            merged["arguments"] = {}
        
        if "arguments" in child:
            child_args = child["arguments"]
            
            # Combinar argumentos JVM (parent primero, luego child)
            # CRÍTICO: El orden importa para algunos mods/deps
            if "jvm" in parent.get("arguments", {}):
                merged["arguments"]["jvm"] = parent["arguments"]["jvm"].copy()
            else:
                merged["arguments"]["jvm"] = []
            
            if "jvm" in child_args:
                # Agregar argumentos JVM del child al final
                merged["arguments"]["jvm"].extend(child_args["jvm"])
            
            # Combinar argumentos del juego (parent primero, luego child)
            if "game" in parent.get("arguments", {}):
                merged["arguments"]["game"] = parent["arguments"]["game"].copy()
            else:
                merged["arguments"]["game"] = []
            
            if "game" in child_args:
                # Agregar argumentos del juego del child al final
                merged["arguments"]["game"].extend(child_args["game"])
        
        # Combinar minecraftArguments (versiones antiguas)
        # Si el child tiene minecraftArguments, sobrescribe el del parent
        if "minecraftArguments" in child:
            merged["minecraftArguments"] = child["minecraftArguments"]
        elif "minecraftArguments" in parent:
            merged["minecraftArguments"] = parent["minecraftArguments"]
        
        # El child sobrescribe otros campos importantes
        # pero mantenemos algunos del parent si el child no los tiene
        for key, value in child.items():
            if key not in ["libraries", "arguments", "inheritsFrom", "minecraftArguments"]:
                merged[key] = value
        
        # Asegurar que el mainClass del child tenga prioridad si existe
        if "mainClass" in child:
            merged["mainClass"] = child["mainClass"]
        elif "mainClass" not in merged and "mainClass" in parent:
            merged["mainClass"] = parent["mainClass"]
        
        return merged
    
    def _maven_name_to_path(self, name: str) -> Optional[str]:
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
    
    def _build_classpath(self, version_json: Dict, version: str) -> Optional[str]:
        """
        Construye el classpath completo para Minecraft.
        
        CRÍTICO: El classpath incluye TODAS las libraries del JSON (después del merge)
        + el JAR de la versión principal, en el orden exacto que aparecen en el JSON.
        Este es el classpath completo que se pasa con -cp, incluso cuando también se usa -p.
        """
        libraries_dir = os.path.join(self.minecraft_path, "libraries")
        version_jar = os.path.join(self.minecraft_path, "versions", version, f"{version}.jar")
        
        classpath_parts = []
        # CRÍTICO: Usar un set para detectar duplicados por ruta absoluta normalizada
        # El launcher oficial elimina duplicados: si el mismo JAR aparece varias veces,
        # solo se incluye una vez (la última prevalece)
        seen_jars = set()
        
        # CRÍTICO: Agregar TODAS las librerías PRIMERO en el orden del JSON
        # El launcher oficial incluye todas las libraries (después del merge de herencias)
        # en el orden exacto que aparecen, ANTES del JAR de la versión
        libraries_count = 0
        libraries_found = 0
        if "libraries" in version_json:
            libraries_count = len(version_json["libraries"])
            print(f"[DEBUG] Procesando {libraries_count} librerías para classpath")
            
            for lib in version_json["libraries"]:
                # Verificar reglas de la librería (algunas pueden ser opcionales o específicas del OS)
                if "rules" in lib:
                    if not self._should_include_argument(lib):
                        continue
                
                # CRÍTICO: Excluir librerías nativas (solo archivos .jar, no natives-*.jar)
                lib_name = lib.get("name", "")
                if lib_name:
                    # Verificar si es una librería nativa (formato: group:artifact:version:natives-<platform>)
                    if ":natives-" in lib_name:
                        # Esta es una librería nativa, no va en el classpath
                        continue
                    # Verificar si tiene propiedad "natives"
                    if "natives" in lib:
                        # Esta librería tiene nativos, no va en el classpath
                        continue
                
                # Intentar obtener path de downloads si existe
                lib_path = None
                if "downloads" in lib and "artifact" in lib["downloads"]:
                    lib_path = lib["downloads"]["artifact"].get("path")
                
                # Si no hay path en downloads, construir desde name (formato Maven)
                if not lib_path:
                    if lib_name:
                        lib_path = self._maven_name_to_path(lib_name)
                
                if lib_path:
                    full_path = os.path.join(libraries_dir, lib_path)
                    # CRÍTICO: Solo incluir si es un archivo .jar que existe
                    if os.path.exists(full_path) and os.path.isfile(full_path) and full_path.lower().endswith(".jar"):
                        # Normalizar la ruta para comparación de duplicados
                        if not os.path.isabs(full_path):
                            full_path = os.path.abspath(full_path)
                        if self.system == "Windows":
                            full_path_normalized = os.path.normpath(full_path)
                        else:
                            full_path_normalized = full_path
                        
                        # CRÍTICO: Usar ruta real para detectar duplicados (case-insensitive en Windows)
                        # El launcher oficial elimina duplicados: si el mismo JAR aparece varias veces,
                        # solo se incluye la primera instancia (mantener orden original)
                        try:
                            jar_path_real = os.path.realpath(full_path_normalized)
                            jar_key = jar_path_real.lower() if self.system == "Windows" else jar_path_real
                            
                            if jar_key in seen_jars:
                                # JAR duplicado: omitir esta instancia (la primera prevalece)
                                print(f"[SKIP] JAR duplicado omitido: {os.path.basename(full_path)}")
                                continue
                            
                            # JAR nuevo, agregarlo
                            seen_jars.add(jar_key)
                            classpath_parts.append(full_path_normalized)
                            libraries_found += 1
                        except Exception as e:
                            # Si hay error obteniendo ruta real, usar la normalizada
                            jar_key = full_path_normalized.lower() if self.system == "Windows" else full_path_normalized
                            if jar_key in seen_jars:
                                print(f"[SKIP] JAR duplicado omitido: {os.path.basename(full_path)}")
                                continue
                            seen_jars.add(jar_key)
                            classpath_parts.append(full_path_normalized)
                            libraries_found += 1
                    else:
                        # Algunas librerías pueden no existir y eso está bien
                        pass
        
        print(f"[INFO] Librerías para classpath: {libraries_found}/{libraries_count} encontradas (duplicados eliminados)")
        
        # CRÍTICO: Agregar JAR de la versión AL FINAL (como el launcher oficial)
        # El orden es: [todas las libraries] + [JAR de la versión]
        if os.path.exists(version_jar):
            classpath_parts.append(version_jar)
            print(f"[OK] JAR de versión agregado al classpath (al final): {os.path.basename(version_jar)}")
        else:
            print(f"[WARN] JAR de versión no encontrado: {version_jar}")
        
        if not classpath_parts:
            print("[ERROR] No se encontraron archivos para el classpath")
            return None
        
        # Unir con separador según el sistema
        separator = ";" if self.system == "Windows" else ":"
        
        # Asegurar que todas las rutas sean absolutas y normalizadas
        normalized_parts = []
        for part in classpath_parts:
            # Convertir a ruta absoluta si no lo es
            if not os.path.isabs(part):
                part = os.path.abspath(part)
            # Normalizar la ruta para Windows (convertir / a \)
            if self.system == "Windows":
                part = os.path.normpath(part)
            normalized_parts.append(part)
        
        classpath = separator.join(normalized_parts)
        print(f"[INFO] Classpath construido: {len(normalized_parts)} archivos, {len(classpath)} caracteres")
        
        return classpath
    
    def _get_system_architecture(self) -> str:
        """
        Detecta la arquitectura del sistema.
        
        Returns:
            'x64', 'x86', o 'arm64'
        """
        arch = platform.machine().lower()
        
        if arch in ['x86_64', 'amd64']:
            return 'x64'
        elif arch in ['aarch64', 'arm64']:
            return 'arm64'
        elif arch in ['i386', 'i686', 'x86']:
            return 'x86'
        else:
            # Por defecto, asumir x64
            return 'x64'
    
    def _extract_native_jar(self, jar_path: str, dest_dir: str) -> bool:
        """
        Extrae solo las DLLs/archivos nativos de la arquitectura correspondiente
        directamente a la raíz del directorio de destino.
        
        Args:
            jar_path: Ruta al JAR nativo
            dest_dir: Directorio de destino (raíz de bin/<HASH>)
        
        Returns:
            True si se extrajo correctamente, False en caso contrario
        """
        try:
            print(f"[INFO] Extrayendo nativos desde: {jar_path}")
            
            # Detectar arquitectura del sistema
            arch = self._get_system_architecture()
            print(f"[DEBUG] Arquitectura detectada: {arch}")
            
            # Determinar extensión de archivos nativos según plataforma
            if self.system == "Windows":
                native_extensions = ['.dll']
                arch_path_prefix = f"windows/{arch}/"
            elif self.system == "Linux":
                native_extensions = ['.so']
                arch_path_prefix = f"linux/{arch}/"
            elif self.system == "Darwin":
                native_extensions = ['.dylib', '.jnilib']
                arch_path_prefix = f"osx/{arch}/"
            else:
                # Fallback para sistemas desconocidos
                native_extensions = ['.dll', '.so', '.dylib']
                arch_path_prefix = f"windows/{arch}/"  # Por defecto Windows
            
            files_extracted = 0
            
            with zipfile.ZipFile(jar_path, 'r') as z:
                # Buscar archivos nativos en la carpeta de arquitectura correspondiente
                for file_info in z.namelist():
                    # Verificar que el archivo esté en la carpeta de arquitectura correcta
                    if arch_path_prefix in file_info:
                        # Verificar que sea un archivo nativo (no directorio)
                        if not file_info.endswith('/'):
                            # Verificar extensión
                            if any(file_info.lower().endswith(ext) for ext in native_extensions):
                                # Obtener solo el nombre del archivo (sin ruta)
                                filename = os.path.basename(file_info)
                                
                                # Ruta de destino: directamente en la raíz
                                dest_path = os.path.join(dest_dir, filename)
                                
                                # Extraer el archivo
                                try:
                                    with z.open(file_info) as source:
                                        with open(dest_path, 'wb') as target:
                                            target.write(source.read())
                                    files_extracted += 1
                                    print(f"[DEBUG] Extraído: {filename} -> {dest_path}")
                                except Exception as e:
                                    print(f"[WARN] Error extrayendo {filename}: {e}")
            
            if files_extracted > 0:
                print(f"[INFO] Nativos extraídos correctamente ({files_extracted} archivos de arquitectura {arch})")
                return True
            else:
                print(f"[WARN] No se encontraron archivos nativos para arquitectura {arch} en {jar_path}")
                # Intentar buscar en otras arquitecturas como fallback
                print(f"[DEBUG] Buscando en otras arquitecturas como fallback...")
                with zipfile.ZipFile(jar_path, 'r') as z:
                    for file_info in z.namelist():
                        # Buscar cualquier archivo nativo (sin restricción de arquitectura)
                        if not file_info.endswith('/'):
                            if any(file_info.lower().endswith(ext) for ext in native_extensions):
                                filename = os.path.basename(file_info)
                                dest_path = os.path.join(dest_dir, filename)
                                
                                # Evitar sobrescribir si ya existe
                                if not os.path.exists(dest_path):
                                    try:
                                        with z.open(file_info) as source:
                                            with open(dest_path, 'wb') as target:
                                                target.write(source.read())
                                        files_extracted += 1
                                        print(f"[DEBUG] Extraído (fallback): {filename}")
                                    except Exception as e:
                                        print(f"[WARN] Error extrayendo {filename}: {e}")
                
                if files_extracted > 0:
                    print(f"[INFO] Nativos extraídos (fallback): {files_extracted} archivos")
                    return True
                else:
                    print(f"[WARN] No se encontraron archivos nativos en {jar_path}")
                    return False
            
        except Exception as e:
            print(f"[WARN] Error extrayendo nativos de {jar_path}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _extract_natives_to_temp_directory(self, version_json: Dict, version: str) -> Optional[str]:
        """
        Extrae los nativos desde los JARs de librerías a un directorio temporal único con hash.
        Esto replica el comportamiento del launcher oficial que crea bin/<HASH> para cada sesión.
        
        Args:
            version_json: JSON de la versión (mezclado con herencia)
            version: Nombre de la versión (ej: neoforge-21.1.215)
        
        Returns:
            Ruta al directorio temporal de nativos o None si falla
        """
        try:
            # Directorio base para nativos temporales
            bin_base = os.path.join(self.minecraft_path, "bin")
            os.makedirs(bin_base, exist_ok=True)
            
            # Generar hash único para esta sesión
            session_hash = str(uuid.uuid4())
            hash_dir = os.path.join(bin_base, session_hash)
            
            # Crear el directorio
            os.makedirs(hash_dir, exist_ok=True)
            
            print(f"[INFO] Directorio temporal de nativos creado: {hash_dir}")
            
            # Obtener la plataforma actual
            platform_name = None
            if self.system == "Windows":
                platform_name = "windows"
            elif self.system == "Linux":
                platform_name = "linux"
            elif self.system == "Darwin":
                platform_name = "osx"
            
            if not platform_name:
                print(f"[WARN] Plataforma no reconocida: {self.system}")
                return None
            
            # Buscar librerías con nativos en el JSON
            libraries_dir = os.path.join(self.minecraft_path, "libraries")
            natives_extracted = 0
            
            if "libraries" in version_json:
                total_libraries = len(version_json["libraries"])
                print(f"[DEBUG] Total de librerías en JSON (incluyendo heredadas): {total_libraries}")
                print(f"[DEBUG] Buscando librerías con nativos para plataforma: {platform_name}")
                
                libraries_with_natives = 0
                for library in version_json["libraries"]:
                    if not isinstance(library, dict):
                        continue
                    
                    # Verificar reglas de inclusión (puede tener "rules" que filtren por OS)
                    if "rules" in library:
                        if not self._should_include_argument(library):
                            continue
                    
                    # Obtener el nombre de la librería
                    lib_name = library.get("name", "")
                    if not lib_name:
                        continue
                    
                    # CRÍTICO: Las librerías nativas tienen formato: group:artifact:version:natives-<platform>
                    # Ejemplo: "org.lwjgl:lwjgl:3.3.3:natives-windows"
                    # También pueden tener formato antiguo con propiedad "natives"
                    is_native_lib = False
                    native_classifier = None
                    
                    # Formato nuevo: nombre termina con :natives-<platform>
                    if f":natives-{platform_name}" in lib_name:
                        is_native_lib = True
                        # Extraer el classifier del nombre
                        parts = lib_name.split(':')
                        if len(parts) >= 4:
                            native_classifier = parts[3]  # Ejemplo: "natives-windows"
                            libraries_with_natives += 1
                            print(f"[DEBUG] Librería nativa encontrada (formato nuevo): {lib_name}, classifier: {native_classifier}")
                    
                    # Formato antiguo: propiedad "natives" en el objeto
                    elif "natives" in library:
                        natives_info = library.get("natives", {})
                        if platform_name in natives_info:
                            is_native_lib = True
                            native_classifier = natives_info[platform_name]
                            libraries_with_natives += 1
                            print(f"[DEBUG] Librería nativa encontrada (formato antiguo): {lib_name}, classifier: {native_classifier}")
                    
                    if is_native_lib and native_classifier:
                        # Construir la ruta al JAR nativo
                        # El formato Maven es: group:artifact:version
                        # La ruta es: group/artifact/version/artifact-version-natives-platform.jar
                        parts = lib_name.split(':')
                        if len(parts) >= 3:
                            group_id = parts[0].replace('.', '/')
                            artifact_id = parts[1]
                            version = parts[2]
                            
                            # Construir el nombre del JAR nativo
                            # Ejemplo: lwjgl-3.3.3-natives-windows.jar
                            native_jar_name = f"{artifact_id}-{version}-{native_classifier}.jar"
                            
                            # Construir la ruta completa
                            native_jar_path = os.path.join(libraries_dir, group_id, artifact_id, version, native_jar_name)
                            native_jar_path = os.path.normpath(native_jar_path)
                            
                            print(f"[DEBUG] Ruta construida del JAR nativo: {native_jar_path}")
                            
                            # Intentar extraer el JAR nativo
                            extracted = False
                            
                            # Primero intentar con la ruta exacta
                            if os.path.exists(native_jar_path):
                                extracted = self._extract_native_jar(native_jar_path, hash_dir)
                                if extracted:
                                    natives_extracted += 1
                            
                            # Si no se encontró, buscar variantes de arquitectura
                            if not extracted:
                                jar_dir = os.path.dirname(native_jar_path)
                                if os.path.exists(jar_dir):
                                    # Buscar variantes: natives-windows, natives-windows-x86, natives-windows-arm64, etc.
                                    print(f"[DEBUG] JAR nativo exacto no encontrado, buscando variantes en: {jar_dir}")
                                    try:
                                        found_variant = False
                                        for item in os.listdir(jar_dir):
                                            if item.startswith(artifact_id) and "natives" in item.lower() and item.endswith(".jar"):
                                                # Verificar que sea para nuestra plataforma
                                                if platform_name in item.lower():
                                                    variant_path = os.path.join(jar_dir, item)
                                                    print(f"[DEBUG] Variante encontrada: {item}")
                                                    extracted = self._extract_native_jar(variant_path, hash_dir)
                                                    if extracted:
                                                        natives_extracted += 1
                                                        found_variant = True
                                                        break
                                        
                                        if not found_variant:
                                            print(f"[WARN] No se encontró ninguna variante de JAR nativo para {lib_name}")
                                            print(f"[DEBUG] Archivos en directorio:")
                                            for item in os.listdir(jar_dir):
                                                if item.endswith(".jar"):
                                                    print(f"[DEBUG]   - {item}")
                                    except Exception as e:
                                        print(f"[WARN] Error buscando variantes: {e}")
                                else:
                                    print(f"[WARN] Directorio de librería no existe: {jar_dir}")
                
                print(f"[DEBUG] Librerías nativas encontradas: {libraries_with_natives}")
                if libraries_with_natives == 0:
                    print(f"[WARN] No se encontraron librerías nativas en el JSON para plataforma: {platform_name}")
            else:
                print(f"[WARN] No hay sección 'libraries' en el JSON de versión")
            
            if natives_extracted == 0:
                print(f"[WARN] No se extrajeron nativos desde JARs. Verificando si existen en directorio de versión...")
                # Fallback: intentar copiar desde directorio de versión si existe
                base_version = None
                if version:
                    json_path = os.path.join(self.minecraft_path, "versions", version, f"{version}.json")
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                original_json = json.load(f)
                            if "inheritsFrom" in original_json:
                                base_version = original_json["inheritsFrom"]
                        except:
                            pass
                
                if base_version:
                    version_natives_dir = os.path.join(self.minecraft_path, "versions", base_version, "natives")
                    if os.path.exists(version_natives_dir):
                        print(f"[INFO] Copiando nativos desde versión base: {version_natives_dir}")
                        for item in os.listdir(version_natives_dir):
                            src = os.path.join(version_natives_dir, item)
                            dst = os.path.join(hash_dir, item)
                            if os.path.isfile(src):
                                shutil.copy2(src, dst)
                            elif os.path.isdir(src):
                                shutil.copytree(src, dst, dirs_exist_ok=True)
                        print(f"[INFO] Nativos copiados desde versión base")
            
            print(f"[INFO] Total de JARs nativos extraídos: {natives_extracted}")
            
            # Limpiar directorios antiguos (más de 1 día)
            self._cleanup_old_natives_directories(bin_base)
            
            return hash_dir
            
        except Exception as e:
            print(f"[ERROR] Error extrayendo nativos a directorio temporal: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _cleanup_old_natives_directories(self, bin_base: str):
        """Limpia directorios de nativos antiguos (más de 1 día)"""
        try:
            import time
            current_time = time.time()
            one_day_ago = current_time - (24 * 60 * 60)  # 1 día en segundos
            
            if not os.path.exists(bin_base):
                return
            
            for item in os.listdir(bin_base):
                item_path = os.path.join(bin_base, item)
                if os.path.isdir(item_path):
                    try:
                        # Obtener tiempo de modificación
                        mtime = os.path.getmtime(item_path)
                        if mtime < one_day_ago:
                            print(f"[INFO] Eliminando directorio de nativos antiguo: {item}")
                            shutil.rmtree(item_path)
                    except Exception as e:
                        print(f"[WARN] Error eliminando directorio antiguo {item}: {e}")
        except Exception as e:
            print(f"[WARN] Error limpiando directorios antiguos: {e}")
    
    def _get_jvm_arguments(self, version_json: Dict, version: Optional[str] = None, natives_hash_dir: Optional[str] = None) -> list:
        """
        Obtiene los argumentos JVM del archivo de versión.
        
        CRÍTICO: Respeta el orden exacto del JSON y procesa todas las reglas condicionales.
        El launcher oficial procesa los argumentos en el orden que aparecen en el JSON,
        aplicando reglas (rules) para filtrar según el OS.
        """
        jvm_args = []
        
        # CRÍTICO: Agregar argumentos JVM del launcher oficial AL INICIO
        # Estos argumentos son necesarios para que NeoForge funcione correctamente
        # El launcher oficial de Minecraft los agrega automáticamente
        official_jvm_args = [
            "-Xmx2G",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseG1GC",
            "-XX:G1NewSizePercent=20",
            "-XX:G1ReservePercent=20",
            "-XX:MaxGCPauseMillis=50",
            "-XX:G1HeapRegionSize=32M"
        ]
        jvm_args.extend(official_jvm_args)
        
        # CRÍTICO: Luego agregar los argumentos JVM del JSON en el orden exacto
        # El orden importa: algunos mods/deps en NeoForge lo requieren
        if "arguments" in version_json and "jvm" in version_json["arguments"]:
            version_id = version_json.get("id", "")
            
            # CRÍTICO: Usar el directorio temporal con hash si está disponible (como el launcher oficial)
            # Esto evita que Java escanee directorios basura en .minecraft/bin/
            natives_dir = None
            if natives_hash_dir:
                natives_dir = natives_hash_dir
                print(f"[INFO] Usando directorio temporal de nativos (bin/<HASH>): {natives_dir}")
            else:
                # Fallback: buscar en versión base o actual
                print(f"[WARN] No hay directorio temporal de nativos, usando fallback")
                base_version = None
                if version:
                    # Leer el JSON original para obtener inheritsFrom
                    json_path = os.path.join(self.minecraft_path, "versions", version, f"{version}.json")
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                original_json = json.load(f)
                            if "inheritsFrom" in original_json:
                                base_version = original_json["inheritsFrom"]
                        except Exception as e:
                            print(f"[WARN] Error leyendo JSON original para obtener inheritsFrom: {e}")
                
                # Si no se pudo obtener de la versión, intentar del version_json mezclado
                if not base_version and "inheritsFrom" in version_json:
                    base_version = version_json["inheritsFrom"]
                
                if base_version:
                    base_natives_dir = os.path.join(self.minecraft_path, "versions", base_version, "natives")
                    print(f"[INFO] Versión {version_id} hereda de {base_version}")
                    print(f"[INFO] Buscando nativos en versión base: {base_natives_dir}")
                    if os.path.exists(base_natives_dir):
                        natives_dir = base_natives_dir
                        print(f"[INFO] Directorio de nativos de versión base encontrado: {base_natives_dir}")
                    else:
                        print(f"[WARN] Directorio de nativos de versión base NO existe: {base_natives_dir}")
                
                # Si no se encontró en la versión base, intentar en la versión actual
                if not natives_dir:
                    natives_dir = os.path.join(self.minecraft_path, "versions", version_id, "natives")
                    print(f"[INFO] Buscando nativos en versión actual: {natives_dir}")
            
            # Log informativo sobre el directorio de nativos
            print(f"[INFO] Directorio de nativos configurado: {natives_dir}")
            if os.path.exists(natives_dir):
                print(f"[INFO] Directorio de nativos existe")
                if os.path.isdir(natives_dir):
                    try:
                        items = os.listdir(natives_dir)
                        if items:
                            print(f"[INFO] Directorio de nativos contiene {len(items)} elementos:")
                            for item in items[:10]:  # Mostrar solo los primeros 10
                                item_path = os.path.join(natives_dir, item)
                                item_type = "directorio" if os.path.isdir(item_path) else "archivo"
                                print(f"[INFO]   - {item} ({item_type})")
                            if len(items) > 10:
                                print(f"[INFO]   ... y {len(items) - 10} elementos más")
                        else:
                            print(f"[WARN] Directorio de nativos está vacío")
                    except Exception as e:
                        print(f"[WARN] Error listando contenido del directorio de nativos: {e}")
                else:
                    print(f"[WARN] La ruta de nativos no es un directorio")
            else:
                print(f"[WARN] Directorio de nativos NO existe: {natives_dir}")
            
            libraries_dir = os.path.join(self.minecraft_path, "libraries")
            classpath_separator = ";" if self.system == "Windows" else ":"
            
            def replace_variables(text: str) -> str:
                """Reemplaza todas las variables en un texto"""
                # CRÍTICO: Detectar si es un argumento JVM ANTES de procesar
                # Los argumentos JVM empiezan con -D, -X, --, -agent, etc.
                # NO deben ser procesados con os.path.join ni normalización de rutas
                is_jvm_argument = text.strip().startswith(('-D', '-X', '--', '-agent', '-ea', '-da', '-cp', '-classpath', '-p'))
                
                # PRIMERO reemplazar las variables básicas
                text = text.replace("${natives_directory}", natives_dir)
                text = text.replace("${launcher_name}", "custom")
                text = text.replace("${launcher_version}", "1.0")
                text = text.replace("${version_name}", version_id)
                text = text.replace("${library_directory}", libraries_dir)
                
                # Verificar si es un argumento JVM que usa / (como --add-exports, --add-opens)
                # Estos argumentos tienen formato: --add-exports <module>/<package>=<target>
                is_jvm_arg_with_slash = any(text.strip().startswith(prefix) for prefix in [
                    "--add-exports", "--add-opens", "--add-modules", "--add-reads"
                ])
                
                # Reemplazar el separador
                text = text.replace("${classpath_separator}", classpath_separator)
                
                # CRÍTICO: Si es un argumento JVM, retornar inmediatamente sin manipulación de rutas
                if is_jvm_argument:
                    return text
                
                # Si NO es un argumento JVM con /, normalizar rutas SOLO para Windows
                # PERO mantener las rutas con / si son parte del módulo path (Java las maneja bien)
                # IMPORTANTE: Para el module path (-p), las rutas deben ser absolutas y normalizadas
                if not is_jvm_arg_with_slash and self.system == "Windows":
                    # Verificar si contiene el separador (es un module path o classpath)
                    if classpath_separator in text:
                        # Dividir por el separador
                        parts = text.split(classpath_separator)
                        normalized_parts = []
                        for part in parts:
                            part = part.strip()
                            if part:
                                # Construir ruta completa si es relativa
                                if not os.path.isabs(part):
                                    # Si parece una ruta relativa (contiene / o \)
                                    if "/" in part or "\\" in part:
                                        # Construir desde libraries_dir si empieza con una ruta de librería
                                        if part.startswith("cpw/") or part.startswith("org/") or part.startswith("net/"):
                                            part = os.path.join(libraries_dir, part.replace("/", os.path.sep))
                                        else:
                                            # Intentar construir desde libraries_dir
                                            part = os.path.join(libraries_dir, part.replace("/", os.path.sep))
                                
                                # Solo normalizar si es una ruta de archivo (contiene .jar o es absoluta)
                                if part.endswith(".jar") or os.path.isabs(part) or (len(part) > 1 and part[1] == ":"):
                                    # Convertir / a \ para Windows, pero mantener la estructura
                                    normalized = part.replace("/", "\\")
                                    # Usar normpath para limpiar la ruta
                                    normalized = os.path.normpath(normalized)
                                    # Asegurar que sea absoluta
                                    if not os.path.isabs(normalized):
                                        normalized = os.path.abspath(normalized)
                                    normalized_parts.append(normalized)
                                else:
                                    # No es una ruta, mantener como está
                                    normalized_parts.append(part)
                        text = classpath_separator.join(normalized_parts)
                    elif text.endswith(".jar") or os.path.isabs(text) or (len(text) > 1 and text[1] == ":"):
                        # Es una ruta única, normalizar
                        if not os.path.isabs(text):
                            # Construir ruta completa si es relativa
                            if "/" in text or "\\" in text:
                                text = os.path.join(libraries_dir, text.replace("/", os.path.sep))
                        text = text.replace("/", "\\")
                        text = os.path.normpath(text)
                        # Asegurar que sea absoluta
                        if not os.path.isabs(text):
                            text = os.path.abspath(text)
                
                return text
            
            # CRÍTICO: Procesar argumentos JVM en el orden exacto del JSON
            # El launcher oficial respeta este orden estrictamente
            for arg in version_json["arguments"]["jvm"]:
                # Manejar argumentos con reglas condicionales
                if isinstance(arg, dict):
                    # Verificar reglas ANTES de procesar el valor
                    # El launcher oficial evalúa las reglas y solo incluye el argumento si pasa
                    if "rules" in arg:
                        if not self._should_include_argument(arg):
                            # Argumento excluido por reglas (ej: macOS-only, Linux-only)
                            continue
                    
                    # Obtener el valor del argumento
                    if "value" in arg:
                        value = arg["value"]
                        if isinstance(value, list):
                            # Múltiples valores (ej: ["--add-opens", "java.base/java.util.jar=cpw.mods.securejarhandler"])
                            # CRÍTICO: Mantener el orden de los valores
                            for val in value:
                                if isinstance(val, str):
                                    val = replace_variables(val)
                                    # ${classpath} no se reemplaza aquí, se pasa como -cp separado
                                    if "${classpath}" not in val:
                                        jvm_args.append(val)
                        elif isinstance(value, str):
                            # Valor único
                            value = replace_variables(value)
                            # ${classpath} no se reemplaza aquí, se pasa como -cp separado
                            if "${classpath}" not in value:
                                jvm_args.append(value)
                elif isinstance(arg, str):
                    # Argumento simple (string) - procesar en orden
                    # Para argumentos JVM que usan / (--add-exports, --add-opens), NO normalizar
                    # Estos argumentos vienen después de --add-exports/--add-opens
                    # Si el argumento anterior es --add-exports o --add-opens, no normalizar
                    should_normalize = True
                    if len(jvm_args) > 0:
                        prev_arg = jvm_args[-1]
                        if prev_arg in ["--add-exports", "--add-opens", "--add-modules", "--add-reads"]:
                            should_normalize = False
                    
                    if should_normalize:
                        arg = replace_variables(arg)
                    else:
                        # Solo reemplazar variables básicas, sin normalizar rutas
                        # CRÍTICO: Mantener el formato original para argumentos con /
                        arg = arg.replace("${natives_directory}", natives_dir)
                        arg = arg.replace("${launcher_name}", "custom")
                        arg = arg.replace("${launcher_version}", "1.0")
                        arg = arg.replace("${version_name}", version_id)
                        arg = arg.replace("${library_directory}", libraries_dir)
                        arg = arg.replace("${classpath_separator}", classpath_separator)
                    
                    # ${classpath} no se reemplaza aquí, se pasa como -cp separado
                    if "${classpath}" not in arg:
                        jvm_args.append(arg)
        else:
            # Argumentos JVM por defecto
            version_id = version_json.get("id", "")
            
            # CRÍTICO: Usar el directorio temporal con hash si está disponible (como el launcher oficial)
            if natives_hash_dir:
                natives_dir = natives_hash_dir
                print(f"[INFO] Usando directorio temporal de nativos (bin/<HASH>) para argumentos por defecto: {natives_dir}")
            else:
                # Fallback: buscar en versión base o actual
                natives_dir = None
                base_version = None
                if version:
                    json_path = os.path.join(self.minecraft_path, "versions", version, f"{version}.json")
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                original_json = json.load(f)
                            if "inheritsFrom" in original_json:
                                base_version = original_json["inheritsFrom"]
                        except Exception as e:
                            print(f"[WARN] Error leyendo JSON original para obtener inheritsFrom: {e}")
                
                if not base_version and "inheritsFrom" in version_json:
                    base_version = version_json["inheritsFrom"]
                
                if base_version:
                    base_natives_dir = os.path.join(self.minecraft_path, "versions", base_version, "natives")
                    print(f"[INFO] Versión {version_id} hereda de {base_version}")
                    print(f"[INFO] Buscando nativos en versión base: {base_natives_dir}")
                    if os.path.exists(base_natives_dir):
                        natives_dir = base_natives_dir
                        print(f"[INFO] Directorio de nativos de versión base encontrado: {base_natives_dir}")
                    else:
                        print(f"[WARN] Directorio de nativos de versión base NO existe: {base_natives_dir}")
                
                # Si no se encontró en la versión base, intentar en la versión actual
                if not natives_dir:
                    natives_dir = os.path.join(self.minecraft_path, "versions", version_id, "natives")
                    print(f"[INFO] Buscando nativos en versión actual: {natives_dir}")
            
            # Log informativo sobre el directorio de nativos usado en argumentos por defecto
            print(f"[INFO] Usando directorio de nativos para argumentos por defecto: {natives_dir}")
            if os.path.exists(natives_dir):
                print(f"[INFO] Directorio de nativos existe")
                try:
                    items = os.listdir(natives_dir)
                    if items:
                        print(f"[INFO] Directorio de nativos contiene {len(items)} elementos")
                    else:
                        print(f"[WARN] Directorio de nativos está vacío")
                except Exception as e:
                    print(f"[WARN] Error listando contenido del directorio de nativos: {e}")
            else:
                print(f"[WARN] Directorio de nativos NO existe: {natives_dir}")
            
            jvm_args.extend([
                f"-Djava.library.path={natives_dir}",
                "-Dminecraft.launcher.brand=custom",
                "-Dminecraft.launcher.version=1.0"
            ])
        
        return jvm_args
    
    def _should_include_argument(self, arg_rule: Dict) -> bool:
        """Evalúa si un argumento con reglas debe incluirse"""
        if "rules" not in arg_rule:
            return True
        
        for rule in arg_rule["rules"]:
            action = rule.get("action", "allow")
            if "os" in rule:
                os_rule = rule["os"]
                os_name = os_rule.get("name", "").lower()
                current_os = self.system.lower()
                
                if os_name and os_name != current_os:
                    if action == "allow":
                        return False
                    continue
            
            if action == "disallow":
                return False
        
        return True
    
    def _get_game_arguments(self, version_json: Dict, credentials: Dict, version: str) -> list:
        """Obtiene los argumentos del juego"""
        game_args = []
        
        # Versiones modernas: usar arguments.game
        if "arguments" in version_json and "game" in version_json["arguments"]:
            for arg in version_json["arguments"]["game"]:
                if isinstance(arg, str):
                    # Reemplazar variables
                    arg = arg.replace("${version_name}", version)
                    arg = arg.replace("${version_type}", version_json.get("type", "release"))
                    arg = arg.replace("${assets_root}", os.path.join(self.minecraft_path, "assets"))
                    arg = arg.replace("${assets_index_name}", version_json.get("assetIndex", {}).get("id", version))
                    arg = arg.replace("${auth_uuid}", credentials.get("uuid", ""))
                    arg = arg.replace("${auth_access_token}", credentials.get("access_token", ""))
                    arg = arg.replace("${auth_player_name}", credentials.get("username", "Player"))
                    arg = arg.replace("${user_type}", "mojang")
                    arg = arg.replace("${version_type}", version_json.get("type", "release"))
                    arg = arg.replace("${game_directory}", self.minecraft_path)
                    arg = arg.replace("${game_assets}", os.path.join(self.minecraft_path, "assets", "virtual", "legacy"))
                    arg = arg.replace("${user_properties}", "{}")
                    
                    # Reemplazar variables de quick play con valores vacíos (no usamos quick play)
                    arg = arg.replace("${quickPlayPath}", "")
                    arg = arg.replace("${quickPlaySingleplayer}", "")
                    arg = arg.replace("${quickPlayMultiplayer}", "")
                    arg = arg.replace("${quickPlayRealms}", "")
                    
                    # Si el argumento contiene variables sin resolver (${...}), omitirlo
                    if "${" in arg and "}" in arg:
                        # Hay variables sin resolver, omitir este argumento
                        continue
                    
                    game_args.append(arg)
                elif isinstance(arg, dict):
                    # Argumento con reglas
                    if self._should_include_argument(arg):
                        if "value" in arg:
                            values = arg["value"] if isinstance(arg["value"], list) else [arg["value"]]
                            for value in values:
                                if isinstance(value, str):
                                    value = value.replace("${version_name}", version)
                                    value = value.replace("${version_type}", version_json.get("type", "release"))
                                    value = value.replace("${assets_root}", os.path.join(self.minecraft_path, "assets"))
                                    value = value.replace("${assets_index_name}", version_json.get("assetIndex", {}).get("id", version))
                                    value = value.replace("${auth_uuid}", credentials.get("uuid", ""))
                                    value = value.replace("${auth_access_token}", credentials.get("access_token", ""))
                                    value = value.replace("${auth_player_name}", credentials.get("username", "Player"))
                                    value = value.replace("${user_type}", "mojang")
                                    value = value.replace("${game_directory}", self.minecraft_path)
                                    value = value.replace("${game_assets}", os.path.join(self.minecraft_path, "assets", "virtual", "legacy"))
                                    value = value.replace("${user_properties}", "{}")
                                    
                                    # Reemplazar variables de quick play con valores vacíos
                                    value = value.replace("${quickPlayPath}", "")
                                    value = value.replace("${quickPlaySingleplayer}", "")
                                    value = value.replace("${quickPlayMultiplayer}", "")
                                    value = value.replace("${quickPlayRealms}", "")
                                    
                                    # Si el argumento contiene variables sin resolver, omitirlo
                                    if "${" in value and "}" in value:
                                        continue
                                    
                                    game_args.append(value)
        # Versiones antiguas: usar minecraftArguments
        elif "minecraftArguments" in version_json:
            # Parsear minecraftArguments (es un string con espacios)
            args_string = version_json["minecraftArguments"]
            # Dividir por espacios, pero mantener comillas
            import shlex
            args_list = shlex.split(args_string)
            
            for arg in args_list:
                # Reemplazar variables
                arg = arg.replace("${version_name}", version)
                arg = arg.replace("${version_type}", version_json.get("type", "release"))
                arg = arg.replace("${assets_root}", os.path.join(self.minecraft_path, "assets"))
                arg = arg.replace("${assets_index_name}", version_json.get("assetIndex", {}).get("id", version))
                arg = arg.replace("${auth_uuid}", credentials.get("uuid", ""))
                arg = arg.replace("${auth_access_token}", credentials.get("access_token", ""))
                arg = arg.replace("${auth_player_name}", credentials.get("username", "Player"))
                arg = arg.replace("${user_type}", "mojang")
                arg = arg.replace("${game_directory}", self.minecraft_path)
                arg = arg.replace("${game_assets}", os.path.join(self.minecraft_path, "assets", "virtual", "legacy"))
                arg = arg.replace("${user_properties}", "{}")
                
                # Reemplazar variables de quick play con valores vacíos
                arg = arg.replace("${quickPlayPath}", "")
                arg = arg.replace("${quickPlaySingleplayer}", "")
                arg = arg.replace("${quickPlayMultiplayer}", "")
                arg = arg.replace("${quickPlayRealms}", "")
                
                # Si el argumento contiene variables sin resolver, omitirlo
                if "${" in arg and "}" in arg:
                    continue
                
                game_args.append(arg)
        else:
            # Argumentos por defecto si no están en el JSON
            game_args = [
                "--username", credentials.get("username", "Player"),
                "--version", version,
                "--gameDir", self.minecraft_path,
                "--assetsDir", os.path.join(self.minecraft_path, "assets"),
                "--assetIndex", version_json.get("assetIndex", {}).get("id", version),
                "--uuid", credentials.get("uuid", ""),
                "--accessToken", credentials.get("access_token", ""),
                "--userType", "mojang",
                "--versionType", version_json.get("type", "release")
            ]
        
        # Filtrar argumentos de quick play: solo pasar uno o ninguno
        # Si hay múltiples, solo incluir el primero con valor válido
        # También filtrar --demo y flags sin valor (--width, --height, etc.)
        filtered_args = []
        i = 0
        quick_play_included = False  # Flag para saber si ya incluimos uno
        
        # Flags que requieren valores (si no tienen valor, deben omitirse)
        flags_requiring_values = ["--width", "--height", "--quickPlayPath", "--quickPlaySingleplayer", 
                                  "--quickPlayMultiplayer", "--quickPlayRealms"]
        
        while i < len(game_args):
            arg = game_args[i]
            
            # Omitir argumento --demo
            if isinstance(arg, str) and arg == "--demo":
                i += 1
                continue
            
            # CRÍTICO: Filtrar flags que requieren valores pero no los tienen
            # El launcher oficial omite flags como --width y --height si no tienen valores
            if isinstance(arg, str) and arg in flags_requiring_values:
                # Verificar si tiene un valor válido (siguiente argumento no es otro flag)
                has_valid_value = False
                if i + 1 < len(game_args):
                    next_arg = game_args[i + 1]
                    # El valor es válido si no está vacío, no es otro flag, y no tiene variables sin resolver
                    if (isinstance(next_arg, str) and next_arg and next_arg != "" and 
                        not next_arg.startswith("--") and 
                        not ("${" in next_arg and "}" in next_arg)):
                        has_valid_value = True
                
                if has_valid_value:
                    # Tiene valor válido, incluirlo
                    filtered_args.append(arg)
                    filtered_args.append(game_args[i + 1])
                    i += 2
                    continue
                else:
                    # No tiene valor válido, omitirlo
                    print(f"[SKIP] Flag sin valor omitido: {arg}")
                    i += 1
                    continue
            
            # Detectar argumentos de quick play
            if isinstance(arg, str) and arg.startswith("--quickPlay"):
                # Si ya incluimos uno, omitir todos los demás
                if quick_play_included:
                    # Omitir este argumento y su valor (si existe)
                    if i + 1 < len(game_args) and not game_args[i + 1].startswith("--"):
                        i += 2  # Omitir argumento y valor
                    else:
                        i += 1  # Solo omitir el argumento
                    continue
                
                # Verificar si tiene un valor válido
                has_valid_value = False
                if i + 1 < len(game_args):
                    next_arg = game_args[i + 1]
                    # El valor es válido si no está vacío y no tiene variables sin resolver
                    if next_arg and next_arg != "" and not ("${" in str(next_arg) and "}" in str(next_arg)):
                        has_valid_value = True
                
                # Si el argumento mismo tiene variables sin resolver, omitirlo
                if "${" in arg and "}" in arg:
                    i += 1
                    continue
                
                # Si tiene un valor válido, incluirlo (solo el primero)
                if has_valid_value:
                    filtered_args.append(arg)
                    filtered_args.append(game_args[i + 1])
                    quick_play_included = True
                    i += 2
                    continue
                else:
                    # No tiene valor válido, omitirlo
                    print(f"[SKIP] Flag quick play sin valor omitido: {arg}")
                    if i + 1 < len(game_args) and not game_args[i + 1].startswith("--"):
                        i += 2
                    else:
                        i += 1
                    continue
            
            # Argumento normal, incluirlo
            filtered_args.append(arg)
            i += 1
        
        return filtered_args
    
    def check_minecraft_installed(self) -> bool:
        """Verifica si Minecraft está instalado"""
        return os.path.exists(self.minecraft_path)

