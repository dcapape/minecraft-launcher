"""
Módulo para gestionar la autenticación con Microsoft/Mojang
"""
import requests
import json
from typing import Optional, Dict, Tuple
import webbrowser
import time

class AuthManager:
    """Gestiona la autenticación de Minecraft con Microsoft"""
    
    # ID de aplicación de Microsoft para Minecraft
    CLIENT_ID = "00000000402b5328"
    
    # Endpoints de Microsoft OAuth
    DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
    TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    # Endpoints de la API
    XBOX_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
    XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
    MINECRAFT_AUTH_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
    PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
    
    def __init__(self):
        pass
    
    def get_authorization_url(self) -> str:
        """
        Obtiene la URL de autorización para que el usuario la visite
        """
        REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
        import urllib.parse
        auth_params = {
            "client_id": self.CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "XboxLive.signin offline_access",
            "display": "touch"
        }
        return f"https://login.live.com/oauth20_authorize.srf?{urllib.parse.urlencode(auth_params)}"
    
    def exchange_code_for_token(self, redirect_url: str) -> Optional[str]:
        """
        Intercambia el código de autorización de la URL de redirección por un token
        """
        try:
            REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
            
            # Extraer el código de autorización de la URL
            import urllib.parse
            parsed = urllib.parse.urlparse(redirect_url)
            params = urllib.parse.parse_qs(parsed.query)
            
            if "code" not in params:
                print("Error: No se encontró el código de autorización en la URL")
                return None
            
            auth_code = params["code"][0]
            
            # Intercambiar código por token
            token_data = {
                "client_id": self.CLIENT_ID,
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI
            }
            
            token_response = requests.post(
                "https://login.live.com/oauth20_token.srf",
                data=token_data
            )
            
            if token_response.status_code != 200:
                error_text = token_response.text[:500]
                print(f"Error obteniendo token: {error_text}")
                return None
            
            token_result = token_response.json()
            
            if "access_token" not in token_result:
                print(f"Error: No se recibió access_token. Respuesta: {token_result}")
                return None
            
            return token_result["access_token"]
            
        except Exception as e:
            print(f"Error intercambiando código por token: {str(e)}")
            return None
    
    def authenticate(self, redirect_url: str = None) -> Optional[Dict]:
        """
        Realiza el flujo completo de autenticación
        Si redirect_url es None, retorna la URL de autorización en un dict con clave 'auth_url'
        Si redirect_url está presente, completa la autenticación
        """
        try:
            # Si no hay redirect_url, retornar la URL de autorización
            if redirect_url is None:
                return {"auth_url": self.get_authorization_url()}
            
            # Paso 1: Obtener token de Microsoft usando el código de la URL
            ms_access_token = self.exchange_code_for_token(redirect_url)
            if not ms_access_token:
                return None
            
            # Paso 2: Autenticar con Xbox Live
            xbox_token = self._authenticate_xbox(ms_access_token)
            if not xbox_token:
                return None
            
            # Paso 3: Obtener token de XSTS
            xsts_token, userhash = self._get_xsts_token(xbox_token)
            if not xsts_token:
                return None
            
            # Paso 4: Autenticar con Minecraft
            minecraft_token = self._authenticate_minecraft(userhash, xsts_token)
            if not minecraft_token:
                return None
            
            # Paso 5: Obtener perfil de Minecraft
            profile = self._get_minecraft_profile(minecraft_token)
            if not profile:
                return None
            
            return {
                "access_token": minecraft_token,
                "username": profile.get("name"),
                "uuid": profile.get("id"),
                "expires_at": time.time() + 3600  # 1 hora de validez
            }
            
        except Exception as e:
            print(f"Error durante la autenticación: {str(e)}")
            return None
    
    
    def _authenticate_xbox(self, ms_token: str) -> Optional[str]:
        """Autentica con Xbox Live"""
        try:
            payload = {
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={ms_token}"
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            
            response = requests.post(self.XBOX_AUTH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("Token")
        except Exception as e:
            print(f"Error en autenticación Xbox: {str(e)}")
            return None
    
    def _get_xsts_token(self, xbox_token: str) -> Tuple[Optional[str], Optional[str]]:
        """Obtiene token XSTS y userhash"""
        try:
            payload = {
                "Properties": {
                    "SandboxId": "RETAIL",
                    "UserTokens": [xbox_token]
                },
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            }
            
            response = requests.post(self.XSTS_AUTH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            token = data.get("Token")
            userhash = data.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs")
            return token, userhash
        except Exception as e:
            print(f"Error obteniendo token XSTS: {str(e)}")
            return None, None
    
    def _authenticate_minecraft(self, userhash: str, xsts_token: str) -> Optional[str]:
        """Autentica con Minecraft Services"""
        try:
            payload = {
                "identityToken": f"XBL3.0 x={userhash};{xsts_token}"
            }
            
            response = requests.post(self.MINECRAFT_AUTH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
        except Exception as e:
            print(f"Error en autenticación Minecraft: {str(e)}")
            return None
    
    def _get_minecraft_profile(self, access_token: str) -> Optional[Dict]:
        """Obtiene el perfil de Minecraft del usuario"""
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(self.PROFILE_URL, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error obteniendo perfil: {str(e)}")
            return None
    
    def refresh_token(self, refresh_token: str) -> Optional[Dict]:
        """Refresca el token de acceso usando el refresh token"""
        # Nota: La implementación completa dependería de tener un refresh token válido
        # Por ahora, requerimos reautenticación
        return self.authenticate()

