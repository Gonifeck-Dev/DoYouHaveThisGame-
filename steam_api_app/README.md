# Steam API Helper

Aplicación GUI (+ CLI) en Python para consultar, comparar y analizar librerías de Steam entre usuarios de una familia compartida.

## Características

- Consulta la **Shared Library** de Steam Family Sharing de tu cuenta
- **Visor in-app** de juegos con búsqueda y columnas ordenables
- **Comparador de librerías** entre dos usuarios con:
  - Fuente por archivo JSON o por SteamID/Vanity en tiempo real
  - Horas jugadas por cada usuario (columnas dinámicas)
  - **Afinidad** — media armónica de horas (premia los juegos que ambos jugaron)
  - Tags de género/categoría vía SteamSpy con caché local
  - Filtro en tiempo real por nombre o tag
- **Exportar** la intersección a JSON con horas, afinidad y tags
- **Persistencia de configuración** — Vanity, SteamID y Family GroupID se recuerdan entre sesiones
- **Build portable** — un solo `.exe` sin necesidad de Python instalado

---

## Estructura del proyecto

```
steam_api_app/
├── app.py              # Entry point (GUI y build portable)
├── build.ps1           # Script para generar el .exe portable
├── requirements.txt    # Dependencias en tiempo de ejecución
├── README.md
└── src/
    ├── gui.py          # Interfaz gráfica (Tkinter)
    └── main.py         # Cliente Steam API + CLI
```

---

## Instalación y ejecución en modo desarrollo

### 1. Requisitos

- Python 3.10 o superior
- PowerShell (Windows)

### 2. Crear entorno virtual e instalar dependencias

```powershell
cd steam_api_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Ejecutar la GUI

```powershell
python app.py
```

---

## Flujo de uso de la GUI

### Paso 1 — Steam API Key

Ingresa tu Steam Web API Key. Si no tenés una, el botón **"Abrir pagina Steam API Key"** abre la página oficial.

> La API Key **nunca se guarda en disco**.

### Paso 2 — Usuario de Steam

| Campo | Descripción |
|---|---|
| Vanity URL | Tu nombre de usuario de Steam (el que aparece en la URL del perfil) |
| SteamID | Tu SteamID64. Se puede rellenar automáticamente con el botón **"Llenar SteamID"** |

Estos datos se guardan automáticamente en `~/.steam_api_app/config.json`.

### Paso 3 — Access Token

El Access Token es necesario para consultar la Shared Library. Se obtiene desde el navegador:

1. Clic en **"Abrir endpoint Access Token"** — se abre `https://store.steampowered.com/pointssummary/ajaxgetasyncconfig` con tu sesión de Steam activa
2. En la página verás un JSON. Copialo completo (Ctrl+A, Ctrl+C)
3. Pegalo en el cuadro de texto y clic en **"Importar desde JSON navegador"**
4. La app extrae automáticamente `webapi_token` y rellena el campo

> El Access Token **nunca se guarda en disco**.

### Paso 4 — Family GroupID

Clic en **"Llenar Family GroupID"** — usa el Access Token + SteamID para obtenerlo automáticamente desde la API de Steam.

### Paso 5 — Shared Library

- Activá o desactivá **include_own** para incluir tus propios juegos en los resultados
- Clic en **"Consultar Shared Library"** — abre un visor in-app con todos los juegos
- Clic en **"Guardar Shared Library JSON"** — guarda la respuesta cruda como `sharedlibrary_<vanity>.json`

### Paso 6 — Comparar librerías

Clic en **"Comparar librerias"** para abrir la ventana de comparación.

Para cada librería (A y B) podés elegir la fuente:

| Modo | Descripción |
|---|---|
| **Archivo JSON** | Seleccioná un `sharedlibrary_*.json` guardado previamente |
| **SteamID** | Ingresá un SteamID64 o Vanity URL y clic en **"Obtener librería"** — consulta `GetOwnedGames` en tiempo real (solo necesita API Key + perfil público) |

Columnas del comparador:

| Columna | Descripción |
|---|---|
| App ID | ID del juego |
| Nombre | Nombre del juego |
| Hrs A / Hrs B | Horas jugadas por cada usuario |
| Afinidad | Media armónica de horas — `2·Ha·Hb / (Ha+Hb)` |
| Tags | Tags de SteamSpy (géneros, categorías) |

Todas las columnas son **ordenables con clic**. Hay un filtro de texto en tiempo real por nombre o tag.

#### Cargar tags

- **"Cargar tags (SteamSpy)"** — descarga tags desde `steamspy.com/api.php` con 3 workers en paralelo. Los resultados se cachean en `~/.steam_api_app/tags_cache.json` para no repetir descargas.
- **"Cargar tags desde JSON"** — carga tags desde un JSON de comparación exportado previamente (útil sin conexión).

#### Exportar

**"Guardar JSON"** exporta la intersección con el formato:

```json
{
  "common_apps": [
    {
      "appid": "440",
      "name": "Team Fortress 2",
      "playtime_vanityA_min": 1200,
      "playtime_vanityB_min": 340,
      "afinidad_h": 4.6,
      "tags": ["Free to Play", "Action", "FPS"]
    }
  ]
}
```

---

## Build portable (.exe)

Genera un único ejecutable que funciona en cualquier PC con Windows sin instalar Python ni dependencias.

```powershell
cd steam_api_app
.\.venv\Scripts\Activate.ps1
.\build.ps1
```

El resultado estará en:

```
dist\SteamAPIHelper.exe
```

Si PowerShell bloquea la ejecución de scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## CLI (uso avanzado)

`src/main.py` también funciona como herramienta de línea de comandos.

### Ejemplos

```powershell
# Con access_token ya conocido
python src/main.py --api-key "TU_API_KEY" --access-token "TU_ACCESS_TOKEN"

# Generar access_token desde refresh_token
python src/main.py --api-key "TU_API_KEY" --refresh-token "TU_REFRESH_TOKEN"

# Resolver SteamID desde Vanity primero
python src/main.py --api-key "TU_API_KEY" --vanity-url "gaben" --refresh-token "TU_REFRESH_TOKEN"

# Imprimir payloads completos para debug
python src/main.py --api-key "TU_API_KEY" --access-token "TU_ACCESS_TOKEN" --debug
```

### Salida

```json
{
  "access_token": "...",
  "steamid": "...",
  "family_groupid": "..."
}
```

---

## Variables de entorno (opcional)

```powershell
$env:STEAM_API_KEY    = "TU_API_KEY"
$env:STEAM_ACCESS_TOKEN = "TU_ACCESS_TOKEN"
$env:STEAM_STEAMID    = "76561198..."
$env:STEAM_VANITY_URL = "tu_vanity"
python app.py
```

> `STEAM_API_KEY` y `STEAM_ACCESS_TOKEN` son las únicas credenciales sensibles. **Nunca se guardan en disco.**

---

## APIs utilizadas

| Endpoint | Uso |
|---|---|
| `ISteamUser/ResolveVanityURL/v1` | Resolver nombre de usuario → SteamID64 |
| `IFamilyGroupsService/GetFamilyGroupForUser/v1` | Obtener Family GroupID |
| `IFamilyGroupsService/GetSharedLibraryApps/v1` | Consultar librería compartida |
| `IPlayerService/GetOwnedGames/v1` | Consultar juegos de un usuario (comparador en modo SteamID) |
| `IAuthenticationService/GenerateAccessTokenForApp/v1` | Generar access token desde refresh token (CLI) |
| `ISteamUserOAuth/GetTokenDetails/v1` | Extraer steamid desde access token (CLI) |
| `steamspy.com/api.php` | Tags de géneros y categorías por juego |

Referencia de endpoints: <https://steamapi.xpaw.me>

---

## Archivos generados por la app

| Archivo | Descripción |
|---|---|
| `~/.steam_api_app/config.json` | Configuración persistida (Vanity, SteamID, Family GroupID) |
| `~/.steam_api_app/tags_cache.json` | Caché de tags de SteamSpy |
| `sharedlibrary_<vanity>.json` | Respuesta cruda de Shared Library (guardado manual) |
| `shared_common_games.json` | Intersección de librerías exportada desde el comparador |
