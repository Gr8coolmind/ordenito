#!/usr/bin/env python3
"""Ordenito: ordena tus descargas solo, leyendo el nombre y el contenido de cada archivo.

Comandos:
  ordenito                    ordena lo que haya en Descargas (lo que hace el servicio)
  ordenito simular            muestra lo que haría, sin mover nada
  ordenito explicar ARCHIVO   explica a qué carpeta iría un archivo y por qué
  ordenito revisar CARPETA    busca archivos que según tus reglas están en otro lugar
  ordenito historial [N]      últimos movimientos
  ordenito deshacer [N]       devuelve a su lugar los últimos N archivos movidos
  ordenito corregir ARCHIVO CARPETA   lo mueve donde va y aprende la pista que faltaba
  ordenito duplicados [CARPETA]       busca copias idénticas (--papelera para quitarlas)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

__version__ = "1.4.0"

HOME = Path.home()
MAC = sys.platform == "darwin"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "ordenito" / "reglas.conf"
ESTADO = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state")) / "ordenito"

EN_CURSO = {".crdownload", ".part", ".tmp", ".download", ".opdownload"}
OFIMATICA = {".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods"}
TEXTO = {".txt", ".md", ".csv", ".pine", ".php", ".js", ".ts", ".py", ".sh", ".sql",
         ".html", ".css", ".json"}
PESO_NOMBRE = 10      # una palabra clave en el nombre vale como 10 en el contenido
PESO_FUERTE = 25      # pista 'fuertes:' (profesor, código, cliente) en nombre, autor, encabezado o portada
PESO_FUERTE_CUERPO = 3  # la misma pista mencionada de pasada en el cuerpo
PORTADA = 1500        # caracteres iniciales que cuentan como portada (metadatos y encabezados van primero)
MINIMO = 2            # puntos mínimos para que un tema cuente
MAX_POR_PALABRA = 5   # una palabra repetida 100 veces no debe ganar sola
MAX_TEXTO = 50_000    # caracteres de contenido que se analizan
MAX_MIEMBRO = 2_000_000  # bytes leídos de cada parte de un zip (protege de zip bombs)


# ───────────────────────────── reglas ─────────────────────────────

@dataclass
class Regla:
    destino: str
    palabras: list = field(default_factory=list)
    fuertes: list = field(default_factory=list)
    extensiones: set = field(default_factory=set)
    fuertes_texto: list = field(default_factory=list)   # tal como están escritas (para mostrarlas)
    palabras_texto: list = field(default_factory=list)

    @property
    def comodin(self):
        """[*/Proyecto Final]: subcarpeta que aplica dentro de cualquier tema."""
        return self.destino.startswith("*/")

    @property
    def respaldo(self):
        """Bloque con solo 'extensiones:': clasifica por tipo si ningún tema coincidió."""
        return not self.palabras and not self.fuertes


NO_SUGERIR = "no sugerir"   # [no sugerir]: tu nombre y el de tus compañeros (no es una carpeta)


def leer_reglas(ruta=None):
    return [r for r in _bloques(ruta) if r.destino.lower() != NO_SUGERIR]


def no_sugerir(ruta=None):
    return {p for r in _bloques(ruta) if r.destino.lower() == NO_SUGERIR for p in r.palabras + r.fuertes}


def _bloques(ruta=None):
    ruta = ruta or CONFIG
    if not ruta.exists():
        sys.exit(f"No encuentro las reglas en {ruta}.\n"
                 "Ejecuta ./instalar.sh o copia reglas.ejemplo.conf a esa ruta.")
    reglas = []
    for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        if linea.startswith("[") and linea.endswith("]"):
            reglas.append(Regla(linea[1:-1].strip()))
        elif not reglas:
            sys.exit(f"{ruta}:{n}: hay palabras antes del primer [destino].")
        elif linea.lower().startswith("fuertes:"):
            crudas = [p.strip() for p in linea.split(":", 1)[1].split(",") if p.strip()]
            reglas[-1].fuertes_texto.extend(crudas)
            reglas[-1].fuertes.extend(normalizar(p).strip() for p in crudas)
        elif linea.lower().startswith("extensiones:"):
            reglas[-1].extensiones.update(
                "." + e.strip().lstrip(".").lower()
                for e in linea.split(":", 1)[1].split(",") if e.strip())
        else:
            crudas = [p.strip() for p in linea.split(",") if p.strip()]
            reglas[-1].palabras_texto.extend(crudas)
            reglas[-1].palabras.extend(normalizar(p).strip() for p in crudas)
    return reglas


# ───────────────────────────── lectura ─────────────────────────────

def normalizar(texto):
    """minúsculas, sin tildes, y guiones/guiones bajos como espacios."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[-_\s]+", " ", texto)


def contenido(f):
    """Texto legible del archivo. Nunca falla: si no se puede leer, devuelve ''."""
    ext = f.suffix.lower()
    try:
        if ext in OFIMATICA:
            with zipfile.ZipFile(f) as z:
                nombres = z.namelist()
                # Primero autor/título y encabezados: ahí suele estar el profesor o la empresa
                partes = [n for n in nombres if n in ("docProps/core.xml", "meta.xml")
                          or re.match(r"word/(header|footer)\d*\.xml$", n)]
                partes += [n for n in nombres if n == "content.xml" or re.match(
                    r"(word/document|ppt/slides/slide\d+|xl/sharedStrings)\.xml$", n)]
                xml = " ".join(_leer_miembro(z, n) for n in partes[:50])
            xml = re.sub(r"</(?:w:p|a:p|text:p|text:h)>", "\n", xml)  # conservar fin de párrafo
            return re.sub(r"<[^>]+>", " ", xml)
        if ext == ".zip":
            with zipfile.ZipFile(f) as z:
                return " ".join(Path(n).name for n in z.namelist()[:500])
        if ext == ".pdf" and shutil.which("pdftotext"):
            meta = ""
            if shutil.which("pdfinfo"):
                info = subprocess.run(["pdfinfo", "--", str(f)], capture_output=True, text=True, timeout=10)
                meta = " ".join(l.split(":", 1)[1] for l in info.stdout.splitlines()
                                if l.startswith(("Title:", "Author:", "Subject:", "Keywords:")))
            r = subprocess.run(["pdftotext", "-l", "5", "--", str(f), "-"],
                               capture_output=True, text=True, timeout=20)
            return meta + " " + r.stdout
        if ext in TEXTO:
            with f.open(encoding="utf-8", errors="ignore") as t:
                return t.read(MAX_TEXTO)
    except (OSError, zipfile.BadZipFile, subprocess.SubprocessError, RuntimeError, ValueError):
        pass
    return ""


def _leer_miembro(z, nombre):
    with z.open(nombre) as m:
        return m.read(MAX_MIEMBRO).decode("utf-8", "ignore")


# ─────────────────────────── clasificación ───────────────────────────

def contar(palabra, texto):
    """Apariciones como palabra completa ('curso' no cuenta dentro de 'recurso')."""
    return len(re.findall(r"(?<!\w)" + re.escape(palabra) + r"(?!\w)", texto))


def puntuar(palabras, nombre, texto, fuertes=()):
    puntos, pistas = 0, []
    for p in fuertes:
        if contar(p, nombre) or contar(p, texto[:PORTADA]):
            puntos += PESO_FUERTE
            pistas.append(f"{p} ★")
        elif contar(p, texto):
            puntos += PESO_FUERTE_CUERPO
            pistas.append(f"{p} ☆ (de pasada)")
    for p in palabras:
        if contar(p, nombre):
            puntos += PESO_NOMBRE
            pistas.append(f"{p} (nombre)")
        veces = min(contar(p, texto), MAX_POR_PALABRA)
        if veces:
            puntos += veces
            pistas.append(f"{p} ×{veces}")
    return puntos, pistas


@dataclass
class Resultado:
    destino: str | None
    puntos: int = 0
    motivo: str = ""
    tabla: dict = field(default_factory=dict)   # destino -> (puntos, pistas)


def clasificar(f, reglas):
    nombre = normalizar(f.stem)
    texto = normalizar(contenido(f))[:MAX_TEXTO]
    tabla, comodines, por_tipo = {}, [], None
    for r in reglas:
        if r.extensiones and f.suffix.lower() not in r.extensiones:
            continue
        if r.respaldo:
            por_tipo = por_tipo or r.destino
        elif r.comodin:
            comodines.append(r)
        else:
            puntos, pistas = puntuar(r.palabras, nombre, texto, r.fuertes)
            if puntos:
                tabla[r.destino] = (puntos, pistas)

    validos = {d: p for d, (p, _) in tabla.items() if p >= MINIMO}
    if not validos:
        if por_tipo:
            return Resultado(por_tipo, 0, f"ningún tema coincidió; por tipo ({f.suffix})", tabla)
        return Resultado(None, 0, "ninguna regla coincidió", tabla)

    mejor = max(validos, key=validos.get)
    motivo = "más puntos"
    # Si también encaja en una subcarpeta del ganador, la subcarpeta es más específica
    hijos = {d: p for d, p in validos.items() if d.startswith(mejor + "/")}
    while hijos:
        mejor = max(hijos, key=hijos.get)
        motivo = "subcarpeta más específica"
        hijos = {d: p for d, p in validos.items() if d.startswith(mejor + "/")}
    puntos = validos[mejor]

    # [*/Sub]: el tema ya está decidido, así que basta una mención
    for r in comodines:
        sub = r.destino[2:]
        if mejor.endswith("/" + sub):
            break
        extra, pistas = puntuar(r.palabras, nombre, texto, r.fuertes)
        if extra:
            tabla[r.destino] = (extra, pistas)
            return Resultado(f"{mejor}/{sub}", puntos, f"dentro del tema: {', '.join(pistas)}", tabla)
    return Resultado(mejor, puntos, motivo, tabla)


# ───────────────────────────── acciones ─────────────────────────────

def carpeta_descargas():
    if os.environ.get("ORDENITO_CARPETA"):
        return Path(os.environ["ORDENITO_CARPETA"]).expanduser()
    try:
        r = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5)
        ruta = Path(r.stdout.strip())
        if r.returncode == 0 and ruta.is_dir() and ruta != HOME:
            return ruta
    except (OSError, subprocess.SubprocessError):
        pass
    return HOME / "Downloads"


def ruta_destino(destino):
    return Path(destino).expanduser() if destino.startswith(("/", "~")) else HOME / destino


def real(ruta):
    """Ruta absoluta sin enlaces: en Silverblue/Bazzite /home es un enlace a /var/home."""
    return Path(ruta).expanduser().resolve()


def bonito(ruta):
    ruta, casa = real(ruta), real(HOME)
    return "~/" + str(ruta.relative_to(casa)) if ruta.is_relative_to(casa) else str(ruta)


def libre(carpeta, nombre):
    """Ruta sin pisar nada: 'informe.pdf' -> 'informe (2).pdf' si ya existe."""
    d, n = carpeta / nombre, 2
    while d.exists():
        d = carpeta / f"{Path(nombre).stem} ({n}){Path(nombre).suffix}"
        n += 1
    return d


def terminado(f, intentos=10, pausa=1.5):
    """Espera a que la descarga deje de crecer."""
    for _ in range(intentos):
        antes = f.stat().st_size
        time.sleep(pausa)
        if f.exists() and f.stat().st_size == antes and antes > 0:
            return True
    return False


def _json(nombre, defecto):
    try:
        return json.loads((ESTADO / nombre).read_text())
    except (OSError, ValueError):
        return defecto


def _guardar_json(nombre, datos):
    ESTADO.mkdir(parents=True, exist_ok=True)
    (ESTADO / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=1))


def _historial():
    try:
        lineas = (ESTADO / "historial.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(l) for l in lineas if l.strip()]


def _registrar(desde, hacia, puntos=0, **extra):
    ESTADO.mkdir(parents=True, exist_ok=True)
    with (ESTADO / "historial.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"),
                            "desde": str(desde), "hacia": str(hacia), "puntos": puntos, **extra},
                           ensure_ascii=False) + "\n")


def papelera():
    if MAC:
        return HOME / ".Trash"
    return Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / "Trash"


def cesto():
    """Carpeta donde quedan los archivos tirados (en Linux, Trash/files)."""
    return papelera() if MAC else papelera() / "files"


def a_papelera(f):
    """Manda a la papelera del sistema: se puede restaurar desde Archivos/Finder o con 'deshacer'."""
    cesto().mkdir(parents=True, exist_ok=True)
    destino = libre(cesto(), f.name)
    if not MAC:  # estándar freedesktop: el gestor de archivos sabe de dónde vino
        (papelera() / "info").mkdir(parents=True, exist_ok=True)
        (papelera() / "info" / f"{destino.name}.trashinfo").write_text(
            f"[Trash Info]\nPath={quote(str(f.resolve()))}\n"
            f"DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n")
    shutil.move(str(f), str(destino))
    return destino


def huella(f):
    h = hashlib.sha256()
    with f.open("rb") as a:
        for bloque in iter(lambda: a.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def gemelo(f, carpeta):
    """Archivo con exactamente el mismo contenido que f dentro de carpeta (sin subcarpetas)."""
    if not carpeta.is_dir():
        return None
    tam = f.stat().st_size
    mismos = [c for c in carpeta.iterdir() if c.is_file() and c != f and c.stat().st_size == tam]
    if not mismos:
        return None
    propia = huella(f)
    return next((c for c in mismos if huella(c) == propia), None)


def notificar(titulo, cuerpo):
    if MAC:  # los textos van como argumentos, nunca dentro del script
        subprocess.run(["osascript", "-e", "on run argv", "-e",
                        'display notification (item 2 of argv) with title "Ordenito" subtitle (item 1 of argv)',
                        "-e", "end run", titulo, cuerpo.replace("\n", " ")], check=False)
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Ordenito", "-i", "folder-documents", titulo, cuerpo],
                       check=False)


def pendientes(dl=None):
    """Archivos de Descargas que Ordenito tendría que mirar."""
    dl = dl or carpeta_descargas()
    ignorados = set(_json("ignorados.json", []))
    return [f for f in (sorted(dl.iterdir()) if dl.is_dir() else [])
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() not in EN_CURSO
            and f.name not in ignorados]


def vista_previa():
    """[(archivo, Resultado, carpeta destino, archivo idéntico o None)] sin mover nada."""
    reglas, plan = leer_reglas(), []
    for f in pendientes():
        res = clasificar(f, reglas)
        carpeta = ruta_destino(res.destino) if res.destino else None
        plan.append((f, res, carpeta, gemelo(f, carpeta) if carpeta else None))
    return plan


def ordenar(simular=False, esperar=True, avisar=True):
    reglas, dl = leer_reglas(), carpeta_descargas()
    ignorados = set(_json("ignorados.json", []))
    presentes = {f.name for f in dl.iterdir()} if dl.is_dir() else set()
    if ignorados - presentes:  # los que ya no están en Descargas dejan de ignorarse
        ignorados &= presentes
        _guardar_json("ignorados.json", sorted(ignorados))

    movidos = 0
    for f in sorted(dl.iterdir()) if dl.is_dir() else []:
        if (not f.is_file() or f.name.startswith(".") or f.suffix.lower() in EN_CURSO
                or f.name in ignorados):
            continue
        if not simular and esperar and not terminado(f):
            continue
        res = clasificar(f, reglas)
        if not res.destino:
            continue
        carpeta = ruta_destino(res.destino)
        igual = gemelo(f, carpeta)
        if igual:  # ya lo tenías: no guardar una copia "(2)"
            if simular:
                print(f"  {f.name}  →  papelera  {gris(f'(ya lo tienes: {bonito(igual)})')}")
                continue
            tirado = a_papelera(f)
            movidos += 1
            _registrar(f, tirado, res.puntos, duplicado_de=str(igual))
            if avisar:
                notificar("Ya lo tenías", f"{f.name} es idéntico a {bonito(igual)}.\n"
                                          "La copia nueva fue a la papelera.")
            continue
        nuevo = libre(carpeta, f.name)
        if simular:
            print(f"  {f.name}  →  {bonito(nuevo.parent)}  {gris(f'({res.puntos} pts, {res.motivo})')}")
            continue
        nuevo.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(nuevo))
        movidos += 1
        _registrar(f, nuevo, res.puntos)
        if avisar:
            notificar("Descarga ordenada", f"{f.name}\n→ {bonito(nuevo.parent)}")
    return movidos


def deshacer_indices(indices):
    """Devuelve a su lugar los movimientos del historial con esos índices. -> [(ok, mensaje)]"""
    registros, indices = _historial(), set(indices)
    ignorados, mensajes = set(_json("ignorados.json", [])), []
    for i in sorted(indices, reverse=True):
        r = registros[i]
        actual, origen = Path(r["hacia"]), Path(r["desde"])
        if not actual.exists():
            mensajes.append((False, f"{actual.name}: ya no está en {bonito(actual.parent)}"))
            continue
        vuelta = libre(origen.parent, origen.name)
        origen.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(actual), str(vuelta))
        if not MAC and actual.is_relative_to(cesto()):
            (papelera() / "info" / f"{actual.name}.trashinfo").unlink(missing_ok=True)
        ignorados.add(vuelta.name)  # para que el servicio no lo vuelva a mover
        mensajes.append((True, f"{vuelta.name}  →  {bonito(vuelta.parent)}"))
    _guardar_json("ignorados.json", sorted(ignorados))
    with (ESTADO / "historial.jsonl").open("w", encoding="utf-8") as h:
        h.writelines(json.dumps(r, ensure_ascii=False) + "\n" for i, r in enumerate(registros) if i not in indices)
    return mensajes


def deshacer(n=1):
    total = len(_historial())
    if n < 1 or not total:
        print("No hay movimientos que deshacer.")
        return
    for ok, mensaje in deshacer_indices(range(max(0, total - n), total)):
        print(f"  {'↩' if ok else '✗'} {mensaje}")


def historial(n=15):
    registros = _historial()[-n:]
    if not registros:
        print("Todavía no se ha movido nada.")
    for r in registros:
        fecha, nombre = gris(r["fecha"].replace("T", " ")), Path(r["desde"]).name
        if r.get("duplicado_de"):
            print(f"  {fecha}  {nombre}  →  papelera {gris('(igual a ' + bonito(r['duplicado_de']) + ')')}")
        else:
            print(f"  {fecha}  {nombre}  →  {bonito(Path(r['hacia']).parent)}")


def explicar(f):
    f = Path(f).expanduser()
    if not f.is_file():
        sys.exit(f"No existe el archivo: {f}")
    res = clasificar(f, leer_reglas())
    print(negrita(f.name))
    if not res.tabla:
        print(gris("  Ninguna palabra clave coincidió."))
    for destino, (puntos, pistas) in sorted(res.tabla.items(), key=lambda x: -x[1][0]):
        elegido = destino == res.destino or (destino.startswith("*/") and (res.destino or "").endswith(destino[1:]))
        marca = "✓" if elegido else " "
        print(f"  {marca} {puntos:>3} pts  {destino}")
        print(gris(f"            {', '.join(pistas)}"))
    destino = bonito(ruta_destino(res.destino)) if res.destino else "se queda en Descargas"
    print(f"\n  → {negrita(destino)}  {gris('(' + res.motivo + ')')}")


def propia(carpeta, destinos):
    """Subcarpeta que creaste tú dentro de un destino (ej. Screenshots/Clase): se respeta."""
    return carpeta not in destinos and any(carpeta.is_relative_to(d) for d in destinos)


def fuera_de_lugar(carpeta):
    """[(archivo, carpeta donde debería estar, motivo)] según las reglas. No mueve nada."""
    raiz, reglas, lista = real(carpeta), leer_reglas(), []
    destinos = {real(ruta_destino(r.destino)) for r in reglas if not r.comodin}
    for f in sorted(p for p in raiz.rglob("*") if p.is_file() and not p.name.startswith(".")):
        if propia(f.parent, destinos):
            continue
        res = clasificar(f, reglas)
        if res.destino and real(ruta_destino(res.destino)) != f.parent:
            lista.append((f, ruta_destino(res.destino), res.motivo))
    return lista


def mover(f, carpeta, **extra):
    """Mueve sin pisar nada y lo anota en el historial (para poder deshacer)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    nuevo = libre(carpeta, f.name)
    shutil.move(str(f), str(nuevo))
    _registrar(f, nuevo, **extra)
    return nuevo


def revisar(carpeta):
    lista = fuera_de_lugar(carpeta)
    for f, destino, motivo in lista:
        print(f"  {bonito(f)}\n      → {bonito(destino)}  {gris(f'({motivo})')}")
    distintos = len(lista)
    print(f"\n{distintos} archivo(s) estarían en otro lugar según tus reglas. No se movió nada.")
    print(gris("Las subcarpetas que creaste tú dentro de un destino se respetan y no se revisan."))


def autor(f):
    """Autor guardado en el documento (Office/LibreOffice/PDF), o ''."""
    ext = f.suffix.lower()
    try:
        if ext in OFIMATICA:
            with zipfile.ZipFile(f) as z:
                for parte in ("docProps/core.xml", "meta.xml"):
                    if parte in z.namelist():
                        m = re.search(r"<(?:dc:creator|meta:initial-creator)>([^<]+)<", _leer_miembro(z, parte))
                        if m:
                            return m.group(1).strip()
        if ext == ".pdf" and shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", "--", str(f)], capture_output=True, text=True, timeout=10)
            m = re.search(r"^Author:\s*(.+)$", info.stdout, re.M)
            if m:
                return m.group(1).strip()
    except (OSError, zipfile.BadZipFile, subprocess.SubprocessError, ValueError):
        pass
    return ""


def _mi_nombre():
    try:
        import pwd
        return normalizar(pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0]).strip()
    except (ImportError, KeyError):
        return ""


NOMBRE = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[ \t]+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}"  # sin saltar de línea


def candidatas(f):
    """Pistas de identidad que se ven en el archivo: autor, códigos de materia y docentes."""
    portada = re.sub(r"[ \t]+", " ", contenido(f))[:3000]
    vistas, pistas = {_mi_nombre(), ""} | no_sugerir(), []
    encontradas = [autor(f)]
    encontradas += re.findall(r"\b[A-Z]{2,5}-\d{3,4}(?:-\d{2,4})?\b", portada)
    encontradas += re.findall(r"(?:Prof(?:esora?)?\.?|Docente|Maestr[oa]|Teacher|Facilitador[a]?|Presentado a)"
                              r"[ \t]*:?[ \t]*(?:Prof\.?[ \t]*)?(" + NOMBRE + ")", portada)
    for p in encontradas:
        clave = normalizar(p).strip()
        if len(clave) > 3 and not any(clave in v or v in clave for v in vistas if v):
            vistas.add(clave)
            pistas.append(p.strip())
    return pistas


def agregar_fuertes(destino, pistas, ruta=None):
    """Agrega pistas a la línea 'fuertes:' del bloque [destino] (o crea el bloque)."""
    ruta = ruta or CONFIG
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    nuevas = ", ".join(p.strip() for p in pistas)
    try:
        i = next(n for n, l in enumerate(lineas) if l.strip() == f"[{destino}]")
    except StopIteration:
        lineas += ["", f"[{destino}]", f"fuertes: {nuevas}"]
    else:
        fin = next((n for n in range(i + 1, len(lineas)) if lineas[n].strip().startswith("[")), len(lineas))
        f = next((n for n in range(i + 1, fin) if lineas[n].strip().lower().startswith("fuertes:")), None)
        if f is not None:
            lineas[f] = lineas[f].rstrip().rstrip(",") + ", " + nuevas
        else:
            j = i + 1
            while j < fin and lineas[j].strip().startswith("#"):
                j += 1
            lineas.insert(j, f"fuertes: {nuevas}")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def destino_de(carpeta):
    """Nombre del bloque de reglas para una carpeta (el existente o uno nuevo relativo a HOME)."""
    carpeta, casa = real(carpeta), real(HOME)
    return next((r.destino for r in leer_reglas() if not r.comodin and real(ruta_destino(r.destino)) == carpeta),
                str(carpeta.relative_to(casa)) if carpeta.is_relative_to(casa) else str(carpeta))


def pistas_nuevas(f, destino):
    """Pistas de identidad del archivo que ese destino todavía no conoce."""
    ya = {p for r in leer_reglas() if r.destino == destino for p in r.fuertes}
    return [p for p in candidatas(f) if normalizar(p).strip() not in ya]


def corregir(archivo, carpeta, pistas=None, todas=False):
    f, carpeta = real(archivo), Path(carpeta).expanduser()
    if not f.is_file():
        sys.exit(f"No existe el archivo: {f}")
    carpeta = real(carpeta if carpeta.is_absolute() else HOME / carpeta)
    destino = destino_de(carpeta)

    if f.parent != carpeta:
        nuevo = mover(f, carpeta, corregido=True)
        print(f"  📁 {f.name}  →  {bonito(carpeta)}")
        f = nuevo

    if pistas is None:
        sugeridas = pistas_nuevas(f, destino)
        if not sugeridas:
            print(gris("  No encontré pistas nuevas (autor, código o docente) para aprender."))
            pistas = []
        elif todas:
            pistas = sugeridas
        else:
            print("\n  Pistas que encontré en el archivo:")
            for n, p in enumerate(sugeridas, 1):
                print(f"    {n}. {p}")
            if not sys.stdin.isatty():
                print(gris("  (Agrégalas con --todas o --pista TEXTO)"))
                pistas = []
            else:
                elegidas = input("  ¿Cuáles agrego a esa carpeta? (ej. 1,3 · Enter = ninguna): ")
                pistas = [sugeridas[int(n) - 1] for n in re.findall(r"\d+", elegidas)
                          if 0 < int(n) <= len(sugeridas)]
    if pistas:
        agregar_fuertes(destino, pistas)
        print(f"  ✓ Aprendido para [{destino}]: {', '.join(pistas)}")

    res = clasificar(f, leer_reglas())
    if res.destino and real(ruta_destino(res.destino)) == carpeta:
        print(f"  ✓ La próxima vez un archivo así irá solo a {bonito(carpeta)}")
    else:
        print(f"  ⚠ Con las reglas actuales todavía iría a "
              f"{bonito(ruta_destino(res.destino)) if res.destino else 'Descargas'}. "
              f"Mira por qué con: ordenito explicar \"{f}\"")


def grupos_duplicados(carpeta):
    """Grupos de archivos idénticos. El primero de cada grupo es el que conviene conservar."""
    raiz = Path(carpeta).expanduser()
    por_tam = {}
    for f in raiz.rglob("*"):
        if f.is_file() and not f.is_symlink() and not f.name.startswith(".") and f.stat().st_size > 0:
            por_tam.setdefault(f.stat().st_size, []).append(f)
    grupos = {}
    for mismos in (v for v in por_tam.values() if len(v) > 1):
        for f in mismos:
            grupos.setdefault(huella(f), []).append(f)
    copia = re.compile(r"\s*\(\d+\)$")
    resultado = []
    for g in (g for g in grupos.values() if len(g) > 1):
        # Se queda el de nombre "limpio" (sin "(1)") y, si empatan, el más antiguo
        g.sort(key=lambda f: (bool(copia.search(f.stem)), f.stat().st_mtime, len(f.name)))
        resultado.append(g)
    return sorted(resultado, key=lambda g: str(g[0]))


def quitar_copias(grupos):
    """Manda a la papelera todo menos el primero de cada grupo. -> (copias, bytes)"""
    n, ahorro = 0, 0
    for g in grupos:
        for f in g[1:]:
            if f.exists():
                ahorro += f.stat().st_size
                _registrar(f, a_papelera(f), duplicado_de=str(g[0]))
                n += 1
    return n, ahorro


def duplicados(carpeta, quitar=False):
    """Busca archivos idénticos; con quitar=True manda las copias sobrantes a la papelera."""
    sobran, ahorro = 0, 0
    for g in grupos_duplicados(carpeta):
        print(f"  ✓ {bonito(g[0])}")
        for f in g[1:]:
            sobran, ahorro = sobran + 1, ahorro + f.stat().st_size
            if quitar:
                _registrar(f, a_papelera(f), duplicado_de=str(g[0]))
                print(f"    🗑 {bonito(f)}")
            else:
                print(f"    = {bonito(f)}")
    if not sobran:
        print("No hay archivos duplicados.")
    elif quitar:
        print(f"\n{sobran} copia(s) a la papelera ({ahorro / 1e6:.1f} MB). Se recuperan con 'ordenito deshacer {sobran}'.")
    else:
        print(f"\n{sobran} copia(s) repetida(s), {ahorro / 1e6:.1f} MB. Quítalas con: ordenito duplicados {carpeta} --papelera")


# ─────────────────────── edición de reglas ───────────────────────

def _limites_bloque(lineas, destino):
    """(inicio, fin) del bloque [destino] en las líneas, o None."""
    i = next((n for n, l in enumerate(lineas) if l.strip() == f"[{destino}]"), None)
    if i is None:
        return None
    fin = next((n for n in range(i + 1, len(lineas)) if lineas[n].strip().startswith("[")), len(lineas))
    while fin > i + 1 and not lineas[fin - 1].strip():  # las líneas en blanco del final no son del bloque
        fin -= 1
    return i, fin


def guardar_bloque(destino, fuertes=(), palabras=(), extensiones=(), anterior=None, ruta=None):
    """Crea o reemplaza un bloque de reglas. Conserva los comentarios del bloque anterior."""
    ruta = ruta or CONFIG
    lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []
    nuevo = [f"[{destino}]"]
    lim = _limites_bloque(lineas, anterior or destino)
    if lim:
        nuevo += [l for l in lineas[lim[0] + 1:lim[1]] if l.strip().startswith("#")]
    if extensiones:
        nuevo.append("extensiones: " + ", ".join(e.lstrip(".") for e in extensiones))
    if fuertes:
        nuevo.append("fuertes: " + ", ".join(fuertes))
    if palabras:
        nuevo.append(", ".join(palabras))
    if lim:
        lineas[lim[0]:lim[1]] = nuevo
    else:
        lineas += ["", *nuevo]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def eliminar_bloque(destino, ruta=None):
    """Quita un bloque de reglas (la carpeta y sus archivos no se tocan)."""
    ruta = ruta or CONFIG
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    lim = _limites_bloque(lineas, destino)
    if lim:
        del lineas[lim[0]:lim[1]]
        ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# ───────────────────────── servicio y sistema ─────────────────────────

ETIQUETA_MAC = "com.gr8coolmind.ordenito"


def _plist():
    return HOME / "Library" / "LaunchAgents" / f"{ETIQUETA_MAC}.plist"


def servicio_activo():
    """¿Está vigilando Descargas el servicio automático?"""
    try:
        if MAC:
            return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{ETIQUETA_MAC}"],
                                  capture_output=True, timeout=10).returncode == 0
        return subprocess.run(["systemctl", "--user", "is-active", "--quiet", "ordenito.path"],
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def cambiar_servicio(encender):
    """Enciende o apaga el servicio. Devuelve True si quedó como se pidió."""
    try:
        if MAC:
            accion = "bootstrap" if encender else "bootout"
            subprocess.run(["launchctl", accion, f"gui/{os.getuid()}", str(_plist())],
                           capture_output=True, timeout=15)
        else:
            subprocess.run(["systemctl", "--user", "enable" if encender else "disable", "--now",
                            "ordenito.path"], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass
    return servicio_activo() == encender


def abrir(ruta):
    """Abre una carpeta o archivo con la aplicación del sistema."""
    subprocess.Popen(["open" if MAC else "xdg-open", str(ruta)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ───────────────────────────── consola ─────────────────────────────

def _color(codigo):
    usar = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    return lambda t: f"\033[{codigo}m{t}\033[0m" if usar else t


negrita, gris = _color("1"), _color("2")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ordenito", description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=f"Reglas: {bonito(CONFIG)}")
    p.add_argument("--version", action="version", version=f"ordenito {__version__}")
    sub = p.add_subparsers(dest="comando", metavar="comando")
    sub.add_parser("ordenar", help="ordena Descargas ahora (lo que hace el servicio)")
    sub.add_parser("simular", help="muestra lo que haría, sin mover nada")
    s = sub.add_parser("explicar", help="a dónde iría un archivo y por qué")
    s.add_argument("archivo")
    s = sub.add_parser("revisar", help="busca archivos que estarían mejor en otra carpeta")
    s.add_argument("carpeta", nargs="?", default="~/Documents")
    s = sub.add_parser("historial", help="últimos movimientos")
    s.add_argument("n", nargs="?", type=int, default=15)
    s = sub.add_parser("deshacer", help="devuelve a su lugar los últimos N archivos")
    s.add_argument("n", nargs="?", type=int, default=1)
    s = sub.add_parser("corregir", help="mueve un archivo a donde va y aprende la pista que faltaba")
    s.add_argument("archivo")
    s.add_argument("carpeta", help="carpeta correcta (ej. ~/Documents/Universidad/Redes)")
    s.add_argument("--pista", action="append", metavar="TEXTO", help="pista fuerte a aprender (repetible)")
    s.add_argument("--todas", action="store_true", help="aprende todas las pistas sugeridas sin preguntar")
    s = sub.add_parser("servicio", help="enciende, apaga o muestra el servicio automático")
    s.add_argument("accion", nargs="?", choices=["encender", "apagar", "estado"], default="estado")
    s = sub.add_parser("duplicados", help="busca archivos idénticos repetidos")
    s.add_argument("carpeta", nargs="?", default="~/Documents")
    s.add_argument("--papelera", action="store_true", help="manda las copias sobrantes a la papelera")
    a = p.parse_args(argv)

    if a.comando in (None, "ordenar"):
        ordenar()
    elif a.comando == "simular":
        print(negrita(f"Simulación sobre {bonito(carpeta_descargas())}:"))
        ordenar(simular=True)
    elif a.comando == "explicar":
        explicar(a.archivo)
    elif a.comando == "revisar":
        revisar(a.carpeta)
    elif a.comando == "historial":
        historial(a.n)
    elif a.comando == "deshacer":
        deshacer(a.n)
    elif a.comando == "corregir":
        corregir(a.archivo, a.carpeta, a.pista, a.todas)
    elif a.comando == "duplicados":
        duplicados(a.carpeta, a.papelera)
    elif a.comando == "servicio":
        if a.accion != "estado" and not cambiar_servicio(a.accion == "encender"):
            sys.exit("No pude cambiar el servicio. ¿Ejecutaste ./instalar.sh?")
        print("Servicio " + ("encendido: vigilando " + bonito(carpeta_descargas())
                             if servicio_activo() else "apagado"))


if __name__ == "__main__":
    main()
