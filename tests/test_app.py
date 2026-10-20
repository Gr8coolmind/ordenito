"""Pruebas de la app (Tkinter). Necesitan pantalla: en Linux sin escritorio usa xvfb-run.
Se saltan solas si no hay Tkinter o no hay pantalla."""
import importlib.util
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent

try:
    import tkinter
    _raiz = tkinter.Tk()
    _raiz.destroy()
    HAY_PANTALLA = True
except Exception:  # sin Tkinter o sin pantalla
    HAY_PANTALLA = False

if HAY_PANTALLA:
    _spec = importlib.util.spec_from_file_location("ordenito_app", RAIZ / "ordenito_app.py")
    app_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(app_mod)
    o = app_mod.o


@unittest.skipUnless(HAY_PANTALLA, "sin Tkinter o sin pantalla")
class TestApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.dl = self.home / "Downloads"
        self.dl.mkdir()
        parches = [
            mock.patch.object(o, "HOME", self.home),
            mock.patch.object(o, "CONFIG", self.home / ".config" / "ordenito" / "reglas.conf"),
            mock.patch.object(o, "ESTADO", self.home / ".estado"),
            mock.patch.object(o, "servicio_activo", lambda: False),
            mock.patch.object(o, "abrir", lambda ruta: None),
            mock.patch.object(o, "notificar", lambda *a: None),
            mock.patch.object(o, "carpeta_escritorio", lambda: self.home / "Desktop"),
            mock.patch.object(app_mod, "sistema_oscuro", lambda: False),
            mock.patch.dict(os.environ, {"ORDENITO_CARPETA": str(self.dl),
                                         "XDG_DATA_HOME": str(self.home / ".share")}),
        ]
        if o.WINDOWS:  # nunca tocar la Papelera de reciclaje de verdad
            parches.append(mock.patch.object(o, "papelera", lambda f=None: self.home / "Papelera"))
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def asistente(self, raiz):
        """Rellena el asistente como lo haría una persona y pulsa Crear."""
        a = app_mod.Asistente(raiz, primera_vez=True)
        materia = a.materias[0]
        materia[0].insert(0, "Redes I")
        materia[1].insert(0, "Ana Pérez")
        materia[2].insert(0, "RED-1010")
        a.nombre.insert(0, "Juan Estudiante")
        a.crear()
        return a.resultado

    def esperar(self, app, segundos=30):
        """Procesa eventos hasta que terminen las tareas en segundo plano."""
        limite = time.time() + segundos
        fin_arranque = time.time() + 0.4  # la app arranca 100 ms después de abrirse
        while time.time() < fin_arranque:
            app.update()
            time.sleep(0.02)
        while (app.trabajos or not app.cola.empty()) and time.time() < limite:
            app.update()
            time.sleep(0.02)
        app.update()

    def test_asistente_crea_carpetas_y_reglas(self):
        raiz = tkinter.Tk()
        self.addCleanup(raiz.destroy)
        creadas = self.asistente(raiz)
        self.assertGreater(creadas, 10)
        texto = o.CONFIG.read_text(encoding="utf-8")
        self.assertIn("[Documents/Universidad/Redes I]", texto)
        self.assertIn("fuertes: Ana Pérez, RED-1010", texto)
        self.assertIn("[no sugerir]", texto)
        self.assertTrue((self.home / "Documents/Personal/Finanzas").is_dir())
        self.assertNotIn("juan estudiante", {p for r in o.leer_reglas() for p in r.fuertes})
        # Volver a abrirlo no duplica bloques
        self.assertEqual(self.asistente(raiz), 0)

    def test_flujo_completo_descargas_ordenar_deshacer(self):
        raiz = tkinter.Tk()
        self.asistente(raiz)
        raiz.destroy()
        with zipfile.ZipFile(self.dl / "tarea.docx", "w") as z:
            z.writestr("word/document.xml", "<w:p><w:t>Subnetting</w:t></w:p>")
            z.writestr("docProps/core.xml", "<dc:creator>Ana Pérez</dc:creator>")
        (self.dl / "factura.txt").write_text("Factura y comprobante de pago")
        (self.dl / "raro.xyz").write_text("?")
        (self.dl / "desktop.ini").write_text("[.ShellClassInfo]")

        app = app_mod.App()
        self.addCleanup(app.destroy)
        self.esperar(app)
        filas = {app.descargas.item(i)["values"][0]: app.descargas.item(i)["values"][1]
                 for i in app.descargas.get_children()}
        self.assertEqual(filas["tarea.docx"], "~/Documents/Universidad/Redes I")
        self.assertEqual(filas["raro.xyz"], "Se queda en Descargas")
        self.assertNotIn("desktop.ini", filas, "los archivos del sistema no se muestran ni se mueven")

        app.ordenar_ahora()
        self.esperar(app)
        self.assertTrue((self.home / "Documents/Universidad/Redes I/tarea.docx").exists())
        self.assertTrue((self.home / "Documents/Personal/Finanzas/factura.txt").exists())
        self.assertEqual(len(app.actividad.get_children()), 2)

        app.actividad.selection_set(app.actividad.get_children()[0])
        app.deshacer()
        self.esperar(app)
        self.assertEqual(len(o._historial()), 1)
        # la primera fila es el movimiento más reciente (la tarea, que se ordenó última)
        self.assertEqual(sorted(f.name for f in self.dl.iterdir() if f.is_file()),
                         ["desktop.ini", "raro.xyz", "tarea.docx"])

    def test_editor_guarda_y_quitar_borra_la_regla(self):
        raiz = tkinter.Tk()
        self.asistente(raiz)
        raiz.destroy()
        app = app_mod.App()
        self.addCleanup(app.destroy)
        self.esperar(app)
        ed = app_mod.EditorRegla(app)
        ed.destino.insert(0, "Documents/Cocina")
        ed.fuertes.insert(0, "Chef Juan")
        ed.palabras.insert("1.0", "receta, ingredientes")
        ed.guardar()
        self.assertTrue((self.home / "Documents/Cocina").is_dir())
        regla = next(r for r in o.leer_reglas() if r.destino == "Documents/Cocina")
        self.assertEqual(regla.fuertes_texto, ["Chef Juan"])
        with mock.patch.object(app_mod.messagebox, "askyesno", return_value=True):
            app.cargar_carpetas()
            app.carpetas.selection_set("Documents/Cocina")
            app.quitar_carpeta()
        self.assertFalse(any(r.destino == "Documents/Cocina" for r in o.leer_reglas()))
        self.assertTrue((self.home / "Documents/Cocina").is_dir(), "quitar la regla no borra la carpeta")

    def test_asistente_puede_vigilar_escritorio_y_activar_limpieza(self):
        (self.home / "Desktop").mkdir()
        raiz = tkinter.Tk()
        self.addCleanup(raiz.destroy)
        a = app_mod.Asistente(raiz, primera_vez=True)
        a.escritorio.set(True)
        a.limpieza.set(True)
        a.crear()
        self.assertEqual([c.name for c in o.carpetas_vigiladas()], ["Downloads", "Desktop"])
        self.assertTrue(o.ajustes_limpieza()[0])
        self.assertIn("[vigilar]\nDesktop", o.CONFIG.read_text(encoding="utf-8"))

    def test_ajustes_vigiladas_limpieza_y_tema(self):
        raiz = tkinter.Tk()
        self.asistente(raiz)
        raiz.destroy()
        escritorio = self.home / "Desktop"
        escritorio.mkdir()
        (escritorio / "factura.txt").write_text("Factura y comprobante de pago")
        app = app_mod.App()
        self.addCleanup(app.destroy)
        self.esperar(app)

        app.agregar_escritorio()
        self.esperar(app)
        self.assertEqual(len(app.vigiladas.get_children()), 2)
        nombres = [app.descargas.item(i)["values"][0] for i in app.descargas.get_children()]
        self.assertIn("factura.txt   (Desktop)", nombres)
        with mock.patch.object(app_mod.messagebox, "showwarning") as aviso:
            app.agregar_vigilada(str(self.home / "Documents/Personal/Finanzas"))
        aviso.assert_called_once()  # un destino no se puede vigilar
        app.vigiladas.selection_set(str(escritorio))
        app.quitar_vigilada()
        self.assertEqual([c.name for c in o.carpetas_vigiladas()], ["Downloads"])

        app.limpia.set(True)
        app.dias.set("12")
        app.tipos_limpieza.delete(0, "end")
        app.tipos_limpieza.insert(0, "exe, .ISO")
        app.guardar_limpieza()
        self.assertEqual(o.ajustes_limpieza(), (True, 12, {".exe", ".iso"}))

        app.tema.set("oscuro")
        app.cambiar_tema()
        self.assertEqual(app_mod.C, app_mod.OSCURO)
        self.assertEqual(app_mod.preferencias()["tema"], "oscuro")
        app.tema.set("claro")
        app.cambiar_tema()
        self.assertEqual(app_mod.C, app_mod.CLARO)


if __name__ == "__main__":
    unittest.main()
