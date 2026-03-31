from __future__ import annotations

import base64
import html
import json
import os
import re
import tempfile
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict, Optional

from main import SteamApiClient, SteamApiError, deep_find_first, normalize_string


class SteamGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Steam API Helper")
        self.root.geometry("980x840")
        self.root.minsize(860, 680)

        self.api_key_var = tk.StringVar(value=os.getenv("STEAM_API_KEY", ""))
        self.access_token_var = tk.StringVar(value=os.getenv("STEAM_ACCESS_TOKEN", ""))
        self.family_groupid_var = tk.StringVar(value="")
        self.steamid_var = tk.StringVar(value=os.getenv("STEAM_STEAMID", ""))
        self.vanity_url_var = tk.StringVar(value=os.getenv("STEAM_VANITY_URL", ""))
        self.include_own_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Listo")

        self.output_text: ScrolledText
        self.browser_response_text: ScrolledText
        self.save_shared_button: ttk.Button

        self._busy = False
        self._busy_buttons: list[ttk.Button] = []
        self.last_shared_library_payload: Optional[Dict[str, Any]] = None
        self.last_shared_library_steamid: Optional[str] = None
        self.last_shared_library_html: Optional[str] = None
        self.compare_window: Optional[tk.Toplevel] = None

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Steam API Visual Helper", font=("Segoe UI", 16, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            outer,
            text="Completa los campos por categoria y usa los botones para llenar Access Token, SteamID y Family GroupID.",
        )
        subtitle.pack(anchor=tk.W, pady=(2, 10))

        form_frame = ttk.Frame(outer)
        form_frame.pack(fill=tk.X, pady=(0, 10))

        key_frame = ttk.LabelFrame(form_frame, text="Steam API Key")
        key_frame.pack(fill=tk.X)
        self._add_labeled_entry(key_frame, 0, "Steam API Key", self.api_key_var)
        ttk.Button(
            key_frame,
            text="Abrir pagina Steam API Key",
            command=self._open_api_key_page,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 8))

        ttk.Separator(form_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        identity_frame = ttk.LabelFrame(form_frame, text="Usuario de Steam")
        identity_frame.pack(fill=tk.X)
        self._add_labeled_entry(identity_frame, 0, "Nombre de usuario (Vanity)", self.vanity_url_var)
        self._add_labeled_entry(identity_frame, 1, "SteamID (editable)", self.steamid_var)

        resolve_button = ttk.Button(
            identity_frame,
            text="Llenar SteamID",
            command=self._start_resolve_steamid,
        )
        resolve_button.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 8))
        self._busy_buttons.append(resolve_button)

        ttk.Button(
            identity_frame,
            text="Abrir calculadora SteamID",
            command=self._open_steamid_calculator_page,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        ttk.Separator(form_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        token_frame = ttk.LabelFrame(form_frame, text="Access Token")
        token_frame.pack(fill=tk.X)
        self._add_labeled_entry(token_frame, 0, "Access Token", self.access_token_var, readonly=True)

        token_buttons_frame = ttk.Frame(token_frame)
        token_buttons_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 6))

        endpoint_button = ttk.Button(
            token_buttons_frame,
            text="Abrir endpoint Access Token",
            command=self._start_fetch_access_token,
        )
        endpoint_button.pack(side=tk.LEFT)

        import_button = ttk.Button(
            token_buttons_frame,
            text="Importar desde JSON navegador",
            command=self._import_access_token_from_browser_json,
        )
        import_button.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(
            token_frame,
            text="Pega aqui la respuesta JSON copiada del navegador:",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8)

        self.browser_response_text = ScrolledText(token_frame, wrap=tk.WORD, height=6)
        self.browser_response_text.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(2, 8),
        )
        token_frame.grid_columnconfigure(1, weight=1)

        ttk.Separator(form_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        family_frame = ttk.LabelFrame(form_frame, text="Family GroupID")
        family_frame.pack(fill=tk.X)
        self._add_labeled_entry(
            family_frame,
            0,
            "Family GroupID",
            self.family_groupid_var,
            readonly=True,
        )
        family_button = ttk.Button(
            family_frame,
            text="Llenar Family GroupID",
            command=self._start_fetch_family_group_id,
        )
        family_button.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 8))
        self._busy_buttons.append(family_button)

        ttk.Separator(form_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        shared_frame = ttk.LabelFrame(form_frame, text="Shared Library Apps")
        shared_frame.pack(fill=tk.X)
        ttk.Checkbutton(
            shared_frame,
            text="include_own",
            variable=self.include_own_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        shared_fetch_button = ttk.Button(
            shared_frame,
            text="Consultar Shared Library",
            command=self._start_fetch_shared_library,
        )
        shared_fetch_button.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        self._busy_buttons.append(shared_fetch_button)

        self.save_shared_button = ttk.Button(
            shared_frame,
            text="Guardar Shared Library JSON",
            command=self._save_shared_library_json,
            state=tk.DISABLED,
        )
        self.save_shared_button.grid(row=0, column=2, sticky="w", padx=8, pady=6)

        ttk.Button(
            shared_frame,
            text="Comparar librerias",
            command=self._open_compare_libraries_window,
        ).grid(row=0, column=3, sticky="w", padx=8, pady=6)

        actions_frame = ttk.Frame(outer)
        actions_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(actions_frame, text="Copiar JSON", command=self._copy_output).pack(side=tk.LEFT)
        ttk.Button(actions_frame, text="Limpiar", command=self._clear_all).pack(side=tk.LEFT, padx=8)

        ttk.Label(actions_frame, textvariable=self.status_var).pack(side=tk.RIGHT)

        output_frame = ttk.LabelFrame(outer, text="Salida (HTML / JSON)")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = ScrolledText(output_frame, wrap=tk.WORD, height=18)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.output_text.insert(
            "1.0",
            "Flujo recomendado:\n"
            "1) Abrir endpoint Access Token\n"
            "2) Pegar JSON y usar Importar\n"
            "3) Llenar SteamID (manual o con Vanity)\n"
            "4) Llenar Family GroupID\n"
            "5) Consultar Shared Library y guardar JSON",
        )

    def _add_labeled_entry(
        self,
        parent: ttk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        readonly: bool = False,
    ) -> None:
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        entry_state = "readonly" if readonly else "normal"
        ttk.Entry(parent, textvariable=variable, state=entry_state).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=6,
        )
        parent.grid_columnconfigure(1, weight=1)

    def _set_busy(self, busy: bool, status: Optional[str] = None) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for button in self._busy_buttons:
            button.config(state=state)
        if not busy and self.last_shared_library_payload is not None:
            self.save_shared_button.config(state=tk.NORMAL)
        if status:
            self.status_var.set(status)

    def _start_thread(self, target: Any, status: str) -> None:
        if self._busy:
            return
        self._set_busy(True, status)

        def runner() -> None:
            try:
                target()
            except Exception as exc:
                self.root.after(0, lambda: self._on_lookup_error(f"Error inesperado: {exc}"))

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

    def _open_url(self, url: str) -> None:
        webbrowser.open(url, new=2)

    def _open_api_key_page(self) -> None:
        self._open_url("https://steamcommunity.com/dev/apikey")

    def _open_steamid_calculator_page(self) -> None:
        self._open_url("https://steamdb.info/calculator/")

    def _open_access_token_browser_endpoint(self) -> None:
        self._open_url("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
        self.status_var.set("Navegador abierto: copia el JSON y pegalo en la app")

    def _start_resolve_steamid(self) -> None:
        if self._busy:
            return

        api_key = normalize_string(self.api_key_var.get())
        vanity_url = normalize_string(self.vanity_url_var.get())
        if not api_key or not vanity_url:
            messagebox.showwarning(
                "Faltan datos",
                "Para resolver SteamID desde Vanity necesitas Steam API Key y Vanity URL.",
            )
            return

        self._start_thread(self._resolve_steamid_worker, "Resolviendo SteamID desde Vanity...")

    def _resolve_steamid_worker(self) -> None:
        try:
            timeout_value = self._safe_timeout()
            client = SteamApiClient(api_key=normalize_string(self.api_key_var.get()), timeout=timeout_value)
            vanity_url = normalize_string(self.vanity_url_var.get())
            payload = client.resolve_vanity_url(vanity_url or "")
            steamid = normalize_string(deep_find_first(payload, {"steamid"}))
            if not steamid:
                raise SteamApiError("No se pudo resolver SteamID desde Vanity URL.")
            self.root.after(0, lambda: self._on_resolve_steamid_success(steamid, payload))
        except SteamApiError as exc:
            self.root.after(0, lambda: self._on_lookup_error(str(exc)))
        except Exception as exc:
            self.root.after(0, lambda: self._on_lookup_error(f"Error inesperado: {exc}"))

    def _on_resolve_steamid_success(self, steamid: str, payload: Dict[str, Any]) -> None:
        self._set_busy(False)
        self.steamid_var.set(steamid)

        output: Dict[str, Any] = {
            "result": {"steamid": steamid},
            "payloads": {"resolve_vanity": payload},
        }
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", json.dumps(output, indent=2, ensure_ascii=True))
        self.status_var.set("SteamID resuelto")

    def _start_fetch_access_token(self) -> None:
        self._open_access_token_browser_endpoint()

    def _import_access_token_from_browser_json(self) -> None:
        raw_text = self.browser_response_text.get("1.0", tk.END).strip()
        if not raw_text:
            try:
                raw_text = self.root.clipboard_get().strip()
            except tk.TclError:
                raw_text = ""

        if not raw_text:
            messagebox.showwarning(
                "Sin contenido",
                "Pega primero el JSON del navegador en el cuadro de Access Token.",
            )
            return

        payload = self._parse_browser_payload(raw_text)
        if payload is None:
            messagebox.showerror(
                "JSON invalido",
                "No se pudo interpretar la respuesta. Verifica que pegaste JSON valido.",
            )
            return

        webapi_token = normalize_string(deep_find_first(payload, {"webapi_token"}))
        if not webapi_token:
            regex_match = re.search(r'"webapi_token"\s*:\s*"([^"]+)"', raw_text)
            if regex_match:
                webapi_token = normalize_string(regex_match.group(1))

        if not webapi_token:
            messagebox.showerror(
                "Token no encontrado",
                "No se encontro data.webapi_token en el contenido pegado.",
            )
            return

        steamid = normalize_string(self.steamid_var.get())
        if not steamid:
            steamid = self._extract_steamid_from_jwt(webapi_token)

        self.access_token_var.set(webapi_token)
        if steamid:
            self.steamid_var.set(steamid)

        output: Dict[str, Any] = {
            "result": {
                "access_token": webapi_token,
                "steamid": steamid,
            },
            "payloads": {"browser_response": payload},
        }
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", json.dumps(output, indent=2, ensure_ascii=True))
        self.status_var.set("Access Token importado desde navegador")

    def _parse_browser_payload(self, raw_text: str) -> Dict[str, Any] | None:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            fragment = raw_text[start : end + 1]
            try:
                parsed = json.loads(fragment)
                if isinstance(parsed, dict):
                    return parsed
                return None
            except json.JSONDecodeError:
                return None

    def _extract_steamid_from_jwt(self, token: str) -> str | None:
        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload_part = parts[1]
        padding = "=" * ((4 - len(payload_part) % 4) % 4)
        try:
            decoded_bytes = base64.urlsafe_b64decode(payload_part + padding)
            payload_data = json.loads(decoded_bytes.decode("utf-8", errors="ignore"))
        except Exception:
            return None

        sub_value = normalize_string(payload_data.get("sub"))
        if sub_value and sub_value.isdigit():
            return sub_value
        return None

    def _extract_apps_from_payload(self, payload: Dict[str, Any]) -> list[Dict[str, str]]:
        if not isinstance(payload, dict):
            return []

        apps_raw: list[Any] = []
        response = payload.get("response")
        if isinstance(response, dict) and isinstance(response.get("apps"), list):
            apps_raw = response.get("apps") or []
        elif isinstance(payload.get("apps"), list):
            apps_raw = payload.get("apps") or []
        else:
            nested_payloads = payload.get("payloads")
            if isinstance(nested_payloads, dict):
                for nested in nested_payloads.values():
                    if isinstance(nested, dict):
                        extracted = self._extract_apps_from_payload(nested)
                        if extracted:
                            return extracted

        apps: list[Dict[str, str]] = []
        for app in apps_raw:
            if not isinstance(app, dict):
                continue
            appid = app.get("appid")
            if appid is None:
                continue
            appid_text = str(appid)
            name_text = normalize_string(app.get("name")) or "Unknown"
            apps.append({"appid": appid_text, "name": name_text})
        return apps

    def _build_shared_library_html(self, apps: list[Dict[str, str]]) -> str:
        rows = []
        for app in apps:
            appid = html.escape(app.get("appid", ""))
            name = html.escape(app.get("name", "Unknown"))
            rows.append(
                "<tr>"
                f"<td class=\"appid-col\">{appid}</td>"
                f"<td>{name}</td>"
                "</tr>"
            )

        rows_html = "\n".join(rows) if rows else (
            "<tr><td class=\"appid-col\">-</td><td>No games found</td></tr>"
        )

        return f"""
<style>
    body {{
        font-family: Arial, sans-serif;
        padding: 16px;
        background-color: #f4f4f4;
    }}
    h2 {{
        color: #333;
        margin-bottom: 12px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        background-color: #fff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-radius: 6px;
        overflow: hidden;
    }}
    thead tr {{
        background-color: #1b2838;
        color: #c6d4df;
        text-align: left;
    }}
    thead th {{
        padding: 12px 16px;
        font-size: 14px;
        letter-spacing: 0.5px;
    }}
    tbody tr:nth-child(odd) {{
        background-color: #f9f9f9;
    }}
    tbody tr:nth-child(even) {{
        background-color: #eef2f5;
    }}
    tbody tr:hover {{
        background-color: #d6e4f0;
    }}
    tbody td {{
        padding: 10px 16px;
        font-size: 13px;
        color: #333;
        border-bottom: 1px solid #ddd;
    }}
    .appid-col {{
        width: 120px;
        font-weight: bold;
        color: #555;
    }}
</style>

<h2>Shared Library Games ({len(apps)} total)</h2>
<table>
    <thead>
        <tr>
            <th class=\"appid-col\">App ID</th>
            <th>Game Name</th>
        </tr>
    </thead>
    <tbody>
        {rows_html}
    </tbody>
</table>
""".strip()

    def _open_shared_library_html_preview(self, steamid: str, html_content: str) -> Optional[Path]:
        preview_dir = Path(tempfile.gettempdir()) / "steam_api_app"
        try:
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview_path = preview_dir / f"sharedlibrary_preview_{steamid or 'unknown'}.html"
            preview_path.write_text(html_content, encoding="utf-8")
            webbrowser.open(preview_path.resolve().as_uri(), new=2)
            return preview_path
        except OSError:
            return None

    def _open_compare_libraries_window(self) -> None:
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.lift()
            self.compare_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.compare_window = window
        window.title("Comparar librerias")
        window.geometry("860x560")
        window.minsize(760, 460)

        file_a_var = tk.StringVar(value="")
        file_b_var = tk.StringVar(value="")
        count_var = tk.StringVar(value="Coincidencias: 0")
        shared_cache: list[Dict[str, str]] = []

        container = ttk.Frame(window, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="JSON libreria A:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=file_a_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(container, text="JSON libreria B:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=file_b_var).grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        def pick_file(target_var: tk.StringVar) -> None:
            selected = filedialog.askopenfilename(
                title="Seleccionar JSON",
                filetypes=[("JSON", "*.json")],
            )
            if selected:
                target_var.set(selected)

        ttk.Button(container, text="Buscar", command=lambda: pick_file(file_a_var)).grid(
            row=0,
            column=2,
            padx=6,
            pady=4,
        )
        ttk.Button(container, text="Buscar", command=lambda: pick_file(file_b_var)).grid(
            row=1,
            column=2,
            padx=6,
            pady=4,
        )

        tree = ttk.Treeview(container, columns=("appid", "name"), show="headings", height=14)
        tree.heading("appid", text="App ID")
        tree.heading("name", text="Game Name")
        tree.column("appid", width=140, anchor="center")
        tree.column("name", width=620, anchor="w")
        tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 6))

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=3, column=3, sticky="ns", pady=(10, 6))

        def load_json(path: str) -> Dict[str, Any]:
            with open(path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            if not isinstance(data, dict):
                raise ValueError("El JSON debe ser un objeto")
            return data

        def compare() -> None:
            nonlocal shared_cache
            path_a = normalize_string(file_a_var.get())
            path_b = normalize_string(file_b_var.get())
            if not path_a or not path_b:
                messagebox.showwarning(
                    "Faltan archivos",
                    "Selecciona los dos archivos JSON para comparar.",
                    parent=window,
                )
                return

            try:
                payload_a = load_json(path_a)
                payload_b = load_json(path_b)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                messagebox.showerror("Error", f"No se pudo leer algun JSON: {exc}", parent=window)
                return

            apps_a = self._extract_apps_from_payload(payload_a)
            apps_b = self._extract_apps_from_payload(payload_b)

            map_a = {app["appid"]: app["name"] for app in apps_a if app.get("appid")}
            map_b = {app["appid"]: app["name"] for app in apps_b if app.get("appid")}

            common_ids = set(map_a.keys()) & set(map_b.keys())
            ordered_ids = sorted(
                common_ids,
                key=lambda appid: (0, int(appid)) if appid.isdigit() else (1, appid),
            )

            shared_cache = [
                {
                    "appid": appid,
                    "name": map_a.get(appid) or map_b.get(appid) or "Unknown",
                }
                for appid in ordered_ids
            ]

            for row_id in tree.get_children():
                tree.delete(row_id)
            for game in shared_cache:
                tree.insert("", tk.END, values=(game["appid"], game["name"]))

            count_var.set(f"Coincidencias: {len(shared_cache)}")

        def save_comparison_json() -> None:
            if not shared_cache:
                messagebox.showwarning(
                    "Sin coincidencias",
                    "Primero ejecuta la comparacion de librerias.",
                    parent=window,
                )
                return

            file_path = filedialog.asksaveasfilename(
                title="Guardar coincidencias",
                defaultextension=".json",
                initialfile="shared_common_games.json",
                filetypes=[("JSON", "*.json")],
            )
            if not file_path:
                return

            try:
                with open(file_path, "w", encoding="utf-8") as file_obj:
                    json.dump({"common_apps": shared_cache}, file_obj, indent=2, ensure_ascii=True)
            except OSError as exc:
                messagebox.showerror("Error", f"No se pudo guardar: {exc}", parent=window)

        actions = ttk.Frame(container)
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Button(actions, text="Comparar", command=compare).pack(side=tk.LEFT)
        ttk.Button(actions, text="Guardar coincidencias JSON", command=save_comparison_json).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Label(actions, textvariable=count_var).pack(side=tk.LEFT, padx=(12, 0))

        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(3, weight=1)

        def on_close() -> None:
            self.compare_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

    def _start_fetch_family_group_id(self) -> None:
        if self._busy:
            return

        access_token = normalize_string(self.access_token_var.get())
        if not access_token:
            messagebox.showwarning(
                "Falta Access Token",
                "Primero obten o pega el Access Token para consultar Family GroupID.",
            )
            return

        steamid = normalize_string(self.steamid_var.get())
        if not steamid:
            messagebox.showwarning(
                "Falta SteamID",
                "Necesitas SteamID para consultar Family GroupID.",
            )
            return

        self._start_thread(self._fetch_family_group_worker, "Consultando Family GroupID...")

    def _fetch_family_group_worker(self) -> None:
        timeout_value = 30
        access_token = normalize_string(self.access_token_var.get())
        steamid = normalize_string(self.steamid_var.get())
        client = SteamApiClient(api_key=normalize_string(self.api_key_var.get()), timeout=timeout_value)

        try:
            payload = client.get_family_group_for_user(
                steamid=steamid,
                include_family_group_response=False,
                access_token=access_token,
            )
            family_groupid = normalize_string(
                deep_find_first(
                    payload,
                    {"family_groupid", "family_group_id", "gidfamily", "familyid", "groupid"},
                )
            )
            if not family_groupid:
                raise SteamApiError("No se encontro Family GroupID en la respuesta.")
            self.root.after(0, lambda: self._on_fetch_family_group_success(family_groupid, payload))
        except SteamApiError as exc:
            self.root.after(0, lambda: self._on_lookup_error(str(exc)))
        except Exception as exc:
            self.root.after(0, lambda: self._on_lookup_error(f"Error inesperado: {exc}"))

    def _on_fetch_family_group_success(self, family_groupid: str, payload: Dict[str, Any]) -> None:
        self._set_busy(False)
        self.family_groupid_var.set(family_groupid)

        output: Dict[str, Any] = {
            "result": {"family_groupid": family_groupid},
            "payloads": {"family_group": payload},
        }
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", json.dumps(output, indent=2, ensure_ascii=True))
        self.status_var.set("Family GroupID obtenido")

    def _start_fetch_shared_library(self) -> None:
        if self._busy:
            return

        access_token = normalize_string(self.access_token_var.get())
        steamid = normalize_string(self.steamid_var.get())
        family_groupid = normalize_string(self.family_groupid_var.get())

        if not access_token:
            messagebox.showwarning("Falta Access Token", "Importa primero un Access Token.")
            return
        if not steamid:
            messagebox.showwarning("Falta SteamID", "Necesitas SteamID para consultar Shared Library.")
            return
        if not family_groupid:
            messagebox.showwarning(
                "Falta Family GroupID",
                "Primero usa el boton 'Llenar Family GroupID'.",
            )
            return

        self._start_thread(self._fetch_shared_library_worker, "Consultando Shared Library...")

    def _fetch_shared_library_worker(self) -> None:
        timeout_value = 30
        access_token = normalize_string(self.access_token_var.get())
        steamid = normalize_string(self.steamid_var.get())
        family_groupid = normalize_string(self.family_groupid_var.get())
        include_own = self.include_own_var.get()

        client = SteamApiClient(api_key=normalize_string(self.api_key_var.get()), timeout=timeout_value)

        try:
            payload = client.get_shared_library_apps(
                access_token=access_token or "",
                include_own=include_own,
                steamid=steamid or "",
                family_groupid=family_groupid or "",
            )
            self.root.after(
                0,
                lambda: self._on_fetch_shared_library_success(
                    steamid or "",
                    include_own,
                    payload,
                ),
            )
        except SteamApiError as exc:
            self.root.after(0, lambda: self._on_lookup_error(str(exc)))
        except Exception as exc:
            self.root.after(0, lambda: self._on_lookup_error(f"Error inesperado: {exc}"))

    def _on_fetch_shared_library_success(
        self,
        steamid: str,
        include_own: bool,
        payload: Dict[str, Any],
    ) -> None:
        self._set_busy(False)
        self.last_shared_library_payload = payload
        self.last_shared_library_steamid = steamid
        self.save_shared_button.config(state=tk.NORMAL)

        apps = self._extract_apps_from_payload(payload)
        html_content = self._build_shared_library_html(apps)
        self.last_shared_library_html = html_content

        preview_path = self._open_shared_library_html_preview(steamid, html_content)

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", html_content)

        if preview_path:
            self.status_var.set(
                f"Shared Library consultada ({len(apps)} juegos). Vista HTML abierta en navegador."
            )
        else:
            self.status_var.set(f"Shared Library consultada ({len(apps)} juegos)")

    def _save_shared_library_json(self) -> None:
        if not self.last_shared_library_payload or not self.last_shared_library_steamid:
            messagebox.showwarning(
                "Sin datos",
                "Primero consulta Shared Library antes de guardar.",
            )
            return

        default_name = f"sharedlibrary_{self.last_shared_library_steamid}.json"
        file_path = filedialog.asksaveasfilename(
            title="Guardar Shared Library",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON", "*.json")],
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as file_obj:
                json.dump(self.last_shared_library_payload, file_obj, indent=2, ensure_ascii=True)
        except OSError as exc:
            messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo: {exc}")
            return

        self.status_var.set(f"Shared Library guardada: {file_path}")

    def _on_lookup_error(self, message: str) -> None:
        self._set_busy(False)
        self.status_var.set("Error")
        messagebox.showerror("Steam API", message)

    def _copy_output(self) -> None:
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("Copiar", "No hay contenido para copiar.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_var.set("JSON copiado al portapapeles")

    def _clear_all(self) -> None:
        self.access_token_var.set("")
        self.family_groupid_var.set("")
        self.steamid_var.set("")
        self.vanity_url_var.set("")
        self.browser_response_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", "Campos limpiados.")
        self.last_shared_library_payload = None
        self.last_shared_library_steamid = None
        self.last_shared_library_html = None
        self.save_shared_button.config(state=tk.DISABLED)
        self.status_var.set("Listo")

    def _safe_timeout(self) -> int:
        return 30


def main() -> None:
    root = tk.Tk()
    app = SteamGuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
