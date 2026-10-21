"""tkinter GUI for synapseforge colors — replaces terminal color editor."""

from __future__ import annotations

import io
import json
import re
import sys
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Any, Dict, Optional
from pathlib import Path
import ctypes

_HERE = Path(__file__).resolve().parent
_ICO_PATH = _HERE / "logo.ico"
_LOGO_PNG_PATH = _HERE / "logo.png"   

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageTk = None

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

COLOR_FIELDS = [
    ("primary", "Color principal: botón de enviar, burbuja y avatar del asistente, barra de actividad, opción seleccionada del menú, enlaces de las respuestas y puntos de “escribiendo…”"),
    ("secondary", "Color de los detalles suaves: borde que se ilumina al hacer clic en un campo, anillo de la conversación seleccionada, bordes de las tarjetas y cursor de escritura"),
    ("primary_text", "Color del texto e íconos que van sobre el color principal: flecha de enviar, texto de botones, ícono del avatar y texto de la burbuja del asistente"),
    ("gradient_secondary", "Color final del degradé de los botones y del avatar del asistente (el inicio es el color principal)"),
]


# ──────────────────────────────────────────────────────────────
# Fijar el AppUserModelID ANTES de crear cualquier ventana
# ──────────────────────────────────────────────────────────────
def _set_app_user_model_id() -> None:
    """Set the Windows AppUserModelID so the taskbar shows the icon of the app."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "synapseforge.colors.1"
        )
    except Exception:
        pass

_set_app_user_model_id()


class ColorsApp:
    """GUI for editing runtime colors.json."""

    def __init__(self, colors_path: Path, current: Dict[str, str]) -> None:
        """Build the window of the colors editor.

        Args:
            colors_path: File where the colors are saved.
            current: Current value of each color.
        """
        self.colors_path = colors_path
        self.current = current
        self.result: Optional[Dict[str, str]] = None

        self.root = tk.Tk()
        self.root.title("synapseForge — Colors")
        self.root.resizable(False, False)

        # ── Configurar el ícono (con retraso para asegurar que la ventana esté lista) ──
        self.root.after(100, self._set_icon)

        # ── Logo header (desde archivo local) ────────────────────────
        self._load_logo_local()

        # ── Instruction ──────────────────────────────────────────────
        ttk.Label(
            self.root,
            text="Colores del proyecto (dejá vacío para mantener el actual):",
            font=("", 10, ""),
        ).pack(pady=(5, 10))

        # ── Color fields ─────────────────────────────────────────────
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self._entries: Dict[str, tk.Entry] = {}
        self._previews: Dict[str, tk.Canvas] = {}

        for i, (key, desc) in enumerate(COLOR_FIELDS):
            row = i * 2

            # Explanation (wraps so it doesn't push the selector out of view)
            ttk.Label(frame, text=desc, wraplength=430, justify="left").grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(8, 0), padx=(0, 10)
            )

            # Preview square (18×18)
            cv = tk.Canvas(frame, width=20, height=20, highlightthickness=1,
                           highlightbackground="#ccc")
            cv.grid(row=row + 1, column=0, pady=(4, 8), padx=(0, 6))
            self._previews[key] = cv

            # Entry with current value
            ent = ttk.Entry(frame, width=14)
            ent.grid(row=row + 1, column=1, pady=(4, 8), padx=(0, 6))
            cur_val = current.get(key, "")
            if cur_val:
                ent.insert(0, cur_val)
            ent.bind("<KeyRelease>", lambda _e, k=key: self._update_preview(k))
            self._entries[key] = ent

            # Color picker button
            ttk.Button(
                frame, text="Seleccionar", command=lambda k=key: self._pick_color(k)
            ).grid(row=row + 1, column=2, pady=(4, 8), padx=(0, 0), sticky="w")

            # Initial preview
            self._update_preview(key)

        # ── Gradient toggle ──────────────────────────────────────────
        gradient_frame = ttk.Frame(self.root)
        gradient_frame.pack(fill="x", padx=15, pady=(0, 5))

        grad_default = current.get("usar_gradiente", True)
        if isinstance(grad_default, str):
            grad_default = grad_default.lower() in ("true", "1", "yes")
        self._usar_gradiente_var = tk.BooleanVar(value=bool(grad_default))
        ttk.Checkbutton(
            gradient_frame,
            text="Usar degradé en botones y avatar",
            variable=self._usar_gradiente_var,
            command=self._toggle_gradient_fields,
        ).pack(anchor="w")

        self._toggle_gradient_fields()

        # ── Bottom buttons ───────────────────────────────────────────
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=15, pady=(0, 12))

        ttk.Button(bottom, text="Cancelar", command=self._on_cancel).pack(
            side="right", padx=(5, 0)
        )
        ttk.Button(bottom, text="Guardar", command=self._on_save).pack(side="right")

        # ── Center ───────────────────────────────────────────────────
        self._center(660, 800)

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
            lbl.pack(pady=(10, 2))
        except Exception:
            pass  # silencioso si falla

    # ------------------------------------------------------------------
    # Color helpers
    # ------------------------------------------------------------------
    def _pick_color(self, key: str) -> None:
        """Open OS color chooser, fill entry and update preview.

        Args:
            key: Name of the color being edited.
        """
        result = colorchooser.askcolor(
            title=key,
            color=self._entries[key].get() or None,
            parent=self.root,
        )
        if result and result[1]:
            self._entries[key].delete(0, tk.END)
            self._entries[key].insert(0, result[1])
            self._update_preview(key)

    def _update_preview(self, key: str) -> None:
        """Update the preview square for the given color key.

        Args:
            key: Name of the color being previewed.
        """
        cv = self._previews[key]
        raw = self._entries[key].get().strip()
        cv.delete("all")
        if raw and _HEX_RE.match(raw):
            cv.config(bg=raw)
        else:
            cv.config(bg="#ffffff")

    def _toggle_gradient_fields(self) -> None:
        """Enable/disable gradient_secondary picker based on checkbox."""
        state = "normal" if self._usar_gradiente_var.get() else "disabled"
        key = "gradient_secondary"
        if key in self._entries:
            self._entries[key].config(state=state)
        if key in self._previews:
            self._previews[key].config(highlightbackground="#ccc" if state == "normal" else "#eee")

    # ------------------------------------------------------------------
    # Save / Cancel
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        """Validate the colors, write them to the file and close the window."""
        updated: Dict[str, str] = {}
        errors: list[str] = []
        usar_gradiente = self._usar_gradiente_var.get()
        updated["usar_gradiente"] = str(usar_gradiente).lower()
        for key, _desc in COLOR_FIELDS:
            raw = self._entries[key].get().strip()
            if key == "gradient_secondary" and not usar_gradiente:
                # If gradient off, set same as primary so gradient looks solid
                updated[key] = updated.get("primary") or self.current.get("primary", "#000000")
                continue
            if not raw:
                updated[key] = self.current.get(key, "")
            elif _HEX_RE.match(raw):
                updated[key] = raw
            else:
                errors.append(f"'{key}': '{raw}' no es un color hex válido (#RRGGBB).")

        if errors:
            messagebox.showerror("Errores de validación",
                                 "\n".join(errors), parent=self.root)
            return

        # Write
        try:
            self.colors_path.write_text(
                json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.result = updated
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror("Error al guardar",
                                 f"No se pudo escribir colors.json:\n{exc}",
                                 parent=self.root)

    def _on_cancel(self) -> None:
        """Close the window without saving."""
        self.result = None
        self.root.destroy()

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
    def launch(project_dir: str) -> Optional[Dict[str, str]]:
        """Open the colors GUI and return the updated dict (or None if cancelled).

        Args:
            project_dir: Path to project root containing frontend/public/colors.json.

        Returns:
            Updated colors dict, or ``None`` if the user cancelled.
        """
        colors_path = Path(project_dir).resolve() / "frontend" / "public" / "colors.json"
        if not colors_path.is_file():
            print(f"ERROR: No se encontró {colors_path}", file=sys.stderr)
            sys.exit(1)

        try:
            current = json.loads(colors_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR leyendo colors.json: {exc}", file=sys.stderr)
            sys.exit(1)

        app = ColorsApp(colors_path, current)
        app.root.mainloop()
        return app.result