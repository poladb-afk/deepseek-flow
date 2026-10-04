"""Debate multi-agente con colas (patrón multi_agent del cookbook).

Dos agentes —Proponente y Crítico— corren como flujos async INDEPENDIENTES
que se auto-apuntan (agente - "continue" >> agente) y se hablan solo por
asyncio.Queue, como el juego Taboo del doc. Cada ronda: argumento del
proponente + réplica del crítico; al agotarse las rondas, un sentinel FIN
viaja por la cola para que ambos terminen limpio. Al final, un Juez dicta
en YAML (structured output reutilizado: extraer_yaml + assert + retry).

Las llamadas call_llm son síncronas dentro de exec_async: el debate es
ping-pong (solo uno piensa a la vez), así que bloquear el loop es correcto
y medible, no un bug.

Uso: python3 main.py debate "tema" [--rondas 2]
"""
import argparse
import asyncio

from pocketflow import AsyncFlow, AsyncNode, Flow, Node

from utils.call_llm import call_llm
from utils.estructura import extraer_yaml

FIN = "<<FIN>>"
RONDAS_DEFAULT = 2


class Proponente(AsyncNode):
    async def prep_async(self, shared):
        mensaje = await shared["q_critica"].get()
        if mensaje == FIN or shared.get("ronda", 0) >= shared["rondas"]:
            return None
        return shared["tema"], mensaje, shared.get("transcript", [])

    async def exec_async(self, inputs):
        if inputs is None:
            return None
        tema, mensaje, transcript = inputs
        historial = "\n".join(f"{q}: {t[:300]}" for q, t in transcript[-6:]) or "(arranque)"
        prompt = f"""Tema del debate: {tema}

Último mensaje del crítico:
{mensaje}

Historial reciente:
{historial}

Eres el PROPONENTE: defiende la postura a favor con argumentos concretos,
evidencia y refutación puntual de la crítica. Máximo 8 líneas, sin título."""
        return call_llm(prompt)

    async def post_async(self, shared, prep_res, exec_res):
        if exec_res is None:
            await shared["q_propon"].put(FIN)
            return "end"
        shared["ronda"] = shared.get("ronda", 0) + 1
        shared.setdefault("transcript", []).append(("proponente", exec_res))
        print(f"\n🟢 PROPONENTE (ronda {shared['ronda']}):\n{exec_res}\n")
        await shared["q_propon"].put(exec_res)
        return "continue"


class Critico(AsyncNode):
    async def prep_async(self, shared):
        argumento = await shared["q_propon"].get()
        if argumento == FIN:
            return None
        return shared["tema"], argumento, shared.get("transcript", [])

    async def exec_async(self, inputs):
        if inputs is None:
            return None
        tema, argumento, transcript = inputs
        historial = "\n".join(f"{q}: {t[:300]}" for q, t in transcript[-6:]) or "(arranque)"
        prompt = f"""Tema del debate: {tema}

Argumento del proponente a refutar:
{argumento}

Historial reciente:
{historial}

Eres el CRÍTICO: ataca los puntos débiles, señala supuestos no demostrados
y ofrece contra-evidencia o contraejemplos. Máximo 8 líneas, sin título."""
        return call_llm(prompt)

    async def post_async(self, shared, prep_res, exec_res):
        if exec_res is None:
            return "end"
        shared.setdefault("transcript", []).append(("critico", exec_res))
        print(f"🔴 CRÍTICO:\n{exec_res}\n")
        await shared["q_critica"].put(exec_res)
        return "continue"


class FinAgente(AsyncNode):
    async def post_async(self, shared, prep_res, exec_res):
        pass


class JuezDebate(Node):
    def prep(self, shared):
        return shared["tema"], shared.get("transcript", [])

    def exec(self, inputs):
        tema, transcript = inputs
        texto = "\n\n".join(f"[{q.upper()}]\n{t}" for q, t in transcript)
        prompt = f"""Tema: {tema}

Transcript completo del debate:
{texto}

Dictamina en español, SOLO yaml:
```yaml
ganador: proponente
sintesis: |
  Cinco líneas: el mejor argumento de cada lado,
  por qué ganó quien ganó, y qué quedaría por resolver.
```"""
        veredicto = extraer_yaml(call_llm(prompt))
        assert veredicto["ganador"] in ("proponente", "critico", "empate"), "ganador inválido"
        assert veredicto["sintesis"].strip(), "síntesis vacía"
        return veredicto

    def post(self, shared, prep_res, exec_res):
        shared["veredicto"] = exec_res


def debatir(tema, rondas=RONDAS_DEFAULT):
    shared = {
        "tema": tema,
        "rondas": rondas,
        "ronda": 0,
        "q_propon": asyncio.Queue(),
        "q_critica": asyncio.Queue(),
    }

    async def correr_debate():
        await shared["q_critica"].put("Apertura: presenta tu postura a favor del tema.")
        p, c, fin = Proponente(), Critico(), FinAgente()
        p - "continue" >> p
        p - "end" >> fin
        c - "continue" >> c
        c - "end" >> fin
        await asyncio.gather(
            AsyncFlow(start=p).run_async(shared),
            AsyncFlow(start=c).run_async(shared),
        )

    asyncio.run(correr_debate())

    juez = JuezDebate(max_retries=3, wait=5)
    Flow(start=juez).run(shared)
    return shared["veredicto"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="debate", description="Debate multi-agente (colas) con juez final"
    )
    parser.add_argument("tema", help="tema a debatir")
    parser.add_argument("--rondas", type=int, default=RONDAS_DEFAULT)
    args = parser.parse_args(argv)

    veredicto = debatir(args.tema, args.rondas)
    print(f"\n⚖️  VEREDICTO: gana {veredicto['ganador']}\n\n{veredicto['sintesis']}")


if __name__ == "__main__":
    main()
