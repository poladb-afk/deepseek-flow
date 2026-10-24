"""Tests de convergencia del supervisor (exp/96): la telemetría de rondas
secas (tanda de hechos contra tanda) y el caso de la tanda vacía."""
import supervisor as sup


def test_supervisor_telemetria_seca_por_ronda(tmp_path, monkeypatch):
    """exp/96, C2 (telemetría SIN corte): la ronda 1 no compara (no hay
    anterior); las siguentes comparan la TANDA de hechos de esta ronda
    contra la de la anterior. Tres rondas con la MISMA respuesta de la tool →
    dos secas. El comportamiento no cambia: corre las mismas rondas y cierra.

    Usa la métrica tanda-contra-tanda a propósito: comparar el acumulado
    inflaría el ratio con el prefijo idéntico y toda ronda tardía saldría
    seca (falso positivo que este test atrapa: aquí los hechos repiten)."""

    ejecuciones = {"n": 0}

    def siempre_igual(**kwargs):
        ejecuciones["n"] += 1
        return "42 archivos listados"

    monkeypatch.setitem(sup.REGISTRO, "search_files", siempre_igual)

    class MsgFake:
        def __init__(self, tool_calls=None, content=None):
            self.tool_calls, self.content = tool_calls, content

    class TCFake:
        def __init__(self, args, i):
            self.id, self.type = f"c{i}", "function"
            self.function = type("F", (), {"name": "search_files",
                                           "arguments": args})()

    # Args DISTINTOS por ronda: la misma firma dos veces dispararía el veto de
    # repetición (otra ley) y la ronda no produciría hechos.
    pasos = {"n": 0}

    def call_llm_agent_fake(messages, tools=None):
        pasos["n"] += 1
        if pasos["n"] <= 3:
            return MsgFake(tool_calls=[TCFake(f'{{"glob": "r{pasos["n"]}*.py"}}',
                                              pasos["n"])])
        return MsgFake(content="cerrado")

    monkeypatch.setattr(sup, "call_llm_agent", call_llm_agent_fake)
    monkeypatch.setattr(sup, "call_llm", lambda *a, **k: "cierre de prueba")

    un_paso, ejecutar, sintetizar = sup.UnPaso(), sup.Ejecutar(), sup.Sintetizar()
    un_paso - "tool" >> ejecutar
    un_paso - "sintetizar" >> sintetizar
    ejecutar - "default" >> un_paso

    shared = sup.semilla("tarea", str(tmp_path / "sup.md"))
    shared["salida"] = str(tmp_path / "sup.md")
    from pocketflow import Flow

    Flow(start=un_paso).run(shared)
    assert shared["rondas"] == 3  # la telemetría NO corta nada (sin corte)
    assert ejecuciones["n"] == 3
    assert shared["secadas"] == [True, True]  # ronda 1 no compara


def test_supervisor_telemetria_ronda_distinta_no_es_seca(tmp_path, monkeypatch):
    """El contraste de C2: si cada ronda trae material nuevo, ninguna seca."""

    salidas = iter(["3 funciones en a.py", "42 archivos markdown distintos"])

    monkeypatch.setitem(sup.REGISTRO, "read_file", lambda **k: next(salidas))

    class MsgFake:
        def __init__(self, tool_calls=None, content=None):
            self.tool_calls, self.content = tool_calls, content

    def tc(i):
        return type("TC", (), {"id": f"c{i}", "type": "function",
                               "function": type("F", (), {
                                   "name": "read_file",
                                   "arguments": f'{{"path": "f{i}.py"}}'})()})()

    pasos = {"n": 0}

    def call_llm_agent_fake(messages, tools=None):
        pasos["n"] += 1
        if pasos["n"] <= 2:
            return MsgFake(tool_calls=[tc(pasos["n"])])
        return MsgFake(content="cerrado")

    monkeypatch.setattr(sup, "call_llm_agent", call_llm_agent_fake)
    monkeypatch.setattr(sup, "call_llm", lambda *a, **k: "cierre de prueba")

    un_paso, ejecutar, sintetizar = sup.UnPaso(), sup.Ejecutar(), sup.Sintetizar()
    un_paso - "tool" >> ejecutar
    un_paso - "sintetizar" >> sintetizar
    ejecutar - "default" >> un_paso

    shared = sup.semilla("tarea", str(tmp_path / "sup.md"))
    from pocketflow import Flow

    Flow(start=un_paso).run(shared)
    assert shared["secadas"] == [False]


def test_supervisor_tanda_vacia_es_seca(tmp_path):
    """Una ronda sin hechos tiene tanda vacía: seco decide con eso (una
    tanda vacía contra otra vacía es seca; vacía contra material, no)."""
    from utils.convergencia import seco

    assert seco("", "") is True
    assert seco("", "1 read_file(path=a.py) -> algo") is False


