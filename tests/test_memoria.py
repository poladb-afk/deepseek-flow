"""Memoria y RAG: búsqueda, guardado, pre-filtro por Laya y resumen de sesión (PR 4)."""
from pathlib import Path

import pytest

import modules.memoria as mem


def test_memory_search_encuentra_y_lista(tmp_path, monkeypatch):
    """La memoria es una BIBLIOTECA consultable: memory_search encuentra el
    texto (case-insensitive) con archivo+línea y siempre lista la biblioteca."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    # biblioteca vacía: lo dice y no explota
    vacio = mem.memory_search("cualquier-cosa")
    assert "vacía" in vacio

    (tmp_path / "nota_2026-10-05_prueba.md").write_text(
        "Hallazgo de LaYa\n\nEl router degrada al lado SEGURO.\n", encoding="utf-8")
    (tmp_path / "sesion_2026-10-05.md").write_text(
        "Tema: streaming\n\nSe implementó el modo clásico y el stream.\n", encoding="utf-8")

    # búsqueda insensible a mayúsculas + archivo/línea
    r = mem.memory_search("laya")
    assert "nota_2026-10-05_prueba.md" in r and "L1" in r
    # siempre lista la biblioteca completa
    assert "nota_2026-10-05_prueba.md" in r and "sesion_2026-10-05.md" in r

    # sin query: solo lista
    solo_lista = mem.memory_search("")
    assert "Biblioteca" in solo_lista and "L1" not in solo_lista

    # sin coincidencias: lo dice pero igual lista
    assert "no aparece" in mem.memory_search("inexistente-xyz")

def test_memory_save_contiene_el_slug(tmp_path, monkeypatch):
    """Contención dura: el título genera el slug, no es una ruta. Un título
    con barra, '..' o solo símbolos se rechaza o se neutraliza."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    # el slug neutraliza la barra y los '..': nada sale de memoria/
    r = mem.memory_save("../../etc/passwd", "contenido malicioso")
    assert r.startswith("Guardado")
    destino = Path(r.split("Guardado en ", 1)[1])
    assert destino.parent == tmp_path.resolve()
    assert ".." not in destino.name and "/" not in destino.name

    # un título sin caracteres utilizables se rechaza
    assert mem.memory_save("///", "x").startswith("ERROR")
    assert mem.memory_save("...", "x").startswith("ERROR")

    # y SOLO escribe dentro de memoria/: ningún archivo fuera de tmp_path
    fuera = list(tmp_path.parent.glob("passwd*"))
    assert not fuera

def test_memory_save_escribe_con_titulo_primera_linea(tmp_path, monkeypatch):
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    r = mem.memory_save("Mi hallazgo", "detalle del hallazgo")
    assert r.startswith("Guardado")
    destino = Path(r.split("Guardado en ", 1)[1])
    assert destino.exists() and destino.parent == tmp_path.resolve()
    assert destino.name.startswith("nota_") and destino.name.endswith("_mi-hallazgo.md")
    lineas = destino.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "Mi hallazgo"  # el título es la primera línea
    assert "detalle del hallazgo" in destino.read_text(encoding="utf-8")

def test_resumen_de_sesion_escribe_con_llm(tmp_path, monkeypatch):
    """Al salir, con MEMORIA activo y >=2 preguntas, UNA llamada a call_llm
    resume y guarda memoria/sesion_FECHA.md. La llamada va fiteada."""
    import utils.call_llm as c

    monkeypatch.setenv("MEMORIA", "1")
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    llamadas = {"n": 0}

    def llm_fake(prompt):
        llamadas["n"] += 1
        assert "Resumí esta conversación" in prompt
        assert "hola mundo" in prompt and "chau mundo" in prompt  # ve la charla
        return "Tema: charla\n- Pedidos: hola\n- Resultado: chau"

    monkeypatch.setattr(c, "call_llm", llm_fake, raising=False)
    shared = {"messages": [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "hola mundo"},
        {"role": "assistant", "content": "respuesta uno"},
        {"role": "user", "content": "chau mundo"},
        {"role": "assistant", "content": "respuesta dos"},
    ]}
    mem.resumen_de_sesion(shared)
    assert llamadas["n"] == 1  # UNA sola llamada

    sesiones = list(tmp_path.glob("sesion_*.md"))
    assert len(sesiones) == 1
    assert "Tema: charla" in sesiones[0].read_text(encoding="utf-8")

def test_resumen_de_sesion_se_apaga_y_no_rompe(tmp_path, monkeypatch):
    """MEMORIA=0 no resume; menos de 2 preguntas tampoco; y un fallo del LLM
    no rompe la salida (bookkeeping)."""
    import utils.call_llm as c

    def no_llamar(prompt):
        raise AssertionError("no debería llamar al LLM")

    monkeypatch.setattr(c, "call_llm", no_llamar, raising=False)
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    monkeypatch.setenv("MEMORIA", "0")
    mem.resumen_de_sesion({"messages": [
        {"role": "user", "content": "una"}, {"role": "user", "content": "dos"}]})
    assert not list(tmp_path.glob("sesion_*.md"))

    monkeypatch.setenv("MEMORIA", "1")
    mem.resumen_de_sesion({"messages": [{"role": "user", "content": "una sola"}]})
    assert not list(tmp_path.glob("sesion_*.md"))  # <2 preguntas

    # fallo del LLM: se sale igual, sin archivo, sin excepción
    def explota(prompt):
        raise RuntimeError("sin saldo")

    monkeypatch.setattr(c, "call_llm", explota, raising=False)
    mem.resumen_de_sesion({"messages": [
        {"role": "user", "content": "una"}, {"role": "user", "content": "dos"}]})
    assert not list(tmp_path.glob("sesion_*.md"))

def test_resumen_de_sesion_rutas_visibles(capsys, monkeypatch, tmp_path):
    """Ninguna ruta del exit-summary es muda (episodio silencioso no
    reproducido: sin prints es indecidible cuál disparó)."""

    # desactivada
    monkeypatch.setenv("MEMORIA", "0")
    mem.resumen_de_sesion({"messages": []})
    assert "desactivada" in capsys.readouterr().out

    # sesión corta
    monkeypatch.setenv("MEMORIA", "1")
    mem.resumen_de_sesion({"messages": [
        {"role": "user", "content": "hola"},
    ]})
    assert "sesión corta" in capsys.readouterr().out

    # feliz: escribe y anuncia el destino
    monkeypatch.setattr("utils.call_llm.call_llm", lambda p: "resumen de prueba")
    monkeypatch.setattr(mem, "_raiz", lambda: tmp_path)
    mem.resumen_de_sesion({"messages": [
        {"role": "user", "content": "uno"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "dos"},
    ]})
    salida = capsys.readouterr().out
    assert "resumen de sesión guardado" in salida
    assert list(tmp_path.glob("sesion_*.md")), "no escribió el archivo"

def test_rag_indice_inconsistente_falla_cerrado(tmp_path, monkeypatch):
    """Un índice semántico con chunks.json y vectores.npy de largos distintos
    (reindexado interrumpido, o índice mezclado) hacía reventar buscar() con
    IndexError y, si sobran vectores, desalineaba el ranking en silencio.
    _cargar() debe detectar la inconsistencia y fallar con un error claro
    (reindexar) en vez de crashear o devolver basura."""
    import json

    import numpy as np

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)

    # 4 chunks pero solo 2 vectores: el caso del IndexError
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "semantico",
                    "chunks": [{"path": "a", "texto": "x"}] * 4}), encoding="utf-8")
    np.save(tmp_path / "vectores.npy", np.random.rand(2, 8).astype(np.float32))

    with pytest.raises(RuntimeError) as exc:
        rag._cargar()
    assert "inconsistente" in str(exc.value).lower() or "reindexa" in str(exc.value).lower()

    # y buscar() tampoco debe crashear con IndexError: propaga el RuntimeError claro
    monkeypatch.setattr(rag, "_indice_cache", None)
    with pytest.raises(RuntimeError):
        rag.buscar("cualquier cosa")

def test_rag_indice_sobran_vectores_falla_cerrado(tmp_path, monkeypatch):
    """El caso inverso (más vectores que chunks) no crashea pero desalinea el
    ranking en silencio: tambien debe fallar cerrado."""
    import json

    import numpy as np

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "semantico",
                    "chunks": [{"path": "a", "texto": "x"}] * 2}), encoding="utf-8")
    np.save(tmp_path / "vectores.npy", np.random.rand(5, 8).astype(np.float32))

    with pytest.raises(RuntimeError):
        rag._cargar()

def test_rag_indice_lexico_sin_vectores_ok(tmp_path, monkeypatch):
    """El modo léxico no lleva vectores: cargarlo NO debe exigir vectores.npy."""
    import json

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "lexico",
                    "chunks": [{"path": "a", "texto": "hola mundo"}]}), encoding="utf-8")

    modo, vectores, chunks = rag._cargar()
    assert modo == "lexico" and vectores is None and len(chunks) == 1

# Pre-filtro de contexto por Laya (Mesa 6)

def test_unidades_bloques_no_parte_parrafos():
    from utils.contexto import unidades_bloques

    texto = "# Título\n\nprimer párrafo\ncon dos líneas\n\n# Sección\n\nsegundo párrafo"
    bloques = unidades_bloques(texto)
    assert bloques == ["# Título", "primer párrafo\ncon dos líneas", "# Sección", "segundo párrafo"]
    assert unidades_bloques("") == []

def test_elegir_por_laya_sin_modelo_es_noop(monkeypatch):
    """Regla de hierro: sin Laya disponible, entran los primeros max sin
    perder recall (no-op). El filtro es un acelerador, no una dependencia.
    Desde exp/13 el checkpoint existe: la ausencia se SIMULA con monkeypatch
    (la regla es 'si no está disponible', no 'si nunca se entrenó')."""
    import utils.laya as ul
    from utils.contexto import elegir_por_laya

    monkeypatch.setattr(ul, "disponible", lambda setting=None: False)
    unidades = ["a", "b", "c", "d"]
    # checkpoint indisponible: _puntuar → None → TODAS (no-op real: antes
    # devolvía los primeros N y perdía recall en silencio)
    out = elegir_por_laya("consulta", unidades, 2, setting_modelo="LAYA_MODEL_PREFILTRO")
    assert out == unidades
    # con max<=0 o menos unidades que el tope, devuelve intactas
    assert elegir_por_laya("q", unidades, 0) == unidades
    assert elegir_por_laya("q", unidades[:2], 5) == unidades[:2]

def test_elegir_por_laya_elige_y_conserva_orden(monkeypatch):
    """Con un Laya simulado, elige los de mayor puntaje y los devuelve en
    ORDEN ORIGINAL (la relevancia decide qué entra, no cómo se muestra)."""
    import utils.contexto as ctx

    # simula puntajes de Laya: "a" y "c" aportan; "b" y "d" no
    puntajes = {"bloque a": 0.9, "bloque b": 0.1, "bloque c": 0.8, "bloque d": 0.4}
    # _puntuar suma texto_de (A07: el clasificador ve el CONTENIDO, no la ruta)
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting, texto_de=None: {
                            i: puntajes[u] for i, u in enumerate(unidades)})

    unidades = ["bloque a", "bloque b", "bloque c", "bloque d"]
    out = ctx.elegir_por_laya("q", unidades, 2)
    assert out == ["bloque a", "bloque c"]  # los 2 mejores, en orden original

def test_rag_prefiltro_noop_sin_modelo(monkeypatch):
    """rag_search con RAG_PREFILTRO=1 pero sin Laya: la salida queda intacta."""
    import modules.rag as rag
    import utils.contexto as ctx

    salida = ("3 fragmentos indexados (modo lexico); top 3:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b\n\n"
              "--- c.py (score 0.3) ---\ncuerpo c")
    # sin checkpoint del prefiltro: _puntuar levanta (Laya no está) → no-op
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting: (_ for _ in ()).throw(RuntimeError("sin modelo")))
    monkeypatch.setenv("RAG_PREFILTRO", "1")
    monkeypatch.setenv("RAG_PREFILTRO_N", "2")
    assert rag._prefiltrar("consulta", salida, 3) == salida  # sin Laya: intacta
    # con 0 lo apaga explícitamente
    monkeypatch.setenv("RAG_PREFILTRO", "0")
    assert rag._prefiltrar("consulta", salida, 3) == salida

def test_rag_prefiltro_actua_con_laya_simulado(monkeypatch):
    import modules.rag as rag
    import utils.contexto as ctx

    salida = ("3 fragmentos indexados (modo lexico); top 3:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b\n\n"
              "--- c.py (score 0.3) ---\ncuerpo c")
    monkeypatch.setenv("RAG_PREFILTRO", "1")
    monkeypatch.setenv("RAG_PREFILTRO_N", "1")
    # el fragmento que contiene "cuerpo c" aporta; el resto no
    monkeypatch.setattr(ctx, "_puntuar", lambda consulta, unidades, setting, texto_de=None: {
        i: (0.9 if "cuerpo c" in u else 0.1) for i, u in enumerate(unidades)})
    out = rag._prefiltrar("consulta", salida, 3)
    assert "[prefiltro Laya: 3 → 1 fragmentos]" in out
    assert out.startswith("3 fragmentos indexados")  # el resumen original se conserva
    assert "cuerpo c" in out and "cuerpo a" not in out

def test_memoria_prefiltro_noop_sin_modelo(tmp_path, monkeypatch):
    """memory_search sin Laya devuelve la memoria completa (no-op)."""
    import modules.memoria as mem
    import utils.contexto as ctx

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting: (_ for _ in ()).throw(RuntimeError("sin modelo")))
    (tmp_path / "a.md").write_text("nota sobre pytest y compacción\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("otra nota cualquiera\n", encoding="utf-8")
    out = mem.memory_search("compacción")
    assert "a.md" in out  # encuentra la nota real
    assert "prefiltro Laya" not in out  # sin Laya, sin aviso (no-op)

def test_memoria_prefiltro_actua(tmp_path, monkeypatch):
    import modules.memoria as mem
    import utils.contexto as ctx

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setenv("MEMORIA_PREFILTRO_N", "1")
    for nombre in ("a.md", "b.md", "c.md"):
        (tmp_path / nombre).write_text(f"contenido {nombre} sobre compacción\n", encoding="utf-8")
    # con el patch, el clasificador sigue viendo las unidades (en memoria son
    # Paths); en producción ve el CONTENIDO vía texto_de (A07)
    monkeypatch.setattr(ctx, "_puntuar", lambda consulta, unidades, setting, texto_de=None: {
        i: (0.9 if "b.md" in str(u) else 0.1) for i, u in enumerate(unidades)})
    out = mem.memory_search("compacción")
    assert "[prefiltro Laya: 3 → 1 archivos]" in out
    assert "b.md" in out

def test_rag_prefiltro_extrae_fragmentos():
    """El parser de la salida de buscar() separa fragmentos sin romper el
    shape (y devuelve None cuando no hay fragmentos)."""
    import modules.rag as rag

    salida = ("2 fragmentos indexados (modo lexico); top 2:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b")
    frags = rag._extraer_fragmentos(salida)
    assert len(frags) == 2
    assert frags[0].startswith("--- a.py (score 0.5) ---")
    assert "cuerpo b" in frags[1]
    assert rag._extraer_fragmentos("El índice está vacío: reindexa con rag_index.") is None

def test_catalogo_memoria_al_arranque(tmp_path, monkeypatch, capsys):
    """El arranque muestra el CATÁLOGO de la biblioteca (qué notas hay) SIN
    inyectar su contenido al contexto — el arranque vacío es regla (mesa 8)."""

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    (tmp_path / "nota_a.md").write_text("contenido secreto A\n", encoding="utf-8")
    (tmp_path / "nota_b.md").write_text("contenido secreto B\n", encoding="utf-8")

    mem.catalogo()
    salida = capsys.readouterr().out
    assert "biblioteca: 2 notas" in salida
    assert "nota_a.md" in salida and "nota_b.md" in salida
    # catálogo, no contenido: el cuerpo de las notas NO se imprime
    assert "contenido secreto" not in salida

    # MEMORIA=0 no muestra nada
    monkeypatch.setenv("MEMORIA", "0")
    mem.catalogo()
    assert capsys.readouterr().out == ""

def test_catalogo_memoria_vacio(tmp_path, monkeypatch, capsys):
    """Biblioteca vacía: no imprime nada (arranque silencioso)."""

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA", "1")
    mem.catalogo()
    assert capsys.readouterr().out == ""

def test_catalogo_memoria_resumen_acotado(tmp_path, monkeypatch, capsys):
    """Con muchas notas el arranque imprime el total y solo las últimas
    CATALOGO_MAX (la lista completa era spam: 229 de 234 tapaban las útiles)."""
    import os


    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA", "1")
    total = 20
    for i in range(total):
        p = tmp_path / f"nota_{i:02d}.md"
        p.write_text(f"cuerpo {i}\n", encoding="utf-8")
        # mtime creciente y determinista: nota_19 es la más reciente
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))

    mem.catalogo()
    salida = capsys.readouterr().out
    lineas = [linea for linea in salida.splitlines() if linea.strip().startswith("- ")]
    assert f"biblioteca: {total} notas" in salida
    assert len(lineas) == mem.CATALOGO_MAX < total
    assert "nota_19.md" in salida and "nota_00.md" not in salida
    assert "memory_search" in salida
    assert "cuerpo" not in salida

    # biblioteca vacía: ni catálogo ni recordatorio
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    monkeypatch.setenv("MEMORIA_DIR", str(vacia))
    mem.catalogo()
    assert capsys.readouterr().out == ""


def test_catalogo_memoria_nunca_rompe(monkeypatch, capsys):
    """Aunque la lectura de la biblioteca falle, el arranque sigue."""

    monkeypatch.setenv("MEMORIA", "1")
    import modules.memoria as mem

    def boom():
        raise OSError("disco")

    monkeypatch.setattr(mem, "_archivos_md", boom)
    mem.catalogo()  # no levanta
    assert capsys.readouterr().out == ""

def test_embed_decide_prefijo_despues_de_cargar(monkeypatch):
    """Fix 1: en la PRIMERA llamada de un proceso con e5 activo el prefijo
    debe decidirse sobre el nombre EFECTIVAMENTE cargado, no sobre la global
    (que arranca en None). Un fake de get_modelo deja _nombre_modelo en un
    nombre con 'e5' y captura el input: el texto debe llegar prefijado."""
    import utils.embeddings as emb

    capturado = {}

    class FakeModelo:
        def embed(self, textos):
            capturado["textos"] = list(textos)
            return [[0.0, 0.1] for _ in textos]

    def fake_get_modelo():
        emb._nombre_modelo = "intfloat/multilingual-e5-large"
        return FakeModelo()

    monkeypatch.setattr(emb, "_nombre_modelo", None)
    monkeypatch.setattr(emb, "get_modelo", fake_get_modelo)

    r = emb.embed(["hola"])  # UNA sola llamada

    assert capturado["textos"] == ["passage: hola"], capturado
    assert r == [[0.0, 0.1]]

def test_guardar_resumen_sesion_no_pisa_el_mismo_dia(tmp_path, monkeypatch):
    """Fix 6: dos sesiones el mismo día NO se pisan. La primera conserva el
    nombre clásico `sesion_FECHA.md`; la segunda usa sufijo horario, así que
    quedan DOS archivos distintos y cada uno con su contenido."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    p1 = mem.guardar_resumen_sesion("uno")
    p2 = mem.guardar_resumen_sesion("dos")

    assert p1 is not None and p2 is not None
    assert p1 != p2, "la segunda sesión del día pisó el archivo de la primera"
    # la primera conserva el nombre clásico
    from datetime import date

    assert p1.name == f"sesion_{date.today().isoformat()}.md"
    # ambas existen con su contenido propio
    assert p1.read_text(encoding="utf-8").strip() == "uno"
    assert p2.read_text(encoding="utf-8").strip() == "dos"
    sesiones = sorted(f.name for f in tmp_path.glob("sesion_*.md"))
    assert len(sesiones) == 2

def test_guardar_resumen_sesion_no_pisa_el_mismo_minuto(tmp_path, monkeypatch):
    """Fix 6 (residual): el sufijo del segundo archivo era solo HHMM, así que
    una TERCERA sesión dentro del mismo minuto volvía a pisar a la segunda.
    El nombre se hace único contra lo que YA existe, no contra el reloj."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    rutas = [mem.guardar_resumen_sesion(f"contenido {i}") for i in range(3)]

    assert all(p is not None for p in rutas)
    assert len(set(rutas)) == 3, f"dos sesiones del mismo minuto se pisaron: {rutas}"
    for i, p in enumerate(rutas):
        assert p.read_text(encoding="utf-8").strip() == f"contenido {i}"
    assert len(list(tmp_path.glob("sesion_*.md"))) == 3

def test_rag_invalida_la_cache_al_reindexar(tmp_path, monkeypatch):
    """exp/23 (C10 de la auditoría externa): el índice en disco puede ser
    nuevo y la búsqueda de la MISMA sesión devolver el anterior —
    _indice_cache solo se llenaba y nadie la invalidaba al reindexar."""
    import json as _json

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)

    def escribir(texto):
        (tmp_path / "chunks.json").write_text(
            _json.dumps({"modo": "lexico", "chunks": [{"texto": texto, "ruta": "a.txt"}]}),
            encoding="utf-8",
        )

    escribir("ALFA")
    assert rag._cargar()[2][0]["texto"] == "ALFA"
    escribir("BETA")
    assert rag._cargar()[2][0]["texto"] == "ALFA"   # caché vieja, a propósito

    rag.SaveIndex().post({}, None, ("lexico", 1, False))
    assert rag._cargar()[2][0]["texto"] == "BETA"   # el índice se publicó
