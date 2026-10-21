"""tkinter GUI for synapseforge init — replaces terminal get_user_input()."""

from __future__ import annotations

import io
import re
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Dict, Optional
from pathlib import Path
import ctypes
import sys

_HERE = Path(__file__).resolve().parent
_ICO_PATH = _HERE / "logo.ico"
_LOGO_PNG_PATH = _HERE / "logo.png"   

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageTk = None

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

COLOR_TAB_FIELDS = [
    ("primary", "Color principal: botón de enviar, burbuja y avatar del asistente, barra de actividad, opción seleccionada del menú, enlaces de las respuestas y puntos de “escribiendo…”"),
    ("secondary", "Color de los detalles suaves: borde que se ilumina al hacer clic en un campo, anillo de la conversación seleccionada, bordes de las tarjetas y cursor de escritura"),
    ("primary_text", "Color del texto e íconos que van sobre el color principal: flecha de enviar, texto de botones, ícono del avatar y texto de la burbuja del asistente"),
    ("gradient_secondary", "Color final del degradé de los botones y del avatar del asistente (el inicio es el color principal)"),
]

# ──────────────────────────────────────────────────────────────
# Tooltips for project tab fields (hover info, no layout impact)
# ──────────────────────────────────────────────────────────────
TOOLTIPS: dict[str, str] = {
    "empresa": "Nombre de la empresa que desarrolla el proyecto.",
    "owner": "Tu usuario de GitHub.",
    "legal": "Razón social o nombre legal de la empresa.",
    "repo": "Nombre del repositorio en GitHub.",
    "cliente": "Nombre del cliente para quien se hace el proyecto.",
    "nombre": "Nombre del agente.",
    "tarea": "Rubro o tipo de trabajo (ej: desarrollo web, data pipeline).",
}


def _create_tooltip(widget: tk.Widget, text: str) -> None:
    """Attach a hover tooltip to *widget* without affecting layout.

    Args:
        widget: Widget that shows the tooltip.
        text: Text of the tooltip.
    """
    _tip = {"window": None}

    def _show(event: tk.Event) -> None:
        """Show the tooltip near the pointer.

        Args:
            event: The enter event.
        """
        if _tip["window"]:
            return
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 5}")
        lbl = tk.Label(
            tw, text=text, justify="left",
            background="#ffffe0", relief="solid", borderwidth=1,
            font=("", 9), padx=6, pady=4, wraplength=350,
        )
        lbl.pack()
        _tip["window"] = tw

    def _hide(_event: tk.Event | None) -> None:
        """Hide the tooltip.

        Args:
            _event: The leave event (unused).
        """
        if _tip["window"]:
            _tip["window"].destroy()
            _tip["window"] = None

    widget.bind("<Enter>", _show)
    widget.bind("<Leave>", _hide)


# ──────────────────────────────────────────────────────────────
# Fijar el AppUserModelID ANTES de crear cualquier ventana
# ──────────────────────────────────────────────────────────────
def _set_app_user_model_id() -> None:
    """Set the Windows AppUserModelID so the taskbar shows the icon of the app."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "synapseforge.init.1"
        )
    except Exception:
        pass

_set_app_user_model_id()


class InitApp:
    """GUI for collecting project configuration for synapseforge init."""

    def __init__(self, target_dir: str) -> None:
        """Build the window of the init wizard.

        Args:
            target_dir: Directory where the project is created.
        """
        self.target_dir = target_dir
        self.result: Optional[Dict[str, Any]] = None

        # Crear la ventana
        self.root = tk.Tk()
        self.root.title("synapseForge — Init")
        self.root.resizable(False, False)

        # ── Configurar el ícono (con retraso para asegurar que la ventana esté lista) ──
        self.root.after(100, self._set_icon)

        # ── Logo header (desde archivo local) ────────────────────────
        self._load_logo_local()

        # ── Notebook (tabs) ──────────────────────────────────────────
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._build_project_tab()
        self._build_logos_tab()
        self._build_colors_tab()

        # ── Bottom frame (progress + buttons) ────────────────────────
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=400)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_cancel = ttk.Button(bottom, text="Cancelar", command=self._on_cancel)
        self.btn_cancel.pack(side="right", padx=(5, 0))

        self.btn_submit = ttk.Button(bottom, text="Crear Proyecto", command=self._on_submit)
        self.btn_submit.pack(side="right")

        # ── Center window ────────────────────────────────────────────
        self._center(640, 800)

    # ──────────────────────────────────────────────────────────────────
    # Configuración robusta del ícono usando ctypes
    # ──────────────────────────────────────────────────────────────────
    def _set_icon(self) -> None:
        """Set the icon of the window and of the taskbar using ctypes."""
        if not _ICO_PATH.is_file():
            return

        try:
            # 1. iconbitmap (funciona para la ventana)
            self.root.iconbitmap(str(_ICO_PATH.resolve()))

            # 2. Forzar actualización de la barra de tareas con ctypes
            hwnd = self.root.winfo_id()
            user32 = ctypes.windll.user32
            # Cargar el ícono desde el archivo
            hicon = user32.LoadImageW(
                0,
                str(_ICO_PATH.resolve()),
                1,  # IMAGE_ICON
                0, 0,
                0x00000010  # LR_LOADFROMFILE
            )
            if hicon:
                # GCL_HICON = -14, GCL_HICONSM = -34
                user32.SetClassLongW(hwnd, -14, hicon)
                user32.SetClassLongW(hwnd, -34, hicon)
                # WM_SETICON = 0x0080, ICON_BIG = 0, ICON_SMALL = 1
                user32.SendMessageW(hwnd, 0x0080, 0, hicon)
                user32.SendMessageW(hwnd, 0x0080, 1, hicon)

        except Exception:
            pass  # Silencioso si falla

    # ------------------------------------------------------------------
    # Logo (cargado desde archivo local)
    # ------------------------------------------------------------------
    def _load_logo_local(self) -> None:
        """Load the logo from logo_transparente.png (local) and show it in the window."""
        if Image is None or ImageTk is None:
            return
        if not _LOGO_PNG_PATH.is_file():
            return
        try:
            pil = Image.open(_LOGO_PNG_PATH)
            pil.thumbnail((150, 150), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(pil)
            lbl = tk.Label(self.root, image=self._logo_img)
            lbl.pack(pady=(10, 5))
        except Exception:
            pass  # silencioso si falla

    # ------------------------------------------------------------------
    # Tab 1: Project info
    # ------------------------------------------------------------------
    def _build_project_tab(self) -> None:
        """Build the tab with the name and the data of the project."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="Proyecto")

        fields: list[tuple[str, str, bool]] = [
            ("empresa", "Nombre de la empresa desarrolladora", True),
            ("owner", "Owner del repo (usuario de GitHub)", True),
            ("legal", "Nombre legal / razón social", True),
            ("repo", "Nombre del repo", True),
            ("cliente", "Nombre del cliente", True),
            ("nombre", "Nombre", True),
            ("tarea", "Nombre de la tarea / rubro", True),
        ]

        self._entries: Dict[str, tk.Entry] = {}
        for i, (key, label, required) in enumerate(fields):
            lbl_text = label + " *" if required else label
            lbl = ttk.Label(tab, text=lbl_text)
            lbl.grid(row=i, column=0, sticky="w", pady=3, padx=(0, 10))
            ent = ttk.Entry(tab, width=55)
            ent.grid(row=i, column=1, pady=3)
            self._entries[key] = ent
            # Attach hover tooltip if available
            if key in TOOLTIPS:
                _create_tooltip(ent, TOOLTIPS[key])

    # ------------------------------------------------------------------
    # Tab 2: Logos (file pickers)
    # ------------------------------------------------------------------
    def _build_logos_tab(self) -> None:
        """Build the tab where the logos are chosen."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="Logos")

        # ── Logo empresa (required) ──────────────────────────────────
        ttk.Label(tab, text="Logo de la empresa (para README) *").grid(
            row=0, column=0, sticky="w", pady=3
        )
        self._logo_path_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self._logo_path_var, width=50).grid(
            row=0, column=1, padx=(0, 5), pady=3
        )
        ttk.Button(tab, text="Examinar…", command=self._browse_logo).grid(
            row=0, column=2, pady=3
        )

        # ── Logo cliente (optional) ──────────────────────────────────
        ttk.Label(tab, text="Logo del cliente (para la app)").grid(
            row=1, column=0, sticky="w", pady=(15, 3)
        )
        self._logo_cliente_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self._logo_cliente_var, width=50).grid(
            row=1, column=1, padx=(0, 5), pady=(15, 3)
        )
        ttk.Button(tab, text="Examinar…", command=self._browse_logo_cliente).grid(
            row=1, column=2, pady=(15, 3)
        )

    def _browse_logo(self) -> None:
        """Choose the company logo with a file dialog."""
        path = filedialog.askopenfilename(
            title="Seleccionar logo de la empresa",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")],
        )
        if path:
            self._logo_path_var.set(path)

    def _browse_logo_cliente(self) -> None:
        """Choose the client logo with a file dialog."""
        path = filedialog.askopenfilename(
            title="Seleccionar logo del cliente",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")],
        )
        if path:
            self._logo_cliente_var.set(path)

    # ------------------------------------------------------------------
    # Tab 3: Colors (optional hex fields with color picker)
    # ------------------------------------------------------------------
    def _build_colors_tab(self) -> None:
        """Build the tab where the colors are chosen."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="Colores")

        ttk.Label(
            tab,
            text="Colores del proyecto (obligatorios):",
            font=("", 10, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        self._color_entries: Dict[str, tk.Entry] = {}
        self._color_previews: Dict[str, tk.Canvas] = {}

        for i, (key, desc) in enumerate(COLOR_TAB_FIELDS, start=1):
            row = i * 2

            # Explanation (wraps so it doesn't push the selector out of view)
            ttk.Label(tab, text=desc, wraplength=420, justify="left").grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(6, 0), padx=(0, 8)
            )

            # Preview square (16×16)
            cv = tk.Canvas(tab, width=18, height=18, highlightthickness=1,
                           highlightbackground="#ccc")
            cv.grid(row=row + 1, column=0, pady=(4, 6), padx=(0, 4))
            self._color_previews[key] = cv

            ent = ttk.Entry(tab, width=12)
            ent.grid(row=row + 1, column=1, pady=(4, 6), padx=(0, 4))
            self._color_entries[key] = ent

            # Bind entry change → update preview
            ent.bind("<KeyRelease>", lambda _e, k=key: self._update_preview(k))

            ttk.Button(tab, text="Seleccionar", command=lambda k=key: self._pick_color(k)).grid(
                row=row + 1, column=2, pady=(4, 6), sticky="w"
            )

        # ── Gradient toggle ──────────────────────────────────────────
        self._usar_gradiente_var = tk.BooleanVar(value=True)
        cb = ttk.Checkbutton(
            tab,
            text="Usar degradé en botones y avatar",
            variable=self._usar_gradiente_var,
            command=self._toggle_gradient_fields,
        )
        cb.grid(row=len(COLOR_TAB_FIELDS) * 2 + 2, column=0, columnspan=4, sticky="w", pady=(12, 0))

        ttk.Label(
            tab,
            text="Si lo desactivás, botones y avatar usan el color principal liso.",
            font=("", 8, "italic"),
            foreground="#888",
        ).grid(row=len(COLOR_TAB_FIELDS) * 2 + 3, column=0, columnspan=4, sticky="w")

    def _pick_color(self, key: str) -> None:
        """Open OS color chooser, fill entry and update preview.

        Args:
            key: Name of the color being edited.
        """
        result = colorchooser.askcolor(
            title=key,
            parent=self.root,
        )
        if result and result[1]:  # result is ((R,G,B), "#RRGGBB")
            hex_val = result[1]
            self._color_entries[key].delete(0, tk.END)
            self._color_entries[key].insert(0, hex_val)
            self._update_preview(key)

    def _update_preview(self, key: str) -> None:
        """Update the preview square for the given color key.

        Args:
            key: Name of the color being previewed.
        """
        cv = self._color_previews[key]
        raw = self._color_entries[key].get().strip()
        cv.delete("all")
        if raw and _HEX_RE.match(raw):
            cv.config(bg=raw)
        else:
            cv.config(bg="#ffffff")

    def _toggle_gradient_fields(self) -> None:
        """Enable/disable gradient_secondary picker based on checkbox."""
        state = "normal" if self._usar_gradiente_var.get() else "disabled"
        key = "gradient_secondary"
        if key in self._color_entries:
            self._color_entries[key].config(state=state)
        if key in self._color_previews:
            self._color_previews[key].config(highlightbackground="#ccc" if state == "normal" else "#eee")

    # ------------------------------------------------------------------
    # Collect + validate
    # ------------------------------------------------------------------
    def _collect_config(self) -> Optional[Dict[str, Any]]:
        """Read all fields and validate them.

        Returns:
            The config dict, or None if validation fails.
        """

        # ── Required text fields ──────────────────────────────────────
        required = ["empresa", "owner", "legal", "repo", "cliente", "nombre", "tarea"]
        config: Dict[str, Any] = {}
        for key in required:
            val = self._entries[key].get().strip()
            if not val:
                messagebox.showwarning("Campo requerido",
                                       f"'{key}' es obligatorio.", parent=self.root)
                return None
            config[key] = val

        # ── Logo empresa ──────────────────────────────────────────────
        logo_path = self._logo_path_var.get().strip()
        if not logo_path:
            messagebox.showwarning("Campo requerido",
                                   "El logo de la empresa es obligatorio.", parent=self.root)
            return None
        from pathlib import Path
        logo_resolved = Path(logo_path).resolve()
        if not logo_resolved.is_file():
            messagebox.showwarning("Archivo no encontrado",
                                   f"No se encontró: {logo_resolved}", parent=self.root)
            return None

        config["logo"] = {
            "path": str(logo_resolved),
        }

        # ── Logo cliente ──────────────────────────────────────────────
        logo_cliente = self._logo_cliente_var.get().strip()
        config["logo_cliente"] = logo_cliente or None

        # ── Colors (required) ─────────────────────────────────────────
        colors: Dict[str, str] = {}
        usar_gradiente = self._usar_gradiente_var.get()
        colors["usar_gradiente"] = usar_gradiente
        for key, _desc in COLOR_TAB_FIELDS:
            # Skip gradient_secondary if gradient toggle is off
            if key == "gradient_secondary" and not usar_gradiente:
                colors[key] = colors.get("primary", "#000000")
                continue
            val = self._color_entries[key].get().strip()
            if not val:
                messagebox.showwarning(
                    "Color requerido",
                    f"'{_desc}' es obligatorio.",
                    parent=self.root,
                )
                return None
            if not _HEX_RE.match(val):
                messagebox.showwarning(
                    "Color inválido",
                    f"{key}: '{val}' no es un color hex válido (#RRGGBB).",
                    parent=self.root,
                )
                return None
            colors[key] = val
        config["colors"] = colors

        return config

    def _on_submit(self) -> None:
        """Validate the form and start the pipeline in a background thread."""
        config = self._collect_config()
        if config is None:
            return  # validation failed

        # Disable UI and start progress
        self._set_ui_enabled(False)
        self.progress.start(15)

        # Run pipeline in daemon thread
        t = threading.Thread(target=self._run_pipeline, args=(config,), daemon=True)
        t.start()

    def _run_pipeline(self, config: Dict[str, Any]) -> None:
        """Execute init pipeline in background thread.

        Args:
            config: The configuration collected from the form.
        """
        try:
            from pipeline.init.main import run
            run(self.target_dir, config=config)
            self.result = config
            self.root.after(0, self._on_success)
        except Exception as exc:
            # Bind the message now: ``exc`` is deleted when the except block
            # exits, before the deferred callback runs.
            msg = str(exc)
            self.root.after(0, lambda: self._on_error(msg))

    def _on_success(self) -> None:
        """Tell the user the project was created and close the window."""
        self.progress.stop()
        self.root.destroy()

    def _on_error(self, msg: str) -> None:
        """Show the error of the pipeline and enable the form again.

        Args:
            msg: Description of the error.
        """
        self.progress.stop()
        messagebox.showerror("Error", msg, parent=self.root)
        self._set_ui_enabled(True)

    def _on_cancel(self) -> None:
        """Close the window without creating the project."""
        self.result = None
        self.root.destroy()

    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enable or disable the form controls while the pipeline runs.

        Args:
            enabled: True to enable them.
        """
        state = "normal" if enabled else "disabled"
        self.btn_submit.config(state=state)
        self.btn_cancel.config(state=state)
        for ent in self._entries.values():
            ent.config(state=state)
        # notebooks aren't easily disabled, skip for UX

    # ------------------------------------------------------------------
    # Window utils
    # ------------------------------------------------------------------
    def _center(self, w: int, h: int) -> None:
        """Center the window on the screen.

        Args:
            w: Width of the window.
            h: Height of the window.
        """
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    @staticmethod
    def launch(target_dir: str) -> Optional[Dict[str, Any]]:
        """Open the init GUI and return the config dict (or None if cancelled).

        Args:
            target_dir: Absolute path to the target project directory.

        Returns:
            Config dictionary matching ``input_handler.get_user_input()``
            format, or ``None`` if the user cancelled.
        """
        app = InitApp(target_dir)
        app.root.mainloop()
        return app.result