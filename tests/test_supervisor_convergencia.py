"""Tests de convergencia del supervisor (exp/96): la telemetría de rondas
secas (tanda de hechos contra tanda) y el caso de la tanda vacía."""
import supervisor as sup


class MsgFake:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls, self.content = tool_calls, content


def tc_fake(nombre, args, i=1):
    return type("TC", (), {"id": f"c{i}", "type": "function",
                           "function": type("F", (), {"name": nombre, "arguments": args})()})()


def correr_supervisor(sup, tmp_path, monkeypatch, guion, shared_extra=None):
    """El flujo REAL del supervisor (loop del kernel → Auditar → Sintetizar)
    con un LLM guionado. `guion(n, messages, tools)` devuelve el mensaje."""
    pasos = {"n": 0}

    def llm(messages, tools=None):
        pasos["n"] += 1
        return guion(pasos["n"], messages, tools)

    monkeypatch.setattr(sup, "call_llm", lambda *a, **k: "cierre de prueba")
    shared = sup.semilla("tarea", str(tmp_path / "sup.md"), llm=llm)
    for clave, valor in (shared_extra or {}).items():
        shared["ley"][clave] = valor
    sup.create_supervisor_flow().run(shared)
    return shared


def test_supervisor_telemetria_seca_por_ronda(tmp_path, monkeypatch):
    """exp/96, C2 (telemetría SIN corte): la ronda 1 no compara (no hay
    anterior); las siguientes comparan la TANDA de hechos de esta ronda
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

    # Args DISTINTOS por ronda: la misma firma dos veces dispararía el veto de
    # repetición (otra ley) y la ronda no produciría hechos.
    def guion(n, messages, tools):
        if n <= 3:
            return MsgFake(tool_calls=[tc_fake("search_files", f'{{"glob": "r{n}*.py"}}', n)])
        return MsgFake(content="cerrado")

    shared = correr_supervisor(sup, tmp_path, monkeypatch, guion)
    assert shared["rondas"] == 3  # la telemetría NO corta nada (sin corte)
    assert ejecuciones["n"] == 3
    assert shared["secadas"] == [True, True]  # ronda 1 no compara


def test_supervisor_telemetria_ronda_distinta_no_es_seca(tmp_path, monkeypatch):
    """El contraste de C2: si cada ronda trae material nuevo, ninguna seca."""
    salidas = iter(["3 funciones en a.py", "42 archivos markdown distintos"])
    monkeypatch.setitem(sup.REGISTRO, "read_file", lambda **k: next(salidas))

    def guion(n, messages, tools):
        if n <= 2:
            return MsgFake(tool_calls=[tc_fake("read_file", f'{{"path": "f{n}.py"}}', n)])
        return MsgFake(content="cerrado")

    shared = correr_supervisor(sup, tmp_path, monkeypatch, guion)
    assert shared["secadas"] == [False]


def test_supervisor_tanda_vacia_es_seca(tmp_path):
    """Una ronda sin hechos tiene tanda vacía: seco decide con eso (una
    tanda vacía contra otra vacía es seca; vacía contra material, no)."""
    from utils.convergencia import seco

    assert seco("", "") is True
    assert seco("", "1 read_file(path=a.py) -> algo") is False





# H2 PR 2 — el supervisor sobre el kernel ----------------------------------

def test_las_lecturas_del_supervisor_corren_en_paralelo_y_las_escrituras_no(monkeypatch):
    """El efecto lo decide el catálogo: las del CORE leen; el
    resto —run_command, write_file, tools de módulos— va en orden."""
    shared = sup.semilla("tarea", "salidas/x.md", llm=lambda m, t: None)
    efecto = {t.nombre: t.efecto for t in shared["tools"]}
    assert {efecto[n] for n in ("list_files", "read_file", "search_files")} == {"lectura"}
    assert {efecto[n] for n in ("run_command", "write_file", "edit_file")} == {"escritura"}
    assert "run_supervisor" not in efecto                      # L1: anti-recursión
