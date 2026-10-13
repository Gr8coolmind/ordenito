#!/usr/bin/env python3
"""Ordenito: ordena tus descargas solo, leyendo el nombre y el contenido de cada archivo.

Comandos:
  ordenito                    ordena lo que haya en Descargas (lo que hace el servicio)
  ordenito simular            muestra lo que haría, sin mover nada
  ordenito explicar ARCHIVO   explica a qué carpeta iría un archivo y por qué
  ordenito revisar CARPETA    busca archivos que según tus reglas están en otro lugar
  ordenito historial [N]      últimos movimientos
  ordenito deshacer [N]       devuelve a Descargas los últimos N archivos movidos
"""
from __future__ import annotations

import argparse
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

__version__ = "1.1.0"

HOME = Path.home()
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

    @property
    def comodin(self):
        """[*/Proyecto Final]: subcarpeta que aplica dentro de cualquier tema."""
        return self.destino.startswith("*/")

    @property
    def respaldo(self):
        """Bloque con solo 'extensiones:': clasifica por tipo si ningún tema coincidió."""
        return not self.palabras and not self.fuertes


def leer_reglas(ruta=None):
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
            reglas[-1].fuertes.extend(normalizar(p).strip() for p in linea.split(":", 1)[1].split(",") if p.strip())
        elif linea.lower().startswith("extensiones:"):
            reglas[-1].extensiones.update(
                "." + e.strip().lstrip(".").lower()
                for e in linea.split(":", 1)[1].split(",") if e.strip())
        else:
            reglas[-1].palabras.extend(normalizar(p).strip() for p in linea.split(",") if p.strip())
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


def bonito(ruta):
    ruta = Path(ruta)
    return "~/" + str(ruta.relative_to(HOME)) if ruta.is_relative_to(HOME) else str(ruta)


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


def notificar(titulo, cuerpo):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Ordenito", "-i", "folder-documents", titulo, cuerpo],
                       check=False)


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
        nuevo = libre(ruta_destino(res.destino), f.name)
        if simular:
            print(f"  {f.name}  →  {bonito(nuevo.parent)}  {gris(f'({res.puntos} pts, {res.motivo})')}")
            continue
        nuevo.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(nuevo))
        movidos += 1
        ESTADO.mkdir(parents=True, exist_ok=True)
        with (ESTADO / "historial.jsonl").open("a", encoding="utf-8") as h:
            h.write(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"),
                                "desde": str(f), "hacia": str(nuevo), "puntos": res.puntos},
                               ensure_ascii=False) + "\n")
        if avisar:
            notificar("Descarga ordenada", f"{f.name}\n→ {bonito(nuevo.parent)}")
    return movidos


def deshacer(n=1):
    registros = _historial()
    if n < 1 or not registros:
        print("No hay movimientos que deshacer.")
        return
    ultimos, resto = registros[-n:], registros[:-n]
    ignorados = set(_json("ignorados.json", []))
    for r in reversed(ultimos):
        actual, origen = Path(r["hacia"]), Path(r["desde"])
        if not actual.exists():
            print(f"  ✗ {actual.name}: ya no está en {bonito(actual.parent)}, lo salto")
            continue
        vuelta = libre(origen.parent, origen.name)
        shutil.move(str(actual), str(vuelta))
        ignorados.add(vuelta.name)  # para que el servicio no lo vuelva a mover
        print(f"  ↩ {vuelta.name}  →  {bonito(vuelta.parent)}")
    _guardar_json("ignorados.json", sorted(ignorados))
    with (ESTADO / "historial.jsonl").open("w", encoding="utf-8") as h:
        h.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in resto)


def historial(n=15):
    registros = _historial()[-n:]
    if not registros:
        print("Todavía no se ha movido nada.")
    for r in registros:
        print(f"  {gris(r['fecha'].replace('T', ' '))}  {Path(r['hacia']).name}  →  "
              f"{bonito(Path(r['hacia']).parent)}")


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


def revisar(carpeta):
    raiz, reglas, distintos = Path(carpeta).expanduser(), leer_reglas(), 0
    destinos = {ruta_destino(r.destino) for r in reglas if not r.comodin}
    for f in sorted(p for p in raiz.rglob("*") if p.is_file() and not p.name.startswith(".")):
        if propia(f.parent, destinos):
            continue
        res = clasificar(f, reglas)
        if res.destino and ruta_destino(res.destino) != f.parent:
            distintos += 1
            print(f"  {bonito(f)}\n      → {bonito(ruta_destino(res.destino))}  {gris(f'({res.motivo})')}")
    print(f"\n{distintos} archivo(s) estarían en otro lugar según tus reglas. No se movió nada.")
    print(gris("Las subcarpetas que creaste tú dentro de un destino se respetan y no se revisan."))


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
    s = sub.add_parser("deshacer", help="devuelve a Descargas los últimos N archivos")
    s.add_argument("n", nargs="?", type=int, default=1)
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


if __name__ == "__main__":
    main()
