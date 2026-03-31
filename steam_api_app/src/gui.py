from __future__ import annotations

import base64
import json
import os
import re
import threading
import tkinter as tk
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict, Optional

from main import SteamApiClient, SteamApiError, deep_find_first, normalize_string

_TAGS_CACHE_PATH = Path.home() / ".steam_api_app" / "tags_cache.json"
_CONFIG_PATH = Path.home() / ".steam_api_app" / "config.json"


def _vanity_from_path(path: str) -> str:
    """Extract a display name from a sharedlibrary_<vanity>.json filename."""
    stem = Path(path).stem
    for prefix in ("sharedlibrary_", "ownedgames_"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem

class SteamGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Steam API Helper")
        self.root.geometry("760x880")
        self.root.minsize(760, 880)

        self.api_key_var = tk.StringVar(value=os.getenv("STEAM_API_KEY", ""))
        self.access_token_var = tk.StringVar(value=os.getenv("STEAM_ACCESS_TOKEN", ""))
        self.family_groupid_var = tk.StringVar(value="")
        self.steamid_var = tk.StringVar(value=os.getenv("STEAM_STEAMID", ""))
        self.vanity_url_var = tk.StringVar(value=os.getenv("STEAM_VANITY_URL", ""))
        self.include_own_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Listo")

        self._load_config()

        # Auto-save config whenever a non-sensitive field changes.
        for _var in (self.vanity_url_var, self.steamid_var, self.family_groupid_var):
            _var.trace_add("write", lambda *_: self._save_config())

        self.browser_response_text: ScrolledText
        self.save_shared_button: ttk.Button

        self._busy = False
        self._busy_buttons: list[ttk.Button] = []
        self.last_shared_library_payload: Optional[Dict[str, Any]] = None
        self.last_shared_library_steamid: Optional[str] = None
        self.library_window: Optional[tk.Toplevel] = None
        self.compare_window: Optional[tk.Toplevel] = None

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Steam API Visual Helper", font=("Segoe UI", 16, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            outer,
            text="Flujo: Importar Access Token → SteamID → Family GroupID → Consultar Shared Library → Guardar JSON → Comparar",
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
        actions_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(actions_frame, text="Limpiar", command=self._clear_all).pack(side=tk.LEFT)
        ttk.Label(actions_frame, textvariable=self.status_var).pack(side=tk.RIGHT)

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
        self.status_var.set(f"SteamID resuelto: {steamid}")

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

    def _extract_apps_from_payload(self, payload: Dict[str, Any]) -> list[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []

        apps_raw: list[Any] = []
        response = payload.get("response")
        if isinstance(response, dict):
            if isinstance(response.get("apps"), list):
                apps_raw = response.get("apps") or []
            elif isinstance(response.get("games"), list):
                apps_raw = response.get("games") or []
        elif isinstance(payload.get("apps"), list):
            apps_raw = payload.get("apps") or []
        elif isinstance(payload.get("games"), list):
            apps_raw = payload.get("games") or []
        else:
            nested_payloads = payload.get("payloads")
            if isinstance(nested_payloads, dict):
                for nested in nested_payloads.values():
                    if isinstance(nested, dict):
                        extracted = self._extract_apps_from_payload(nested)
                        if extracted:
                            return extracted

        apps: list[Dict[str, Any]] = []
        for app in apps_raw:
            if not isinstance(app, dict):
                continue
            appid = app.get("appid")
            if appid is None:
                continue
            apps.append({
                "appid": str(appid),
                "name": normalize_string(app.get("name")) or "Unknown",
                "playtime": int(app.get("rt_playtime") or app.get("playtime_forever") or 0),
            })
        return apps

    def _open_library_window(self, apps: list[Dict[str, str]], steamid: str) -> None:
        """Open (or refresh) an in-app library viewer window."""
        if self.library_window is not None and self.library_window.winfo_exists():
            win = self.library_window
            win.lift()
            win.focus_force()
        else:
            win = tk.Toplevel(self.root)
            self.library_window = win

            def on_close() -> None:
                self.library_window = None
                win.destroy()

            win.protocol("WM_DELETE_WINDOW", on_close)

        win.title(f"Librería Steam — {steamid} ({len(apps)} juegos)")
        win.geometry("860x560")
        win.minsize(600, 400)

        for child in win.winfo_children():
            child.destroy()

        container = ttk.Frame(win, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(container)
        top_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top_bar, text="Buscar:").pack(side=tk.LEFT)
        search_var = tk.StringVar()
        ttk.Entry(top_bar, textvariable=search_var, width=32).pack(side=tk.LEFT, padx=6)
        count_lbl = ttk.Label(top_bar, text=f"{len(apps)} juegos")
        count_lbl.pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(tree_frame, columns=("appid", "name"), show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sort_state: Dict[str, Any] = {"col": None, "reverse": False}
        sorted_apps = list(apps)

        def populate(query: str = "") -> None:
            for row_id in tree.get_children():
                tree.delete(row_id)
            q = query.lower()
            visible = [a for a in sorted_apps if not q or q in a["name"].lower() or q in a["appid"]]
            for a in visible:
                tree.insert("", tk.END, values=(a["appid"], a["name"]))
            if q:
                count_lbl.config(text=f"{len(visible)} / {len(apps)} juegos")
            else:
                count_lbl.config(text=f"{len(apps)} juegos")

        def sort_col(col: str) -> None:
            reverse = sort_state["col"] == col and not sort_state["reverse"]
            sort_state["col"] = col
            sort_state["reverse"] = reverse
            if col == "appid":
                sorted_apps.sort(
                    key=lambda a: int(a["appid"]) if a["appid"].isdigit() else 0,
                    reverse=reverse,
                )
            else:
                sorted_apps.sort(key=lambda a: a["name"].lower(), reverse=reverse)
            populate(search_var.get())

        tree.heading("appid", text="App ID ▲▼", command=lambda: sort_col("appid"))
        tree.heading("name", text="Nombre ▲▼", command=lambda: sort_col("name"))
        tree.column("appid", width=120, anchor="center", stretch=False)
        tree.column("name", width=700, anchor="w")

        search_var.trace_add("write", lambda *_: populate(search_var.get()))
        populate()

    def _open_compare_libraries_window(self) -> None:
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.lift()
            self.compare_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.compare_window = window
        window.title("Comparar librerias")
        window.geometry("1120x720")
        window.minsize(880, 540)

        count_var = tk.StringVar(value="Coincidencias: 0")
        tags_status_var = tk.StringVar(value="")
        tag_filter_var = tk.StringVar(value="")

        vanity_a: list[str] = ["A"]
        vanity_b: list[str] = ["B"]
        shared_cache: list[Dict[str, Any]] = []
        playtime_a: Dict[str, float] = {}
        playtime_b: Dict[str, float] = {}
        tag_data: Dict[str, list] = {}
        tag_loading = [False]
        sort_state: Dict[str, Any] = {"col": None, "reverse": False}

        container = ttk.Frame(window, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_columnconfigure(0, weight=1)

        # ── Source panel builder ──────────────────────────────────────────
        def _make_source_panel(grid_row: int, label: str, default_name: str):
            """
            Build a LabelFrame with JSON / SteamID toggle.
            Returns (get_payload, get_display_name) closures.
            """
            mode_var = tk.StringVar(value="json")
            file_var = tk.StringVar(value="")
            steamid_var = tk.StringVar(value="")
            fetch_status_var = tk.StringVar(value="Sin datos")
            payload_store: list[Optional[Dict[str, Any]]] = [None]

            lf = ttk.LabelFrame(container, text=label, padding=(6, 4))
            lf.grid(row=grid_row, column=0, sticky="ew", pady=(0, 4))
            lf.grid_columnconfigure(2, weight=1)

            ttk.Radiobutton(
                lf, text="Archivo JSON", variable=mode_var,
                value="json", command=lambda: _toggle(),
            ).grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Radiobutton(
                lf, text="SteamID", variable=mode_var,
                value="steamid", command=lambda: _toggle(),
            ).grid(row=0, column=1, sticky="w", padx=(0, 10))

            # JSON sub-frame
            json_frame = ttk.Frame(lf)
            json_frame.grid(row=0, column=2, sticky="ew")
            json_frame.grid_columnconfigure(0, weight=1)
            ttk.Entry(json_frame, textvariable=file_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ttk.Button(json_frame, text="Buscar", command=lambda: _pick()).grid(row=0, column=1)

            # SteamID sub-frame
            sid_frame = ttk.Frame(lf)
            sid_frame.grid(row=0, column=2, sticky="ew")
            sid_frame.grid_columnconfigure(1, weight=1)
            ttk.Label(sid_frame, text="SteamID/Vanity:").grid(row=0, column=0, sticky="w", padx=(0, 4))
            ttk.Entry(sid_frame, textvariable=steamid_var, width=22).grid(row=0, column=1, sticky="ew")
            ttk.Button(sid_frame, text="Obtener librería", command=lambda: _fetch()).grid(
                row=0, column=2, padx=(4, 0)
            )
            ttk.Label(sid_frame, textvariable=fetch_status_var, foreground="#555").grid(
                row=0, column=3, padx=(6, 0)
            )

            def _toggle() -> None:
                if mode_var.get() == "json":
                    sid_frame.grid_remove()
                    json_frame.grid()
                else:
                    json_frame.grid_remove()
                    sid_frame.grid()

            def _pick() -> None:
                selected = filedialog.askopenfilename(
                    title=f"Seleccionar JSON — {label}",
                    filetypes=[("JSON", "*.json")],
                    parent=window,
                )
                if selected:
                    file_var.set(selected)
                    payload_store[0] = None

            def _fetch() -> None:
                sid = normalize_string(steamid_var.get())
                if not sid:
                    messagebox.showwarning(
                        "Falta SteamID", "Ingresa un SteamID o Vanity URL.", parent=window
                    )
                    return
                api_key = normalize_string(self.api_key_var.get())
                if not api_key:
                    messagebox.showwarning(
                        "Falta API Key",
                        "Necesitas la Steam API Key en la app principal para consultar juegos.",
                        parent=window,
                    )
                    return
                fetch_status_var.set("Obteniendo…")
                payload_store[0] = None

                def worker() -> None:
                    try:
                        client = SteamApiClient(api_key=api_key, timeout=30)
                        target_steamid = sid
                        if not sid.isdigit():
                            vresp = client.resolve_vanity_url(sid)
                            resolved = normalize_string(deep_find_first(vresp, {"steamid"}))
                            if not resolved:
                                window.after(
                                    0,
                                    lambda: fetch_status_var.set(f"Error: no se pudo resolver '{sid}'"),
                                )
                                return
                            target_steamid = resolved
                        payload = client.get_owned_games(
                            steamid=target_steamid,
                            include_appinfo=True,
                            include_played_free_games=True,
                        )
                        apps = self._extract_apps_from_payload(payload)
                        payload_store[0] = payload
                        window.after(
                            0,
                            lambda: fetch_status_var.set(
                                f"✓ {len(apps)} juegos ({target_steamid})"
                            ),
                        )
                    except Exception as exc:
                        window.after(0, lambda: fetch_status_var.set(f"Error: {exc}"))

                threading.Thread(target=worker, daemon=True).start()

            _toggle()  # initialize visibility

            def get_payload() -> Optional[Dict[str, Any]]:
                if mode_var.get() == "steamid":
                    return payload_store[0]
                path = normalize_string(file_var.get())
                if not path:
                    return None
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data if isinstance(data, dict) else None

            def get_display_name() -> str:
                if mode_var.get() == "steamid":
                    return normalize_string(steamid_var.get()) or default_name
                path = normalize_string(file_var.get())
                return _vanity_from_path(path) if path else default_name

            return get_payload, get_display_name

        get_payload_a, get_name_a = _make_source_panel(0, "Librería A", "A")
        get_payload_b, get_name_b = _make_source_panel(1, "Librería B", "B")

        # ── Filter bar ───────────────────────────────────────────────────
        filter_frame = ttk.Frame(container)
        filter_frame.grid(row=2, column=0, sticky="ew", pady=(8, 2))
        ttk.Label(filter_frame, text="Filtrar por tag o nombre:").pack(side=tk.LEFT)
        ttk.Entry(filter_frame, textvariable=tag_filter_var, width=28).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(filter_frame, textvariable=count_var).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Label(filter_frame, textvariable=tags_status_var, foreground="#666").pack(side=tk.LEFT, padx=(10, 0))

        # ── Tree ─────────────────────────────────────────────────────────
        COLS = ("appid", "name", "horas_a", "horas_b", "afinidad", "tags")
        tree = ttk.Treeview(container, columns=COLS, show="headings", height=16)
        tree.grid(row=4, column=0, sticky="nsew", pady=(4, 6))
        vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=4, column=1, sticky="ns", pady=(4, 6))
        container.grid_rowconfigure(4, weight=1)

        def _fmt_hrs(minutes: float) -> str:
            h = minutes / 60.0
            return "\u2014" if h < 0.1 else f"{h:.1f}h"

        def _harmonic_score(ma: float, mb: float) -> float:
            # Media armónica de horas (análogo al F₁-score):
            # premia juegos que AMBOS jugaron bastante; resiste outliers unilaterales.
            ha, hb = ma / 60.0, mb / 60.0
            if ha > 0 and hb > 0:
                return 2.0 * ha * hb / (ha + hb)
            return 0.0

        def refresh_tree(*_args: Any) -> None:
            query = tag_filter_var.get().strip().lower()
            for row_id in tree.get_children():
                tree.delete(row_id)
            visible = 0
            for game in shared_cache:
                appid = game["appid"]
                ma = playtime_a.get(appid, 0.0)
                mb = playtime_b.get(appid, 0.0)
                game_tags = tag_data.get(appid, [])
                if query and not (
                    query in game["name"].lower()
                    or any(query in t.lower() for t in game_tags)
                ):
                    continue
                score = _harmonic_score(ma, mb)
                tree.insert("", tk.END, values=(
                    appid,
                    game["name"],
                    _fmt_hrs(ma),
                    _fmt_hrs(mb),
                    "\u2014" if score < 0.05 else f"{score:.1f}h",
                    ", ".join(game_tags),
                ))
                visible += 1
            total = len(shared_cache)
            count_var.set(f"Mostrando: {visible} / {total}" if query else f"Coincidencias: {total}")

        def _sort_key(game: Dict[str, Any], col: str) -> Any:
            appid = game["appid"]
            if col == "appid":
                return int(appid) if appid.isdigit() else 0
            if col == "name":
                return game["name"].lower()
            if col == "horas_a":
                return playtime_a.get(appid, 0.0)
            if col == "horas_b":
                return playtime_b.get(appid, 0.0)
            if col == "afinidad":
                return _harmonic_score(playtime_a.get(appid, 0.0), playtime_b.get(appid, 0.0))
            if col == "tags":
                return ", ".join(tag_data.get(appid, []))
            return ""

        def sort_by(col: str) -> None:
            nonlocal shared_cache
            reverse = sort_state["col"] == col and not sort_state["reverse"]
            sort_state["col"] = col
            sort_state["reverse"] = reverse
            shared_cache = sorted(shared_cache, key=lambda g: _sort_key(g, col), reverse=reverse)
            refresh_tree()

        def _update_tree_headers() -> None:
            tree.heading("appid", text="App ID \u25b2\u25bc", command=lambda: sort_by("appid"))
            tree.heading("name", text="Nombre \u25b2\u25bc", command=lambda: sort_by("name"))
            tree.heading("horas_a", text=f"Hrs {vanity_a[0]} \u25b2\u25bc", command=lambda: sort_by("horas_a"))
            tree.heading("horas_b", text=f"Hrs {vanity_b[0]} \u25b2\u25bc", command=lambda: sort_by("horas_b"))
            tree.heading("afinidad", text="Afinidad \u25b2\u25bc", command=lambda: sort_by("afinidad"))
            tree.heading("tags", text="Tags (SteamSpy) \u25b2\u25bc", command=lambda: sort_by("tags"))

        tree.column("appid", width=90, anchor="center", stretch=False)
        tree.column("name", width=230, anchor="w")
        tree.column("horas_a", width=90, anchor="center", stretch=False)
        tree.column("horas_b", width=90, anchor="center", stretch=False)
        tree.column("afinidad", width=80, anchor="center", stretch=False)
        tree.column("tags", width=400, anchor="w")
        _update_tree_headers()

        tag_filter_var.trace_add("write", refresh_tree)

        # ── Compare ───────────────────────────────────────────────────────
        def compare() -> None:
            nonlocal shared_cache
            try:
                payload_a = get_payload_a()
                payload_b = get_payload_b()
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                messagebox.showerror("Error", f"No se pudo leer algun JSON: {exc}", parent=window)
                return

            if payload_a is None:
                messagebox.showwarning(
                    "Falta Librería A",
                    "Selecciona un archivo JSON o usa el botón 'Obtener librería' en modo SteamID.",
                    parent=window,
                )
                return
            if payload_b is None:
                messagebox.showwarning(
                    "Falta Librería B",
                    "Selecciona un archivo JSON o usa el botón 'Obtener librería' en modo SteamID.",
                    parent=window,
                )
                return

            vanity_a[0] = get_name_a()
            vanity_b[0] = get_name_b()
            _update_tree_headers()

            apps_a = self._extract_apps_from_payload(payload_a)
            apps_b = self._extract_apps_from_payload(payload_b)
            map_a = {app["appid"]: app for app in apps_a if app.get("appid")}
            map_b = {app["appid"]: app for app in apps_b if app.get("appid")}

            common_ids = set(map_a.keys()) & set(map_b.keys())
            ordered_ids = sorted(
                common_ids,
                key=lambda aid: (0, int(aid)) if aid.isdigit() else (1, aid),
            )
            playtime_a.clear()
            playtime_b.clear()
            for aid in common_ids:
                playtime_a[aid] = float(map_a[aid].get("playtime") or 0)
                playtime_b[aid] = float(map_b[aid].get("playtime") or 0)

            shared_cache = [
                {"appid": aid, "name": map_a[aid].get("name") or map_b[aid].get("name") or "Unknown"}
                for aid in ordered_ids
            ]
            tag_data.clear()
            tags_status_var.set("")
            refresh_tree()
            load_tags_button.config(state=tk.NORMAL)
            load_tags_file_button.config(state=tk.NORMAL)

        load_tags_button: ttk.Button
        load_tags_file_button: ttk.Button

        # ── Load tags (SteamSpy) ──────────────────────────────────────────
        def start_load_tags() -> None:
            if tag_loading[0] or not shared_cache:
                return
            tag_loading[0] = True
            load_tags_button.config(state=tk.DISABLED)
            appids = [g["appid"] for g in shared_cache]
            total = len(appids)
            api_key = normalize_string(self.api_key_var.get())
            client = SteamApiClient(api_key=api_key, timeout=15)

            def worker() -> None:
                cache: Dict[str, list] = {}
                try:
                    if _TAGS_CACHE_PATH.exists():
                        with open(_TAGS_CACHE_PATH, encoding="utf-8") as _f:
                            cache = json.load(_f)
                except Exception:
                    pass

                for aid in appids:
                    if aid in cache:
                        tag_data[aid] = cache[aid]

                to_fetch = [aid for aid in appids if aid not in tag_data]
                cached_count = total - len(to_fetch)

                if to_fetch:
                    window.after(0, lambda: tags_status_var.set(
                        f"Cache: {cached_count}/{total} \u2014 descargando {len(to_fetch)}..."
                    ))
                    window.after(0, refresh_tree)

                    def fetch_one(aid: str) -> tuple[str, list]:
                        try:
                            data = client.get_steamspy_app_details(aid)
                            tags_dict = data.get("tags") or {}
                            if isinstance(tags_dict, dict):
                                st = sorted(tags_dict.items(), key=lambda x: -int(x[1]))
                                return aid, [t[0] for t in st[:6]]
                        except Exception:
                            pass
                        return aid, []

                    done_count = cached_count
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {pool.submit(fetch_one, aid): aid for aid in to_fetch}
                        for future in as_completed(futures):
                            aid, tags = future.result()
                            tag_data[aid] = tags
                            cache[aid] = tags
                            done_count += 1
                            d = done_count
                            window.after(0, lambda d=d: tags_status_var.set(f"Cargando... {d}/{total}"))
                            window.after(0, refresh_tree)

                    try:
                        _TAGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        with open(_TAGS_CACHE_PATH, "w", encoding="utf-8") as _f:
                            json.dump(cache, _f, ensure_ascii=True)
                    except Exception:
                        pass
                else:
                    window.after(0, refresh_tree)

                fetched = len(to_fetch)
                tag_loading[0] = False
                window.after(0, lambda: tags_status_var.set(
                    f"Tags listos ({total} juegos \u2014 {total - fetched} de cache)"
                ))

            threading.Thread(target=worker, daemon=True).start()

        # ── Load tags from JSON ───────────────────────────────────────────
        def load_tags_from_json_file() -> None:
            path = filedialog.askopenfilename(
                title="Cargar tags desde JSON exportado",
                filetypes=[("JSON", "*.json")],
                parent=window,
            )
            if not path:
                return
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("Error", f"No se pudo leer el JSON: {exc}", parent=window)
                return
            loaded = 0
            if isinstance(data, dict):
                apps_list = data.get("common_apps") or []
                if isinstance(apps_list, list):
                    for entry in apps_list:
                        if isinstance(entry, dict):
                            aid = str(entry.get("appid", ""))
                            tags = entry.get("tags") or []
                            if aid and isinstance(tags, list):
                                tag_data[aid] = tags
                                loaded += 1
                else:
                    for aid, tags in data.items():
                        if isinstance(tags, list):
                            tag_data[aid] = tags
                            loaded += 1
            refresh_tree()
            tags_status_var.set(f"Tags cargados desde JSON: {loaded} juegos")

        # ── Save ─────────────────────────────────────────────────────────
        def save_comparison_json() -> None:
            if not shared_cache:
                messagebox.showwarning("Sin coincidencias", "Primero ejecuta la comparacion.", parent=window)
                return
            file_path = filedialog.asksaveasfilename(
                title="Guardar coincidencias",
                defaultextension=".json",
                initialfile="shared_common_games.json",
                filetypes=[("JSON", "*.json")],
                parent=window,
            )
            if not file_path:
                return
            export = [
                {
                    "appid": g["appid"],
                    "name": g["name"],
                    f"playtime_{vanity_a[0]}_min": int(playtime_a.get(g["appid"], 0)),
                    f"playtime_{vanity_b[0]}_min": int(playtime_b.get(g["appid"], 0)),
                    "afinidad_h": round(_harmonic_score(
                        playtime_a.get(g["appid"], 0.0), playtime_b.get(g["appid"], 0.0)
                    ), 2),
                    "tags": tag_data.get(g["appid"], []),
                }
                for g in shared_cache
            ]
            try:
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump({"common_apps": export}, fh, indent=2, ensure_ascii=True)
            except OSError as exc:
                messagebox.showerror("Error", f"No se pudo guardar: {exc}", parent=window)

        # ── Action bar ───────────────────────────────────────────────────
        actions = ttk.Frame(container)
        actions.grid(row=3, column=0, sticky="w", pady=(4, 2))
        ttk.Button(actions, text="Comparar", command=compare).pack(side=tk.LEFT)
        load_tags_button = ttk.Button(
            actions, text="Cargar tags (SteamSpy)", command=start_load_tags, state=tk.DISABLED,
        )
        load_tags_button.pack(side=tk.LEFT, padx=(8, 0))
        load_tags_file_button = ttk.Button(
            actions, text="Cargar tags desde JSON", command=load_tags_from_json_file, state=tk.DISABLED,
        )
        load_tags_file_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Guardar JSON", command=save_comparison_json).pack(side=tk.LEFT, padx=(8, 0))

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
        self.status_var.set(f"Family GroupID obtenido: {family_groupid}")

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
        self.status_var.set(f"Shared Library consultada ({len(apps)} juegos)")
        self._open_library_window(apps, steamid)

    def _save_shared_library_json(self) -> None:
        if not self.last_shared_library_payload or not self.last_shared_library_steamid:
            messagebox.showwarning(
                "Sin datos",
                "Primero consulta Shared Library antes de guardar.",
            )
            return

        vanity = normalize_string(self.vanity_url_var.get())
        filename_id = vanity or self.last_shared_library_steamid
        default_name = f"sharedlibrary_{filename_id}.json"
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

    def _clear_all(self) -> None:
        self.access_token_var.set("")
        self.family_groupid_var.set("")
        self.steamid_var.set("")
        self.vanity_url_var.set("")
        self.browser_response_text.delete("1.0", tk.END)
        self.last_shared_library_payload = None
        self.last_shared_library_steamid = None
        self.save_shared_button.config(state=tk.DISABLED)
        self.status_var.set("Listo")

    def _load_config(self) -> None:
        """Load non-sensitive settings from disk config, if present."""
        try:
            if _CONFIG_PATH.exists():
                with open(_CONFIG_PATH, encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    return
                if data.get("vanity_url"):
                    self.vanity_url_var.set(data["vanity_url"])
                if data.get("steamid"):
                    self.steamid_var.set(data["steamid"])
                if data.get("family_groupid"):
                    self.family_groupid_var.set(data["family_groupid"])
        except Exception:
            pass  # Corrupt or missing config — silently ignore.

    def _save_config(self) -> None:
        """Persist non-sensitive settings to disk config."""
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "vanity_url": normalize_string(self.vanity_url_var.get()),
                "steamid": normalize_string(self.steamid_var.get()),
                "family_groupid": normalize_string(self.family_groupid_var.get()),
            }
            with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=True)
        except Exception:
            pass  # Best-effort — never crash the UI over a config write.

    def _safe_timeout(self) -> int:
        return 30


def main() -> None:
    root = tk.Tk()
    app = SteamGuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
