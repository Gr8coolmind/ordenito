#!/usr/bin/env python3
"""Ordenito (app): la ventana para ordenar, revisar, corregir y configurar tus carpetas.

Usa el mismo motor que el comando 'ordenito'. Requiere Tkinter (viene con Python;
en algunas distribuciones se instala aparte: python3-tk / python3-tkinter / brew python-tk).
"""
import gc
import importlib.machinery
import importlib.util
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, font, messagebox, ttk
except ImportError:
    sys.exit("La app necesita Tkinter. Instálalo con: python3-tk (Ubuntu/Debian), "
             "python3-tkinter (Fedora), 'brew install python-tk' (Mac/Homebrew) o, en Windows, "
             "reinstalando Python desde python.org con la opción 'tcl/tk and IDLE' marcada.")


def _cargar_motor():
    """Carga ordenito.py (o el comando 'ordenito' instalado) que está junto a esta app."""
    aqui = Path(__file__).resolve().parent
    for nombre in ("ordenito.py", "ordenito"):
        ruta = aqui / nombre
        if ruta.is_file():
            cargador = importlib.machinery.SourceFileLoader("ordenito", str(ruta))
            modulo = importlib.util.module_from_spec(importlib.util.spec_from_loader("ordenito", cargador))
            sys.modules["ordenito"] = modulo  # dataclasses lo necesita registrado
            cargador.exec_module(modulo)
            return modulo
    sys.exit("No encuentro ordenito.py junto a la app.")


o = _cargar_motor()


def preparar_windows():
    """Antes de abrir la ventana: letras nítidas en pantallas con escala (125 %, 150 %…) y el ícono
    de Ordenito en la barra de tareas (si no, Windows la agrupa con el de Python)."""
    if not o.WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(o.APP_ID)
    except (OSError, AttributeError):
        pass


# ───────────────────────────── colores ─────────────────────────────

CLARO = dict(fondo="#f6f7fb", superficie="#ffffff", texto="#111827", suave="#5b6474", borde="#d1d5db",
             acento="#2563eb", acento_activo="#1d4ed8", acento_apagado="#93c5fd", texto_acento="#ffffff",
             par="#f9fafb", apagado="#9ca3af", seleccion="#dbeafe", control="#e5e7eb", control_activo="#d1d5db")
OSCURO = dict(fondo="#15171c", superficie="#1e2128", texto="#e6e8ec", suave="#9aa3b2", borde="#3a3f4b",
              acento="#3b82f6", acento_activo="#60a5fa", acento_apagado="#1e3a8a", texto_acento="#ffffff",
              par="#22262e", apagado="#6b7280", seleccion="#1d3a63", control="#2a2e37", control_activo="#353a45")
C = dict(CLARO)   # la paleta en uso: se cambia en su lugar para que todo la vea


def sistema_oscuro():
    """¿El sistema está en modo oscuro? (Windows, macOS o GNOME/KDE)"""
    try:
        if o.WINDOWS:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        if o.MAC:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True,
                               text=True, timeout=3)
            return "dark" in r.stdout.lower()
        r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                           capture_output=True, text=True, timeout=3)
        return "dark" in r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def preferencias():
    return o._json("app.json", {})


def guardar_preferencia(clave, valor):
    datos = preferencias()
    datos[clave] = valor
    o._guardar_json("app.json", datos)


def tema_elegido():
    """'claro' u 'oscuro' según lo que eligió la persona (o el sistema, si eligió 'sistema')."""
    tema = preferencias().get("tema", "sistema")
    if tema == "sistema":
        return "oscuro" if sistema_oscuro() else "claro"
    return tema


def barra_de_titulo(ventana, oscura):
    """En Windows 10/11 la barra de título es del sistema: se le pide que siga el tema."""
    if not o.WINDOWS:
        return
    try:
        import ctypes
        ventana.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(ventana.winfo_id()) or ventana.winfo_id()
        valor = ctypes.c_int(1 if oscura else 0)
        for atributo in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (y su número viejo)
            if not ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(valor),
                                                              ctypes.sizeof(valor)):
                break
    except (OSError, AttributeError, tk.TclError):
        pass


# ─────────────────────── carpetas recomendadas ───────────────────────
# (título, descripción, [(destino, fuertes, palabras, extensiones)])

VIDEOS = "Movies" if o.MAC else "Videos"

CATEGORIAS = [
    ("Cursos en línea", "Certificados y materiales de Coursera, Udemy, Platzi…", [
        ("Documents/Cursos", ["coursera", "udemy", "platzi", "edx", "linkedin learning"],
         ["certificado", "certificate", "course certificate"], [])]),
    ("Finanzas", "Facturas, recibos, comprobantes y estados de cuenta", [
        ("Documents/Personal/Finanzas", [], ["factura", "recibo", "comprobante de pago",
         "comprobante de transferencia", "estado de cuenta", "invoice", "receipt", "paypal", "impuesto"], [])]),
    ("Documentos de identidad", "Cédula, pasaporte, actas, licencia", [
        ("Documents/Personal/Identidad", [], ["cedula", "pasaporte", "passport", "acta de nacimiento",
         "licencia de conducir", "dni", "curp"], [])]),
    ("CV y cartas", "Currículum, cartas de presentación y recomendación", [
        ("Documents/Personal/CV", [], ["curriculum", "curriculum vitae", "cv", "hoja de vida",
         "carta de presentacion", "cover letter", "carta de recomendacion"], [])]),
    ("Salud", "Recetas, análisis de laboratorio, seguro médico", [
        ("Documents/Personal/Salud", [], ["receta medica", "laboratorio clinico", "analisis clinico",
         "resultados de laboratorio", "cita medica", "seguro medico"], [])]),
    ("Trading", "Indicadores de TradingView y análisis de mercados", [
        ("Documents/Trading", [], ["tradingview", "pine script", "smart money", "order block",
         "fair value gap", "forex", "xauusd", "nasdaq", "backtest", "prop firm", "analisis tecnico", "trading"], []),
        ("Documents/Trading/Indicadores", [], ["@version=5", "@version=6", "indicator(", "strategy("],
         ["pine", "ts", "txt"])]),
    ("Manuales", "Manuales de usuario y garantías", [
        ("Documents/Manuales", [], ["manual de usuario", "user manual", "user guide", "quick start guide",
         "datasheet", "garantia", "warranty"], [])]),
    ("Fondos de pantalla y capturas", "Wallpapers 4K y capturas de pantalla", [
        ("Pictures/Wallpapers", [], ["wallpaper", "wallpapers", "fondo de pantalla", "3840x2160",
         "2560x1440", "1920x1080", "4k"], ["jpg", "jpeg", "png", "webp"]),
        ("Pictures/Screenshots", [], ["screenshot", "captura de pantalla", "screen shot"],
         ["png", "jpg", "jpeg", "webp"])]),
    ("Fotos, videos y música", "Por tipo de archivo, si no encajan en otro tema", [
        ("Pictures/Descargadas", [], [], ["jpg", "jpeg", "png", "gif", "webp", "svg", "heic", "avif"]),
        (VIDEOS, [], [], ["mp4", "mkv", "webm", "mov", "avi", "m4v", "srt"]),
        ("Music", [], [], ["mp3", "flac", "ogg", "wav", "m4a", "opus", "aac"])]),
    ("Libros y diseño", "Ebooks, archivos de diseño, fuentes y modelos 3D", [
        ("Documents/Libros", [], [], ["epub", "mobi", "azw3", "djvu", "cbz", "cbr"]),
        ("Documents/Diseno", [], [], ["psd", "ai", "xcf", "fig", "xd", "sketch", "afdesign", "kra", "eps"]),
        ("Documents/Diseno/Fuentes", [], [], ["ttf", "otf", "woff", "woff2"]),
        ("Documents/3D", [], [], ["stl", "obj", "blend", "3mf", "fbx", "gcode"])]),
    ("Instaladores", "Programas, imágenes ISO y torrents (se quedan dentro de Descargas)", [
        ("Downloads/Instaladores", [], [], ["appimage", "rpm", "deb", "flatpakref", "exe", "msi", "msix", "apk",
                                            "dmg", "pkg"]),
        ("Downloads/ISOs", [], [], ["iso", "img"]),
        ("Downloads/Torrents", [], [], ["torrent"])]),
]

UNIVERSIDAD_FIJOS = [
    ("Documents/Universidad/Administrativo", [], ["seleccion de asignaturas", "calendario academico",
     "historial academico", "record de notas", "carta de admision", "pensum", "horario de clases"], []),
    ("*/Proyecto Final", [], ["proyecto final", "final project", "entrega final", "trabajo final",
                              "capstone", "portafolio"], []),
]


def lista(texto):
    """'a, b,c' -> ['a', 'b', 'c']"""
    return [p.strip() for p in texto.replace("\n", ",").split(",") if p.strip()]


def hora(iso):
    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    hoy = datetime.now().date()
    if momento.date() == hoy:
        return "hoy " + momento.strftime("%H:%M")
    return momento.strftime("%d/%m %H:%M")


# ───────────────────────────── ventanas auxiliares ─────────────────────────────

class Dialogo(tk.Toplevel):
    """Ventana modal centrada sobre la principal."""

    def __init__(self, padre, titulo, desplazable=False):
        super().__init__(padre)
        self.title(titulo)
        self.configure(bg=C["fondo"])
        self.transient(padre)
        self.resultado = None
        self.desplazable = desplazable
        if not desplazable:
            self.cuerpo = ttk.Frame(self, padding=18)
            self.cuerpo.pack(fill="both", expand=True)
            self.botones = self.cuerpo
            return
        # Botones siempre visibles abajo; el contenido se desplaza si no cabe en la pantalla
        self.botones = ttk.Frame(self, padding=(18, 10, 18, 14))
        self.botones.pack(side="bottom", fill="x")
        ttk.Separator(self).pack(side="bottom", fill="x")
        self.lienzo = tk.Canvas(self, bg=C["fondo"], highlightthickness=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.lienzo.yview)
        self.lienzo.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.cuerpo = ttk.Frame(self.lienzo, padding=18)
        self.lienzo.create_window((0, 0), window=self.cuerpo, anchor="nw")
        self.cuerpo.bind("<Configure>", lambda e: self.lienzo.configure(scrollregion=self.lienzo.bbox("all")))
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(evento, self._rueda, add="+")

    def _rueda(self, evento):
        if not self.desplazable or not self.winfo_exists():
            return
        paso = -1 if getattr(evento, "num", 0) == 4 or getattr(evento, "delta", 0) > 0 else 1
        self.lienzo.yview_scroll(paso, "units")

    def mostrar(self):
        self.update_idletasks()
        if self.desplazable:
            ancho = self.cuerpo.winfo_reqwidth() + 20
            alto = min(self.cuerpo.winfo_reqheight() + self.botones.winfo_reqheight() + 4,
                       int(self.winfo_screenheight() * 0.85))
            self.geometry(f"{ancho}x{alto}")
            self.update_idletasks()
        padre = self.master
        x = padre.winfo_rootx() + (padre.winfo_width() - self.winfo_width()) // 2
        y = padre.winfo_rooty() + (padre.winfo_height() - self.winfo_height()) // 3
        if self.desplazable:  # que quepa entera en la pantalla
            y = min(max(y, 0), max(self.winfo_screenheight() - self.winfo_height() - 40, 0))
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        barra_de_titulo(self, C == OSCURO)
        self.grab_set()
        self.wait_window()
        return self.resultado


class Explicacion(Dialogo):
    def __init__(self, padre, archivo):
        super().__init__(padre, "¿Por qué va ahí?")
        res = o.clasificar(archivo, o.leer_reglas())
        ttk.Label(self.cuerpo, text=archivo.name, style="Titulo.TLabel").pack(anchor="w")
        destino = o.bonito(o.ruta_destino(res.destino)) if res.destino else "Se queda en Descargas"
        ttk.Label(self.cuerpo, text=f"→ {destino}", style="Destino.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(self.cuerpo, text=res.motivo, style="Suave.TLabel").pack(anchor="w", pady=(0, 10))
        arbol = ttk.Treeview(self.cuerpo, columns=("pts", "carpeta", "pistas"), show="headings", height=8)
        for col, texto, ancho in (("pts", "Puntos", 60), ("carpeta", "Carpeta", 300), ("pistas", "Pistas encontradas", 380)):
            arbol.heading(col, text=texto)
            arbol.column(col, width=ancho, anchor="e" if col == "pts" else "w")
        for destino_r, (puntos, pistas) in sorted(res.tabla.items(), key=lambda x: -x[1][0]):
            arbol.insert("", "end", values=(puntos, destino_r, ", ".join(pistas)))
        if not res.tabla:
            arbol.insert("", "end", values=("", "Ninguna palabra clave coincidió", ""))
        arbol.pack(fill="both", expand=True)
        ttk.Label(self.cuerpo, style="Suave.TLabel", wraplength=720, justify="left",
                  text="★ = pista fuerte (profesor, código, empresa) en el nombre, autor, encabezado o portada. "
                       "Las demás suman 1 punto por aparición en el contenido o 10 si están en el nombre.").pack(
            anchor="w", pady=(10, 0))
        ttk.Button(self.cuerpo, text="Cerrar", command=self.destroy).pack(anchor="e", pady=(12, 0))


class Aprender(Dialogo):
    """Después de corregir: elegir qué pistas aprender para esa carpeta."""

    def __init__(self, padre, archivo, destino, sugeridas):
        super().__init__(padre, "Aprender de la corrección")
        ttk.Label(self.cuerpo, text=f"{archivo.name}", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self.cuerpo, text=f"ahora está en ~/{destino}", style="Suave.TLabel").pack(anchor="w")
        ttk.Label(self.cuerpo, wraplength=460, justify="left",
                  text="Para que la próxima vez vaya solo ahí, marca las pistas que identifican a esa "
                       "carpeta (profesor, código de la materia, empresa…):").pack(anchor="w", pady=(12, 6))
        self.marcas = []
        for p in sugeridas:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(self.cuerpo, text=p, variable=var).pack(anchor="w", padx=8)
            self.marcas.append((p, var))
        if not sugeridas:
            ttk.Label(self.cuerpo, text="No encontré autor, código ni docente en el archivo.",
                      style="Suave.TLabel").pack(anchor="w", padx=8)
        ttk.Label(self.cuerpo, text="Otra pista (opcional, separadas por coma):").pack(anchor="w", pady=(12, 2))
        self.extra = ttk.Entry(self.cuerpo, width=50)
        self.extra.pack(fill="x")
        botones = ttk.Frame(self.cuerpo)
        botones.pack(fill="x", pady=(14, 0))
        ttk.Button(botones, text="Aprender", style="Acento.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Solo mover", command=self.destroy).pack(side="right", padx=8)

    def aceptar(self):
        self.resultado = [p for p, v in self.marcas if v.get()] + lista(self.extra.get())
        self.destroy()


class EditorRegla(Dialogo):
    def __init__(self, padre, regla=None):
        super().__init__(padre, "Editar carpeta" if regla else "Nueva carpeta")
        self.anterior = regla.destino if regla else None
        campos = ttk.Frame(self.cuerpo)
        campos.pack(fill="both", expand=True)
        campos.columnconfigure(1, weight=1)

        ttk.Label(campos, text="Carpeta").grid(row=0, column=0, sticky="w", pady=4)
        fila = ttk.Frame(campos)
        fila.grid(row=0, column=1, sticky="ew", pady=4)
        self.destino = ttk.Entry(fila, width=48)
        self.destino.pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Elegir…", command=self.elegir).pack(side="left", padx=(6, 0))
        ttk.Label(campos, text="Relativa a tu carpeta personal, ej. Documents/Universidad/Redes",
                  style="Suave.TLabel").grid(row=1, column=1, sticky="w")

        ttk.Label(campos, text="Pistas fuertes").grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.fuertes = ttk.Entry(campos)
        self.fuertes.grid(row=2, column=1, sticky="ew", pady=(12, 4))
        ttk.Label(campos, text="Lo que identifica al dueño: profesor, código de la materia, empresa, cliente.",
                  style="Suave.TLabel").grid(row=3, column=1, sticky="w")

        ttk.Label(campos, text="Palabras del tema").grid(row=4, column=0, sticky="nw", pady=(12, 4))
        self.palabras = tk.Text(campos, height=4, width=50, wrap="word", relief="flat", borderwidth=0,
                                font="TkDefaultFont", bg=C["superficie"], fg=C["texto"],
                                insertbackground=C["texto"], selectbackground=C["seleccion"],
                                selectforeground=C["texto"], highlightthickness=1,
                                highlightbackground=C["borde"], highlightcolor=C["acento"], padx=6, pady=4)
        self.palabras.grid(row=4, column=1, sticky="ew", pady=(12, 4))
        ttk.Label(campos, text="Separadas por coma. Cada aparición en el contenido suma 1 punto.",
                  style="Suave.TLabel").grid(row=5, column=1, sticky="w")

        ttk.Label(campos, text="Tipos de archivo").grid(row=6, column=0, sticky="w", pady=(12, 4))
        self.extensiones = ttk.Entry(campos)
        self.extensiones.grid(row=6, column=1, sticky="ew", pady=(12, 4))
        ttk.Label(campos, text="Opcional, ej. pdf, docx. Si dejas vacías las pistas y palabras, "
                               "la carpeta recibe todo archivo de esos tipos.",
                  style="Suave.TLabel", wraplength=440, justify="left").grid(row=7, column=1, sticky="w")

        if regla:
            self.destino.insert(0, regla.destino)
            self.fuertes.insert(0, ", ".join(regla.fuertes_texto or regla.fuertes))
            self.palabras.insert("1.0", ", ".join(regla.palabras_texto or regla.palabras))
            self.extensiones.insert(0, ", ".join(e.lstrip(".") for e in sorted(regla.extensiones)))

        botones = ttk.Frame(self.cuerpo)
        botones.pack(fill="x", pady=(16, 0))
        ttk.Button(botones, text="Guardar", style="Acento.TButton", command=self.guardar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=8)

    def elegir(self):
        ruta = filedialog.askdirectory(parent=self, initialdir=str(o.HOME / "Documents"), mustexist=False)
        if ruta:
            self.destino.delete(0, "end")
            self.destino.insert(0, o.destino_de(ruta))

    def guardar(self):
        destino = self.destino.get().strip().strip("/")
        fuertes, palabras = lista(self.fuertes.get()), lista(self.palabras.get("1.0", "end"))
        extensiones = [e.lstrip(".") for e in lista(self.extensiones.get())]
        if not destino:
            messagebox.showwarning("Falta la carpeta", "Escribe o elige la carpeta destino.", parent=self)
            return
        if not (fuertes or palabras or extensiones):
            messagebox.showwarning("Faltan pistas", "Agrega al menos una pista, palabra o tipo de archivo.",
                                   parent=self)
            return
        o.guardar_bloque(destino, fuertes, palabras, extensiones, anterior=self.anterior)
        if not destino.startswith("*/"):
            o.ruta_destino(destino).mkdir(parents=True, exist_ok=True)
        self.resultado = destino
        self.destroy()


class Asistente(Dialogo):
    """Carpetas recomendadas: se marcan categorías y se escriben las materias."""

    def __init__(self, padre, primera_vez=False):
        super().__init__(padre, "Carpetas recomendadas", desplazable=True)
        ttk.Label(self.cuerpo, text="¡Hola! Vamos a armar tus carpetas" if primera_vez else "Carpetas recomendadas",
                  style="Grande.TLabel").pack(anchor="w")
        ttk.Label(self.cuerpo, style="Suave.TLabel", wraplength=820, justify="left",
                  text="Marca lo que quieres ordenar. Ordenito creará las carpetas y las reglas; después "
                       "puedes cambiarlas cuando quieras en la pestaña Carpetas.").pack(anchor="w", pady=(2, 12))

        rejilla = ttk.Frame(self.cuerpo)
        rejilla.pack(fill="x")
        self.marcas = []
        for i, (titulo, descripcion, bloques) in enumerate(CATEGORIAS):
            var = tk.BooleanVar(value=True)
            celda = ttk.Frame(rejilla)
            celda.grid(row=i // 3, column=i % 3, sticky="nw", padx=(0, 18), pady=3)
            ttk.Checkbutton(celda, text=titulo, variable=var, style="Negrita.TCheckbutton").pack(anchor="w")
            ttk.Label(celda, text=descripcion, style="Suave.TLabel", wraplength=250,
                      justify="left").pack(anchor="w", padx=(24, 0))
            self.marcas.append((var, bloques))

        ttk.Separator(self.cuerpo).pack(fill="x", pady=14)
        self.uni = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.cuerpo, text="Universidad o colegio: una carpeta por materia", variable=self.uni,
                        style="Negrita.TCheckbutton").pack(anchor="w")
        ttk.Label(self.cuerpo, style="Suave.TLabel", wraplength=760, justify="left",
                  text="El profesor y el código son las mejores pistas: casi siempre salen en la portada o el "
                       "encabezado de las tareas. Puedes dejar alguno vacío.").pack(anchor="w", padx=(24, 0))
        self.tabla = ttk.Frame(self.cuerpo)
        self.tabla.pack(fill="x", padx=(24, 0), pady=(6, 0))
        for col, texto in enumerate(("Materia", "Profesor(a)", "Código")):
            ttk.Label(self.tabla, text=texto, style="Suave.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 6))
        self.materias = []
        for _ in range(3):
            self.agregar_materia()
        ttk.Button(self.cuerpo, text="+ Otra materia", command=self.agregar_materia).pack(anchor="w", padx=(24, 0),
                                                                                        pady=(4, 0))

        ttk.Separator(self.cuerpo).pack(fill="x", pady=14)
        otros = ttk.Frame(self.cuerpo)
        otros.pack(fill="x")
        otros.columnconfigure(1, weight=1)
        ttk.Label(otros, text="Empresa donde trabajas o haces pasantía").grid(row=0, column=0, sticky="w", pady=3)
        self.empresa = ttk.Entry(otros, width=40)
        self.empresa.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Label(otros, text="Tu nombre completo").grid(row=1, column=0, sticky="w", pady=3)
        self.nombre = ttk.Entry(otros, width=40)
        self.nombre.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Label(otros, text="Sale en todos tus trabajos, así que Ordenito nunca lo usará como pista.",
                  style="Suave.TLabel").grid(row=2, column=1, sticky="w", padx=(10, 0))

        ttk.Separator(self.cuerpo).pack(fill="x", pady=14)
        ya_vigila = o.CONFIG.exists() and any(o.real(c) == o.real(o.carpeta_escritorio())
                                               for c in o.carpetas_vigiladas())
        self.escritorio = tk.BooleanVar(value=ya_vigila)
        ttk.Checkbutton(self.cuerpo, text="Ordenar también el Escritorio", variable=self.escritorio,
                        style="Negrita.TCheckbutton").pack(anchor="w")
        ttk.Label(self.cuerpo, style="Suave.TLabel", wraplength=760, justify="left",
                  text="Lo que guardes en el Escritorio se ordenará igual que tus descargas. "
                       "Los accesos directos no se tocan.").pack(anchor="w", padx=(24, 0), pady=(0, 6))
        activa, dias, _ = o.ajustes_limpieza() if o.CONFIG.exists() else (False, o.LIMPIEZA_DIAS, None)
        self.limpieza = tk.BooleanVar(value=activa)
        ttk.Checkbutton(self.cuerpo, text=f"Limpiar instaladores viejos de Descargas ({dias} días)",
                        variable=self.limpieza, style="Negrita.TCheckbutton").pack(anchor="w")
        ttk.Label(self.cuerpo, style="Suave.TLabel", wraplength=760, justify="left",
                  text="Los .exe, .msi, ISOs y torrents que ya usaste van a la papelera (se pueden "
                       "recuperar). Los días se cambian en Ajustes.").pack(anchor="w", padx=(24, 0))

        ttk.Button(self.botones, text="Crear mis carpetas", style="Acento.TButton",
                   command=self.crear).pack(side="right")
        if not primera_vez:
            ttk.Button(self.botones, text="Cancelar", command=self.destroy).pack(side="right", padx=8)

    def agregar_materia(self):
        fila = len(self.materias) + 1
        entradas = []
        for col, ancho in enumerate((26, 26, 14)):
            e = ttk.Entry(self.tabla, width=ancho)
            e.grid(row=fila, column=col, sticky="w", padx=(0, 6), pady=2)
            entradas.append(e)
        self.materias.append(entradas)

    def crear(self):
        existentes = {r.destino for r in o.leer_reglas()} if o.CONFIG.exists() else set()
        bloques = []
        for var, lista_bloques in self.marcas:
            if var.get():
                bloques += lista_bloques
        if self.uni.get():
            for materia, profe, codigo in ((m.get().strip(), p.get().strip(), c.get().strip())
                                           for m, p, c in self.materias):
                if materia:
                    carpeta = materia.replace("/", "-")
                    bloques.append((f"Documents/Universidad/{carpeta}", [x for x in (profe, codigo) if x],
                                    [materia.lower()], []))
            bloques += UNIVERSIDAD_FIJOS
        empresa = self.empresa.get().strip()
        if empresa:
            bloques.append((f"Documents/Trabajo/{empresa.replace('/', '-')}", [empresa],
                            ["informe semanal", "reporte diario", "pasantia", "practicas profesionales"], []))
        if not o.CONFIG.exists():
            o.CONFIG.parent.mkdir(parents=True, exist_ok=True)
            o.CONFIG.write_text("# Reglas de Ordenito. Se editan desde la app (pestaña Carpetas) o aquí a mano.\n"
                                "# Formato: https://github.com/Gr8coolmind/ordenito#-tus-reglas\n",
                                encoding="utf-8")
        if self.nombre.get().strip():
            ya = o.no_sugerir()
            nuevos = [n for n in lista(self.nombre.get()) if o.normalizar(n).strip() not in ya]
            if nuevos:
                o.guardar_bloque("no sugerir", palabras=sorted(ya | {o.normalizar(n).strip() for n in nuevos}))
        creadas = 0
        for destino, fuertes, palabras, extensiones in bloques:
            if destino in existentes:
                continue
            o.guardar_bloque(destino, fuertes, palabras, extensiones)
            existentes.add(destino)
            if not destino.startswith("*/"):
                o.ruta_destino(destino).mkdir(parents=True, exist_ok=True)
            creadas += 1
        extra = o.carpetas_vigiladas()[1:]
        escritorio = o.carpeta_escritorio()
        tiene = any(o.real(c) == o.real(escritorio) for c in extra)
        if self.escritorio.get() != tiene:
            o.guardar_vigiladas(extra + [escritorio] if self.escritorio.get()
                                else [c for c in extra if o.real(c) != o.real(escritorio)])
        activa, dias, extensiones = o.ajustes_limpieza()
        if self.limpieza.get() != activa:
            o.guardar_limpieza(self.limpieza.get(), dias, sorted(extensiones))
        self.resultado = creadas
        self.destroy()


class Limpieza(Dialogo):
    """Lo que la limpieza mandaría a la papelera ahora mismo, con un botón para hacerlo."""

    def __init__(self, padre):
        super().__init__(padre, "Limpieza de Descargas")
        _, dias, _ = o.ajustes_limpieza()
        self.viejos = o.para_limpiar()
        total = sum(f.stat().st_size for f in self.viejos) / 1e6
        ttk.Label(self.cuerpo, text=f"Instaladores con más de {dias} días", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self.cuerpo, style="Suave.TLabel",
                  text=f"{len(self.viejos)} archivo(s), {total:.0f} MB. Van a la papelera: se pueden recuperar."
                  if self.viejos else "No hay nada que limpiar.").pack(anchor="w", pady=(2, 10))
        arbol = ttk.Treeview(self.cuerpo, columns=("archivo", "carpeta", "tam"), show="headings", height=10)
        for col, texto, ancho in (("archivo", "Archivo", 300), ("carpeta", "Carpeta", 260), ("tam", "Tamaño", 80)):
            arbol.heading(col, text=texto)
            arbol.column(col, width=ancho, anchor="e" if col == "tam" else "w")
        for f in self.viejos:
            arbol.insert("", "end", values=(f.name, o.bonito(f.parent), f"{f.stat().st_size / 1e6:.1f} MB"))
        arbol.pack(fill="both", expand=True)
        botones = ttk.Frame(self.cuerpo)
        botones.pack(fill="x", pady=(14, 0))
        if self.viejos:
            ttk.Button(botones, text="Mandar a la papelera", style="Acento.TButton",
                       command=self.limpiar).pack(side="right")
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=8)

    def limpiar(self):
        _, dias, _ = o.ajustes_limpieza()
        for f in self.viejos:
            if f.exists():
                try:
                    o._registrar(f, o.a_papelera(f), limpieza=dias)
                except OSError:
                    continue
        self.resultado = True
        self.destroy()


# ───────────────────────────── ventana principal ─────────────────────────────

class App(tk.Tk):
    def __init__(self):
        preparar_windows()
        super().__init__(className="Ordenito")  # enlaza la ventana con su ícono del menú
        self.title("Ordenito")
        if o.WINDOWS:  # Segoe UI a 9 puntos se lee chico en una ventana con tablas
            for nombre in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
                font.nametofont(nombre).configure(size=10)
        ancho = min(1080, self.winfo_screenwidth() - 60)
        alto = min(680, self.winfo_screenheight() - 120)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(min(860, ancho), min(520, alto))
        self.arboles = []          # se vuelven a pintar al cambiar de tema
        self._estilos()
        self._icono()
        self.cola = queue.Queue()
        self.trabajos = 0          # tareas en segundo plano todavía sin terminar
        self.plan = {}
        self.registros = []
        self.marca_historial = None
        self.vueltas = 0

        self._cabecera()
        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._pestana_actividad()
        self._pestana_descargas()
        self._pestana_carpetas()
        self._pestana_revisar()
        self._pestana_duplicados()
        self._pestana_ajustes()
        self.estado = ttk.Label(self, text="", style="Estado.TLabel", anchor="w")
        self.estado.pack(fill="x", padx=18, pady=(0, 10))

        self._programadas = {self.after(100, self._arrancar)}

    def destroy(self):
        for tarea in self._programadas:  # que no queden refrescos pendientes al cerrar
            try:
                self.after_cancel(tarea)
            except tk.TclError:
                pass
        super().destroy()

    # ── apariencia ──
    def _estilos(self):
        C.clear()
        C.update(OSCURO if tema_elegido() == "oscuro" else CLARO)
        s = ttk.Style(self)
        if not o.MAC and "clam" in s.theme_names():
            s.theme_use("clam")
        familia = font.nametofont("TkDefaultFont").actual("family")
        alto_fila = int(font.nametofont("TkDefaultFont").metrics("linespace") * 1.9)
        self.configure(bg=C["fondo"])
        # Para los widgets clásicos de Tk (cuadros de texto y listas de los menús desplegables)
        for clave, valor in (("background", C["superficie"]), ("foreground", C["texto"]),
                             ("selectBackground", C["seleccion"]), ("selectForeground", C["texto"]),
                             ("insertBackground", C["texto"])):
            self.option_add(f"*Text.{clave}", valor)
            self.option_add(f"*TCombobox*Listbox.{clave}", valor)

        s.configure(".", background=C["fondo"], foreground=C["texto"], fieldbackground=C["superficie"],
                    bordercolor=C["borde"], lightcolor=C["control"], darkcolor=C["control"],
                    troughcolor=C["fondo"], selectbackground=C["seleccion"], selectforeground=C["texto"],
                    insertcolor=C["texto"], arrowcolor=C["suave"], focuscolor=C["acento"])
        s.map(".", foreground=[("disabled", C["apagado"])])
        s.configure("TFrame", background=C["fondo"])
        s.configure("Tarjeta.TFrame", background=C["superficie"], relief="solid", borderwidth=1)
        s.configure("TLabel", background=C["fondo"], foreground=C["texto"])
        for tipo in ("TCheckbutton", "Negrita.TCheckbutton", "TRadiobutton"):
            s.configure(tipo, background=C["fondo"], foreground=C["texto"],
                        indicatorbackground=C["superficie"], indicatorforeground=C["texto_acento"],
                        indicatorrelief="flat", upperbordercolor=C["borde"], lowerbordercolor=C["borde"])
            s.map(tipo, background=[("active", C["fondo"])],
                  indicatorbackground=[("selected", C["acento"]), ("pressed", C["control_activo"])])
        if not o.MAC:
            s.configure("Negrita.TCheckbutton", font=(familia, 10, "bold"))
        s.configure("Grande.TLabel", font=(familia, 18, "bold"))
        s.configure("Titulo.TLabel", font=(familia, 13, "bold"))
        s.configure("Destino.TLabel", font=(familia, 12, "bold"), foreground=C["acento"])
        s.configure("Suave.TLabel", foreground=C["suave"])
        s.configure("Estado.TLabel", foreground=C["suave"])
        s.configure("Logo.TLabel", font=(familia, 22, "bold"), foreground=C["texto"])
        s.configure("TButton", padding=(10, 5), background=C["control"], foreground=C["texto"],
                    bordercolor=C["borde"], lightcolor=C["control"], darkcolor=C["control"])
        s.map("TButton", background=[("pressed", C["control_activo"]), ("active", C["control_activo"])])
        if o.MAC:  # en macOS los botones son nativos: no se puede cambiar su color de fondo
            s.configure("Acento.TButton", font=(familia, 13, "bold"))
        else:
            s.configure("Acento.TButton", foreground=C["texto_acento"], background=C["acento"], padding=(14, 6),
                        bordercolor=C["acento"], lightcolor=C["acento"], darkcolor=C["acento"])
            s.map("Acento.TButton", background=[("disabled", C["acento_apagado"]), ("pressed", C["acento_activo"]),
                                                ("active", C["acento_activo"])],
                  foreground=[("disabled", C["texto_acento"])])
        for tipo in ("TEntry", "TSpinbox"):
            s.configure(tipo, fieldbackground=C["superficie"], foreground=C["texto"], insertcolor=C["texto"],
                        bordercolor=C["borde"], lightcolor=C["superficie"], darkcolor=C["superficie"],
                        background=C["control"], arrowcolor=C["suave"], padding=4)
            s.map(tipo, bordercolor=[("focus", C["acento"])], lightcolor=[("focus", C["acento"])])
        s.configure("Treeview", rowheight=alto_fila, fieldbackground=C["superficie"], background=C["superficie"],
                    foreground=C["texto"], bordercolor=C["borde"], lightcolor=C["superficie"],
                    darkcolor=C["superficie"])
        s.map("Treeview", background=[("selected", C["seleccion"])], foreground=[("selected", C["texto"])])
        s.configure("Treeview.Heading", font=(familia, 10, "bold"), background=C["control"],
                    foreground=C["texto"], bordercolor=C["borde"], lightcolor=C["control"],
                    darkcolor=C["control"], relief="flat", padding=(6, 4))
        s.map("Treeview.Heading", background=[("active", C["control_activo"])])
        s.configure("TNotebook", background=C["fondo"], borderwidth=0, bordercolor=C["borde"],
                    lightcolor=C["fondo"], darkcolor=C["fondo"])
        s.configure("TNotebook.Tab", padding=(16, 7), background=C["fondo"], foreground=C["suave"],
                    bordercolor=C["borde"], lightcolor=C["fondo"])
        s.map("TNotebook.Tab", background=[("selected", C["superficie"])], foreground=[("selected", C["texto"])],
              lightcolor=[("selected", C["superficie"])])
        s.configure("TScrollbar", background=C["control"], troughcolor=C["fondo"], bordercolor=C["fondo"],
                    lightcolor=C["control"], darkcolor=C["control"], arrowcolor=C["suave"])
        s.map("TScrollbar", background=[("active", C["control_activo"])])
        s.configure("TSeparator", background=C["borde"])
        for arbol in self.arboles:
            self._colores_arbol(arbol)
        barra_de_titulo(self, C == OSCURO)

    @staticmethod
    def _colores_arbol(arbol):
        arbol.tag_configure("par", background=C["par"])
        arbol.tag_configure("apagado", foreground=C["apagado"])

    def cambiar_tema(self):
        guardar_preferencia("tema", self.tema.get())
        self._estilos()
        self.avisar({"sistema": "La app sigue el tema del sistema.", "claro": "Tema claro.",
                     "oscuro": "Tema oscuro."}[self.tema.get()])

    def _icono(self):
        icono = Path(__file__).resolve().parent / "ordenito.png"
        for ruta in (icono, Path(__file__).resolve().parent.parent / "share" / "ordenito" / "ordenito.png"):
            if ruta.is_file():
                try:
                    self.iconphoto(True, tk.PhotoImage(file=str(ruta)))
                except tk.TclError:
                    pass
                break

    def _cabecera(self):
        cab = ttk.Frame(self, padding=(18, 14, 18, 10))
        cab.pack(fill="x")
        izquierda = ttk.Frame(cab)
        izquierda.pack(side="left")
        ttk.Label(izquierda, text="Ordenito", style="Logo.TLabel").pack(anchor="w")
        self.vigila = ttk.Label(izquierda, text="", style="Suave.TLabel")
        self.vigila.pack(anchor="w")
        derecha = ttk.Frame(cab)
        derecha.pack(side="right")
        self.auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(derecha, text="Ordenar automáticamente", variable=self.auto,
                        command=self.cambiar_servicio).pack(side="left", padx=(0, 14))
        ttk.Button(derecha, text="Ordenar ahora", style="Acento.TButton", command=self.ordenar_ahora).pack(side="left")

    def _arbol(self, padre, columnas, alto=12):
        marco = ttk.Frame(padre)
        marco.pack(fill="both", expand=True)
        arbol = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", height=alto)
        for clave, titulo, ancho in columnas:
            arbol.heading(clave, text=titulo)
            arbol.column(clave, width=ancho, anchor="w", stretch=True)
        barra = ttk.Scrollbar(marco, orient="vertical", command=arbol.yview)
        arbol.configure(yscrollcommand=barra.set)
        arbol.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._colores_arbol(arbol)
        self.arboles.append(arbol)
        return arbol

    def _botonera(self, padre, botones):
        fila = ttk.Frame(padre)
        fila.pack(fill="x", pady=(10, 0))
        creados = []
        for texto, accion, *estilo in botones:
            b = ttk.Button(fila, text=texto, command=accion, style=estilo[0] if estilo else "TButton")
            b.pack(side="left", padx=(0, 8))
            creados.append(b)
        return fila, creados

    def _explicacion_pestana(self, padre, texto):
        ttk.Label(padre, text=texto, style="Suave.TLabel", wraplength=900, justify="left").pack(anchor="w",
                                                                                                pady=(0, 8))

    # ── pestañas ──
    def _pestana_actividad(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="Actividad")
        self._explicacion_pestana(p, "Lo último que Ordenito movió. Si algo cayó donde no va, selecciónalo y "
                                     "pulsa Corregir: lo mueves y Ordenito aprende para la próxima vez.")
        self.actividad = self._arbol(p, [("fecha", "Cuándo", 110), ("archivo", "Archivo", 360),
                                         ("carpeta", "Carpeta", 420)])
        self.actividad.bind("<Double-1>", lambda e: self.abrir_seleccion())
        self._botonera(p, [("Deshacer", self.deshacer), ("Corregir…", self.corregir_actividad),
                           ("¿Por qué fue aquí?", self.explicar_actividad), ("Abrir carpeta", self.abrir_seleccion)])

    def _pestana_descargas(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="En Descargas")
        self._explicacion_pestana(p, "Lo que hay ahora en tu carpeta de descargas y a dónde iría cada archivo. "
                                     "No se mueve nada hasta que pulses Ordenar ahora.")
        self.descargas = self._arbol(p, [("archivo", "Archivo", 340), ("destino", "Irá a", 380),
                                         ("motivo", "Por qué", 220)])
        self._botonera(p, [("Actualizar", self.cargar_descargas), ("Mover a…", self.mover_descarga),
                           ("¿Por qué?", self.explicar_descarga), ("Abrir Descargas", lambda: o.abrir(o.carpeta_descargas()))])

    def _pestana_carpetas(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="Carpetas")
        self._explicacion_pestana(p, "Tus carpetas y cómo las reconoce Ordenito. Las pistas fuertes (★) son lo "
                                     "que identifica al dueño de un documento: profesor, código, empresa.")
        self.carpetas = self._arbol(p, [("carpeta", "Carpeta", 400), ("fuertes", "★ Pistas fuertes", 230),
                                        ("palabras", "Palabras del tema", 230), ("tipos", "Tipos", 100)])
        self.carpetas.bind("<Double-1>", lambda e: self.editar_carpeta())
        self._botonera(p, [("Nueva carpeta…", self.nueva_carpeta), ("Editar…", self.editar_carpeta),
                           ("Quitar", self.quitar_carpeta), ("Carpetas recomendadas…", self.recomendadas),
                           ("Abrir archivo de reglas", lambda: o.abrir(o.CONFIG))])

    def _pestana_revisar(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="Revisar")
        self._explicacion_pestana(p, "Busca en una carpeta los archivos que, según tus reglas, estarían mejor en "
                                     "otro lugar. Las subcarpetas que creaste tú se respetan.")
        self.revision = self._arbol(p, [("archivo", "Archivo", 380), ("ahora", "Está en", 260),
                                        ("destino", "Debería ir a", 300)])
        _, (self.b_revisar, *_resto) = self._botonera(p, [
            ("Elegir carpeta y revisar…", self.revisar, "Acento.TButton"),
            ("Mover seleccionados", self.mover_revisados), ("Mover todos", lambda: self.mover_revisados(True))])
        self.fuera = {}

    def _pestana_duplicados(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="Duplicados")
        self._explicacion_pestana(p, "Archivos con exactamente el mismo contenido (aunque se llamen distinto). "
                                     "Se conserva el de nombre más limpio; las copias van a la papelera.")
        self.duplicados = self._arbol(p, [("archivo", "Archivo", 420), ("carpeta", "Carpeta", 380),
                                          ("tam", "Tamaño", 90)])
        _, (self.b_duplicados, *_resto) = self._botonera(p, [
            ("Elegir carpeta y buscar…", self.buscar_duplicados, "Acento.TButton"),
            ("Mandar copias a la papelera", self.quitar_duplicados)])
        self.grupos = []

    def _pestana_ajustes(self):
        p = ttk.Frame(self.pestanas, padding=14)
        self.pestanas.add(p, text="Ajustes")
        p.columnconfigure(0, weight=3, uniform="col")
        p.columnconfigure(1, weight=2, uniform="col")
        p.rowconfigure(0, weight=1)

        izq = ttk.Frame(p)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 28))
        ttk.Label(izq, text="Carpetas que se ordenan solas", style="Titulo.TLabel").pack(anchor="w")
        texto = ("Descargas siempre. Agrega otras, como el Escritorio, y lo que guardes ahí también irá a su "
                 "lugar. Los accesos directos y los archivos ocultos nunca se tocan.")
        if not o.WINDOWS:
            texto += (" En Linux y Mac, las carpetas extra se revisan cuando llega algo a Descargas o al pulsar "
                      "Ordenar ahora.")
        ttk.Label(izq, text=texto, style="Suave.TLabel", wraplength=500, justify="left").pack(anchor="w",
                                                                                               pady=(2, 10))
        self.vigiladas = self._arbol(izq, [("carpeta", "Carpeta", 420)], alto=7)
        self._botonera(izq, [("Agregar carpeta…", self.agregar_vigilada),
                             ("Agregar el Escritorio", self.agregar_escritorio), ("Quitar", self.quitar_vigilada)])

        der = ttk.Frame(p)
        der.grid(row=0, column=1, sticky="nsew")
        ttk.Label(der, text="Limpieza de Descargas", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(der, style="Suave.TLabel", wraplength=360, justify="left",
                  text="Los instaladores que ya usaste ocupan espacio. Ordenito puede mandarlos a la papelera "
                       "(se recuperan con Deshacer).").pack(anchor="w", pady=(2, 8))
        self.limpia = tk.BooleanVar(value=False)
        ttk.Checkbutton(der, text="Limpiar automáticamente", variable=self.limpia,
                        command=self.guardar_limpieza).pack(anchor="w")
        fila = ttk.Frame(der)
        fila.pack(anchor="w", pady=8)
        ttk.Label(fila, text="Cuando lleven más de").pack(side="left")
        self.dias = ttk.Spinbox(fila, from_=1, to=365, width=5, command=self.guardar_limpieza)
        self.dias.pack(side="left", padx=6)
        ttk.Label(fila, text="días en Descargas").pack(side="left")
        ttk.Label(der, text="Tipos de archivo").pack(anchor="w")
        self.tipos_limpieza = ttk.Entry(der)
        self.tipos_limpieza.pack(fill="x", pady=(2, 0))
        for campo in (self.dias, self.tipos_limpieza):
            campo.bind("<FocusOut>", lambda e: self.guardar_limpieza())
            campo.bind("<Return>", lambda e: self.guardar_limpieza())
        self._botonera(der, [("Ver qué se limpiaría…", self.ver_limpieza)])

        ttk.Separator(der).pack(fill="x", pady=18)
        ttk.Label(der, text="Apariencia", style="Titulo.TLabel").pack(anchor="w", pady=(0, 4))
        self.tema = tk.StringVar(value=preferencias().get("tema", "sistema"))
        for valor, texto in (("sistema", "Como el sistema"), ("claro", "Claro"), ("oscuro", "Oscuro")):
            ttk.Radiobutton(der, text=texto, value=valor, variable=self.tema,
                            command=self.cambiar_tema).pack(anchor="w", pady=1)

    # ── arranque y refresco ──
    def _arrancar(self):
        if not o.CONFIG.exists():
            creadas = Asistente(self, primera_vez=True).mostrar()
            if not o.CONFIG.exists():
                self.destroy()
                return
            self.avisar(f"Listo: {creadas} carpetas creadas.")
        self.auto.set(o.servicio_activo())
        self.vigila.configure(text=self._texto_vigila())
        self.cargar_actividad()
        self.cargar_descargas()
        self.cargar_carpetas()
        self.cargar_ajustes()
        self._programadas.add(self.after(3000, self._refrescar))

    def _texto_vigila(self):
        carpetas = o.carpetas_vigiladas() if o.CONFIG.exists() else [o.carpeta_descargas()]
        dl = o.bonito(carpetas[0]) + (f" y {len(carpetas) - 1} carpeta(s) más" if len(carpetas) > 1 else "")
        return f"Vigilando {dl}" if self.auto.get() else f"Pausado · {dl} no se ordena solo"

    def _refrescar(self):
        try:
            marca = (o.ESTADO / "historial.jsonl").stat().st_mtime
        except OSError:
            marca = None
        if marca != self.marca_historial:
            self.cargar_actividad()
            self.cargar_descargas()
        self.vueltas += 1
        # Si sigue al sistema, cambia sola cuando cambias el tema de Windows/Mac (cada ~30 s)
        if self.vueltas % 10 == 0 and self.tema.get() == "sistema" and (C == OSCURO) != (tema_elegido() == "oscuro"):
            self._estilos()
        self._programadas = {self.after(3000, self._refrescar)}

    def avisar(self, texto):
        self.estado.configure(text=texto)

    def _llenar(self, arbol, filas):
        arbol.delete(*arbol.get_children())
        for i, (iid, valores, *tags) in enumerate(filas):
            arbol.insert("", "end", iid=iid, values=valores, tags=(("par",) if i % 2 else ()) + tuple(tags))

    def _seleccion(self, arbol, aviso="Selecciona primero un archivo de la lista."):
        sel = arbol.selection()
        if not sel:
            self.avisar(aviso)
        return sel

    def en_segundo_plano(self, trabajo, al_terminar, mensaje):
        """Ejecuta trabajo() en un hilo y llama al_terminar(resultado) en la ventana."""
        self.avisar(mensaje)
        self.configure(cursor="watch")

        def hilo():
            try:
                self.cola.put((al_terminar, trabajo(), None))
            except Exception as error:  # se muestra en la ventana, no se pierde en el hilo
                self.cola.put((al_terminar, None, error))

        self.trabajos += 1
        if self.trabajos == 1:
            self.after(100, self._revisar_cola)
        # Las variables de Tk de ventanas ya cerradas deben liberarse en este hilo: si el recolector
        # las encuentra dentro del hilo de trabajo, cada una lo frena esperando a la ventana principal.
        gc.collect()
        threading.Thread(target=hilo, daemon=True).start()

    def _revisar_cola(self):
        while True:
            try:
                al_terminar, resultado, error = self.cola.get_nowait()
            except queue.Empty:
                break
            self.trabajos -= 1
            if error:
                messagebox.showerror("Algo salió mal", str(error), parent=self)
                self.avisar("")
            else:
                al_terminar(resultado)
        if self.trabajos:
            self.after(100, self._revisar_cola)
        else:
            self.configure(cursor="")

    # ── actividad ──
    def cargar_actividad(self):
        self.registros = o._historial()
        try:
            self.marca_historial = (o.ESTADO / "historial.jsonl").stat().st_mtime
        except OSError:
            self.marca_historial = None
        filas = []
        for i in reversed(range(len(self.registros))):
            r = self.registros[i]
            if r.get("duplicado_de"):
                carpeta = f"Papelera (ya lo tenías en {o.bonito(Path(r['duplicado_de']).parent)})"
            elif r.get("limpieza"):
                carpeta = f"Papelera (limpieza: más de {r['limpieza']} días en Descargas)"
            else:
                carpeta = o.bonito(Path(r["hacia"]).parent)
            filas.append((str(i), (hora(r["fecha"]), Path(r["desde"]).name, carpeta),
                          *(("apagado",) if not Path(r["hacia"]).exists() else ())))
        if not filas:
            filas = [("vacio", ("", "Todavía no se ha movido nada", ""), "apagado")]
        self._llenar(self.actividad, filas[:300])

    def _registros_elegidos(self):
        return [(int(i), self.registros[int(i)]) for i in self._seleccion(self.actividad) if i.isdigit()]

    def deshacer(self):
        elegidos = self._registros_elegidos()
        if not elegidos:
            return
        mensajes = o.deshacer_indices(i for i, _ in elegidos)
        self.cargar_actividad()
        self.cargar_descargas()
        malos = [m for ok, m in mensajes if not ok]
        self.avisar(f"Devuelto: {len(mensajes) - len(malos)} archivo(s)." + (f" No encontré: {'; '.join(malos)}" if malos else ""))

    def corregir_actividad(self):
        elegidos = self._registros_elegidos()
        if not elegidos:
            return
        _, r = elegidos[0]
        actual = Path(r["hacia"])
        if r.get("duplicado_de") or r.get("limpieza"):
            motivo = "una copia idéntica" if r.get("duplicado_de") else "un instalador viejo"
            messagebox.showinfo("Está en la papelera", f"Ese archivo era {motivo} y está en la papelera. "
                                "Usa Deshacer si lo quieres recuperar.", parent=self)
            return
        if not actual.exists():
            messagebox.showinfo("Ya no está", f"{actual.name} ya no está en {o.bonito(actual.parent)}.", parent=self)
            return
        self.corregir(actual)

    def corregir(self, archivo):
        carpeta = filedialog.askdirectory(parent=self, title=f"¿A qué carpeta va {archivo.name}?",
                                          initialdir=str(o.HOME / "Documents"), mustexist=False)
        if not carpeta:
            return
        carpeta = o.real(carpeta)
        destino = o.destino_de(carpeta)
        if archivo.parent.resolve() != carpeta:
            archivo = o.mover(archivo, carpeta, corregido=True)
        pistas = Aprender(self, archivo, destino, o.pistas_nuevas(archivo, destino)).mostrar()
        if pistas:
            o.agregar_fuertes(destino, pistas)
        res = o.clasificar(archivo, o.leer_reglas())
        if res.destino and o.real(o.ruta_destino(res.destino)) == carpeta:
            self.avisar(f"Listo. La próxima vez un archivo así irá solo a {o.bonito(carpeta)}.")
        else:
            self.avisar(f"Movido. Con las reglas actuales un archivo así todavía iría a "
                        f"{o.bonito(o.ruta_destino(res.destino)) if res.destino else 'Descargas'}: "
                        f"agrega una pista en la pestaña Carpetas.")
        self.cargar_actividad()
        self.cargar_carpetas()
        self.cargar_descargas()

    def explicar_actividad(self):
        elegidos = self._registros_elegidos()
        if elegidos:
            actual = Path(elegidos[0][1]["hacia"])
            if actual.exists():
                Explicacion(self, actual).mostrar()
            else:
                self.avisar(f"{actual.name} ya no está ahí.")

    def abrir_seleccion(self):
        elegidos = self._registros_elegidos()
        if elegidos:
            o.abrir(Path(elegidos[0][1]["hacia"]).parent)

    # ── descargas ──
    def cargar_descargas(self):
        def trabajo():
            return o.vista_previa()

        def listo(plan):
            self.plan = {str(f): f for f, *_ in plan}
            dl = o.real(o.carpeta_descargas())
            filas = []
            for f, res, carpeta, igual in plan:
                de_descargas = o.real(f.parent) == dl
                if igual:
                    destino, motivo = "Papelera", f"ya lo tienes en {o.bonito(igual.parent)}"
                elif carpeta:
                    destino, motivo = o.bonito(carpeta), self._motivo(f, res)
                else:
                    destino = "Se queda en Descargas" if de_descargas else "Se queda donde está"
                    motivo = res.motivo if res.motivo == "ya está en su carpeta" else "ninguna regla coincidió"
                nombre = f.name if de_descargas else f"{f.name}   ({f.parent.name})"
                filas.append((str(f), (nombre, destino, motivo), *(() if carpeta else ("apagado",))))
            if not filas:
                filas = [("vacio", ("Descargas está al día ✓", "Todo lo que llega se ordena solo"
                                    if self.auto.get() else "No hay nada pendiente", ""), "apagado")]
            self._llenar(self.descargas, filas)
            pendientes = sum(1 for _, _, c, _ in plan if c)
            self.pestanas.tab(1, text=f"En Descargas ({pendientes})" if pendientes else "En Descargas")
            if self.estado.cget("text") == "Mirando tus descargas…":
                self.avisar(f"{pendientes} archivo(s) esperando en Descargas." if pendientes else "")

        self.en_segundo_plano(trabajo, listo, "Mirando tus descargas…")

    @staticmethod
    def _motivo(f, res):
        """Las pistas que decidieron, en lugar de 'más puntos'."""
        if not res.puntos:
            return f"por tipo de archivo ({f.suffix})"
        decisivas = []
        for destino, (_, pistas) in res.tabla.items():
            if res.destino == destino or res.destino.startswith(destino + "/") or (
                    destino.startswith("*/") and res.destino.endswith(destino[1:])):
                decisivas += pistas
        limpias = []
        for p in decisivas:
            p = re.sub(r" (\(nombre\)|×\d+|★|☆ \(de pasada\))$", "", p)
            if p not in limpias:
                limpias.append(p)
        return ("★ " if any("★" in p for p in decisivas) else "") + ", ".join(limpias[:3])

    def ordenar_ahora(self):
        def listo(movidos):
            self.cargar_actividad()
            self.cargar_descargas()
            self.avisar(f"Ordenados: {movidos} archivo(s)." if movidos else "No había nada que ordenar.")

        self.en_segundo_plano(lambda: o.ordenar(esperar=False, avisar=False), listo, "Ordenando…")

    def _descarga_elegida(self):
        sel = self._seleccion(self.descargas)
        return self.plan.get(sel[0]) if sel else None  # la fila "al día" no es un archivo

    def mover_descarga(self):
        f = self._descarga_elegida()
        if f and f.exists():
            self.corregir(f)

    def explicar_descarga(self):
        f = self._descarga_elegida()
        if f and f.exists():
            Explicacion(self, f).mostrar()

    # ── carpetas ──
    def cargar_carpetas(self):
        self.reglas = {r.destino: r for r in o.leer_reglas()}
        filas = []
        for r in self.reglas.values():
            palabras = ", ".join(r.palabras)
            filas.append((r.destino, (r.destino, ", ".join(r.fuertes_texto or r.fuertes),
                                      palabras if len(palabras) < 90 else palabras[:87] + "…",
                                      ", ".join(e.lstrip(".") for e in sorted(r.extensiones)))))
        self._llenar(self.carpetas, filas)

    def nueva_carpeta(self):
        if EditorRegla(self).mostrar():
            self.cargar_carpetas()
            self.avisar("Carpeta guardada.")

    def editar_carpeta(self):
        sel = self._seleccion(self.carpetas, "Selecciona primero una carpeta.")
        if sel and EditorRegla(self, self.reglas[sel[0]]).mostrar():
            self.cargar_carpetas()
            self.avisar("Cambios guardados.")

    def quitar_carpeta(self):
        sel = self._seleccion(self.carpetas, "Selecciona primero una carpeta.")
        if sel and messagebox.askyesno("Quitar carpeta", f"¿Dejar de ordenar hacia {sel[0]}?\n\n"
                                       "La carpeta y sus archivos no se borran; solo se quita la regla.",
                                       parent=self):
            o.eliminar_bloque(sel[0])
            self.cargar_carpetas()
            self.avisar(f"Quitada la regla de {sel[0]}.")

    def recomendadas(self):
        creadas = Asistente(self).mostrar()
        if creadas is not None:
            self.cargar_carpetas()
            self.avisar(f"{creadas} carpeta(s) nuevas." if creadas else "Ya tenías todas esas carpetas.")

    # ── revisar ──
    def revisar(self):
        carpeta = filedialog.askdirectory(parent=self, title="¿Qué carpeta reviso?", initialdir=str(o.HOME))
        if not carpeta:
            return

        def listo(lista_fuera):
            self.fuera = {str(f): (f, destino) for f, destino, _ in lista_fuera}
            self._llenar(self.revision, [(str(f), (f.name, o.bonito(f.parent), o.bonito(destino)))
                                         for f, destino, _ in lista_fuera])
            self.avisar(f"{len(lista_fuera)} archivo(s) estarían mejor en otro lugar. No se movió nada."
                        if lista_fuera else "Todo está en su lugar.")

        self.en_segundo_plano(lambda: o.fuera_de_lugar(carpeta), listo, f"Revisando {o.bonito(carpeta)}…")

    def mover_revisados(self, todos=False):
        claves = list(self.fuera) if todos else self._seleccion(self.revision)
        movidos = 0
        for clave in claves:
            f, destino = self.fuera.pop(clave)
            if f.exists():
                o.mover(f, destino)
                movidos += 1
            self.revision.delete(clave)
        if claves:
            self.cargar_actividad()
            self.avisar(f"Movidos: {movidos}. Puedes deshacerlo desde Actividad.")

    # ── duplicados ──
    def buscar_duplicados(self):
        carpeta = filedialog.askdirectory(parent=self, title="¿Dónde busco duplicados?",
                                          initialdir=str(o.HOME / "Documents"))
        if not carpeta:
            return

        def listo(grupos):
            self.grupos = grupos
            filas = []
            for n, g in enumerate(grupos):
                for k, f in enumerate(g):
                    tam = f"{f.stat().st_size / 1e6:.1f} MB" if f.exists() else ""
                    etiqueta = ("✓ " if k == 0 else "    copia: ") + f.name
                    filas.append((f"{n}:{k}", (etiqueta, o.bonito(f.parent), tam), *(("apagado",) if k else ())))
            self._llenar(self.duplicados, filas)
            sobran = sum(len(g) - 1 for g in grupos)
            self.avisar(f"{sobran} copia(s) repetida(s). Se conserva la marcada con ✓." if sobran
                        else "No hay archivos duplicados.")

        self.en_segundo_plano(lambda: o.grupos_duplicados(carpeta), listo, f"Buscando en {o.bonito(carpeta)}…")

    def quitar_duplicados(self):
        sobran = sum(len(g) - 1 for g in self.grupos)
        if not sobran:
            self.avisar("Primero busca duplicados.")
            return
        if messagebox.askyesno("Mandar a la papelera", f"¿Mandar {sobran} copia(s) a la papelera?\n\n"
                               "Se conserva un ejemplar de cada archivo. Puedes recuperarlas desde la "
                               "papelera o con Deshacer en Actividad.", parent=self):
            n, ahorro = o.quitar_copias(self.grupos)
            self.grupos = []
            self.duplicados.delete(*self.duplicados.get_children())
            self.cargar_actividad()
            self.avisar(f"{n} copia(s) a la papelera, {ahorro / 1e6:.1f} MB liberados.")

    # ── ajustes ──
    def cargar_ajustes(self):
        carpetas = o.carpetas_vigiladas()
        filas = [("descargas", (f"{o.bonito(carpetas[0])}   (Descargas, siempre)",), "apagado")]
        filas += [(str(c), (o.bonito(c) + ("" if c.is_dir() else "   (no existe)"),)) for c in carpetas[1:]]
        self._llenar(self.vigiladas, filas)
        activa, dias, extensiones = o.ajustes_limpieza()
        self.limpia.set(activa)
        self.dias.set(dias)
        self.tipos_limpieza.delete(0, "end")
        self.tipos_limpieza.insert(0, ", ".join(sorted(e.lstrip(".") for e in extensiones)))

    def _guardar_vigiladas(self, carpetas, aviso):
        o.guardar_vigiladas(carpetas)
        self.cargar_ajustes()
        self.vigila.configure(text=self._texto_vigila())
        self.cargar_descargas()
        self.avisar(aviso)

    def agregar_vigilada(self, carpeta=None):
        carpeta = carpeta or filedialog.askdirectory(parent=self, title="¿Qué carpeta quieres que se ordene sola?",
                                                     initialdir=str(o.HOME))
        if not carpeta:
            return
        actuales = o.carpetas_vigiladas()
        if any(o.real(c) == o.real(carpeta) for c in actuales):
            self.avisar(f"{o.bonito(carpeta)} ya se ordena sola.")
            return
        destinos = {o.real(o.ruta_destino(r.destino)) for r in o.leer_reglas() if not r.comodin}
        if o.real(carpeta) in destinos or o.real(carpeta) == o.real(o.HOME):
            messagebox.showwarning("Esa carpeta no", "Esa carpeta es un destino de tus reglas (o tu carpeta "
                                   "personal). Vigilarla haría que Ordenito saque archivos de donde ya los "
                                   "guardaste. Elige una carpeta de \"entrada\", como el Escritorio.", parent=self)
            return
        self._guardar_vigiladas(actuales[1:] + [Path(carpeta)], f"Ahora también se ordena {o.bonito(carpeta)}.")

    def agregar_escritorio(self):
        self.agregar_vigilada(o.carpeta_escritorio())

    def quitar_vigilada(self):
        sel = self._seleccion(self.vigiladas, "Selecciona primero una carpeta.")
        if not sel:
            return
        if "descargas" in sel:
            self.avisar("Descargas siempre se ordena. Para pausarlo, desmarca Ordenar automáticamente.")
            return
        quedan = [c for c in o.carpetas_vigiladas()[1:] if str(c) not in sel]
        self._guardar_vigiladas(quedan, "Listo: esa carpeta ya no se ordena sola (sus archivos no se tocan).")

    def guardar_limpieza(self):
        try:
            dias = max(1, min(int(self.dias.get()), 3650))
        except ValueError:
            dias = o.ajustes_limpieza()[1]
            self.dias.set(dias)
        extensiones = [e.lstrip(".").lower() for e in lista(self.tipos_limpieza.get())]
        if not extensiones:
            extensiones = o.LIMPIEZA_TIPOS
        actual = o.ajustes_limpieza()
        nuevo = (self.limpia.get(), dias, {"." + e for e in extensiones})
        if nuevo == actual:
            return
        o.guardar_limpieza(self.limpia.get(), dias, extensiones)
        self.avisar(f"Limpieza automática: instaladores con más de {dias} días a la papelera." if self.limpia.get()
                    else "Limpieza automática apagada.")

    def ver_limpieza(self):
        self.guardar_limpieza()
        if Limpieza(self).mostrar():
            self.cargar_actividad()

    # ── servicio ──
    def cambiar_servicio(self):
        quiero = self.auto.get()
        if not o.cambiar_servicio(quiero):
            self.auto.set(not quiero)
            instalador = "instalar.cmd" if o.WINDOWS else "./instalar.sh"
            messagebox.showwarning("No pude cambiarlo", "No pude encender o apagar el servicio automático. "
                                   f"¿Instalaste Ordenito con {instalador}?", parent=self)
        self.vigila.configure(text=self._texto_vigila())
        self.avisar("Ordenito ordenará tus descargas solo." if self.auto.get()
                    else "Pausado: usa Ordenar ahora cuando quieras.")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
