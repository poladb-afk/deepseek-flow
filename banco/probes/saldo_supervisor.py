"""X203 — cuánto del árbol chat → supervisor ve el saldo del chat (sin LLM).

**Pregunta.** S0 y P2 (c) dicen que una copia hereda el saldo de su padre y la
Ley 1 promete llamadas ≤ 2R + 1 para TODO el árbol. Desde X202 el saldo cobra
las llamadas al LLM que hace una tool, pero el supervisor arma su propio
`Ledger(MAX_PASOS)`: sus rondas no descuentan del chat y sus llamadas se cobran
a ese saldo propio. Esta sonda corre el chat REAL con un cliente falso: el
chat pide `n` supervisores en una ronda y cada supervisor pide leer hasta
agotar su saldo. Devuelve llamadas reales, las que contó el saldo del chat,
las rondas que el chat descontó y la cota 2R + 1.

Determinista, sin red. Uso:
    python3 banco/probes/saldo_supervisor.py [n ...]   (default: 1 3 8)
"""
import builtins
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

RAIZ = Path(__file__).resolve().parent.parent.parent


def _cliente(contador):
    """Con tools (el loop del supervisor): siempre pide leer otra cosa. Sin
    tools (cierre y síntesis): responde. Toda llamada pasa por `_contabilizar`."""
    def create(**kwargs):
        contador["n"] += 1
        n = contador["n"]
        if kwargs.get("tools"):
            llamada = NS(id=f"s{n}", type="function",
                         function=NS(name="list_files", arguments=json.dumps({"path": ".", "depth": 1 + n % 3})))
            return NS(choices=[NS(message=NS(content=None, tool_calls=[llamada]))], usage=None)
        return NS(choices=[NS(message=NS(content="síntesis", tool_calls=None))], usage=None)
    return NS(chat=NS(completions=NS(create=create)))


def medir(n, salidas):
    """Una pregunta del chat que lanza `n` supervisores en la misma ronda."""
    import flow
    import nodes
    import supervisor
    from utils import call_llm as cliente
    from utils.kernel import Ledger

    saldos, contador = [], {"n": 0}
    flow.Ledger = lambda rondas: saldos.append(Ledger(rondas)) or saldos[-1]
    cliente._client = lambda: _cliente(contador)
    supervisor.call_llm_agent, supervisor.call_llm = cliente.call_llm_agent, cliente.call_llm
    pedidos = [NS(id=f"c{i}", function=NS(name="run_supervisor", arguments=json.dumps(
        {"tarea": f"t{i}", "salida": str(Path(salidas) / f"sup_{n}_{i}.md")}))) for i in range(n)]
    chat = iter([NS(content=None, tool_calls=pedidos), NS(content="listo", tool_calls=None)])
    nodes.call_llm_agent = lambda mensajes, tools=None: next(chat)
    entradas = iter(["hacé t", "salir"])
    builtins.input = lambda *a, **k: next(entradas)
    with contextlib.redirect_stdout(io.StringIO()):
        flow.create_agent_flow().run({"messages": [{"role": "system", "content": "s"}]})
    techo = nodes.presupuesto({})
    return {"supervisores": n, "llamadas_reales": 2 + contador["n"],
            "contadas_por_el_chat": saldos[0].llamadas,
            "rondas_descontadas_al_chat": techo - saldos[0].rondas,
            "cota_2r_mas_1": 2 * techo + 1}


def main(argv=None):
    import tempfile

    sys.path.insert(0, str(RAIZ))
    os.chdir(RAIZ)
    salidas = tempfile.mkdtemp(prefix="saldo_supervisor_")
    for clave, valor in {"CHAT_STREAM": "0", "PREFETCH": "0", "SKILLS": "0", "CITAS_VERIFICAR": "0",
                         "TRACE": "0", "PREGUNTAS_LOG": "0", "AGENT_ALLOWED_DIRS": f"{RAIZ}:{salidas}"}.items():
        os.environ[clave] = valor
    for n in [int(a) for a in (argv if argv is not None else sys.argv[1:])] or [1, 3, 8]:
        print(json.dumps(medir(n, salidas), ensure_ascii=False))


if __name__ == "__main__":
    main()
