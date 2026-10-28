"""El kernel fractal (H2): agente = Flow = Node = Tool.

Una sola primitiva para todo loop agéntico del harness. `loop()` es el grafo
(Paso → Actuar → Paso, con el cierre por presupuesto como ARISTA, no como
guardas); `agente()` lo envuelve como una `Tool` que cualquier otro loop puede
llamar, con contexto fresco y profundidad acotada. El presupuesto (`Ledger`)
es UNO para todo el árbol: un sub-agente gasta del mismo saldo que su padre.

Leyes, por construcción (evidencia en docs/roadmap.md, sección H2/H3):
- presupuesto en código, único por árbol (L8);
- en paralelo solo lo que lee (`efecto="lectura"`); lo que escribe, en un
  solo hilo y por `run_tool_call` (hooks, denylist y HITL de siempre);
- profundidad máxima 1 por defecto (un agente puede llamar agentes; esos no);
- la respuesta final es siempre del agente que se llamó (agents as tools).

Sync a propósito: el harness entero lo es (call_llm_agent, run_tool_call,
input()). Las lecturas en paralelo usan hilos: son I/O."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pocketflow import Flow, Node

from utils import fs_tools
from utils.historial import as_dict, historiar
from utils.proveedor import normalizar

PARALELO_MAX = 8


@dataclass
class Ledger:
    """Rondas de tools que le quedan a TODO el árbol de agentes."""

    rondas: int

    def tomar(self):
        if self.rondas <= 0:
            return False
        self.rondas -= 1
        return True


@dataclass
class Tool:
    """Una capacidad: esquema para el modelo + cómo correrla + qué efecto tiene.
    `correr(args, ctx) -> str`; el texto es lo que ve el modelo."""

    nombre: str
    esquema: dict
    correr: object
    efecto: str = "lectura"  # lectura | escritura (lo no declarado, escritura)
    agente: bool = False     # es un sub-agente: necesita saldo para correr su propio loop


@dataclass
class Ctx:
    """Lo que el árbol comparte: el LLM, el saldo y la traza."""

    llm: object
    ledger: Ledger
    profundidad: int = 0
    max_profundidad: int = 1
    traza: list = field(default_factory=list)

    def hijo(self):
        return Ctx(self.llm, self.ledger, self.profundidad + 1, self.max_profundidad, self.traza)


def desde_fs(nombre, efecto="lectura"):
    """Una tool del CORE (`fs_tools`) como Tool: pasa por `run_tool_call`, el
    único camino con hooks pre/post."""
    esquema = next(t for t in fs_tools.TOOLS if t["function"]["name"] == nombre)

    def correr(llamada, ctx):
        return fs_tools.run_tool_call(llamada)["content"]

    return Tool(nombre, esquema, correr, efecto)


class _DelLoop(Node):
    """Un nodo del loop: el LLM, el saldo y las tools viven EN el nodo (se
    fijan al armar el grafo), no en el shared — el shared queda solo con datos
    y se puede checkpointear como JSON (X94)."""

    def __init__(self, ctx, tools, **kwargs):
        super().__init__(**kwargs)
        self.ctx, self.tools = ctx, tools


class Paso(_DelLoop):
    """Una llamada al modelo. Sin saldo, la llamada va SIN tools (cierre). Un
    sub-agente solo se ofrece si queda saldo para él Y para su loop (≥ 2): con
    1, arrancaría sin poder leer nada."""

    def prep(self, s):
        saldo = self.ctx.ledger.rondas
        tools = [t.esquema for t in self.tools if saldo >= (2 if t.agente else 1)] or None
        return s["messages"], tools

    def exec(self, entrada):
        mensajes, tools = entrada
        msg, _ = normalizar(self.ctx.llm(mensajes, tools), tools)
        return msg

    def post(self, s, entrada, msg):
        s["messages"].append(historiar(msg))
        if not msg.tool_calls:
            return "respuesta"
        return "actuar" if self.ctx.ledger.tomar() else "cerrar"


class Actuar(_DelLoop):
    """Corre las tool calls del último mensaje. Si TODAS son de lectura van
    en paralelo; si alguna escribe, todas van en orden (un solo hilo)."""

    def prep(self, s):
        return [as_dict(tc) for tc in s["messages"][-1]["tool_calls"]]

    def exec(self, llamadas):
        por_nombre = {t.nombre: t for t in self.tools}

        def una(llamada):
            tool = por_nombre.get(llamada["function"]["name"])
            if tool is None:
                return f"ERROR: herramienta desconocida: {llamada['function']['name']}"
            return str(tool.correr(llamada, self.ctx))

        lectura = all(getattr(por_nombre.get(c["function"]["name"]), "efecto", "") == "lectura"
                      for c in llamadas)
        if lectura and len(llamadas) > 1:
            with ThreadPoolExecutor(min(PARALELO_MAX, len(llamadas))) as hilos:
                return list(hilos.map(una, llamadas))
        return [una(c) for c in llamadas]

    def post(self, s, llamadas, contenidos):
        for llamada, contenido in zip(llamadas, contenidos, strict=True):
            self.ctx.traza.append((self.ctx.profundidad, llamada["function"]["name"]))
            s["messages"].append({"role": "tool", "tool_call_id": llamada["id"], "content": contenido})
        return "paso"


class Fin(Node):
    """La respuesta quedó en el historial: el loop termina acá."""


NO_EJECUTADA = "(no ejecutada: presupuesto de herramientas agotado)"


class Cerrar(Node):
    """Saldo agotado con tool calls pendientes: no se ejecutan; se responden
    como no ejecutadas (el historial queda válido) y el modelo cierra sin tools."""

    def post(self, s, *_):
        for tc in s["messages"][-1]["tool_calls"]:
            s["messages"].append({"role": "tool", "tool_call_id": tc["id"], "content": NO_EJECUTADA})
        return "paso"


def loop(ctx, tools, max_retries=3, wait=5):
    """El grafo del agente. Es un Flow, así que también es un Node: otro flujo
    lo encadena como un paso más (el supervisor: loop >> Auditar >> Sintetizar).
    `ctx` y `tools` quedan en los nodos; del shared lee y escribe `messages`."""
    paso, actuar, cerrar = Paso(ctx, tools, max_retries=max_retries, wait=wait), Actuar(ctx, tools), Cerrar()
    paso - "actuar" >> actuar
    paso - "cerrar" >> cerrar
    paso - "respuesta" >> Fin()
    actuar - "paso" >> paso
    cerrar - "paso" >> paso
    return Flow(start=paso)


def semilla(system, pedido):
    """El shared de un agente: contexto FRESCO (system + pedido, nada del
    llamador). Solo datos: es JSON y viaja en un checkpoint."""
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": pedido}]}


def correr(system, pedido, tools, ctx, max_retries=3, wait=5):
    """Un agente de punta a punta. Devuelve (respuesta, messages)."""
    s = semilla(system, pedido)
    loop(ctx, tools, max_retries, wait).run(s)
    return s["messages"][-1].get("content") or "", s["messages"]


def agente(nombre, descripcion, system, tools, parametro="pedido"):
    """El fractal: un agente ES una Tool. El que lo llama le pasa el pedido;
    el agente corre su loop con contexto fresco y el MISMO ledger, y devuelve
    su respuesta como texto. Más allá de `max_profundidad`, se niega.

    `system` es el texto o una función `pedido -> texto` (un sub-agente que
    arma el suyo con el pedido). Argumentos ilegibles vuelven como ERROR al
    modelo, como cualquier tool: no cortan el loop del padre."""
    import json

    if not system:
        raise ValueError(f"agente {nombre!r} sin system: el sub-agente correría sin instrucciones")
    armar = system if callable(system) else (lambda _pedido: system)

    esquema = {"type": "function", "function": {
        "name": nombre, "description": descripcion,
        "parameters": {"type": "object", "required": [parametro], "properties": {
            parametro: {"type": "string", "description": "Qué tiene que resolver, autocontenido"}}}}}

    def correr_agente(llamada, ctx):
        if ctx.profundidad >= ctx.max_profundidad:
            return f"ERROR: {nombre} no puede delegar más (profundidad máxima {ctx.max_profundidad})"
        try:
            args = json.loads(llamada["function"].get("arguments") or "{}")
        except (ValueError, TypeError):
            return f"ERROR: argumentos de {nombre} ilegibles (se espera JSON con `{parametro}`)"
        pedido = str(args.get(parametro, "") if isinstance(args, dict) else "").strip()
        if not pedido:
            return f"ERROR: {nombre} necesita `{parametro}`"
        respuesta, _ = correr(armar(pedido), pedido, tools, ctx.hijo())
        return respuesta

    lectura = all(t.efecto == "lectura" for t in tools)
    return Tool(nombre, esquema, correr_agente, "lectura" if lectura else "escritura", agente=True)
