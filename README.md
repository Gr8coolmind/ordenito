<div align="center">

# 🗂️ Ordenito

**Tus descargas se ordenan solas.**
Ordenito lee el nombre *y el contenido* de cada archivo que descargas y lo lleva a la carpeta que le corresponde, al instante.

[![Pruebas](https://github.com/Gr8coolmind/ordenito/actions/workflows/pruebas.yml/badge.svg)](https://github.com/Gr8coolmind/ordenito/actions/workflows/pruebas.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-systemd-FCC624?logo=linux&logoColor=black)
![Sin dependencias](https://img.shields.io/badge/dependencias-0-success)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)

</div>

---

```text
📥 Descargas/
 ├─ Tarea3_subnetting.docx         ──▶  📁 Universidad/Redes
 ├─ informe-final-tienda.md        ──▶  📁 Universidad/Redes/Proyecto Final
 ├─ factura_octubre.pdf             ──▶  📁 Personal/Finanzas
 ├─ indicador_fvg.pine              ──▶  📁 Trading/Indicadores
 ├─ dark-forest-3840x2160.jpg       ──▶  🖼️ Pictures/Wallpapers
 └─ Bazaar.flatpakref               ──▶  📦 Descargas/Instaladores
```

La mayoría de los organizadores solo miran la extensión: todos los PDF juntos, todas las imágenes juntas. **Ordenito lee lo que dice el documento.** Una tarea que menciona a tu profesora y el código de la materia va a la carpeta de esa materia, aunque se llame `documento(3).docx`.

## ✨ Qué lo hace distinto

| | |
|---|---|
| 🧠 **Lee el contenido** | Word, PowerPoint, Excel, LibreOffice, PDF, texto, código… y hasta los nombres de lo que trae un `.zip` (sin descomprimirlo). |
| ⚡ **Al instante** | Un servicio de systemd vigila tu carpeta de descargas. Unos 2 segundos después de terminar una descarga, el archivo ya está en su lugar. |
| 🪪 **Reconoce al dueño del documento** | Lee el autor, el título, los encabezados y la portada. Si una tarea es *del* profesor de Seguridad, va a Seguridad, aunque hable mucho de redes. |
| 🪆 **Entiende subcarpetas** | Si un archivo encaja en `Universidad` y también en `Universidad/Redes`, va a la más específica. |
| 🃏 **Comodines** | `[*/Proyecto Final]` crea esa subcarpeta dentro de *cualquier* materia que gane. |
| 🔍 **Te explica sus decisiones** | `ordenito explicar archivo.pdf` muestra los puntos de cada carpeta y las palabras que coincidieron. |
| 🎓 **Aprende de tus correcciones** | `ordenito corregir archivo carpeta` lo mueve a donde va y te ofrece aprender la pista que faltaba (el autor, el código de la materia, el docente). |
| 👯 **Sin duplicados** | Si descargas algo que ya tenías, no guarda una copia `(1)`: la manda a la papelera y te avisa. `ordenito duplicados` encuentra las copias que ya tienes. |
| ↩️ **Se puede deshacer** | `ordenito deshacer` devuelve el archivo, y Ordenito no lo vuelve a mover. |
| 🔒 **100 % local** | No usa internet ni IA en la nube. Nada de tus documentos sale de tu computadora. |
| 🪶 **Cero dependencias** | Un solo archivo de Python, solo con la biblioteca estándar. `pdftotext` es opcional. |

## 🚀 Instalación

```bash
git clone https://github.com/Gr8coolmind/ordenito.git
cd ordenito
./instalar.sh
```

No necesita `sudo`. El instalador:
1. copia el programa a `~/.local/bin/ordenito`;
2. crea tus reglas en `~/.config/ordenito/reglas.conf` (a partir del [ejemplo](reglas.ejemplo.conf));
3. activa el servicio que vigila tu carpeta de descargas (la detecta sola, aunque tu sistema esté en español).

> 💡 Para que lea los PDF instala `pdftotext`: `sudo dnf install poppler-utils` · `sudo apt install poppler-utils` · `sudo pacman -S poppler`

## 🧭 Cómo decide

```mermaid
flowchart LR
    A[📄 Nueva descarga] --> B{¿Terminó de<br/>descargarse?}
    B -- no --> B
    B -- sí --> C[Lee nombre<br/>y contenido]
    C --> D[Puntúa cada carpeta<br/>de tus reglas]
    D --> E{¿Algún tema<br/>con ≥ 2 puntos?}
    E -- sí --> F[Gana el de más puntos<br/>→ baja a la subcarpeta<br/>más específica<br/>→ aplica comodines]
    E -- no --> G{¿Hay respaldo<br/>para su tipo?}
    G -- sí --> H[Carpeta por tipo<br/>Fotos, Videos…]
    G -- no --> I[Se queda en<br/>Descargas]
    F --> J[📁 Mueve + 🔔 avisa]
    H --> J
```

- Una pista **fuerte** (profesor, código de materia, empresa, cliente) vale **25 puntos** si aparece en el nombre, el autor, el encabezado o la portada, y **3** si solo se menciona de pasada en el cuerpo.
- Cada palabra clave en el **nombre** del archivo vale **10 puntos**.
- En el **contenido**, cada aparición vale **1 punto** (máximo 5 por palabra, así ninguna repetida gana sola).
- Las palabras se comparan **completas**, sin importar mayúsculas, tildes, guiones ni guiones bajos: `curso` no coincide dentro de `recurso`.

## 📝 Tus reglas

Las reglas se escriben en un archivo de texto muy simple, `~/.config/ordenito/reglas.conf`:

```ini
# [carpeta destino]   (relativa a tu HOME)
# palabras clave separadas por coma

[Documents/Universidad/Redes]
fuertes: red-1010, ana perez          # identidad: código y profesor
subnetting, vlan, cisco packet tracer # temas

# Comodín: dentro de cualquier materia, si menciona "proyecto final"
[*/Proyecto Final]
proyecto final, entrega final, capstone

# Solo para ciertos tipos de archivo
[Documents/Trading/Indicadores]
extensiones: pine, txt
@version=6, indicator(, strategy(

# Respaldo por tipo: solo extensiones, sin palabras
[Videos]
extensiones: mp4, mkv, webm
```

**Consejos para buenas reglas**
- Las mejores pistas son **únicas**: el nombre del profesor, el código de la materia, el nombre del cliente o de la empresa. Ponlas en `fuertes:` y escríbelas como salen en los documentos.
- Evita palabras que salen en todo (tu carrera, tu universidad): no ayudan a distinguir.
- Si dos materias comparten prefijo (`MAT-101-01` y `MAT-101-02`), usa el código **completo**.
- Después de editar, comprueba con `ordenito explicar` y `ordenito revisar`.

El [archivo de ejemplo](reglas.ejemplo.conf) trae categorías listas para estudios, trabajo, trading, documentos personales, imágenes y respaldos por tipo.

## 🛠️ Comandos

| Comando | Qué hace |
|---|---|
| `ordenito` | Ordena ahora lo que haya en Descargas (es lo que ejecuta el servicio). |
| `ordenito simular` | Muestra lo que haría, sin mover nada. |
| `ordenito explicar ARCHIVO` | Explica a qué carpeta iría un archivo y por qué. |
| `ordenito revisar [CARPETA]` | Busca archivos que, según tus reglas, estarían mejor en otro lugar. Respeta las subcarpetas que creaste tú. No mueve nada. |
| `ordenito historial [N]` | Muestra los últimos movimientos. |
| `ordenito deshacer [N]` | Devuelve a su lugar los últimos N archivos movidos (también los que fueron a la papelera). |
| `ordenito corregir ARCHIVO CARPETA` | Mueve un archivo mal clasificado y aprende la pista que faltaba. `--todas` acepta todas las sugerencias y `--pista TEXTO` agrega una a mano. |
| `ordenito duplicados [CARPETA]` | Lista archivos idénticos (compara el contenido, no el nombre). Con `--papelera` quita las copias y se queda con el nombre más limpio. |

```console
$ ordenito explicar Tarea3_redes.docx
Tarea3_redes.docx
      8 pts  Documents/Universidad/Redes
            red 1010 ×1, prof. ana perez ×1, subnetting ×1, vlan ×2, enrutamiento ×1, cisco packet tracer ×2
  ✓   1 pts  */Proyecto Final
            proyecto final ×1

  → ~/Documents/Universidad/Redes/Proyecto Final  (dentro del tema: proyecto final ×1)
```

### Cuando algo cae donde no va

```console
$ ordenito corregir "Caso de estudio 2.docx" ~/Documents/Universidad/Seguridad
  📁 Caso de estudio 2.docx  →  ~/Documents/Universidad/Seguridad

  Pistas que encontré en el archivo:
    1. Carlos Ruiz
    2. SEG-2040
  ¿Cuáles agrego a esa carpeta? (ej. 1,3 · Enter = ninguna): 1,2
  ✓ Aprendido para [Documents/Universidad/Seguridad]: Carlos Ruiz, SEG-2040
  ✓ La próxima vez un archivo así irá solo a ~/Documents/Universidad/Seguridad
```

Tu nombre y el de tus compañeros salen en todos tus trabajos, así que no sirven para distinguir. Ponlos en el bloque `[no sugerir]` y nunca se te ofrecerán como pistas.

## 🛡️ Seguridad y privacidad

- **Todo ocurre en tu equipo.** No hay red, telemetría ni servicios externos.
- **Nunca sobrescribe ni borra nada.** Si ya existe un `informe.pdf` distinto, guarda el nuevo como `informe (2).pdf`. Si es idéntico, la copia va a la **papelera** (no se borra) y se recupera con `ordenito deshacer`.
- **No toca descargas a medias.** Ignora `.part` y `.crdownload`, y espera a que el archivo deje de crecer.
- **Lee con límites.** Lee como máximo 2 MB por parte de cada documento y 5 páginas de cada PDF, así que una *zip bomb* no puede llenarte la memoria.
- **Corre con baja prioridad** (`Nice=10`, E/S en modo *idle*), sin `sudo` y solo dentro de tu usuario.
- Lleva un registro en `~/.local/state/ordenito/historial.jsonl`, que es lo que hace posible `deshacer`.

## 🧪 Pruebas

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas cubren la puntuación, las pistas fuertes (autor, encabezado y menciones de pasada), `corregir`, los duplicados, las rutas con enlaces de Silverblue, las subcarpetas, los comodines, los zips, los respaldos por tipo, los nombres repetidos, `deshacer` y la protección contra zip bombs. Se ejecutan en GitHub Actions con Python 3.9 a 3.13.

## 🗑️ Desinstalar

```bash
./desinstalar.sh          # quita el programa y el servicio; conserva tus reglas
./desinstalar.sh --todo   # también borra las reglas y el historial
```

Tus archivos se quedan donde Ordenito los dejó.

## ❓ Preguntas frecuentes

<details>
<summary><b>¿Funciona fuera de GNOME?</b></summary>

Sí. Solo necesita Linux con systemd (Fedora, Ubuntu, Debian, Arch, Bazzite, Silverblue…). Las notificaciones usan `notify-send`, y si no está, simplemente no avisa.
</details>

<details>
<summary><b>Abrí la descarga desde el navegador y dice que no existe</b></summary>

Ordenito ya la movió. La notificación te dice a dónde, y también lo ves con `ordenito historial`.
</details>

<details>
<summary><b>¿Puedo vigilar otra carpeta?</b></summary>

Sí. Usa la variable `ORDENITO_CARPETA` (por ejemplo, `ORDENITO_CARPETA=~/Escritorio ordenito simular`). Para el servicio, edita `PathChanged=` en `~/.config/systemd/user/ordenito.path`.
</details>

<details>
<summary><b>Un archivo cayó en la carpeta equivocada</b></summary>

Usa `ordenito corregir ARCHIVO CARPETA_CORRECTA`. Lo mueve y te ofrece aprender la pista que faltaba. Si quieres entender qué pasó, `ordenito explicar ARCHIVO` muestra los puntos de cada carpeta.
</details>

---

<details>
<summary>🇬🇧 <b>English</b></summary>

**Ordenito** auto-sorts your Downloads folder on Linux. Instead of sorting only by file extension, it reads each file's **name and content** (docx, pptx, xlsx, odt, pdf, text, code, and the file names inside zips) and scores it against simple keyword rules. A systemd path unit triggers it instantly whenever a download finishes. It supports nested folders (the most specific one wins), wildcard subfolders such as `[*/Final Project]`, per-extension rules, type-based fallbacks, `explain`/`review`/`history`/`undo` commands, and runs 100% locally with zero dependencies. Install with `./instalar.sh`. The CLI and docs are in Spanish.
</details>

<div align="center">
<sub>Hecho con ☕ por Gr8coolmind</sub>
</div>
