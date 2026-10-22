"""Pruebas de Ordenito. Ejecutar con:  python3 -m unittest discover -s tests -v"""
import importlib.util
import io
import os
import struct
import sys
import tempfile
import time
import unittest
import zipfile
import zlib
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
            mock.patch.object(ordenito, "notificar", lambda *a: None),
            mock.patch.dict(os.environ, {"ORDENITO_CARPETA": str(self.dl)}),
        ]
        if ordenito.WINDOWS:  # nunca tocar la Papelera de reciclaje de verdad
            parches.append(mock.patch.object(ordenito, "papelera", lambda f=None: self.home / "Papelera"))
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
        conf.write_text(conf.read_text(encoding="utf-8") + "\n[no sugerir]\nmarta ruiz\n", encoding="utf-8")
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
        tirado = Path(ordenito._historial()[-1]["hacia"])
        self.assertEqual(tirado.parent, ordenito.cesto())
        self.assertEqual(tirado.read_text(), "misma foto")
        if ordenito.WINDOWS:  # la ficha $I… es la que permite "Restaurar" desde la Papelera
            self.assertTrue(tirado.with_name("$I" + tirado.name[2:]).exists())
        elif not ordenito.MAC:
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
        self.assertFalse(any(ordenito.cesto().iterdir()), "no deben quedar fantasmas en la papelera")
        if not ordenito.MAC and not ordenito.WINDOWS:
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
        self.assertIn("pedro marte", ordenito.CONFIG.read_text(encoding="utf-8").lower())
        self.assertIn("La próxima vez", salida)
        # Después: otro documento del mismo autor ya va solo a Seguridad
        g = docx(self.dl / "caso2.docx", "subnetting vlan router " * 3, autor="Pedro Marte")
        self.assertEqual(ordenito.clasificar(g, ordenito.leer_reglas()).destino, "Docs/Uni/Seguridad")

    def test_corregir_extiende_linea_fuertes_existente(self):
        f = self.archivo("x.txt", "algo")
        self.corregir(f, self.home / "Docs/Uni/Seguridad", pistas=["Ana Rivas"])
        bloque = ordenito.CONFIG.read_text(encoding="utf-8").split("[Docs/Uni/Seguridad]")[1].split("[")[0]
        self.assertIn("fuertes: carlos ruiz, ana rivas", bloque.lower())

    def test_corregir_a_carpeta_nueva_crea_el_bloque(self):
        f = self.archivo("receta.txt", "algo")
        self.corregir(f, self.home / "Docs/Cocina", pistas=["Chef Juan"])
        self.assertIn("[Docs/Cocina]\nfuertes: Chef Juan", ordenito.CONFIG.read_text(encoding="utf-8"))
        self.assertTrue(any(r.destino == "Docs/Cocina" for r in ordenito.leer_reglas()))

    def test_corregir_en_su_misma_carpeta_via_enlace_no_mueve(self):
        # En Silverblue/Bazzite /home es un enlace a /var/home: la misma carpeta con otra ruta
        real = self.home / "Docs/Uni/Redes"
        real.mkdir(parents=True)
        f = docx(real / "tarea.docx", "subnetting")
        enlace = self.home / "atajo"
        try:
            enlace.symlink_to(self.home, target_is_directory=True)
        except OSError:  # Windows sin "modo desarrollador" no deja crear enlaces
            self.skipTest("este sistema no permite crear enlaces simbólicos")
        self.corregir(enlace / "Docs/Uni/Redes/tarea.docx", enlace / "Docs/Uni/Redes", pistas=[])
        self.assertEqual([x.name for x in real.iterdir()], ["tarea.docx"], "no debe crear 'tarea (2).docx'")
        self.assertEqual(ordenito._historial(), [])

    def test_no_sugiere_nombres_de_no_sugerir(self):
        with ordenito.CONFIG.open("a", encoding="utf-8") as c:
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


def armar_pdf(ruta, objetos, raiz, info=None, extra=b""):
    """Escribe un PDF con esos objetos {número: (diccionario, stream o None)}."""
    salida = bytearray(b"%PDF-1.7\n")
    for n, (dic, stream) in sorted(objetos.items()):
        salida += b"%d 0 obj\n" % n + dic
        if stream is not None:
            salida += b"\nstream\n" + stream + b"\nendstream"
        salida += b"\nendobj\n"
    salida += b"trailer\n<< /Root %d 0 R" % raiz + (b" /Info %d 0 R" % info if info else b"") + extra
    salida += b" >>\n%%EOF\n"
    ruta.write_bytes(bytes(salida))
    return ruta


def pdf_simple(ruta, lineas, autor=b"", info_extra=b""):
    """PDF con fuente Helvetica (WinAnsi), contenido comprimido y una línea por Td."""
    texto = b"BT /F1 12 Tf 72 720 Td " + b" 0 -14 Td ".join(lineas) + b" ET"
    objetos = {
        1: (b"<< /Type /Catalog /Pages 2 0 R >>", None),
        2: (b"<< /Type /Pages /Kids [3 0 R] /Count 1 /Resources << /Font << /F1 5 0 R >> >> >>", None),
        3: (b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>", None),  # recursos heredados de /Pages
        4: (b"<< /Length %d /Filter /FlateDecode >>" % len(zlib.compress(texto)), zlib.compress(texto)),
        5: (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>", None),
        6: (b"<< /Author " + autor + info_extra + b" >>", None),
    }
    return armar_pdf(ruta, objetos, 1, 6)


def pdf_de_word(ruta):
    """Como los PDF que exporta Word: fuente Type0 con códigos de 2 bytes, tabla /ToUnicode,
    una letra por TD, cada palabra en su BT, y la fuente guardada dentro de un /ObjStm."""
    cmap = (b"begincmap 1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            b"5 beginbfchar <0001> <0048> <0002> <006F> <0003> <006C> <0004> <0061> <0005> <004D> endbfchar\n"
            b"2 beginbfrange <0006> <0007> [<0075> <006E>] <0008> <0008> <0064> endbfrange endcmap")
    contenido = (b"q BT /F1 10 Tf 1 0 0 1 72 700 Tm <0001>Tj 6 0 TD <0002>Tj 5 0 TD <0003>Tj 3 0 TD <0004>Tj ET\n"
                 b"BT /F1 10 Tf 1 0 0 1 93.8 700 Tm <00050006000700080002>Tj ET\n"
                 b"BT /F1 10 Tf 1 0 0 1 72 680 Tm [<0001>-20<0002>] TJ ET Q")
    fuente = b"<< /Type /Font /Subtype /Type0 /BaseFont /Calibri /Encoding /Identity-H " \
             b"/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>"
    hija = b"<< /Type /Font /Subtype /CIDFontType2 /DW 1000 /W [1 [600 500 300 500] 5 8 550] >>"
    cabecera = b"5 0 6 %d " % len(fuente)
    objstm = cabecera + fuente + hija
    objetos = {
        1: (b"<< /Type /Catalog /Pages 2 0 R >>", None),
        2: (b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", None),
        3: (b"<< /Type /Page /Parent 2 0 R /Contents [4 0 R] /Resources << /Font << /F1 5 0 R >> >> >>", None),
        4: (b"<< /Filter /FlateDecode >>", zlib.compress(contenido)),
        7: (b"<< /Filter /FlateDecode >>", zlib.compress(cmap)),
        8: (b"<< /Type /ObjStm /N 2 /First %d /Filter /FlateDecode >>" % len(cabecera), zlib.compress(objstm)),
    }
    return armar_pdf(ruta, objetos, 1)


class TestPdf(Base):
    def test_lee_texto_metadatos_y_tildes(self):
        f = pdf_simple(self.dl / "a.pdf", [b"(Factura de Acme SRL) Tj", b"[(Comprobante) -300 (de pago)] TJ",
                                           b"(Ingl\\351s \\(b\\341sico\\)) Tj"],
                       autor=b"(Ana P\\351rez)", info_extra=b" /Title <FEFF00540061007200650061>")
        pdf = ordenito.Pdf(f)
        self.assertEqual(pdf.info(), {"Author": "Ana Pérez", "Title": "Tarea"})
        self.assertEqual(pdf.texto().split("\n"), ["Factura de Acme SRL", "Comprobante de pago", "Inglés (básico)"])

    def test_pdf_de_word_con_tabla_tounicode(self):
        self.assertEqual(ordenito.Pdf(pdf_de_word(self.dl / "w.pdf")).texto().split("\n"), ["Hola Mundo", "Ho"])

    def test_clasifica_pdf_sin_pdftotext(self):
        f = pdf_simple(self.dl / "documento.pdf", [b"(Reporte semanal) Tj"], autor=b"(Carlos Ruiz)")
        g = pdf_simple(self.dl / "otro.pdf", [b"(Pasante: reporte diario para ACME SRL) Tj"])
        with mock.patch.object(ordenito.shutil, "which", return_value=None):
            self.assertEqual(ordenito.clasificar(f, self.reglas).destino, "Docs/Uni/Seguridad")
            self.assertEqual(ordenito.clasificar(g, self.reglas).destino, "Docs/Trabajo")
            self.assertEqual(ordenito.autor(f), "Carlos Ruiz")

    def test_pdf_cifrado_o_roto_no_falla(self):
        cifrado = pdf_simple(self.dl / "c.pdf", [b"(secreto) Tj"])
        cifrado.write_bytes(cifrado.read_bytes().replace(b" >>\n%%EOF", b" /Encrypt 9 0 R >>\n%%EOF"))
        self.assertEqual(ordenito.Pdf(cifrado).texto(), "")
        roto = self.dl / "roto.pdf"
        roto.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Page /Contents 2 0 R >> endobj\n2 0 obj << /Filter "
                         b"/FlateDecode >>\nstream\nnada comprimido\nendstream\nendobj\n")
        with mock.patch.object(ordenito.shutil, "which", return_value=None):
            self.assertEqual(ordenito.contenido(roto).strip(), "")

    def test_bomba_dentro_de_un_pdf_no_revienta(self):
        enorme = zlib.compress(b"BT (a) Tj ET " * 5_000_000)
        f = armar_pdf(self.dl / "b.pdf", {1: (b"<< /Type /Page /Contents 2 0 R >>", None),
                                          2: (b"<< /Filter /FlateDecode >>", enorme)}, 1)
        self.assertLessEqual(len(ordenito.Pdf(f).stream(2)), ordenito.MAX_MIEMBRO)


class TestWindows(Base):
    """La papelera de Windows se prueba en cualquier sistema, con una carpeta de mentira."""

    def setUp(self):
        super().setUp()
        cesto = self.home / "Papelera"
        for p in (mock.patch.object(ordenito, "WINDOWS", True),
                  mock.patch.object(ordenito, "papelera", lambda f=None: cesto)):
            p.start()
            self.addCleanup(p.stop)

    def test_papelera_como_el_explorador(self):
        f = self.archivo("informe.pdf", "contenido")
        tirado = ordenito.a_papelera(f)
        self.assertTrue(tirado.name.startswith("$R") and tirado.name.endswith(".pdf"))
        datos = tirado.with_name("$I" + tirado.name[2:]).read_bytes()
        version, tam, _, largo = struct.unpack("<qqqi", datos[:28])
        self.assertEqual((version, tam), (2, len("contenido")))
        self.assertEqual(datos[28:28 + 2 * largo].decode("utf-16-le"), str(ordenito.real(f)) + "\0")

    def test_deshacer_borra_la_ficha_de_la_papelera(self):
        f = self.archivo("informe.pdf", "contenido")
        ordenito._registrar(f, ordenito.a_papelera(f), duplicado_de="x")
        with redirect_stdout(io.StringIO()):
            ordenito.deshacer(1)
        self.assertTrue(f.exists())
        self.assertEqual(list((self.home / "Papelera").iterdir()), [])

    def test_bonito_y_destino_de_usan_barras_normales(self):
        carpeta = self.home / "Docs" / "Uni" / "Nueva"
        self.assertEqual(ordenito.bonito(carpeta), "~/Docs/Uni/Nueva")
        self.assertEqual(ordenito.destino_de(carpeta), "Docs/Uni/Nueva")


class TestCarpetas(Base):
    def conf(self, texto):
        with ordenito.CONFIG.open("a", encoding="utf-8") as c:
            c.write("\n" + texto + "\n")

    def ordenar(self, **kw):
        with redirect_stdout(io.StringIO()):
            return ordenito.ordenar(esperar=False, avisar=False, **kw)

    def test_reglas_guardadas_con_bom_del_bloc_de_notas(self):
        ordenito.CONFIG.write_text(REGLAS.lstrip(), encoding="utf-8-sig")
        self.assertEqual(ordenito.leer_reglas()[0].destino, "Docs/Uni/Redes")

    def test_nunca_mueve_ocultos_ni_accesos_directos(self):
        for nombre in ("desktop.ini", "Fortnite.url", "Stremio.lnk", "Thumbs.db"):
            self.archivo(nombre, "english grammar")
        self.assertEqual(self.ordenar(), 0)

    def test_vigila_otras_carpetas(self):
        escritorio = self.home / "Escritorio"
        escritorio.mkdir()
        self.conf("[vigilar]\nEscritorio, ~/no-existe")
        (escritorio / "tarea.txt").write_text("english grammar", encoding="utf-8")
        (escritorio / "Juego.lnk").write_text("english grammar", encoding="utf-8")
        self.assertEqual([c.name for c in ordenito.carpetas_vigiladas()][:2], ["Downloads", "Escritorio"])
        self.assertEqual(self.ordenar(), 1)
        self.assertTrue((self.home / "Docs/Uni/Ingles/tarea.txt").exists())
        self.assertTrue((escritorio / "Juego.lnk").exists(), "los accesos directos no se tocan")
        self.assertFalse(any(r.destino == "vigilar" for r in ordenito.leer_reglas()))

    def test_carpeta_vigilada_que_es_destino_no_se_reordena(self):
        fotos = self.home / "Fotos"
        fotos.mkdir()
        (fotos / "playa.jpg").write_text("x")
        self.conf("[vigilar]\nFotos")
        self.assertEqual(self.ordenar(), 0)
        self.assertEqual([f.name for f in fotos.iterdir()], ["playa.jpg"], "no debe crear 'playa (2).jpg'")

    def test_archivo_bloqueado_no_frena_a_los_demas(self):
        self.archivo("a.txt", "english grammar")
        self.archivo("b.txt", "english grammar")
        real_move, fallos = ordenito.shutil.move, []

        def mover(desde, hacia):
            if desde.endswith("a.txt"):
                raise PermissionError("lo tiene abierto el navegador")
            return real_move(desde, hacia)

        with mock.patch.object(ordenito.shutil, "move", mover):
            self.assertEqual(self.ordenar(fallos=fallos), 1)
        self.assertEqual([f.name for f, _ in fallos], ["a.txt"])

    def test_ignorados_viejos_solo_con_nombre_siguen_valiendo(self):
        self.archivo("foto.jpg")
        ordenito._guardar_json("ignorados.json", ["foto.jpg"])
        self.assertEqual(self.ordenar(), 0)

    def test_limpieza_apagada_por_defecto(self):
        self.assertFalse(ordenito.ajustes_limpieza()[0])
        self.assertEqual(ordenito.limpiar(avisar=False), (0, 0))

    def test_limpieza_manda_instaladores_viejos_a_la_papelera(self):
        self.conf("[limpieza]\ndias: 10\nextensiones: exe, iso")
        self.assertEqual(ordenito.ajustes_limpieza()[:2], (True, 10))
        (self.dl / "Instaladores").mkdir()
        viejo = self.dl / "Instaladores" / "viejo.exe"
        viejo.write_text("x")
        self.archivo("nuevo.exe")
        self.archivo("viejo.pdf")
        hace = time.time() - 30 * 86_400
        with mock.patch.object(ordenito, "_llegada", lambda f: hace if f.stem == "viejo" else time.time()), \
                mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / "share")}):
            self.assertEqual(ordenito.para_limpiar(), [viejo])
            self.assertEqual(ordenito.limpiar(avisar=False)[0], 1)
            self.assertFalse(viejo.exists())
            self.assertTrue((self.dl / "viejo.pdf").exists(), "solo los tipos de la lista")
            with redirect_stdout(io.StringIO()) as salida:
                ordenito.historial()
                ordenito.deshacer(1)
        self.assertIn("limpieza", salida.getvalue())
        self.assertTrue(viejo.exists())

    def test_limpieza_se_puede_apagar_sin_perder_los_dias(self):
        self.conf("[limpieza]\ndias: 45\napagada")
        self.assertEqual(ordenito.ajustes_limpieza()[:2], (False, 45))

    def test_vigilar_ordena_y_termina_al_pedirselo(self):
        self.archivo("tarea.txt", "english grammar")
        ordenito.vigilar(pausa=0.01, vueltas=2)
        self.assertTrue((self.home / "Docs/Uni/Ingles/tarea.txt").exists())
        self.assertFalse((ordenito.ESTADO / "vigilante.pid").exists(), "al salir borra su marca")

    def test_vigilar_no_pierde_lo_que_llega_mientras_ordena(self):
        self.archivo("tarea.txt", "english grammar")
        ordenar = ordenito.ordenar

        def lento(**kw):  # mientras ordena (la IA puede tardar), llega otra descarga
            movidos = ordenar(**kw)
            if not (self.dl / "curso.txt").exists() and not (self.home / "Docs/Cursos/curso.txt").exists():
                self.archivo("curso.txt", "coursera")
            return movidos
        with mock.patch.object(ordenito, "ordenar", lento):
            ordenito.vigilar(pausa=0.01, vueltas=3)
        self.assertTrue((self.home / "Docs/Cursos/curso.txt").exists())

    def test_terminado_no_espera_si_hace_rato_que_no_cambia(self):
        f = self.archivo("viejo.txt", "x")
        os.utime(f, (time.time() - 60, time.time() - 60))
        inicio = time.time()
        self.assertTrue(ordenito.terminado(f))
        self.assertLess(time.time() - inicio, 1)


class TestIA(Base):
    """La IA local (Ollama) se simula: aquí se prueba qué hace Ordenito con lo que responde."""

    def setUp(self):
        super().setUp()
        with ordenito.CONFIG.open("a", encoding="utf-8") as c:
            c.write("\n[no sugerir]\nana perez\n\n[ia]\nmodelo: prueba:1b\n")
        self.preguntas = []

    def responder(self, carpeta, palabras=("bases de datos", "sql", "normalizacion")):
        def falso(modelo, pregunta, piensa=True):
            self.preguntas.append((modelo, pregunta, piensa))
            return {"carpeta": carpeta, "palabras": list(palabras)}
        p = mock.patch.object(ordenito, "_ollama", falso)
        p.start()
        self.addCleanup(p.stop)

    def ordenar(self, **kw):
        with redirect_stdout(io.StringIO()):
            return ordenito.ordenar(esperar=False, avisar=False, **kw)

    def test_sin_bloque_ia_no_pregunta(self):
        ordenito.CONFIG.write_text(REGLAS, encoding="utf-8")
        self.responder("Documents/Universidad/Bases de Datos")
        self.archivo("apuntes.txt", "tablas y llaves primarias")
        self.assertEqual(self.ordenar(), 0)
        self.assertEqual(self.preguntas, [])

    def test_crea_carpeta_y_aprende_la_regla(self):
        self.responder("Documents/Universidad/Bases de Datos")
        self.archivo("apuntes.txt", "tablas, llaves primarias y normalizacion en sql")
        self.assertEqual(self.ordenar(), 1)
        self.assertTrue((self.home / "Documents/Universidad/Bases de Datos/apuntes.txt").exists())
        self.assertEqual(self.preguntas[0][0], "prueba:1b")
        regla = next(r for r in ordenito.leer_reglas() if r.destino == "Documents/Universidad/Bases de Datos")
        self.assertIn("sql", regla.palabras)
        # El siguiente archivo parecido lo reconoce la regla: ya no se le pregunta a la IA
        self.archivo("tarea sql.txt", "consultas")
        self.assertEqual(self.ordenar(), 1)
        self.assertEqual(len(self.preguntas), 1)
        self.assertTrue((self.home / "Documents/Universidad/Bases de Datos/tarea sql.txt").exists())

    def test_las_reglas_van_primero(self):
        self.responder("Documents/Otra")
        self.archivo("tarea.docx", "subnetting y enrutamiento")
        self.ordenar()
        self.assertTrue((self.home / "Docs/Uni/Redes/tarea.docx").exists())
        self.assertEqual(self.preguntas, [])

    def test_no_sabe_y_no_vuelve_a_preguntar(self):
        self.responder("")
        f = self.archivo("plano del departamento.heic")
        self.assertEqual(self.ordenar(), 0)
        self.assertEqual(self.ordenar(), 0)
        self.assertTrue(f.exists())
        self.assertEqual(len(self.preguntas), 2, "un 'no sé' se intenta dos veces y después se recuerda")

    def test_segundo_intento_si_la_primera_no_sirve(self):
        respuestas = iter([{"carpeta": "", "palabras": []},
                           {"carpeta": "Documents/Gimnasio", "palabras": ["sentadillas"]}])
        with mock.patch.object(ordenito, "_ollama", lambda *a: next(respuestas)):
            self.archivo("rutina.txt", "sentadillas y press de banca")
            self.assertEqual(self.ordenar(), 1)
        self.assertTrue((self.home / "Documents/Gimnasio/rutina.txt").exists())

    def test_nombres_mudos_sin_texto_ni_se_preguntan(self):
        self.responder("Documents/Sin texto")
        for nombre in ["IMG_2041.heic", "DSC0012.heic", "Screenshot 2026-10-18 020835.heic", "1234.bin"]:
            self.archivo(nombre)
        self.assertEqual(self.ordenar(), 0)
        self.assertEqual(self.preguntas, [])

    def test_sin_ollama_no_rompe_y_reintenta(self):
        def apagado(*a):
            self.preguntas.append(a)
            raise ConnectionRefusedError("no hay nadie en el puerto 11434")
        with mock.patch.object(ordenito, "_ollama", apagado):
            f = self.archivo("apuntes.txt", "algo")
            self.assertEqual(self.ordenar(), 0)
            self.assertEqual(self.ordenar(), 0)
        self.assertTrue(f.exists())
        self.assertEqual(len(self.preguntas), 2, "un fallo no se recuerda: se vuelve a intentar")

    def test_rutas_peligrosas_se_rechazan(self):
        raices, conocidas = {"Documents", "Docs"}, ["Docs/Uni/Redes"]
        for mala in ["../../Windows", "C:/Windows/System32", "Documents/../..", "Documents", "Desktop/Cosas",
                     "Documents/a/b/c/d", "Documents/CON", "Documents/x:y", "Documents/Ana Perez/Tareas",
                     "Documents/" + "x" * 50, None, 42]:
            self.assertIsNone(ordenito.carpeta_ia(mala, conocidas, raices, {"ana perez"}), mala)
        self.assertEqual(ordenito.carpeta_ia("documents\\Bases de Datos", conocidas, raices),
                         "Documents/Bases de Datos")

    def test_usa_la_carpeta_existente_escrita_distinto(self):
        self.assertEqual(ordenito.carpeta_ia("docs/UNI/redés", ["Docs/Uni/Redes"], {"Docs"}), "Docs/Uni/Redes")

    def test_palabras_limpias(self):
        self.assertEqual(ordenito.palabras_ia(["SQL", "pdf", "ana perez", "a,b", "12", "sql", "x" * 60,
                                               "bases [de] datos"], {"ana perez"}),
                         ["sql", "a b", "bases de datos"])
        self.assertEqual(ordenito.palabras_ia("no es una lista"), [])

    def test_ve_las_carpetas_que_ya_tienes(self):
        (self.home / "Documents/Recetas").mkdir(parents=True)
        (self.home / "Documents/.oculta").mkdir()
        (self.home / "Documents/My Games").mkdir()
        (self.home / "Documents/mi-repo/.git").mkdir(parents=True)
        self.responder("Documents/Recetas")
        self.archivo("pan.txt", "harina y levadura")
        self.ordenar()
        pregunta = self.preguntas[0][1]
        self.assertIn("- Documents/Recetas", pregunta)
        self.assertIn("- Docs/Uni/Redes", pregunta)
        for fuera in (".oculta", "My Games", "mi-repo"):
            self.assertNotIn(fuera, pregunta)
        self.assertTrue((self.home / "Documents/Recetas/pan.txt").exists())

    def test_deshacer_quita_la_carpeta_y_la_regla_que_creo(self):
        self.responder("Documents/Hobbies/Cocina", ["receta", "harina"])
        self.archivo("pan.txt", "harina y levadura")
        self.ordenar()
        with redirect_stdout(io.StringIO()):
            ordenito.deshacer(1)
        self.assertTrue((self.dl / "pan.txt").exists())
        self.assertFalse((self.home / "Documents/Hobbies").exists())
        self.assertFalse(any(r.destino == "Documents/Hobbies/Cocina" for r in ordenito.leer_reglas()))

    def test_ajustes(self):
        self.assertEqual(ordenito.ajustes_ia(), (True, "prueba:1b", True))
        ordenito.CONFIG.write_text(REGLAS + "\n[ia]\nrápida\n", encoding="utf-8")
        self.assertEqual(ordenito.ajustes_ia(), (True, ordenito.IA_MODELO, False))
        ordenito.CONFIG.write_text(REGLAS + "\n[ia]\napagada\n", encoding="utf-8")
        self.assertEqual(ordenito.ajustes_ia()[0], False)
        self.assertFalse(any(r.destino == "ia" for r in ordenito.leer_reglas()))


class TestEjemplo(unittest.TestCase):
    def test_reglas_de_ejemplo_son_validas(self):
        reglas = ordenito.leer_reglas(RAIZ / "reglas.ejemplo.conf")
        self.assertGreater(len(reglas), 10)
        respaldos = [r.destino for r in reglas if r.respaldo]
        self.assertTrue(all(r.extensiones for r in reglas if r.respaldo),
                        f"bloques sin palabras ni extensiones: {respaldos}")


if __name__ == "__main__":
    unittest.main()
