#!/usr/bin/env python3
"""Ordenito (app): la ventana para ordenar, revisar, corregir y configurar tus carpetas.

Usa el mismo motor que el comando 'ordenito'. Requiere Tkinter (viene con Python;
en algunas distribuciones se instala aparte: python3-tk / python3-tkinter / brew python-tk).
"""
import importlib.machinery
import importlib.util
import queue
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, font, messagebox, ttk
except ImportError:
    sys.exit("La app necesita Tkinter. Instálalo con: python3-tk (Ubuntu/Debian), "
             "python3-tkinter (Fedora) o 'brew install python-tk' (Mac/Homebrew).")


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

ACENTO = "#2563eb"
FONDO = "#f6f7fb"
TEXTO_SUAVE = "#5b6474"

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
        ("Downloads/Instaladores", [], [], ["appimage", "rpm", "deb", "flatpakref", "exe", "msi", "apk",
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
        self.configure(bg=FONDO)
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
        self.lienzo = tk.Canvas(self, bg=FONDO, highlightthickness=0)
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
        self.palabras = tk.Text(campos, height=4, width=50, wrap="word", relief="solid", borderwidth=1,
                                font="TkDefaultFont")
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
        self.resultado = creadas
        self.destroy()


# ───────────────────────────── ventana principal ─────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__(className="Ordenito")  # enlaza la ventana con su ícono del menú
        self.title("Ordenito")
        ancho = min(1040, self.winfo_screenwidth() - 60)
        alto = min(660, self.winfo_screenheight() - 120)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(min(860, ancho), min(520, alto))
        self.configure(bg=FONDO)
        self._estilos()
        self._icono()
        self.cola = queue.Queue()
        self.trabajos = 0          # tareas en segundo plano todavía sin terminar
        self.plan = {}
        self.registros = []
        self.marca_historial = None

        self._cabecera()
        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._pestana_actividad()
        self._pestana_descargas()
        self._pestana_carpetas()
        self._pestana_revisar()
        self._pestana_duplicados()
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
        s = ttk.Style(self)
        if not o.MAC and "clam" in s.theme_names():
            s.theme_use("clam")
        familia = font.nametofont("TkDefaultFont").actual("family")
        base = (familia,)
        s.configure(".", background=FONDO)
        s.configure("TFrame", background=FONDO)
        s.configure("Tarjeta.TFrame", background="white", relief="solid", borderwidth=1)
        s.configure("TLabel", background=FONDO)
        s.configure("TCheckbutton", background=FONDO)
        s.configure("Negrita.TCheckbutton", background=FONDO)
        if not o.MAC:
            s.configure("Negrita.TCheckbutton", font=(familia, 10, "bold"))
        s.configure("Grande.TLabel", font=(base[0], 18, "bold"))
        s.configure("Titulo.TLabel", font=(base[0], 13, "bold"))
        s.configure("Destino.TLabel", font=(base[0], 12, "bold"), foreground=ACENTO)
        s.configure("Suave.TLabel", foreground=TEXTO_SUAVE)
        s.configure("Estado.TLabel", foreground=TEXTO_SUAVE)
        s.configure("Logo.TLabel", font=(base[0], 22, "bold"), foreground="#111827")
        if o.MAC:  # en macOS los botones son nativos: no se puede cambiar su color de fondo
            s.configure("Acento.TButton", font=(familia, 13, "bold"))
        else:
            s.configure("Acento.TButton", foreground="white", background=ACENTO, padding=(14, 6))
            s.map("Acento.TButton", background=[("active", "#1d4ed8"), ("disabled", "#93c5fd")])
        s.configure("TButton", padding=(10, 5))
        s.configure("Treeview", rowheight=26, fieldbackground="white", background="white")
        s.configure("Treeview.Heading", font=(base[0], 10, "bold"))
        s.configure("TNotebook", background=FONDO, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 7))

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
        arbol.tag_configure("par", background="#f9fafb")
        arbol.tag_configure("apagado", foreground="#9ca3af")
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
        self._programadas.add(self.after(3000, self._refrescar))

    def _texto_vigila(self):
        dl = o.bonito(o.carpeta_descargas())
        return f"Vigilando {dl}" if self.auto.get() else f"Pausado · {dl} no se ordena solo"

    def _refrescar(self):
        try:
            marca = (o.ESTADO / "historial.jsonl").stat().st_mtime
        except OSError:
            marca = None
        if marca != self.marca_historial:
            self.cargar_actividad()
            self.cargar_descargas()
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
        if r.get("duplicado_de"):
            messagebox.showinfo("Está en la papelera", "Ese archivo era una copia idéntica y está en la papelera. "
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
            filas = []
            for f, res, carpeta, igual in plan:
                if igual:
                    destino, motivo = "Papelera", f"ya lo tienes en {o.bonito(igual.parent)}"
                elif carpeta:
                    destino, motivo = o.bonito(carpeta), self._motivo(f, res)
                else:
                    destino, motivo = "Se queda en Descargas", "ninguna regla coincidió"
                filas.append((str(f), (f.name, destino, motivo), *(() if carpeta else ("apagado",))))
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

    # ── servicio ──
    def cambiar_servicio(self):
        quiero = self.auto.get()
        if not o.cambiar_servicio(quiero):
            self.auto.set(not quiero)
            messagebox.showwarning("No pude cambiarlo", "No pude encender o apagar el servicio automático. "
                                   "¿Instalaste Ordenito con ./instalar.sh?", parent=self)
        self.vigila.configure(text=self._texto_vigila())
        self.avisar("Ordenito ordenará tus descargas solo." if self.auto.get()
                    else "Pausado: usa Ordenar ahora cuando quieras.")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
