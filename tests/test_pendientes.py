"""Cierra los pendientes de la auditoría que seguían abiertos (2026-10-15).

Cubre: A18 (Effective N con JSON de forma inválida), A19 (params por corrida),
A22 (duraciones sin doble conteo), A23 (lote de Laya acotado), A24 (pico de
checkpoints), A28 (cita_ok cuenta el caso que lanza), H13 (read_file acotado),
H14 (escritura atómica) y H17 (el error de búsqueda no llega al LLM).
"""
import contextlib
import io
import json
import sys
import types
from pathlib import Path

import pytest
from conftest import requiere_repo_git

from modules import memoria


@pytest.fixture(autouse=True)
def _bench_en_shadow(monkeypatch):
    """El bench del router mide calibración/modelo: corre en SHADOW. La suite
    no puede depender del .env local (exp/45 puso enforce + calibración ahí y
    movía el veredicto de estos tests). Los tests que necesitan otro modo lo
    fijan explícitamente con monkeypatch (gana el último setenv)."""
    monkeypatch.setenv("LAYA_MODO", "shadow")

# A18 / A19 — Effective N
@pytest.mark.parametrize("crudo", ["[]", "null", '{"fields": null, "answers": {}}'])
def test_effective_n_tolera_forma_invalida(tmp_path, crudo):
    """JSON válido con estructura equivocada se CUENTA, no revienta."""
    import effective_n

    f = tmp_path / "x.jsonl"
    f.write_text(crudo + "\n", encoding="utf-8")
    r = effective_n.HashFile().exec(str(f))
    assert (r["n"], r["rotos"], r["forma"], r["huellas"]) == (1, 0, 1, [])


def test_effective_n_distingue_json_ilegible(tmp_path):
    import effective_n

    f = tmp_path / "x.jsonl"
    f.write_text("{no es json\n", encoding="utf-8")
    r = effective_n.HashFile().exec(str(f))
    assert (r["rotos"], r["forma"]) == (1, 0)


def test_effective_n_reutilizado_procesa_la_carpeta_nueva(tmp_path):
    """Reusar el mismo flow no debe congelar los params de la 1ª corrida."""
    from modules.effective_n import create_effective_n_flow

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for carpeta, nombre in ((a, "a.jsonl"), (b, "b.jsonl")):
        (carpeta / nombre).write_text(
            json.dumps({"fields": {"pregunta": nombre}, "answers": {"next": "x"}}) + "\n",
            encoding="utf-8",
        )
    flujo = create_effective_n_flow()
    with contextlib.redirect_stdout(io.StringIO()):
        flujo.run({"folder": str(a)})
        flujo.run({"folder": str(b)})
    assert flujo.params["folder"] == str(b)


# A22 — duraciones
def test_costo_traza_no_cuenta_dos_veces_lo_anidado():
    """Una tool de 10 s dentro de un nodo de 10 s son 10 s de pared, no 20."""
    import evals

    eventos = [
        {"ts": 100.0, "nodo": "ExecuteTools", "accion": "default", "seg": 10.0},
        {"ts": 100.0, "nodo": "read_file", "accion": "ok", "seg": 10.0},
    ]
    r = evals.costo_traza(eventos)
    assert r["total"] == 10.0
    assert r["total_inclusivo"] == 20.0
    assert r["anidados"] == 1


def test_costo_traza_suma_lo_no_anidado():
    import evals

    eventos = [
        {"ts": 0.0, "nodo": "run_command", "accion": "ok", "seg": 4.0},
        {"ts": 100.0, "nodo": "sql", "accion": "ok", "seg": 1.0},
    ]
    r = evals.costo_traza(eventos)
    assert r["total"] == 5.0 and r["anidados"] == 0


# A23 — lote de Laya
class _AgenteFalso:
    def __init__(self, visto):
        self.visto = visto

    def predict_batch(self, estados, preguntas, **kw):
        self.visto.update(kw)
        return [{"answers": {}} for _ in estados]


def test_preguntar_lote_pasa_batch_size(monkeypatch):
    from utils import laya

    visto = {}
    monkeypatch.setenv("LAYA_BATCH_SIZE", "4")
    monkeypatch.setattr(laya, "agente", lambda *a, **k: _AgenteFalso(visto))
    laya.preguntar_lote([{"x": i} for i in range(10)], {"aporta_contexto": "¿aporta?"})
    assert visto.get("batch_size") == 4


def test_preguntar_lote_sin_config_no_limita(monkeypatch):
    """Sin LAYA_BATCH_SIZE el comportamiento es el de siempre (sin kwargs)."""
    from utils import laya

    visto = {}
    monkeypatch.delenv("LAYA_BATCH_SIZE", raising=False)
    monkeypatch.setattr(laya, "agente", lambda *a, **k: _AgenteFalso(visto))
    laya.preguntar_lote([{"x": i} for i in range(3)], {"aporta_contexto": "¿aporta?"})
    assert "batch_size" not in visto


# A24 — pico de checkpoints
def test_agente_desaloja_antes_de_cargar(monkeypatch):
    """El pico de checkpoints vivos nunca supera MAX_EN_PROCESO."""
    from utils import laya

    vivos_al_cargar = []

    def cargar(clave):
        vivos_al_cargar.append(len(laya._agentes))
        return object()

    monkeypatch.setitem(sys.modules, "laya", types.SimpleNamespace(load=cargar))
    monkeypatch.setattr(laya, "_agentes", {}, raising=False)
    monkeypatch.setattr(laya, "_errores", {}, raising=False)
    monkeypatch.setattr(laya, "_uso", {}, raising=False)
    monkeypatch.setattr(laya, "MAX_EN_PROCESO", 2, raising=False)
    # tres SETTINGS distintos: agente() resuelve la clave con _setting(), así
    # que sin variables de entorno las tres llamadas caen al modelo default
    for i, clave in enumerate(("A", "B", "C")):
        monkeypatch.setenv(f"AUDIT_MODEL_{clave}", f"checkpoint_{i}")
    with contextlib.redirect_stdout(io.StringIO()):
        for clave in ("A", "B", "C"):
            laya.agente(f"AUDIT_MODEL_{clave}")
    # antes de cada carga había a lo sumo MAX-1 vivos ⇒ el pico es MAX
    assert max(vivos_al_cargar) <= 1
    assert len(laya._agentes) == 2


# A28 — cita_ok con el caso que lanza
def test_bench_juez_cuenta_el_caso_que_lanza_como_cita_incumplida(monkeypatch):
    import bench_juez

    casos = [
        {"id": "ok", "pregunta": "ok", "cita_archivo": "demo.py"},
        {"id": "roto", "pregunta": "roto", "cita_archivo": "demo.py"},
    ]

    def responder(pregunta):
        if pregunta == "roto":
            raise RuntimeError("fallo simulado")
        return "cita demo.py:1", None

    monkeypatch.setattr(bench_juez, "cita_ok", lambda texto, caso: True)
    monkeypatch.setattr(bench_juez, "detalle_fallo", lambda texto, caso: [])
    with contextlib.redirect_stdout(io.StringIO()):
        bench = bench_juez.correr(casos, responder)
    # el caso que exigía cita y murió cuenta como incumplida, no se excluye
    assert bench["n_con_cita"] == 2
    assert bench["cita_ok"] == 0.5


# H13 — read_file acotado
def test_read_file_pagina_sin_materializar_el_archivo(tmp_path, monkeypatch):
    from utils import fs_tools

    grande = tmp_path / "grande.txt"
    grande.write_text("\n".join(f"linea {i}" for i in range(5000)) + "\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    salida = fs_tools.read_file(str(grande), offset=4000, limit=3)
    assert "líneas 4000–4002 de 5000" in salida
    assert salida.rstrip().endswith("linea 4001")


def test_read_file_sigue_rechazando_binarios(tmp_path, monkeypatch):
    from utils import fs_tools

    b = tmp_path / "bin.dat"
    b.write_bytes(b"\x00\x01\x02" * 100)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    assert fs_tools.read_file(str(b)).startswith("ERROR: archivo binario")


# H14 — escritura atómica
def test_escribir_atomico_publica_y_no_deja_tmp(tmp_path):
    from utils.fs_tools import escribir_atomico

    destino = tmp_path / "x.md"
    destino.write_text("viejo", encoding="utf-8")
    escribir_atomico(destino, "nuevo")
    assert destino.read_text(encoding="utf-8") == "nuevo"
    assert not list(tmp_path.glob("*.tmp"))


def test_escribir_salida_es_atomico(tmp_path, monkeypatch):
    from utils.fs_tools import escribir_salida

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    destino, err = escribir_salida(str(tmp_path / "sub" / "out.md"), "hola")
    assert err is None and destino.read_text(encoding="utf-8") == "hola"
    assert not list(tmp_path.rglob("*.tmp"))


# H17 — research: el error de búsqueda no va al LLM
def test_research_no_manda_el_error_al_llm(monkeypatch):
    import research

    llamado = []
    monkeypatch.setattr(research, "search_web",
                        lambda q, k=5: "ERROR: búsqueda web falló (RuntimeError: sin red)")
    monkeypatch.setattr(research, "call_llm",
                        lambda *a, **k: llamado.append(1) or "hechos inventados")
    with contextlib.redirect_stdout(io.StringIO()):
        salida = research.Researcher().exec("consulta")
    assert llamado == []
    assert "búsqueda sin resultados" in salida

# A09/H02 — no-clobber en las tools del CHAT
def test_salida_ya_existe(tmp_path, monkeypatch):
    from utils.fs_tools import salida_ya_existe

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    destino = tmp_path / "informe.md"
    assert salida_ya_existe(str(destino)) is None  # libre
    destino.write_text("viejo", encoding="utf-8")
    assert "ya existe" in salida_ya_existe(str(destino))


def test_run_informe_no_pisa_una_salida_elegida(tmp_path, monkeypatch):
    """Si el MODELO eligió la ruta y ya existe, se rechaza antes de correr el flujo."""
    from modules.informe import run_informe

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    salida = tmp_path / "informe.md"
    salida.write_text("viejo", encoding="utf-8")
    r = run_informe(carpeta=str(tmp_path), salida=str(salida))
    assert r.startswith("ERROR: ya existe")
    assert salida.read_text(encoding="utf-8") == "viejo"


def test_la_cli_sigue_pisando(tmp_path, monkeypatch):
    """Sin la guarda (flujos de la CLI) escribir_salida reescribe como siempre."""
    from utils.fs_tools import escribir_salida

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    destino = tmp_path / "out.md"
    destino.write_text("viejo", encoding="utf-8")
    _, err = escribir_salida(str(destino), "nuevo")
    assert err is None and destino.read_text(encoding="utf-8") == "nuevo"


# A17/H12 — la zona fría se respalda antes de descartarla
def _historial_largo():
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "OBJETIVO_ACTIVO"}]
    for i in range(10):
        msgs.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": str(i), "type": "function",
                                     "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": str(i), "content": "X" * 1000})
    return msgs


def test_zona_fria_coincide_con_lo_que_compactar_descarta():
    from utils.compaccion import compactar, zona_fria

    msgs = _historial_largo()
    descartados = len(msgs) - len(compactar(msgs, 4000)) + 1  # +1: el resumen
    assert len(zona_fria(msgs)) == descartados


def test_compaccion_respalda_la_zona_fria(tmp_path, monkeypatch):
    from utils.compaccion import compactar

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path / "memoria"))
    msgs = _historial_largo()
    ruta = memoria.respaldar_zona_fria(msgs)
    assert ruta is not None
    assert "OBJETIVO_ACTIVO" in Path(ruta).read_text(encoding="utf-8")
    assert ruta in compactar(msgs, 4000, respaldo=ruta)[1]["content"]


def test_marcador_sin_respaldo_no_promete_memoria():
    """El texto viejo afirmaba que los hechos estaban en memoria/ sin guardarlos."""
    from utils.compaccion import compactar

    marcador = compactar(_historial_largo(), 4000)[1]["content"]
    assert "memoria/" not in marcador
    assert "compactados" in marcador


def test_compaccion_no_respalda_con_memoria_apagada(tmp_path, monkeypatch):
    """exp/71: con MEMORIA=0 la biblioteca está apagada (no hay catálogo ni
    memory_search), así que el respaldo no tendría recuperación posible: no se
    escribe. La suite corría con MEMORIA=1 y el banco con 0, pero el respaldo
    ignoraba el setting: dejaban respaldos de fixture en `memoria/` (157 de 243)."""

    raiz = tmp_path / "memoria"
    monkeypatch.setenv("MEMORIA_DIR", str(raiz))
    monkeypatch.setenv("MEMORIA", "0")
    assert memoria.respaldar_zona_fria(_historial_largo()) is None
    assert _notas(raiz) == []


# A17 — respaldar la zona fría UNA vez por contenido (no en cada compacción)
def _notas(directorio):
    return sorted(directorio.glob("*.md")) if directorio.exists() else []


def test_zona_fria_identica_no_se_respalda_dos_veces(tmp_path, monkeypatch):
    """Dos compacciones con la MISMA zona fría: la segunda no escribe nota ni
    duplica archivo (medido: 143 respaldos con el mismo cuerpo)."""

    raiz = tmp_path / "memoria"
    monkeypatch.setenv("MEMORIA_DIR", str(raiz))
    msgs = _historial_largo()
    shared = {}

    primera = memoria.respaldar_zona_fria(msgs, shared)
    segunda = memoria.respaldar_zona_fria(msgs, shared)

    assert primera is not None and Path(primera).exists()
    assert segunda == primera          # devuelve la ruta del respaldo que ya existe
    assert len(_notas(raiz)) == 1      # no se escribió una segunda nota


def test_zona_fria_distinta_se_respalda_de_nuevo(tmp_path, monkeypatch):
    """Si la zona fría CAMBIÓ, el respaldo legítimo sigue ocurriendo."""

    raiz = tmp_path / "memoria"
    monkeypatch.setenv("MEMORIA_DIR", str(raiz))
    shared = {}

    primera = memoria.respaldar_zona_fria(_historial_largo(), shared)
    otra = _historial_largo()
    otra[3]["content"] = "Z" * 1000     # la zona fría ahora dice otra cosa
    segunda = memoria.respaldar_zona_fria(otra, shared)

    assert primera != segunda
    assert len(_notas(raiz)) == 2
    assert "ZZZ" in Path(segunda).read_text(encoding="utf-8")


def test_marcador_de_compaccion_menciona_el_ultimo_respaldo(tmp_path, monkeypatch):
    """A17: el mensaje de compacción dice dónde quedó el detalle descartado.
    Si la segunda compacción descarta OTRA zona fría (9 y después 5 mensajes),
    el respaldo es legítimo, va con sufijo -2 y el marcador debe nombrar ESE,
    no el de la primera (el caso "misma zona fría" lo cubre
    test_zona_fria_identica_no_se_respalda_dos_veces)."""
    import nodes
    from utils.compaccion import PREFIJO_COMPACCION

    raiz = tmp_path / "memoria"
    monkeypatch.setenv("MEMORIA_DIR", str(raiz))
    monkeypatch.setenv("COMPACTION_CHARS", "200")
    largo = _historial_largo()

    shared = {"messages": list(largo), "tool_rounds": 0}
    nodes.Contexto()._run(shared)
    mensajes = shared["messages"]
    ruta = shared["_respaldo_ruta"]
    assert mensajes[1]["content"].startswith(PREFIJO_COMPACCION)
    assert ruta in mensajes[1]["content"]
    assert "memory_search" in mensajes[1]["content"]
    assert len(_notas(raiz)) == 1

    # segunda compacción con zona fría distinta: otra nota y el marcador
    # apunta a la nueva ruta.
    shared["messages"] = list(mensajes) + [
        {"role": "assistant", "content": "sigo " + "y" * 500},
        {"role": "user", "content": "seguí"},
    ]
    shared.pop("_compaccion_huella")
    nodes.Contexto()._run(shared)
    mensajes2 = shared["messages"]
    ruta2 = shared["_respaldo_ruta"]
    assert shared["compacciones"] == 2
    assert ruta2 != ruta
    assert Path(ruta2).exists()
    assert mensajes2[1]["content"].startswith(PREFIJO_COMPACCION)
    assert ruta2 in mensajes2[1]["content"]
    assert ruta not in mensajes2[1]["content"]
    assert len(_notas(raiz)) == 2


def test_titulo_de_respaldo_lleva_segundos(tmp_path, monkeypatch):
    """El formato de _ahora() y del nombre de archivo lleva SEGUNDOS (antes
    iba a minutos y dos compacciones del mismo minuto las desambiguaba
    guardar_nota con -2, -3)."""
    import re


    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}", memoria._ahora())
    # el reloj se congela DESPUÉS de medir el formato: lo que se mide acá es
    # el nombre de archivo que produce guardar_nota con un título dado.
    monkeypatch.setattr(memoria, "_ahora", lambda: "2026-10-21 12-34-56")
    # el PREFIJO del nombre usa memoria.date.today() (otra fuente de fecha): sin
    # congelarla el test era un time-bomb — falló al cruzar a 2026-10-22.
    from datetime import date
    from types import SimpleNamespace

    monkeypatch.setattr(
        "modules.memoria.date", SimpleNamespace(today=lambda: date(2026, 10, 21))
    )
    raiz = tmp_path / "memoria"
    monkeypatch.setenv("MEMORIA_DIR", str(raiz))

    memoria.respaldar_zona_fria(_historial_largo(), {})
    nombres = [n.name for n in _notas(raiz)]
    assert nombres == [
        "nota_2026-10-21_compactacion-2026-10-21-12-34-56.md"], nombres
    primera = (raiz / nombres[0]).read_text(encoding="utf-8").splitlines()[0]
    assert primera == "Compactación 2026-10-21 12-34-56", primera

# A10/H10 — el bench mide la política de producción (no una copia)
class _AgenteFijo:
    def __init__(self, choice="directo", conf=0.95):
        self.choice, self.conf = choice, conf
        self.llamadas = 0

    def system_one(self, estado, preguntas, lang="es"):
        self.llamadas += 1
        return {"answers": {"necesita_herramientas": {
            "choice": self.choice,
            "probabilities": {"directo": self.conf,
                              "herramientas": round(1 - self.conf, 4)},
        }}}


def _router_jsonl(tmp_path, casos):
    f = tmp_path / "router.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in casos) + "\n", encoding="utf-8")
    return f


def test_bench_usa_la_politica_y_separa_las_metricas(tmp_path, monkeypatch):
    """La propuesta sale de utils.laya_routing.decide y el modo decide qué se aplica."""
    import evals

    monkeypatch.setenv("LAYA_MODO", "shadow")
    monkeypatch.setattr(evals, "TEST_ROUTER", _router_jsonl(tmp_path, [
        {"id": "a", "fields": {"pregunta": "¿qué es un closure?"},
         "answers": {"necesita_herramientas": "directo"}},
        {"id": "b", "fields": {"pregunta": "leé config"},
         "answers": {"necesita_herramientas": "herramientas"}},
    ]))
    r, err = evals.correr_bench(agente=_AgenteFijo())
    assert err is None and r["modo"] == "shadow"
    # la política propone directo (0.95 >= 0.85), pero en shadow NO se aplica
    assert r["score"] == 0.5             # propuestas acertadas
    assert r["score_aplicada"] == 0.5    # herramientas en los dos casos
    assert r["score_crudo"] == 0.5       # elección pelada del modelo
    assert r["filas"][0]["propuesta"] == "directo"
    assert r["filas"][0]["aplicada"] == "herramientas"


def test_bench_enforce_no_gasta_laya_con_la_regla_temporal(tmp_path, monkeypatch):
    import evals

    monkeypatch.setenv("LAYA_MODO", "enforce")
    monkeypatch.setattr(evals, "TEST_ROUTER", _router_jsonl(tmp_path, [
        {"id": "hoy", "fields": {"pregunta": "¿qué pasó hoy en el repo?"},
         "answers": {"necesita_herramientas": "herramientas"}},
        {"id": "normal", "fields": {"pregunta": "¿qué es un closure?"},
         "answers": {"necesita_herramientas": "directo"}},
    ]))
    agente = _AgenteFijo()
    r, _ = evals.correr_bench(agente=agente)
    assert r["n_regla"] == 1
    assert agente.llamadas == 1  # la regla dura corta ANTES del modelo
    assert r["score"] == 1.0


def test_bench_trunca_la_pregunta_como_produccion(tmp_path, monkeypatch):
    """El estado que ve Laya lleva el mismo corte de 1000 chars que LayaRouter.prep."""
    import evals

    visto = {}

    class Agente:
        def system_one(self, estado, preguntas, lang="es"):
            visto.update(estado)
            return {"answers": {"necesita_herramientas": {
                "choice": "herramientas",
                "probabilities": {"directo": 0.1, "herramientas": 0.9}}}}

    monkeypatch.setattr(evals, "TEST_ROUTER", _router_jsonl(tmp_path, [
        {"id": "larga", "fields": {"pregunta": "x" * 5000},
         "answers": {"necesita_herramientas": "herramientas"}},
    ]))
    evals.correr_bench(agente=Agente())
    assert len(visto["pregunta"]) == 1000

# A21 — cancelar el HITL web no deja el pedido pendiente
def test_cancelar_hitl_web_limpia_el_pedido(monkeypatch):
    from utils import hitl_web

    def _cortar(self, timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(hitl_web, "_arrancar", lambda: 8765)
    monkeypatch.setattr(hitl_web.threading.Event, "wait", _cortar)
    with contextlib.suppress(KeyboardInterrupt):
        hitl_web.aprobar("demo", "sin efectos")
    assert hitl_web._pendientes == {}

# PR 5 — portabilidad: sin rutas personales ni .env ajeno
def test_leer_bmo_env_default_no_lee_el_env_ajeno(tmp_path, monkeypatch):
    """El harness es autónomo: sin LEER_BMO_ENV=1 no se lee el .env de bmo."""
    from utils import call_llm

    ajeno = tmp_path / "bmo.env"
    ajeno.write_text("MARCADOR_SOLO_BMO=1\n", encoding="utf-8")
    monkeypatch.setattr(call_llm, "BMO_ENV", ajeno)
    monkeypatch.delenv("LEER_BMO_ENV", raising=False)
    monkeypatch.delenv("MARCADOR_SOLO_BMO", raising=False)
    assert call_llm._setting("MARCADOR_SOLO_BMO", "no") == "no"   # default: no lo lee
    monkeypatch.setenv("LEER_BMO_ENV", "1")
    assert call_llm._setting("MARCADOR_SOLO_BMO", "no") == "1"    # opt-in: sí


@pytest.mark.git
@requiere_repo_git
def test_ningun_archivo_versionado_tiene_rutas_absolutas_del_autor():
    """Portabilidad: las rutas ABSOLUTAS de la máquina del autor no viajan.

    Se busca `/home/<usuario>` (la ruta puntual de esta máquina), no las
    referencias relativas al HOME (`~/Documentos/00_IA/...`), que son
    portables. Se saltean docs/ (informes históricos), LICENSE, .env.example
    (documenta LEER_BMO_ENV), los archivos grandes (trazas.db), los JSONL de
    calibración (transcripciones grabadas: reescribirlas falsearía el dato),
    utils/call_llm.py (define BMO_ENV a propósito) y este mismo archivo.
    """
    import subprocess

    raiz = Path(__file__).resolve().parent.parent
    archivos = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                              cwd=raiz, check=False).stdout.split()
    permitidos = {"LICENSE", ".env.example", "utils/call_llm.py",
                  "tests/test_pendientes.py"}
    sospechosos = []
    for rel in archivos:
        if rel.startswith(("docs/", "banco/calibracion_")) or rel in permitidos:
            continue
        p = raiz / rel
        try:
            if p.stat().st_size > 2_000_000:
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "/home/roquedb" in texto:
            sospechosos.append(rel)
    assert not sospechosos, f"rutas personales en archivos versionados: {sospechosos}"


def test_los_escenarios_usan_placeholders():
    """Los YAML del banco traen {RAIZ}/{HOME} y banco.py los expande."""
    import importlib.util
    import subprocess

    raiz = Path(__file__).resolve().parent.parent
    yaml_con_ruta = subprocess.run(
        ["grep", "-rl", "{RAIZ}", "banco/escenarios"], capture_output=True, text=True,
        cwd=raiz, check=False).stdout.split()
    assert yaml_con_ruta, "ningún escenario usa {RAIZ}: ¿se perdieron los placeholders?"
    spec = importlib.util.spec_from_file_location("banco_mod", raiz / "banco" / "banco.py")
    mod = importlib.util.module_from_spec(spec)
    with contextlib.suppress(SystemExit):  # el módulo define un main
        spec.loader.exec_module(mod)
    assert mod.sustituir_placeholders("{RAIZ}/x") == f"{raiz}/x"
    assert mod.sustituir_placeholders("{HOME}/x") == f"{Path.home()}/x"

# Hallazgos abiertos de la auditoría — cierre 2026-10-16
def test_router_registra_la_ruta_final_y_el_voto_recibe_la_pregunta(monkeypatch):
    """A04 (la ruta aplicada se registra tras el voto) y A05 (el voto recibe la
    pregunta, no el dict del prep)."""
    import nodes
    from utils import laya_routing

    eventos, recibido = [], []

    class Cfg:
        modo = "enforce"
        umbral = 0.85
        q = None
        version = "test"

    monkeypatch.setattr(laya_routing, "config_router", lambda: Cfg())
    monkeypatch.setattr(laya_routing, "decide",
                        lambda resp, cfg: ("directo", "p(directo)=0.99 >= umbral 0.85", 0.99))
    monkeypatch.setattr(laya_routing, "registrar_decision",
                        lambda ev, pregunta=None, **k: eventos.append((ev, pregunta)))
    monkeypatch.setattr(nodes, "voto_confirmacion_router",
                        lambda pregunta: (recibido.append(pregunta), "herramientas")[1])

    accion = nodes.LayaRouter().post({"messages": []}, {"pregunta": "hola"}, None)

    assert accion == "herramientas"          # 2-de-2: el voto vetó
    assert recibido == ["hola"]              # A05: la pregunta, no "{'pregunta': 'hola'}"
    ev, preg = eventos[0]
    assert ev["aplicada"] == "herramientas"  # A04: lo que se APLICÓ, no lo propuesto
    assert ev["propuesta"] == "directo"
    assert ev["voto"] == "herramientas" and "herramientas" in (ev["veto"] or "")
    assert preg == "hola"


def test_despachador_rechaza_envoltura_incompleta():
    """A27: envoltura incompleta devuelve error de tool, no un KeyError."""
    from utils.fs_tools import run_tool_call

    for tool_call in ({}, {"function": {}}, {"function": {"name": None}}):
        salida = run_tool_call(tool_call)
        assert salida["role"] == "tool"
        assert salida["content"].startswith("ERROR: tool call")


def test_prefiltro_de_memoria_puntua_el_contenido(tmp_path, monkeypatch):
    """A07: el clasificador ve el CONTENIDO de la nota, no su ruta."""
    import modules.memoria as mem
    from utils import laya

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setenv("MEMORIA_PREFILTRO_N", "1")
    (tmp_path / "a.md").write_text("nota sobre arqueología andina", encoding="utf-8")
    (tmp_path / "b.md").write_text("nota sobre cocina", encoding="utf-8")

    visto = {}

    def falso(estados, preguntas, setting=None):
        visto["bloques"] = [e["bloque"] for e in estados]
        return [{"aporta_contexto": ("si", 0.9)} for _ in estados]

    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(laya, "preguntar_lote", falso)
    mem.memory_search("arqueología")

    assert visto["bloques"], "el prefiltro no llamó al clasificador"
    assert any("arqueología andina" in b for b in visto["bloques"])  # contenido
    assert all(not b.endswith(".md") for b in visto["bloques"])      # no la ruta


def test_memory_save_no_pisa_la_nota_del_dia(tmp_path, monkeypatch):
    """X4: dos notas del mismo título el mismo día no se pisan."""
    from modules import memoria

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    r1 = memoria.memory_save("misma nota", "primera versión")
    r2 = memoria.memory_save("misma nota", "segunda versión")
    assert r1 != r2
    assert "primera versión" in Path(r1.split("Guardado en ", 1)[1]).read_text(encoding="utf-8")
    assert "segunda versión" in Path(r2.split("Guardado en ", 1)[1]).read_text(encoding="utf-8")


def test_el_scratch_del_banco_no_sale_del_proyecto():
    """X3: el scratch se borra solo dentro del proyecto."""
    import importlib.util

    raiz = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("banco_mod2", raiz / "banco" / "banco.py")
    mod = importlib.util.module_from_spec(spec)
    with contextlib.suppress(SystemExit):
        spec.loader.exec_module(mod)
    assert mod.objetivo_scratch("salidas/scratch") is not None
    assert mod.objetivo_scratch("/tmp/absoluto") is None
    assert mod.objetivo_scratch("../fuera") is None
    assert mod.objetivo_scratch(".") is None





