"""Flujos y jueces: lote, supervisor, informe, research, debate y verdicts (PR 4)."""
from pathlib import Path

import pytest


def test_extraer_yaml_tres_formatos():
    from utils.estructura import extraer_yaml

    assert extraer_yaml("bla ```yaml\nverdict: ok\n```")["verdict"] == "ok"
    assert extraer_yaml("bla ```\nverdict: retry\n```")["verdict"] == "retry"
    assert extraer_yaml("verdict: ok")["verdict"] == "ok"
    # extraer_yaml valida con assert (el retry del Node es el mismo mecanismo)
    with pytest.raises(AssertionError):
        extraer_yaml("no hay yaml acá")

def test_huella_ignora_id_y_created():
    from effective_n import huella

    base = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "read_file"}}
    mismo_caso = dict(base, id="otro", created="2026-10-02", model="otro-modelo")
    assert huella(base) == huella(mismo_caso)
    otra_etiqueta = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "write_file"}}
    assert huella(base) != huella(otra_etiqueta)

def test_effective_n_flow(tmp_path):
    import json as _json

    from effective_n import create_effective_n_flow

    casos = [
        {"id": "1", "fields": {"task": "a"}, "answers": {"next": "read_file"}},
        {"id": "2", "fields": {"task": "a"}, "answers": {"next": "read_file"}},  # dup interno (id distinto)
        {"id": "3", "fields": {"task": "b"}, "answers": {"next": "list_files"}},
    ]
    (tmp_path / "uno.jsonl").write_text(
        "\n".join(_json.dumps(c) for c in casos) + "\n", encoding="utf-8"
    )
    (tmp_path / "dos.jsonl").write_text(
        _json.dumps(casos[0]) + "\n"  # duplicado ENTRE archivos
        + _json.dumps({"id": "4", "fields": {"task": "c"}, "answers": {"next": "finish"}}) + "\n",
        encoding="utf-8",
    )

    shared = {"folder": str(tmp_path), "glob": "*.jsonl", "salida": str(tmp_path / "out.md")}
    create_effective_n_flow().run(shared)
    assert shared["resumen"] == "5 registros → Effective N 3 (2 duplicados)"
    md = Path(shared["informe"]).read_text(encoding="utf-8")
    assert "Effective N: 3" in md

def _escribir_caso(carpeta, nombre, task, nxt):
    import json as _json

    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_text(
        _json.dumps({"id": task, "fields": {"task": task}, "answers": {"next": nxt}}) + "\n",
        encoding="utf-8",
    )
    return carpeta.resolve()

def test_effective_n_una_carpeta_igual_que_siempre(tmp_path, monkeypatch):
    """Compatibilidad hacia atrás: con una sola carpeta la salida es el
    informe de siempre (sin cabecera conjunta ni secciones por carpeta)."""
    from effective_n import main as en_main

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    salida = tmp_path / "one.md"
    en_main([str(a), "--salida", str(salida)])
    md = salida.read_text(encoding="utf-8")
    assert md.startswith("# Effective N —")
    assert "## Carpeta" not in md  # no es el informe conjunto

def test_effective_n_multi_carpeta_batchflow(tmp_path, capsys, monkeypatch):
    """Dos carpetas con el MISMO flujo faneado (BatchFlow, secuencial):
    secciones de ambas y resumen conjunto, en el orden pedido."""
    from effective_n import main as en_main

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    b = _escribir_caso(tmp_path / "b", "dos.jsonl", "y", "list_files")
    salida = tmp_path / "both.md"

    en_main([str(a), str(b), "--salida", str(salida)])
    md = salida.read_text(encoding="utf-8")
    assert md.splitlines()[0].startswith("# Effective N — lote de 2 carpetas")
    assert md.count("## Carpeta") == 2
    assert f"Carpeta `{a}`" in md and f"Carpeta `{b}`" in md
    # orden determinista: la sección de `a` antes de la de `b`
    assert md.index(str(a)) < md.index(str(b))
    # cada sección lleva SOLO su carpeta (el job viaja en params, no se mezcla)
    sec_a = md.split(f"Carpeta `{a}`")[1].split("## Carpeta")[0]
    assert "uno.jsonl" in sec_a and "dos.jsonl" not in sec_a
    sec_b = md.split(f"Carpeta `{b}`")[1].split("## Carpeta")[0]
    assert "dos.jsonl" in sec_b and "uno.jsonl" not in sec_b
    # secciones degradadas: los H1 de los informes internos pasan a H2
    assert md.count("\n# ") == 0
    assert capsys.readouterr().out.count("Carpeta procesada") == 2

def test_effective_n_multi_carpeta_total(tmp_path):
    """El resumen conjunto suma los registros reales de todas las carpetas."""
    from effective_n import EffectiveNMulti

    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    _escribir_caso(tmp_path / "a", "dos.jsonl", "y", "list_files")
    b = _escribir_caso(tmp_path / "b", "tres.jsonl", "z", "finish")
    shared = {"informes": []}
    EffectiveNMulti([a, b], "*.jsonl", str(tmp_path / "c.md")).run(shared)
    assert shared["resumen"] == "2 carpetas · 3 registros → Effective N 3 (0 duplicados)"
    assert Path(shared["informe"]).is_file()

def test_juez_lote_informe_y_speedup(tmp_path, monkeypatch):
    """juez_lote: N preguntas en paralelo → N secciones, y la medición del
    speedup (suma de tiempos individuales vs reloj de pared). call_llm
    fiteado con latencia real: el paralelismo debe solapar las corridas."""
    import time

    import juez as juez_mod

    def llm_fake(prompt):
        time.sleep(0.15)  # latencia simulada
        if "Evalúa el borrador" in prompt:
            return "verdict: ok"
        return "Respuesta de prueba."

    monkeypatch.setattr(juez_mod, "call_llm", llm_fake)

    preguntas = tmp_path / "preguntas.txt"
    preguntas.write_text(
        "¿Qué hace effective_n?\n\n# comentario\n¿Qué hace juez?\n¿Qué hace el RAG?\n",
        encoding="utf-8",
    )
    salida = tmp_path / "lote.md"
    import juez_lote

    resumen = juez_lote.run_juez_lote(str(preguntas), str(salida))

    md = salida.read_text(encoding="utf-8")
    assert md.count("## P") == 3  # una sección por pregunta
    assert "¿Qué hace effective_n?" in md and "¿Qué hace el RAG?" in md
    assert "Speedup medido" in md
    m = juez_lote.leer_preguntas(str(preguntas))
    assert m == ["¿Qué hace effective_n?", "¿Qué hace juez?", "¿Qué hace el RAG?"]

    # el speedup real es > 1 porque las corridas se solapan
    assert "paralelo" in resumen
    # extraer el speedup del informe y verificar > 1
    import re as _re

    speedup = float(_re.search(r"\*\*([\d.]+)×\*\*", md).group(1))
    assert speedup > 1.0, md

def test_juez_rondas_configurables(monkeypatch):
    """--rondas / responder_con_juez(rondas=N) fija el tope real: con el juez
    insatisfecho, hace exactamente N borradores. Sin pasarlo, usa JUEZ_ROUNDS."""
    import juez

    llamadas = {"n": 0}

    def llm_fake(prompt):
        if "Evalúa el borrador" in prompt:
            return "verdict: retry\nproblems:\n  - sigue mal"
        llamadas["n"] += 1
        return f"borrador {llamadas['n']}"

    monkeypatch.setattr(juez, "call_llm", llm_fake)

    for n in (1, 3):
        llamadas["n"] = 0
        resp, adv = juez.responder_con_juez("¿q?", rondas=n)
        assert llamadas["n"] == n, f"rondas={n} hizo {llamadas['n']} borradores"
        assert adv and "tope de" in adv
        assert resp == f"borrador {n}"

    # default = JUEZ_ROUNDS (compatibilidad hacia atrás)
    llamadas["n"] = 0
    juez.responder_con_juez("¿q?")
    assert llamadas["n"] == juez.JUEZ_ROUNDS

def test_juez_lote_tool_del_chat(tmp_path, monkeypatch):
    """La tool juez_lote del chat corre el lote y devuelve el resumen."""
    import time

    import juez as juez_mod
    import modules.juez as mj

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(juez_mod, "call_llm",
                        lambda p: "verdict: ok" if "Evalúa el borrador" in p
                        else (time.sleep(0.05) or "ok"))
    preguntas = tmp_path / "p.txt"
    preguntas.write_text("uno\ndos\n", encoding="utf-8")
    salida = tmp_path / "s.md"
    r = mj.juez_lote(str(preguntas), str(salida))
    assert "Juez en lote" in r and Path(salida).is_file()
    assert "juez_lote" in {t["function"]["name"] for t in mj.TOOLS}

def test_supervisor_guarda_vetada_pura():
    """Ley L8 como guarda PURA: una herramienta que falló dos veces devuelve
    el TEXTO de veto (no ejecuta); con menos fallos, None (puede correr).
    Reemplaza al test del prompt de veto (el menú en prosa y el 'PROHIBIDO
    elegir' se jubilaron con el despacho viejo)."""
    from supervisor import MAX_FALLOS_POR_HERRAMIENTA, TEXTO_VETO, guarda_vetada

    assert guarda_vetada("search_files", {}) is None
    assert guarda_vetada("search_files", {"search_files": 1}) is None
    assert guarda_vetada("search_files", {"search_files": MAX_FALLOS_POR_HERRAMIENTA}) == TEXTO_VETO
    assert guarda_vetada("search_files", {"otra": 5}) is None  # el fallo es por herramienta

def test_supervisor_guarda_repetida_pura():
    """El caché y el veto de repetición, puros:
      - sin registro → corre (None);
      - idéntica a una exitosa → ("cached", resultado);
      - misma firma vista 2 veces → ("veto", TEXTO_VETO);
      - sin-args ya exitosa → ("veto", TEXTO_VETO).
    Reemplaza a test_supervisor_no_repite_sin_args (misma ley, forma pura)."""
    from supervisor import TEXTO_VETO, guarda_repetida

    firma = ("read_file", '{"path": "a.py"}')
    assert guarda_repetida(firma, {}, [], set()) is None
    previas = {firma: {"n": 1, "resultado": "contenido"}}
    assert guarda_repetida(firma, previas, ["read_file"], set()) == ("cached", "contenido")
    dos_veces = {firma: {"n": 2, "resultado": None}}
    assert guarda_repetida(firma, dos_veces, ["read_file"], set()) == ("veto", TEXTO_VETO)
    firma_sin = ("db_schema", "{}")
    assert guarda_repetida(firma_sin, {}, ["db_schema"], {"db_schema"}) == ("veto", TEXTO_VETO)

def test_supervisor_flujo_nuevo_guarda_antes_de_despachar(tmp_path, monkeypatch):
    """El flujo v2 con fakes: UnPaso elige tool; Ejecutar corre la guarda
    ANTES de run_tool_call. Una tool vetada NO se despacha (el fake contador
    no sube) y el mensaje role=tool lleva el texto de veto. Cierra Sintetizar
    con la sección Pasos."""
    from pocketflow import Flow

    import supervisor as sup

    ejecuciones = {"n": 0}

    def impl_fake(**kwargs):
        ejecuciones["n"] += 1
        return "no debería correr"

    monkeypatch.setitem(sup.REGISTRO, "read_file", impl_fake)

    class MsgFake:
        def __init__(self, tool_calls=None, content=None):
            self.tool_calls = tool_calls
            self.content = content

    class TCFake:
        def __init__(self, name, args):
            self.id, self.type = "c1", "function"
            self.function = type("F", (), {"name": name, "arguments": args})()

    # Una ronda de tool (read_file, ya vetada a 2 fallos) + cierre.
    pasos_llm = {"n": 0}

    def call_llm_agent_fake(messages, tools=None):
        pasos_llm["n"] += 1
        if pasos_llm["n"] == 1:
            return MsgFake(tool_calls=[TCFake("read_file", '{"path": "a.py"}')])
        return MsgFake(content="cerrado")

    monkeypatch.setattr(sup, "call_llm_agent", call_llm_agent_fake)
    monkeypatch.setattr(sup, "call_llm", lambda *a, **k: "cierre de prueba")

    un_paso = sup.UnPaso()
    ejecutar = sup.Ejecutar()
    sintetizar = sup.Sintetizar()
    un_paso - "tool" >> ejecutar
    un_paso - "sintetizar" >> sintetizar
    ejecutar - "default" >> un_paso
    sub = Flow(start=un_paso)

    shared = sup.semilla("tarea", str(tmp_path / "sup.md"))
    shared["fallos"] = {"read_file": sup.MAX_FALLOS_POR_HERRAMIENTA}  # ya vetada
    sub.run(shared)
    assert ejecuciones["n"] == 0  # la guarda cortó antes de run_tool_call
    mensajes_tool = [m for m in shared["messages"] if m.get("role") == "tool"]
    assert mensajes_tool and mensajes_tool[0]["content"] == sup.TEXTO_VETO
    texto = (tmp_path / "sup.md").read_text(encoding="utf-8")
    assert "## Pasos" in texto  # Sintetizar escribió la auditoría

def test_heartbeat_vencidas():
    import time

    from heartbeat import vencidas

    tareas = [
        {"tarea": "a", "salida": "a.md", "cada_horas": 24},
        {"tarea": "b", "salida": "b.md", "cada_horas": 1},
    ]
    estado = {"a.md": time.time()}  # 'a' acaba de correr: no vence
    assert [t["salida"] for t in vencidas(tareas, estado)] == ["b.md"]
    assert vencidas(tareas, {"a.md": time.time() - 25 * 3600}) == tareas  # todo vencido

def test_supervisor_reutiliza_la_llamada_identica(tmp_path, monkeypatch):
    """El caché en el flujo real: dos tool_calls idénticas en la MISMA ronda;
    la segunda sale del caché (guarda_repetida → 'cached') y run_tool_call
    sólo corre una vez. El resultado cacheado vuelve igual al historial."""
    from pocketflow import Flow

    import supervisor as sup

    ejecuciones = {"n": 0}

    def contar(**kwargs):
        ejecuciones["n"] += 1
        return "42 archivos"

    monkeypatch.setitem(sup.REGISTRO, "search_files", contar)

    class MsgFake:
        def __init__(self, tool_calls=None, content=None):
            self.tool_calls, self.content = tool_calls, content

    class TCFake:
        def __init__(self, name, args, i):
            self.id, self.type = f"c{i}", "function"
            self.function = type("F", (), {"name": name, "arguments": args})()

    pasos = {"n": 0}
    args_id = '{"glob": "*.py"}'

    def call_llm_agent_fake(messages, tools=None):
        pasos["n"] += 1
        if pasos["n"] == 1:  # dos llamadas IDÉNTICAS en la misma ronda
            return MsgFake(tool_calls=[TCFake("search_files", args_id, 1),
                                       TCFake("search_files", args_id, 2)])
        return MsgFake(content="cerrado")

    monkeypatch.setattr(sup, "call_llm_agent", call_llm_agent_fake)
    monkeypatch.setattr(sup, "call_llm", lambda *a, **k: "cierre de prueba")

    un_paso, ejecutar, sintetizar = sup.UnPaso(), sup.Ejecutar(), sup.Sintetizar()
    un_paso - "tool" >> ejecutar
    un_paso - "sintetizar" >> sintetizar
    ejecutar - "default" >> un_paso

    shared = sup.semilla("tarea", str(tmp_path / "sup.md"))
    Flow(start=un_paso).run(shared)
    assert ejecuciones["n"] == 1  # la idéntica no se despachó dos veces
    tools = [m for m in shared["messages"] if m.get("role") == "tool"]
    assert [m["content"] for m in tools] == ["42 archivos", "42 archivos"]

def test_juez_lote_aisla_fallas(tmp_path, monkeypatch):
    """Medido en vivo: el verdict inválido persistente de UNA pregunta mató
    el lote entero y perdió el trabajo de las demás. Ahora el fallo es un
    hecho del informe, no la muerte del batch."""
    import juez_lote

    class FlujoFake:
        def run(self, shared):
            if "ROMPE" in shared["question"]:
                raise AssertionError("verdict inválido")
            shared["draft"] = "respuesta verificada"
            shared["rounds"] = 1

    monkeypatch.setattr(juez_lote, "create_juez_flow", lambda: FlujoFake())
    preg = tmp_path / "p.txt"
    preg.write_text("pregunta buena\npregunta ROMPE ahora\n", encoding="utf-8")
    salida = tmp_path / "lote.md"
    resumen = juez_lote.run_juez_lote(preg, salida)
    texto = salida.read_text(encoding="utf-8")
    assert "respuesta verificada" in texto  # la buena sobrevive
    assert "❌ Falló" in texto and "verdict inválido" in texto  # la mala, documentada
    assert "1 fallidas" in resumen

def _judge_verdict(monkeypatch, verdict_yaml):
    """Corre Judge.exec con call_llm fakeado devolviendo YAML crudo.
    Devuelve el veredicto normalizado (o propaga el AssertionError)."""
    import juez

    monkeypatch.setattr(juez, "call_llm", lambda prompt: verdict_yaml)
    inputs = ("¿q?", "borrador sin citas", [], False)
    return juez.Judge().exec(inputs)

def test_verdict_fallback_semantico_sin_raise(monkeypatch):
    """Candado exp/21 fase B2: ambos intentos inválidos → fallback con
    verdict 'retry', el crudo citado en problems y problems es lista.
    Nunca raise por verdict."""
    import juez

    monkeypatch.setattr(juez, "call_llm", lambda prompt: "verdict: nope")
    v = juez.Judge().exec(("¿q?", "borrador", [], False))
    assert v["verdict"] == "retry"
    assert isinstance(v["problems"], list)
    assert len(v["problems"]) == 1
    assert "último crudo" in v["problems"][0]
    assert "nope" in v["problems"][0]

def test_verdict_yaml_roto_dispara_loop_sin_excepcion(monkeypatch):
    """Candado exp/21 fase B2: extraer_yaml reventando es UN caso más de
    invalidez — reparación o fallback, sin excepción que escape de exec."""
    import juez

    monkeypatch.setattr(juez, "call_llm", lambda prompt: "esto no es yaml: : :")
    v = juez.Judge().exec(("¿q?", "borrador", [], False))
    assert v["verdict"] == "retry"
    assert isinstance(v["problems"], list)

    # y si el reintento SÍ trae yaml válido, la reparación lo rescata
    respuestas = iter(["no es yaml : :", "verdict: ok\nproblems: []"])

    def fake(prompt):
        return next(respuestas)

    monkeypatch.setattr(juez, "call_llm", fake)
    v2 = juez.Judge().exec(("¿q?", "borrador", [], False))
    assert v2["verdict"] == "ok"

def test_verdict_problems_string_dispara_reparacion(monkeypatch):
    """Candado exp/21 fase B2: problems con forma inválida (string) también
    dispara la reparación (segunda condición del contrato)."""
    import juez

    respuestas = iter([
        "verdict: retry\nproblems: una sola cadena, no lista",
        "verdict: retry\nproblems:\n  - ahora sí lista",
    ])

    def fake(prompt):
        return next(respuestas)

    monkeypatch.setattr(juez, "call_llm", fake)
    v = juez.Judge().exec(("¿q?", "borrador", [], False))
    assert v["verdict"] == "retry"
    assert v["problems"] == ["ahora sí lista"]

def test_verdict_normaliza_mayus_y_espacios(monkeypatch):
    """Candado exp/21 (a): 'OK'/' ok ' → ok tras str/strip/lower."""
    assert _judge_verdict(monkeypatch, "verdict: OK")["verdict"] == "ok"
    assert _judge_verdict(monkeypatch, "verdict: '  ok  '")["verdict"] == "ok"
    assert _judge_verdict(monkeypatch, "verdict: Retry")["verdict"] == "retry"

def test_verdict_reparacion_por_feedback_sin_alias(monkeypatch):
    """Candado exp/21 fase B2: la reparación FUNCIONA para el sinónimo
    medido ('needs_changes') sin alias alguno. call_llm en SECUENCIA:
    primero el inválido, después el válido → verdict final 'retry' con los
    problems del segundo. El feedback cita el crudo inválido VERBATIM."""
    import juez

    respuestas = iter([
        "verdict: needs_changes\nproblems:\n  - cita floja",
        "verdict: retry\nproblems:\n  - corregí la cita",
    ])
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return next(respuestas)

    monkeypatch.setattr(juez, "call_llm", fake)
    v = juez.Judge().exec(("¿q?", "borrador", [], False))
    assert v["verdict"] == "retry"
    assert v["problems"] == ["corregí la cita"]
    # el reintento fue INFORMADO: cita la respuesta inválida y el contrato
    assert len(prompts) == 2
    assert "needs_changes" in prompts[1]
    assert "ok o retry" in prompts[1]

def test_juez_no_entrega_con_herramienta_alucinada(monkeypatch):
    """exp/42: el Draft alucinó `delete_file` (3/3 corridas). Con verdict ok
    el flujo lo entregaba porque el Judge nunca veía el action space. Ahora
    el inventario real lo aporta el código y una herramienta inventada fuerza
    el retry, sin tocar el contrato observable (los veredictos)."""
    import juez

    monkeypatch.setattr(juez, "call_llm", lambda *a, **k: "verdict: ok\n")
    # (a) borrador que menciona usar delete_file + verdict ok → retry
    v = juez.Judge().exec(
        ("¿q?", "podés usar la herramienta delete_file para borrarlo",
         [], False)
    )
    assert v["verdict"] == "retry"
    assert any("action space" in p for p in v["problems"])

    # (b) borrador honesto (no menciona herramientas inventadas) + ok → ok
    v2 = juez.Judge().exec(("¿q?", "borrador sin herramientas raras", [], False))
    assert v2["verdict"] == "ok"

def test_tools_alucinadas_funcion_pura():
    """exp/42: el contraste contra el action space es un hecho del código.
    Función pura: detecta la herramienta inventada en una línea con contexto
    de tool; NO marca nombres reales (read_file, sql) ni snake_case suelto
    sin contexto.

    exp/42 sesión 4: dos regresiones MEDIDAS con LLM real — (a) un segmento
    de ruta citado en línea con contexto de tool y (b) discutir una función
    interna del código no son claims de herramienta. La trampa NO se afloja:
    'usá la herramienta delete_file' sigue marcando delete_file."""
    from juez import _tools_alucinadas

    inv = {"read_file", "sql", "run_supervisor"}
    # delete_file NO está en el inventario y la línea habla de una tool
    assert _tools_alucinadas(
        "podés usar la herramienta delete_file para borrar", inv
    ) == ["delete_file"]
    # nombres reales: no se marcan
    assert _tools_alucinadas("usá read_file para leer", inv) == []
    # sql no tiene `_`: no es candidato (sesgo hacia no dar falsos positivos)
    assert _tools_alucinadas("usá sql para consultar", inv) == []
    # snake_case SIN contexto de tool: no se marca
    assert _tools_alucinadas("el valor mi_dato quedó raro", inv) == []

    # (a) SEGMENTO DE RUTA (medido en search-vacio): citar 'utils/fs_tools.py'
    # en una línea con contexto de tool NO marca el segmento `fs_tools`.
    assert _tools_alucinadas(
        "usá la herramienta documentada en utils/fs_tools.py para esto", inv
    ) == []
    assert _tools_alucinadas(
        "la herramienta está en ../utils/fs_tools.py y se usa así", inv
    ) == []

    # (b) FUNCIÓN INTERNA (medido en thinking-tools): hablar de la función
    # call_llm_agent (o de reasoning_content) NO marca nada. Nota: un token
    # como 'tool_calls' se auto-dispara como contexto por su substring 'tool';
    # el caso medido que depende del fix de 'función' es call_llm_agent.
    assert _tools_alucinadas("la función call_llm_agent hace X", inv) == []

    # LA TRAMPA NO SE AFLOJA: sigue marcando la tool inventada.
    assert _tools_alucinadas("usá la herramienta delete_file", inv) == [
        "delete_file"
    ]

def test_degradacion_terminal_con_draft(monkeypatch):
    """Candado exp/21 (b): si el flujo revienta con draft presente,
    responder_con_juez entrega (draft, advertencia) en vez de morir."""
    import juez

    class FlowQueRevientaConDraft:
        def run(self, shared):
            shared["draft"] = "borrador de emergencia"
            raise RuntimeError("verdict inválido: 'basura'")

    monkeypatch.setattr(juez, "create_juez_flow", lambda: FlowQueRevientaConDraft())
    draft, advertencia = juez.responder_con_juez("¿q?")
    assert draft == "borrador de emergencia"
    assert advertencia and "veredicto legible" in advertencia

def test_degradacion_terminal_sin_draft_relevanta(monkeypatch):
    """Candado exp/21 (b): sin draft (el Draft también reventó) se re-raise
    tal cual, no se inventa una respuesta."""
    import pytest as _pytest

    import juez

    class FlowQueRevientaSinDraft:
        def run(self, shared):
            raise RuntimeError("el Draft tampoco pudo")

    monkeypatch.setattr(juez, "create_juez_flow", lambda: FlowQueRevientaSinDraft())
    with _pytest.raises(RuntimeError, match="el Draft tampoco pudo"):
        juez.responder_con_juez("¿q?")

def test_informe_dos_corridas_en_el_mismo_proceso(tmp_path, monkeypatch):
    """exp/36 (barrida): el semáforo de módulo se ataba al primer event loop y
    la SEGUNDA corrida del proceso fallaba con RuntimeError (la tool quedaba
    inusable). Ahora cada corrida trae su semáforo."""
    import asyncio
    import json as _json

    import informe

    async def resumen_falso(*a, **k):
        return "resumen"

    monkeypatch.setattr(informe, "interpretar", resumen_falso)
    monkeypatch.setattr(informe, "call_llm", lambda *a, **k: "síntesis falsa")
    monkeypatch.setattr(informe, "MAPA_CONCURRENCIA", 1)   # fuerza contención

    for i in range(2):
        carpeta = tmp_path / f"d{i}"
        carpeta.mkdir()
        for j in range(3):
            (carpeta / f"a{j}.jsonl").write_text(
                _json.dumps({"answers": {"next": "x"}, "fields": {"task": "t"}}) + "\n",
                encoding="utf-8",
            )
        salida = tmp_path / f"out{i}.md"
        shared = {"folder": str(carpeta), "glob": "*.jsonl", "salida": str(salida)}
        asyncio.run(informe.create_informe_flow().run_async(shared))
        assert salida.is_file(), f"la corrida {i + 1} no escribió el informe"

def test_research_recorta_consultas_y_valida_tipos(monkeypatch):
    """exp/28 (C13 + C06a de la auditoría externa): el prompt pide 3 consultas
    y el código aceptaba 20 (las buscaba todas); un content no textual rompía
    en post, que PocketFlow NO reintenta. El tope y los tipos los aplica el
    código, no la obediencia del modelo."""
    import research

    monkeypatch.setattr(
        research, "call_llm", lambda *a, **k: 'queries: ["a", "b", "c", "d", "e"]\n'
    )
    assert research.Planner().exec(("tema", "")) == ["a", "b", "c"]

    monkeypatch.setattr(research, "call_llm", lambda *a, **k: "queries: una sola consulta\n")
    with pytest.raises(ValueError, match="queries inválidas"):
        research.Planner().exec(("tema", ""))

    monkeypatch.setattr(
        research, "call_llm", lambda *a, **k: "action: finalize\ncontent: 42\n"
    )
    with pytest.raises(ValueError, match="no textual"):
        research.Synthesizer().exec(("tema", ["material"], 0))

def test_juez_no_entrega_con_cita_rota(monkeypatch):
    """exp/29 (C07 de la auditoría externa): la verificación de citas se le
    CONTABA al LLM; con verdict ok el flujo entregaba un borrador citando una
    ruta inexistente. Ahora la cita rota es un hecho del código y fuerza el
    retry."""
    import juez

    monkeypatch.setattr(juez, "call_llm", lambda *a, **k: "verdict: ok\n")
    v = juez.Judge().exec(("¿q?", "según /ruta/falsa.md:99", ["[ROTA] /ruta/falsa.md:99 → ERROR: no existe"], False))
    assert v["verdict"] == "retry"
    assert any("no resuelven" in p for p in v["problems"])

    # sin citas rotas, el verdict ok pasa como siempre
    v2 = juez.Judge().exec(("¿q?", "borrador", ["/real.md:1 → contenido real:\nx"], False))
    assert v2["verdict"] == "ok"

def test_cita_rota_detecta_error_y_fuera_de_rango():
    """exp/29: los dos modos objetivos de cita inválida, como función pura."""
    from juez import _cita_rota

    assert _cita_rota("ERROR: no existe: /x", "3") is True
    assert _cita_rota("[/real.md — líneas 9–9 de 8]\n", "9") is True
    assert _cita_rota("[/real.md — líneas 3–4 de 8]\ncontenido", "3") is False

def test_refinamiento_recibe_el_borrador_anterior(monkeypatch):
    """exp/29: el Draft corregía a ciegas — ahora recibe su intento exacto."""
    import juez

    prompts = []

    def capturar(prompt, *a, **k):
        prompts.append(prompt)
        return "borrador nuevo"

    monkeypatch.setattr(juez, "call_llm", capturar)
    inputs = juez.Draft().prep(
        {"question": "¿q?", "draft": "BORRADOR_VIEJO", "feedback": "- cita dudosa"}
    )
    juez.Draft().exec(inputs)
    assert "BORRADOR_VIEJO" in prompts[0]
    assert "cita dudosa" in prompts[0]

def test_researcher_no_reintenta_el_lote_por_una_busqueda(monkeypatch):
    """exp/37 (P6): un fallo de búsqueda hacía que el retry del BatchNode
    re-ejecutara el lote entero y se perdieran las búsquedas ya pagadas. Ahora
    el fallo es un dato de ese ítem."""
    import research

    llamadas = {"n": 0}

    def busca(query, k=4):
        llamadas["n"] += 1
        raise RuntimeError("sin red")

    monkeypatch.setattr(research, "search_web", busca)
    salida = research.Researcher().exec("consulta 1")   # no debe levantar
    assert "ERROR de búsqueda: RuntimeError" in salida
    assert llamadas["n"] == 1


def test_votacion_mayoria_piso_absoluto():
    """S11: el doc decía "la mitad entera por arriba"; el default es piso
    ABSOLUTO 2, no proporcional al total."""
    from utils.votacion import mayoria

    assert mayoria(["sql", "sql", "b", "c", "d"]) == "sql"
    assert mayoria(["sql", "b", "c", "d", "e"], desempate="sql") == "sql"


def test_juez_draft_lee_simbolos_mas_alla_del_excerpt(tmp_path, monkeypatch):
    """A63: los archivos crecieron (fs_tools 514 líneas) y el excerpt fijo de
    200 dejó afuera símbolos que el bench pide; el contexto dirigido los
    agrega sin duplicar todo el archivo."""
    import juez

    grande = tmp_path / "grande.py"
    lineas = ["x = 0"] * 240 + ["TOKEN_CLAVE = 42", "resto = 1"] + ["y = 0"] * 20
    grande.write_text("\n".join(lineas), encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(juez, "_archivos_de", lambda q: [grande])

    _, contexto, _, _ = juez.Draft().prep({"question": "¿Qué valor tiene TOKEN_CLAVE?"})
    assert "TOKEN_CLAVE" in contexto and "TOKEN_CLAVE = 42" in contexto
    assert "contexto de TOKEN_CLAVE" in contexto


def test_juez_draft_pide_cita_exacta(monkeypatch):
    """A65: el bench exige la línea exacta del símbolo; el prompt del Draft
    ahora lo pide explícitamente (citaba el inicio del bloque)."""
    import juez

    visto = {}

    def fake_llm(prompt):
        visto["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(juez, "call_llm", fake_llm)
    juez.Draft().exec(("¿Qué hace sanitizar?", "contexto", None, None))
    assert "línea EXACTA" in visto["prompt"]
    assert "definido" in visto["prompt"]


def test_juez_ancla_citas_a_literal_y_simbolo(tmp_path, monkeypatch):
    """A65 flaky: si la cita apunta a la definición pero el dato está en un
    literal o en otra línea cercana, se re-ancla a la línea que lo contiene."""
    import juez

    archivo = tmp_path / "m.py"
    lineas = [
        "# comentario",
        "def search_files(query=None):",
        "    ...",
        "    return \"ERROR: indica qué buscar: query\"",
        "",
        "def sanitizar(texto):",
        "    return texto",
    ]
    archivo.write_text("\n".join(lineas), encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))

    draft = (f"Devuelve `ERROR: indica qué buscar` (en {archivo}:2).\n"
             f"**sanitizar** corta marcadores (en {archivo}:7).")
    nuevo = juez._anclar_citas(draft)
    assert f"{archivo}:4" in nuevo
    assert f"{archivo}:6" in nuevo
