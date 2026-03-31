# Steam API Python App

Python app (CLI + GUI) to get:

- access_token
- steamid
- family_groupid

Endpoints used (from <https://steamapi.xpaw.me>):

- IAuthenticationService/GenerateAccessTokenForApp/v1
- ISteamUserOAuth/GetTokenDetails/v1
- IFamilyGroupsService/GetFamilyGroupForUser/v1
- IFamilyGroupsService/GetSharedLibraryApps/v1
- ISteamUser/ResolveVanityURL/v1 (optional)

## 1) Install

```powershell
cd steam_api_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Run visual interface (GUI)

```powershell
python src/gui.py
```

Inside the GUI you can:

- Fill fields by category:
  Steam API Key (editable), Nombre de usuario/Vanity (editable), SteamID (editable), Access Token (readonly), Family GroupID (readonly)
- Steam API Key section has a button to open the Steam API key page.
- Nombre de usuario section has a button to resolve and auto-fill SteamID.
- Access Token flow is browser -> app:
  1) Open endpoint `https://store.steampowered.com/pointssummary/ajaxgetasyncconfig`
  2) Copy JSON from browser
  3) Paste in the app and click `Importar desde JSON navegador`
  4) App extracts `data.webapi_token` and auto-fills Access Token
- Family GroupID button fetches and auto-fills `family_groupid` using `access_token` + `steamid`.
- Shared Library section calls `GetSharedLibraryApps` with:
  `access_token`, `include_own`, `steamid`, `family_groupid`
- Shared Library output is rendered as HTML table (Steam-like visualizer style).
- After Shared Library fetch, the app opens an HTML preview in your browser and also shows the HTML source in the output panel.
- You can save response JSON with filename based on the queried SteamID (e.g. `sharedlibrary_....json`).
- `Comparar librerias` opens a separate window where you import 2 JSON files and see only shared games by App ID.
- From compare window, you can export the intersection to JSON.

## 3) Run CLI examples

### A) If you already have access_token

```powershell
python src/main.py --api-key "YOUR_API_KEY" --access-token "YOUR_ACCESS_TOKEN"
```

### B) If you have refresh_token and want app to generate access_token

```powershell
python src/main.py --api-key "YOUR_API_KEY" --refresh-token "YOUR_REFRESH_TOKEN"
```

### C) If you only know vanity URL and want steamid first

```powershell
python src/main.py --api-key "YOUR_API_KEY" --vanity-url "gaben" --refresh-token "YOUR_REFRESH_TOKEN"
```

## 4) Output

The app prints JSON:

```json
{
  "access_token": "...",
  "steamid": "...",
  "family_groupid": "..."
}
```

## Notes

- In this app, `GetFamilyGroupForUser` is called with `access_token` (preferred for this flow).
- `GetTokenDetails` needs `access_token`.
- Steam does not provide a simple public endpoint to mint `access_token` without auth context; this app uses `GenerateAccessTokenForApp` when you already have `refresh_token`.
- For GUI flow, `refresh_token` is not required to import `webapi_token` from browser JSON.

## 5) Environment variables (optional)

You can set these in PowerShell:

```powershell
$env:STEAM_API_KEY="YOUR_API_KEY"
$env:STEAM_REFRESH_TOKEN="YOUR_REFRESH_TOKEN"
$env:STEAM_ACCESS_TOKEN="YOUR_ACCESS_TOKEN"
$env:STEAM_STEAMID="..."
$env:STEAM_VANITY_URL="gaben"
python src/main.py
```
