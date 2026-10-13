# 🍎 Ordenito en Mac: tutorial paso a paso

Esta guía es para alguien que **nunca ha usado la Terminal**. Toma unos 10 minutos y solo hay que hacerla una vez. Al final vas a tener:

- tus descargas ordenándose solas, apenas terminan de bajar;
- la app **Ordenito** en Aplicaciones para revisar, corregir y configurar tus carpetas con botones.

Funciona en **macOS 11 (Big Sur) o más nuevo**, en Macs con Intel y con Apple Silicon (M1, M2, M3, M4…).

---

## Índice

1. [Abrir la Terminal](#1-abrir-la-terminal)
2. [Instalar Homebrew](#2-instalar-homebrew)
3. [Instalar lo que necesita Ordenito](#3-instalar-lo-que-necesita-ordenito)
4. [Descargar e instalar Ordenito](#4-descargar-e-instalar-ordenito)
5. [Dar permiso de acceso al disco](#5-dar-permiso-de-acceso-al-disco-muy-importante)
6. [Abrir la app y crear tus carpetas](#6-abrir-la-app-y-crear-tus-carpetas)
7. [Probar que funciona](#7-probar-que-funciona)
8. [Ordenar lo que ya tienes desordenado](#8-ordenar-lo-que-ya-tienes-desordenado)
9. [Actualizar, pausar o desinstalar](#9-actualizar-pausar-o-desinstalar)
10. [Si algo no funciona](#10-si-algo-no-funciona)

---

## 1. Abrir la Terminal

1. Pulsa **Cmd ⌘ + Espacio** para abrir Spotlight.
2. Escribe **Terminal** y pulsa **Enter**.

Se abre una ventana con texto. Ahí vas a **pegar** los comandos de esta guía: cópialos de aquí, pégalos con **Cmd ⌘ + V** y pulsa **Enter**.

> 💡 Cuando la Terminal pida tu **contraseña**, al escribirla no se ve nada (ni puntitos). Es normal: escríbela y pulsa Enter.

## 2. Instalar Homebrew

[Homebrew](https://brew.sh/es/) es el instalador de programas más usado en Mac. Ordenito lo necesita para instalar Python con soporte de ventanas y el lector de PDF.

**¿Ya lo tienes?** Pega esto:

```bash
brew --version
```

Si sale algo como `Homebrew 4.x.x`, ya lo tienes: salta al [paso 3](#3-instalar-lo-que-necesita-ordenito). Si sale `command not found`, instálalo:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

- Te pedirá tu contraseña del Mac y que pulses **Enter** para confirmar.
- Puede pedirte instalar las **Herramientas de línea de comandos de Xcode**: acepta y espera (unos minutos).
- **Muy importante:** al terminar, Homebrew muestra una sección **"Next steps"** con 2 o 3 comandos que empiezan con `echo` y `eval`. **Cópialos y pégalos** tal cual. En Macs con Apple Silicon suelen ser:

  ```bash
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
  eval "$(/opt/homebrew/bin/brew shellenv)"
  ```

Comprueba que quedó bien con `brew --version`.

## 3. Instalar lo que necesita Ordenito

```bash
brew install python-tk poppler git
```

| Programa | Para qué |
|---|---|
| `python-tk` | Python con soporte de ventanas (la app de Ordenito) |
| `poppler` | Leer el contenido de los PDF |
| `git` | Descargar y actualizar Ordenito |

## 4. Descargar e instalar Ordenito

```bash
git clone https://github.com/Gr8coolmind/ordenito.git ~/ordenito
cd ~/ordenito
./instalar.sh
```

Deberías ver algo así:

```text
✓ Programa:  /Users/tu-usuario/.local/bin/ordenito
✓ App:       /Users/tu-usuario/Applications/Ordenito.app (ábrela desde Aplicaciones o Launchpad)
✓ Reglas:    /Users/tu-usuario/.config/ordenito/reglas.conf (ejemplo, edítalas a tu gusto)
✓ Servicio:  vigilando /Users/tu-usuario/Downloads (launchd)
```

Al final, el instalador muestra un aviso de **"ÚLTIMO PASO EN MAC"** con una **ruta de Python**. Déjala a la vista: la necesitas en el paso siguiente.

> **¿No tienes git o prefieres no usar la Terminal para descargar?** En la [página de Ordenito](https://github.com/Gr8coolmind/ordenito) pulsa el botón verde **Code → Download ZIP**, descomprímelo y mueve la carpeta a tu carpeta personal con el nombre `ordenito`. Después, en la Terminal: `cd ~/ordenito && ./instalar.sh`

> **Para usar el comando `ordenito` en la Terminal** (opcional, la app no lo necesita):
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
> ```

## 5. Dar permiso de acceso al disco (muy importante)

macOS protege tus carpetas **Descargas**, **Documentos** y **Escritorio**: ningún programa que funcione en segundo plano puede leerlas sin tu permiso. **Sin este paso, Ordenito no podrá mover nada.**

El instalador ya abrió la ventana correcta. Si no se abrió, ve a:
**Ajustes del Sistema → Privacidad y seguridad → Acceso total al disco**

1. Pulsa el botón **+** (abajo de la lista). Te pedirá tu contraseña o Touch ID.
2. En la ventana para elegir archivos, pulsa **Cmd ⌘ + Shift ⇧ + G**.
3. **Pega la ruta de Python** que mostró el instalador. Es parecida a una de estas:

   ```text
   /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9
   /opt/homebrew/Cellar/python@3.13/3.13.x/Frameworks/Python.framework/Versions/3.13/bin/python3.13
   ```
4. Pulsa **Enter** y luego **Abrir**.
5. Asegúrate de que el **interruptor** al lado del nuevo elemento (`python3.x`) esté **encendido**.

> **¿Perdiste la ruta?** Pégala de nuevo en la Terminal con:
> ```bash
> grep -A1 ProgramArguments ~/Library/LaunchAgents/com.gr8coolmind.ordenito.plist | tail -1 | sed 's/.*<string>\(.*\)<\/string>.*/\1/'
> ```

> 🔒 **¿Es seguro?** Este permiso es para Python, el programa que ejecuta Ordenito. Ordenito trabaja **solo en tu Mac**: no usa internet ni envía nada a ningún lado, y su código es público para que cualquiera lo revise.

## 6. Abrir la app y crear tus carpetas

1. Abre **Ordenito** desde **Aplicaciones** (en tu carpeta personal → Aplicaciones) o búscalo en **Launchpad** o con **Cmd ⌘ + Espacio**.
2. Si macOS pregunta *"Ordenito quiere acceder a archivos de la carpeta Documentos"*, pulsa **Permitir**.
3. Si es la primera vez, se abre el asistente **"¡Hola! Vamos a armar tus carpetas"**:
   - **Marca lo que quieres ordenar**: finanzas, CV, fondos de pantalla, instaladores…
   - **Universidad o colegio**: escribe cada **materia** con su **profesor(a)** y **código**. Son las mejores pistas, porque casi siempre salen en la portada o el encabezado de las tareas. Si no sabes el código, déjalo vacío.
   - **Empresa**: si trabajas o haces pasantía, su nombre.
   - **Tu nombre completo**: sale en todos tus trabajos, así que Ordenito nunca lo usará como pista.
   - Pulsa **Crear mis carpetas**.

> Si ya habías instalado antes y quieres el asistente, abre la pestaña **Carpetas → Carpetas recomendadas…**

### Qué hay en cada pestaña

| Pestaña | Para qué sirve |
|---|---|
| **Actividad** | Lo último que se movió. Selecciona un archivo y usa **Deshacer**, **Corregir…** (lo mueves y Ordenito aprende), **¿Por qué fue aquí?** o **Abrir carpeta**. |
| **En Descargas** | Lo que hay ahora en Descargas y **a dónde iría** cada archivo, antes de moverlo. |
| **Carpetas** | Tus carpetas y sus pistas. **Nueva**, **Editar**, **Quitar**, sin tocar archivos de texto. |
| **Revisar** | Elige una carpeta y te muestra qué archivos estarían mejor en otro lugar. |
| **Duplicados** | Encuentra copias idénticas y manda las sobrantes a la papelera. |

Arriba a la derecha, **Ordenar automáticamente** enciende o pausa el servicio, y **Ordenar ahora** ordena lo que haya en Descargas en ese momento.

## 7. Probar que funciona

1. Descarga cualquier PDF o imagen de internet (por ejemplo, un fondo de pantalla 4K).
2. Unos segundos después debería **desaparecer de Descargas**. Verás una notificación **"Descarga ordenada"** con la carpeta a la que fue.
3. En la app, pestaña **Actividad**, aparece el movimiento.

Si no se movió, ve a [Si algo no funciona](#10-si-algo-no-funciona).

## 8. Ordenar lo que ya tienes desordenado

Ordenito vigila lo que **llega** a Descargas, pero también te ayuda con lo que ya tienes:

1. **Descargas llena de cosas viejas**: pestaña **En Descargas** → revisa la columna "Irá a" → **Ordenar ahora** (botón azul).
2. **Documentos o Escritorio desordenados**: pestaña **Revisar** → **Elegir carpeta y revisar…** → elige la carpeta → selecciona los archivos y pulsa **Mover seleccionados** (o **Mover todos**).
3. **Archivos repetidos**: pestaña **Duplicados** → **Elegir carpeta y buscar…** → **Mandar copias a la papelera**.

Todo se puede deshacer desde **Actividad → Deshacer**. Nada se borra: lo repetido va a la **Papelera**.

> 💡 **Consejo:** si algo cae en la carpeta equivocada, no lo muevas a mano en el Finder. Usa **Actividad → Corregir…**: así Ordenito aprende y la próxima vez lo hace bien solo.

## 9. Actualizar, pausar o desinstalar

**Actualizar Ordenito** (tus carpetas y reglas no se tocan):

```bash
cd ~/ordenito && git pull && ./instalar.sh
```

**Pausar** el orden automático: en la app, desmarca **Ordenar automáticamente**. O en la Terminal: `ordenito servicio apagar` (y `encender` para volver).

**Desinstalar:**

```bash
cd ~/ordenito && ./desinstalar.sh          # quita la app y el servicio; conserva tus reglas
cd ~/ordenito && ./desinstalar.sh --todo   # también borra tus reglas y el historial
```

Tus archivos se quedan donde están. Si quieres, quita también Python de **Acceso total al disco** con el botón **−**.

## 10. Si algo no funciona

<details>
<summary><b>Las descargas no se mueven solas</b></summary>

1. Comprueba el **paso 5** (Acceso total al disco): el interruptor de Python debe estar encendido.
2. Mira si hay errores:
   ```bash
   cat ~/.local/state/ordenito/errores.log
   ```
   Si dice **`Operation not permitted`**, falta el permiso del paso 5, o se le dio a otro Python. Vuelve a ejecutar `./instalar.sh` y usa la ruta que muestre al final.
3. Comprueba que el servicio está encendido:
   ```bash
   ~/.local/bin/ordenito servicio
   ```
4. Mira si el archivo tiene una carpeta asignada: en la app, pestaña **En Descargas**. Si dice *"Se queda en Descargas"*, ninguna regla lo reconoce: usa **Mover a…** para enseñarle.
</details>

<details>
<summary><b>La app Ordenito no aparece en Aplicaciones</b></summary>

El instalador no encontró un Python con soporte de ventanas. Ejecuta:

```bash
brew install python-tk
cd ~/ordenito && ./instalar.sh
```

Debería aparecer la línea `✓ App: …/Ordenito.app`. La app está en **tu carpeta personal → Aplicaciones** (no en la de Aplicaciones del sistema).
</details>

<details>
<summary><b>"command not found: ordenito"</b></summary>

Usa la ruta completa, `~/.local/bin/ordenito`, o agrega la carpeta a tu PATH una vez:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```
</details>

<details>
<summary><b>Dejó de funcionar después de actualizar macOS o Homebrew</b></summary>

Vuelve a instalar (tus reglas no se tocan) y revisa el permiso del paso 5 con la ruta que muestre:

```bash
cd ~/ordenito && git pull && ./instalar.sh
```
</details>

<details>
<summary><b>"xcrun: error: invalid active developer path"</b></summary>

Faltan las herramientas de desarrollo de Apple, que traen git y Python:

```bash
xcode-select --install
```

Acepta la ventana que aparece y, cuando termine, repite el paso que falló.
</details>

<details>
<summary><b>Un archivo fue a la carpeta equivocada</b></summary>

En la app: **Actividad** → selecciónalo → **Corregir…** → elige la carpeta correcta → marca las pistas que te sugiere (profesor, código…) → **Aprender**. La próxima vez irá solo al lugar correcto.

Para entender qué pasó, selecciónalo y pulsa **¿Por qué fue aquí?**: verás los puntos de cada carpeta y las palabras que coincidieron.
</details>

---

¿Algo no está en esta guía? [Abre un *issue*](https://github.com/Gr8coolmind/ordenito/issues) con lo que pasó y lo que dice `cat ~/.local/state/ordenito/errores.log`.
