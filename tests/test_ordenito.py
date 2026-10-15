"""Pruebas de Ordenito. Ejecutar con:  python3 -m unittest discover -s tests -v"""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ordenito", RAIZ / "ordenito.py")
ordenito = importlib.util.module_from_spec(_spec)
sys.modules["ordenito"] = ordenito  # dataclasses lo necesita registrado
_spec.loader.exec_module(ordenito)

REGLAS = """
[Docs/Uni/Redes]
red-1010, ana perez, subnetting, vlan, enrutamiento, router

[Docs/Uni/Redes/Proyecto Final]
tienda aurora, maqueta

[Docs/Uni/Seguridad]
fuertes: carlos ruiz
red-1015, malware, any.run

[Docs/Trabajo]
fuertes: acme srl
pasante, reporte diario

[Docs/Uni/Ingles]
english, grammar

[Docs/Cursos]
curso, coursera

[Docs/Codigo]
extensiones: php, zip
lms, action.php

[*/Proyecto Final]
proyecto final, entrega final

[Fotos]
extensiones: jpg, png

[Instaladores]
extensiones: flatpakref, rpm
"""


def docx(ruta, texto, autor="", encabezado=""):
    """Crea un .docx mínimo con ese texto (y opcionalmente autor y encabezado)."""
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:t>{texto}</w:t></w:p></w:body></w:document>")
        if autor:
            z.writestr("docProps/core.xml", f"<cp:coreProperties><dc:creator>{autor}</dc:creator></cp:coreProperties>")
        if encabezado:
            z.writestr("word/header1.xml", f"<w:hdr><w:p><w:t>{encabezado}</w:t></w:p></w:hdr>")
    return ruta


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.dl = self.home / "Downloads"
        self.dl.mkdir()
        conf = self.home / "reglas.conf"
        conf.write_text(REGLAS, encoding="utf-8")
        parches = [
            mock.patch.object(ordenito, "HOME", self.home),
            mock.patch.object(ordenito, "CONFIG", conf),
            mock.patch.object(ordenito, "ESTADO", self.home / "estado"),
            mock.patch.dict(os.environ, {"ORDENITO_CARPETA": str(self.dl)}),
        ]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        self.reglas = ordenito.leer_reglas()

    def tearDown(self):
        self.tmp.cleanup()

    def archivo(self, nombre, texto="x"):
        ruta = self.dl / nombre
        if ruta.suffix == ".docx":
            return docx(ruta, texto)
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def destino(self, nombre, texto="x"):
        return ordenito.clasificar(self.archivo(nombre, texto), self.reglas).destino


class TestTexto(unittest.TestCase):
    def test_normalizar_quita_tildes_y_guiones(self):
        self.assertEqual(ordenito.normalizar("Configuración_de-Redes  VLAN"), "configuracion de redes vlan")

    def test_contar_solo_palabras_completas(self):
        self.assertEqual(ordenito.contar("curso", "un recurso y un concurso"), 0)
        self.assertEqual(ordenito.contar("curso", "el curso, otro curso."), 2)

    def test_contar_palabras_con_simbolos(self):
        self.assertEqual(ordenito.contar("any.run", "reporte de any.run hoy"), 1)
        self.assertEqual(ordenito.contar("indicator(", "indicator('x')"), 1)


class TestClasificar(Base):
    def test_por_contenido_de_docx(self):
        self.assertEqual(self.destino("Tarea3.docx", "Prof. Ana Pérez: subnetting y enrutamiento"),
                         "Docs/Uni/Redes")

    def test_nombre_pesa_mas_que_contenido(self):
        self.assertEqual(self.destino("english homework.txt", "malware malware"), "Docs/Uni/Ingles")

    def test_subcarpeta_mas_especifica_gana(self):
        self.assertEqual(self.destino("informe.txt", "vlan y router; red de la tienda aurora, maqueta"),
                         "Docs/Uni/Redes/Proyecto Final")

    def test_comodin_dentro_de_cualquier_tema(self):
        self.assertEqual(self.destino("tarea.txt", "RED-1015 malware. Proyecto final"),
                         "Docs/Uni/Seguridad/Proyecto Final")

    def test_codigos_parecidos_no_se_confunden(self):
        self.assertEqual(self.destino("a.txt", "RED-1015 red-1015"), "Docs/Uni/Seguridad")
        self.assertEqual(self.destino("b.txt", "RED-1010 red-1010"), "Docs/Uni/Redes")

    def test_extensiones_limitan_el_bloque(self):
        self.assertEqual(self.destino("modal.php", "lms lms"), "Docs/Codigo")
        self.assertIsNone(self.destino("distribucion.txt", "lms lms"))

    def test_zip_se_juzga_por_lo_que_trae(self):
        ruta = self.dl / "pruebas.zip"
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("orig_locations-action.php", "")
            z.writestr("logout-action.php", "")
        self.assertEqual(ordenito.clasificar(ruta, self.reglas).destino, "Docs/Codigo")

    def test_respaldo_por_tipo(self):
        self.assertEqual(self.destino("foto.jpg"), "Fotos")
        self.assertEqual(self.destino("App.flatpakref"), "Instaladores")

    def test_tema_gana_al_respaldo(self):
        self.assertEqual(self.destino("tienda aurora maqueta.png"), "Docs/Uni/Redes/Proyecto Final")

    def test_nada_coincide(self):
        self.assertIsNone(self.destino("raro.xyz", "nada que ver"))

    def test_una_sola_mencion_no_basta(self):
        self.assertIsNone(self.destino("notas.txt", "hablamos de una vlan"))

    def test_pista_fuerte_en_autor_gana_a_palabras_de_tema(self):
        # El tema dice "redes" muchas veces, pero el autor del documento es el profesor de Seguridad
        f = docx(self.dl / "caso.docx", "subnetting vlan enrutamiento router " * 5, autor="Carlos Ruiz")
        self.assertEqual(ordenito.clasificar(f, self.reglas).destino, "Docs/Uni/Seguridad")

    def test_pista_fuerte_en_encabezado(self):
        f = docx(self.dl / "guia.docx", "subnetting vlan", encabezado="Prof. Carlos Ruiz")
        self.assertEqual(ordenito.clasificar(f, self.reglas).destino, "Docs/Uni/Seguridad")

    def test_nombre_parecido_a_lo_ya_guardado(self):
        # El texto habla de redes, pero ya guardaste el caso "Tienda Lunar" en Seguridad
        guardado = self.home / "Docs/Uni/Seguridad"
        guardado.mkdir(parents=True)
        (guardado / "Caso de Estudio 3 Tienda Lunar.docx").write_bytes(b"")
        res = ordenito.clasificar(self.archivo("Caso 3 Tienda Lunar - Presentacion.txt", "vlan router"),
                                  self.reglas)
        self.assertEqual(res.destino, "Docs/Uni/Seguridad")
        self.assertEqual(res.tabla["Docs/Uni/Seguridad"][0], ordenito.PESO_VECINO)

    def test_parecido_en_varias_carpetas_no_cuenta(self):
        for carpeta in ("Docs/Uni/Seguridad", "Docs/Uni/Ingles"):
            (self.home / carpeta).mkdir(parents=True)
            (self.home / carpeta / "Tarea Semana Uno.txt").write_text("x")
        res = ordenito.clasificar(self.archivo("Tarea Semana Uno (2).txt", "vlan router"), self.reglas)
        self.assertEqual(res.destino, "Docs/Uni/Redes")

    def test_parecido_ignora_tu_nombre_y_numeros(self):
        (self.home / "Docs/Uni/Seguridad").mkdir(parents=True)
        (self.home / "Docs/Uni/Seguridad/Tarea 2 Marta Ruiz.txt").write_text("x")
        conf = ordenito.CONFIG
        conf.write_text(conf.read_text() + "\n[no sugerir]\nmarta ruiz\n", encoding="utf-8")
        res = ordenito.clasificar(self.archivo("Tarea 2 Marta Ruiz.txt", "vlan router"), ordenito.leer_reglas())
        self.assertEqual(res.destino, "Docs/Uni/Redes")

    def test_pista_fuerte_de_pasada_pesa_poco(self):
        # Mencionar la empresa al final de una tarea de redes no la convierte en documento de trabajo
        texto = "Tarea de subnetting y vlan con router. " + "relleno " * 400 + "Lo usaré en Acme SRL."
        res = ordenito.clasificar(self.archivo("reflexion.txt", texto), self.reglas)
        self.assertEqual(res.destino, "Docs/Uni/Redes")
        self.assertEqual(res.tabla["Docs/Trabajo"][0], ordenito.PESO_FUERTE_CUERPO)

    def test_zip_bomb_no_revienta(self):
        ruta = self.dl / "bomba.docx"
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", "a" * 50_000_000)
        self.assertLessEqual(len(ordenito.contenido(ruta)), ordenito.MAX_MIEMBRO)

    def test_archivo_corrupto_no_falla(self):
        self.assertIsNone(self.destino("roto.pptx", "no soy un zip"))


class TestAcciones(Base):
    def ordenar(self, **kw):
        with redirect_stdout(io.StringIO()):
            return ordenito.ordenar(esperar=False, avisar=False, **kw)

    def test_mueve_y_registra(self):
        self.archivo("tarea.docx", "subnetting y enrutamiento, ana perez")
        self.assertEqual(self.ordenar(), 1)
        self.assertTrue((self.home / "Docs/Uni/Redes/tarea.docx").exists())
        self.assertEqual(len(ordenito._historial()), 1)

    def test_simular_no_mueve(self):
        self.archivo("tarea.docx", "subnetting y enrutamiento, ana perez")
        self.ordenar(simular=True)
        self.assertTrue((self.dl / "tarea.docx").exists())

    def test_no_pisa_archivos_existentes(self):
        destino = self.home / "Fotos"
        destino.mkdir()
        (destino / "foto.jpg").write_text("vieja")
        self.archivo("foto.jpg", "nueva")
        self.ordenar()
        self.assertEqual((destino / "foto.jpg").read_text(), "vieja")
        self.assertEqual((destino / "foto (2).jpg").read_text(), "nueva")

    def test_ignora_descargas_en_curso_y_ocultos(self):
        self.archivo("video.mp4.part")
        self.archivo(".oculto.jpg")
        self.assertEqual(self.ordenar(), 0)

    def test_deshacer_devuelve_y_no_se_vuelve_a_mover(self):
        self.archivo("foto.jpg")
        self.ordenar()
        with redirect_stdout(io.StringIO()):
            ordenito.deshacer(1)
        self.assertTrue((self.dl / "foto.jpg").exists())
        self.assertEqual(self.ordenar(), 0, "un archivo devuelto no debe volver a moverse")
        self.assertEqual(ordenito._historial(), [])

    def test_explicar_y_revisar_no_mueven(self):
        f = self.archivo("foto.jpg")
        with redirect_stdout(io.StringIO()) as salida:
            ordenito.explicar(f)
            ordenito.revisar(self.dl)
        self.assertIn("Fotos", salida.getvalue())
        self.assertTrue(f.exists())


    def test_revisar_respeta_subcarpetas_propias(self):
        propia = self.home / "Fotos" / "Viaje"
        propia.mkdir(parents=True)
        (propia / "playa.txt").write_text("english grammar")
        with redirect_stdout(io.StringIO()) as salida:
            ordenito.revisar(self.home / "Fotos")
        self.assertIn("0 archivo(s)", salida.getvalue())


class TestDuplicados(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / "share")})
        p.start()
        self.addCleanup(p.stop)

    def ordenar(self):
        with redirect_stdout(io.StringIO()):
            return ordenito.ordenar(esperar=False, avisar=False)

    def test_descarga_repetida_va_a_la_papelera(self):
        fotos = self.home / "Fotos"
        fotos.mkdir()
        (fotos / "foto.jpg").write_text("misma foto")
        self.archivo("foto (1).jpg", "misma foto")
        self.ordenar()
        self.assertEqual(sorted(f.name for f in fotos.iterdir()), ["foto.jpg"], "no debe crear copias")
        self.assertTrue((ordenito.cesto() / "foto (1).jpg").exists())
        if not ordenito.MAC:
            self.assertTrue((ordenito.papelera() / "info" / "foto (1).jpg.trashinfo").exists())

    def test_mismo_nombre_distinto_contenido_no_es_duplicado(self):
        fotos = self.home / "Fotos"
        fotos.mkdir()
        (fotos / "foto.jpg").write_text("vieja")
        self.archivo("foto.jpg", "nueva")
        self.ordenar()
        self.assertTrue((fotos / "foto (2).jpg").exists())

    def test_deshacer_saca_de_la_papelera(self):
        fotos = self.home / "Fotos"
        fotos.mkdir()
        (fotos / "foto.jpg").write_text("igual")
        self.archivo("otra.jpg", "igual")
        self.ordenar()
        with redirect_stdout(io.StringIO()):
            ordenito.deshacer(1)
        self.assertTrue((self.dl / "otra.jpg").exists())
        self.assertFalse(any(ordenito.cesto().iterdir()))
        if not ordenito.MAC:
            self.assertFalse(any((ordenito.papelera() / "info").iterdir()))

    def test_comando_duplicados_conserva_el_nombre_limpio(self):
        docs = self.home / "Docs"
        (docs / "sub").mkdir(parents=True)
        (docs / "guia.pdf").write_text("contenido")
        (docs / "guia (1).pdf").write_text("contenido")
        (docs / "sub" / "copia.pdf").write_text("contenido")
        (docs / "otro.pdf").write_text("distinto")
        with redirect_stdout(io.StringIO()) as salida:
            ordenito.duplicados(docs)
        self.assertIn("2 copia(s)", salida.getvalue())
        self.assertTrue((docs / "guia (1).pdf").exists(), "sin --papelera no se toca nada")
        with redirect_stdout(io.StringIO()):
            ordenito.duplicados(docs, quitar=True)
        quedan = sorted(str(f.relative_to(docs)) for f in docs.rglob("*") if f.is_file())
        self.assertEqual(quedan, ["guia.pdf", "otro.pdf"])


class TestCorregir(Base):
    def corregir(self, *args, **kw):
        with redirect_stdout(io.StringIO()) as salida:
            ordenito.corregir(*args, **kw)
        return salida.getvalue()

    def test_candidatas_encuentra_autor_codigo_y_docente(self):
        f = docx(self.dl / "caso.docx", "Asignatura BD-2030 · Docente: Laura Gómez Peña. Caso de estudio",
                 autor="Pedro Marte")
        pistas = ordenito.candidatas(f)
        self.assertIn("Pedro Marte", pistas)
        self.assertIn("BD-2030", pistas)
        self.assertIn("Laura Gómez Peña", pistas)

    def test_corregir_mueve_y_aprende(self):
        # Antes: el tema (redes) gana y el archivo iría a Redes
        f = docx(self.dl / "caso.docx", "subnetting vlan router " * 3, autor="Pedro Marte")
        self.assertEqual(ordenito.clasificar(f, self.reglas).destino, "Docs/Uni/Redes")
        salida = self.corregir(f, self.home / "Docs/Uni/Seguridad", todas=True)
        self.assertTrue((self.home / "Docs/Uni/Seguridad/caso.docx").exists())
        self.assertIn("pedro marte", ordenito.CONFIG.read_text().lower())
        self.assertIn("La próxima vez", salida)
        # Después: otro documento del mismo autor ya va solo a Seguridad
        g = docx(self.dl / "caso2.docx", "subnetting vlan router " * 3, autor="Pedro Marte")
        self.assertEqual(ordenito.clasificar(g, ordenito.leer_reglas()).destino, "Docs/Uni/Seguridad")

    def test_corregir_extiende_linea_fuertes_existente(self):
        f = self.archivo("x.txt", "algo")
        self.corregir(f, self.home / "Docs/Uni/Seguridad", pistas=["Ana Rivas"])
        bloque = ordenito.CONFIG.read_text().split("[Docs/Uni/Seguridad]")[1].split("[")[0]
        self.assertIn("fuertes: carlos ruiz, ana rivas", bloque.lower())

    def test_corregir_a_carpeta_nueva_crea_el_bloque(self):
        f = self.archivo("receta.txt", "algo")
        self.corregir(f, self.home / "Docs/Cocina", pistas=["Chef Juan"])
        self.assertIn("[Docs/Cocina]\nfuertes: Chef Juan", ordenito.CONFIG.read_text())
        self.assertTrue(any(r.destino == "Docs/Cocina" for r in ordenito.leer_reglas()))

    def test_corregir_en_su_misma_carpeta_via_enlace_no_mueve(self):
        # En Silverblue/Bazzite /home es un enlace a /var/home: la misma carpeta con otra ruta
        real = self.home / "Docs/Uni/Redes"
        real.mkdir(parents=True)
        f = docx(real / "tarea.docx", "subnetting")
        enlace = self.home / "atajo"
        enlace.symlink_to(self.home)
        self.corregir(enlace / "Docs/Uni/Redes/tarea.docx", enlace / "Docs/Uni/Redes", pistas=[])
        self.assertEqual([x.name for x in real.iterdir()], ["tarea.docx"], "no debe crear 'tarea (2).docx'")
        self.assertEqual(ordenito._historial(), [])

    def test_no_sugiere_nombres_de_no_sugerir(self):
        with ordenito.CONFIG.open("a") as c:
            c.write("\n[no sugerir]\nlucia fernandez\n")
        f = docx(self.dl / "t.docx", "x", autor="Lucía Fernández")
        self.assertNotIn("Lucía Fernández", ordenito.candidatas(f))
        self.assertFalse(any(r.destino == "no sugerir" for r in ordenito.leer_reglas()))

    def test_nombre_del_docente_no_se_come_la_linea_siguiente(self):
        ruta = self.dl / "t.docx"
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("word/document.xml", "<w:p><w:t>Presentado a Prof. Laura Gómez</w:t></w:p>"
                                            "<w:p><w:t>Santiago de los Caballeros</w:t></w:p>")
        self.assertIn("Laura Gómez", ordenito.candidatas(ruta))
        self.assertNotIn("Laura Gómez Santiago", ordenito.candidatas(ruta))

    def test_corregir_queda_en_historial_y_se_deshace(self):
        f = self.archivo("x.txt", "algo")
        self.corregir(f, self.home / "Docs/Otra", pistas=[])
        with redirect_stdout(io.StringIO()):
            ordenito.deshacer(1)
        self.assertTrue((self.dl / "x.txt").exists())


class TestEjemplo(unittest.TestCase):
    def test_reglas_de_ejemplo_son_validas(self):
        reglas = ordenito.leer_reglas(RAIZ / "reglas.ejemplo.conf")
        self.assertGreater(len(reglas), 10)
        respaldos = [r.destino for r in reglas if r.respaldo]
        self.assertTrue(all(r.extensiones for r in reglas if r.respaldo),
                        f"bloques sin palabras ni extensiones: {respaldos}")


if __name__ == "__main__":
    unittest.main()
