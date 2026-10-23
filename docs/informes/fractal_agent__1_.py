"""Agente fractal mínimo: PocketFlow (async/paralelo) + DBOS (ejecución durable), con 12-factor agents.

- El LLM solo planea (salida estructurada); un compilador determinista arma el flujo.  F4, F8
- `spawn` lanza el mismo agente por subtarea, como workflows hijos en paralelo.         F10
- Cada llamada al LLM es un paso durable: si el proceso muere, se retoma sin repetirla. F5, F6
- El catálogo es un fold sobre los resultados de tareas anteriores.                    F12
"""
import asyncio, hashlib, hmac, json, os, re, sys, time, uuid, urllib.request
from dataclasses import dataclass, field, replace
from typing import Callable
from dbos import DBOS, SetWorkflowID
from pocketflow import AsyncFlow, AsyncNode, AsyncParallelBatchNode, Node

DBOS(config={"name": "fractal-agent", "log_level": "ERROR",
             "system_database_url": os.getenv("DBOS_DATABASE_URL", "sqlite:///fractal.sqlite")})


class PlanError(Exception): pass
class BudgetExceeded(Exception): pass


# ── F2 · Prompts propios: system fijo por rol + los campos que ese rol ve ──
ROLES = {
    "planner": ("""Sos el planificador de un agente fractal. Armá un plan con piezas del catálogo.
Preferí, en orden: usar una pieza, combinar varias, o adaptar una plantilla creando una pieza nueva.
Al inicio solo existe 'task'; cada paso necesita lo que dan los anteriores; el plan debe dar 'draft'.
Si falta información que solo tiene un humano, usá 'ask_human'.
CATÁLOGO:
{catalog}
Respondé solo JSON: {{"mode": "use|compose|adapt", "new": {{"name", "base", "when", "config"}} | null,
"steps": [{{"piece": str, "config": {{}}}}]}}""",
                ["parent", "guidance", "task", "status", "errors"]),
    "splitter": ('Dividí la tarea en 2 a 5 subtareas independientes. Respondé JSON: {{"subtasks": [str]}}',
                 ["guidance", "task"]),
    "worker":   ("Resolvé la tarea. {instructions}", ["parent", "guidance", "task", "feedback", "variant"]),
    "judge":    ('Evaluá el borrador con estos criterios: {criteria}. Respondé JSON: {{"done": bool, "feedback": str}}',
                 ["task", "draft"]),
    "picker":   ('Elegí el mejor borrador para la tarea. Respondé JSON: {{"best": int}}', ["task", "drafts"]),
    "merger":   ("Integrá las partes en un texto coherente.", ["guidance", "task", "subresults"]),
    "refiner":  ("Mejorá el borrador solo si hay algo material; si no, devolvelo igual.", ["task", "draft"]),
    "verifier": ('¿El borrador cumple la tarea? Respondé JSON: {{"ok": bool, "feedback": str}}',
                 ["parent", "guidance", "task", "draft"]),
}

# ── F3 · Contexto propio: solo los campos con valor, en bloques etiquetados ──
def render(view, fields):
    text = lambda v: "\n".join(f"- {x}" for x in v) if isinstance(v, list) else str(v)
    return "\n".join(f"<{k}>\n{text(view[k])}\n</{k}>" for k in fields if view.get(k))

class Ctx(dict):
    def __missing__(self, key): return ""

def as_json(text):
    return json.loads(re.search(r"[\[{].*[\]}]", text, re.S).group())

def log(s, msg):
    print("    " * s["budget"].depth + msg, flush=True)


# ── Pasos durables: DBOS guarda su resultado y no los repite al retomar ──
@DBOS.step(retries_allowed=True, max_attempts=3, interval_seconds=1, backoff_rate=2)
async def llm(role, system, user, json_mode):
    """Devuelve (texto, tokens)."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        from mock_llm import mock
        reply = await mock(role, user)
        return reply, (len(system) + len(user) + len(reply)) // 4
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    r = await client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object" if json_mode else "text"})
    return r.choices[0].message.content, r.usage.total_tokens

@DBOS.step(retries_allowed=True, max_attempts=5, interval_seconds=1, backoff_rate=2)
async def notify(url, body):
    """Webhook firmado con HMAC si hay AGENT_TOKEN. La url vive en el input del workflow: sobrevive reinicios."""
    data = json.dumps(body, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if key := os.getenv("AGENT_TOKEN"):
        headers["X-Signature"] = hmac.new(key.encode(), data, hashlib.sha256).hexdigest()
    await asyncio.to_thread(urllib.request.urlopen, urllib.request.Request(url, data, headers), timeout=5)

@DBOS.step()
async def load_outcomes():
    roots = await DBOS.list_workflows_async(name="agent", status="SUCCESS", has_parent=False, load_input=False)
    return [o for w in roots for o in w.output["outcomes"]]

async def tell(s, status, **body):
    if url := s["meta"].get("callback"):
        try:
            await notify(url, {"id": s["meta"]["root"], "status": status, **body})
        except Exception as e:  # un webhook caído no frena al agente
            log(s, f"aviso falló: {e}")


# ── Kernel: presupuesto y profundidad (fuera del alcance del agente) ──
class Budget:
    def __init__(self, tokens, depth=0, max_depth=2):
        self.left, self.depth, self.max_depth = tokens, depth, max_depth

    def spend(self, tokens):
        if tokens > self.left:
            raise BudgetExceeded(f"faltan {tokens - self.left} tokens")
        self.left -= tokens

    def reserve(self, share):
        if self.depth >= self.max_depth:
            raise PlanError("profundidad máxima")
        tokens = int(self.left * share)
        self.spend(tokens)
        return tokens


# ── F1 · F4 · La única pieza que habla con el LLM ────────────────────
class Ask(AsyncNode):
    def __init__(self, role, out, parse=str, default=None, **vars):
        super().__init__(max_retries=2)
        self.role, self.out, self.parse, self.default, self.vars = role, out, parse, default, vars

    def view(self, s):
        return {**s, **self.vars}

    def prompt(self, view):
        system, fields = ROLES[self.role]
        return system.format_map(Ctx(view)), render(view, fields)

    async def call(self, s, view):
        reply, tokens = await llm(self.role, *self.prompt(view), self.parse is not str)
        s["budget"].spend(tokens)
        return self.parse(reply)

    async def prep_async(self, s):
        return s, self.view(s)

    async def exec_async(self, inp):
        return await self.call(*inp)

    async def exec_fallback_async(self, inp, exc):
        if self.default is None or isinstance(exc, BudgetExceeded):
            raise exc
        inp[0].setdefault("errors", []).append(f"{self.role} respondió mal: {exc}"[:200])  # F9
        return self.default

    async def post_async(self, s, _, value):
        s[self.out] = value


# ── F7 · Contactar a un humano es una herramienta más ────────────────
class AskHuman(AsyncNode):
    def __init__(self, question=None):
        super().__init__()
        self.question = question

    async def prep_async(self, s): return s

    async def exec_async(self, s):
        question = self.question or f"No logro resolver '{s['task']}'. Errores: {'; '.join(s['errors'][-3:])}. ¿Cómo sigo?"
        log(s, f"? {question}")
        await DBOS.set_event_async("pending", question)
        await tell(s, "paused", pending=question)
        answer = await DBOS.recv_async("answer", timeout_seconds=30 * 24 * 3600)  # durable: puede esperar días
        await DBOS.set_event_async("pending", None)
        return answer or "Seguí con tu mejor criterio."

    async def post_async(self, s, _, answer):
        log(s, f"↳ humano: {answer}")
        s["guidance"], s["errors"] = answer, []


# ── Loops: un solo constructor, distintas condiciones de parada ──────
class Check(Node):
    def __init__(self, name, stop, max_iters):
        super().__init__()
        self.name, self.stop, self.max_iters, self.mem = name, stop, max_iters, {"i": 0}  # mem sobrevive a las copias de PocketFlow

    def post(self, s, *_):
        self.mem["i"] += 1
        done = self.stop(s, self.mem) or self.mem["i"] >= self.max_iters
        log(s, f"⟳ {self.name} vuelta {self.mem['i']}: " + ("listo" if done else f"sigue: {s.get('feedback', '')}"))
        return "done" if done else "again"

def loop(name, body, stop, max_iters, judge=None):
    check = Check(name, stop, min(int(max_iters), 6))
    body >> (judge or check)
    if judge:
        judge >> check
    check - "again" >> body
    check - "done" >> Node()
    return AsyncFlow(start=body)

def judged(s, mem):
    done = s["verdict"]["done"]
    s["feedback"] = "" if done else s["verdict"]["feedback"]
    return done

def dried(s, mem):  # se mide el texto, no lo que el agente dice
    same = s["draft"] == mem.get("prev")
    mem["prev"] = s["draft"]
    return same


# ── Paralelo: k borradores a la vez y un juez elige (2 rondas en vez de k) ──
class BestOf(AsyncNode):
    def __init__(self, inner, k):
        super().__init__()
        self.inner, self.k = inner, min(int(k), 5)
        self.picker = Ask("picker", "", lambda r: int(as_json(r)["best"]))

    async def prep_async(self, s): return s

    async def exec_async(self, s):
        views = [{**self.inner.view(s), "variant": f"{i + 1}/{self.k}"} for i in range(self.k)]
        drafts = await asyncio.gather(*(self.inner.call(s, v) for v in views))  # arrancan en orden: replay determinista
        best = await self.picker.call(s, {**s, "drafts": [f"[{i}] {d}" for i, d in enumerate(drafts)]})
        log(s, f"⇉ best_of: {self.k} borradores en paralelo, gana el {best}")
        return drafts[best] if 0 <= best < len(drafts) else drafts[0]

    async def post_async(self, s, _, draft):
        s["draft"] = draft


# ── F10 · Fractal y en paralelo: cada subtarea es un workflow hijo ───
class Spawn(AsyncParallelBatchNode):
    async def prep_async(self, s):
        subtasks = s["subtasks"][:5]
        each = s["budget"].reserve(0.8) // len(subtasks)
        known = s["known"] + s["toolkit"].log
        handles = []
        for task in subtasks:  # se lanzan en orden: mismos ids al retomar
            log(s, f"⇣ subagente '{task}' ({each} tokens)")
            handles.append(await DBOS.start_workflow_async(
                agent, task, tokens=each, depth=s["budget"].depth + 1, parent=s["task"],
                guidance=s.get("guidance", ""), known=known, meta=s["meta"]))
        return handles

    async def exec_async(self, handle):
        return await handle.get_result()

    async def post_async(self, s, _, children):
        for child in children:
            s["budget"].left += child["left"]
            for o in child["outcomes"]:
                if change := s["toolkit"].apply(o):
                    log(s, f"★ '{o['name']}' {change}")
        s["subresults"] = "\n\n".join(c["result"] for c in children)


# ── Toolkit: piezas con contrato ─────────────────────────────────────
@dataclass
class Piece:
    name: str
    kind: str                    # prompt | skill | subagent | loop | parallel | workflow | human
    when: str
    needs: tuple
    gives: tuple
    build: Callable              # (config, toolkit) -> Node
    config: dict = field(default_factory=dict)   # sus claves son lo único adaptable
    base: str = ""               # plantilla de la que deriva (vacío si es core)
    status: str = "core"         # core | incubating | promoted | rejected
    wins: int = 0
    trials: int = 0

class Toolkit(dict):
    def __init__(self):
        super().__init__()
        self.log = []            # resultados de esta corrida

    def add(self, *pieces):
        for p in pieces:
            self[p.name] = p

    def build(self, name, config=None):
        piece, config = self[name], config or {}
        self._check(piece, config)
        return piece.build({**piece.config, **config}, self)

    def adapt(self, name, base, when, config):
        """Pieza nueva = plantilla + config permitida. Nunca código nuevo."""
        if name in self:
            if self[name].status == "core":
                raise PlanError(f"'{name}' es core")
            return
        if not self[base].config:
            raise PlanError(f"'{base}' no es una plantilla")
        self._check(self[base], config)
        self[name] = replace(self[base], name=name, when=when, config={**self[base].config, **config},
                             base=base, status="incubating", wins=0, trials=0)

    def record(self, name, ok):
        p = self[name]
        p.trials, p.wins = p.trials + 1, p.wins + ok
        self.log.append({"name": name, "ok": ok} | ({"base": p.base, "when": p.when, "config": p.config} if p.base else {}))
        if p.status == "incubating" and p.trials >= 3:
            p.status = "promoted" if p.wins / p.trials >= 2 / 3 else "rejected"
            return p.status

    def apply(self, outcome):
        if outcome["name"] not in self:
            self.adapt(outcome["name"], outcome["base"], outcome["when"], outcome["config"])
        return self.record(outcome["name"], outcome["ok"])

    def restore(self, outcomes):
        """F12 · el catálogo es un fold sobre los resultados de tareas anteriores."""
        for o in outcomes:
            if o["name"] in self or o.get("base") in self:  # ignora piezas de versiones viejas
                self.apply(o)
        self.log = []
        return self

    def catalog(self, budget):
        return "\n".join(
            f"- {p.name} [{p.kind}, {p.status}] needs={list(p.needs)} gives={list(p.gives)} config={p.config}: {p.when}"
            for p in self.values()
            if p.status != "rejected" and not (p.kind == "subagent" and budget.depth >= budget.max_depth))

    @staticmethod
    def _check(piece, config):
        if extra := set(config) - set(piece.config):
            raise PlanError(f"'{piece.name}' no acepta {sorted(extra)}")


def inner_piece(c, tk, wrapper):
    inner = tk[c["inner"]]
    if inner.needs != ("task",) or "draft" not in inner.gives:
        raise PlanError(f"{wrapper} no puede envolver '{inner.name}'")
    return tk.build(inner.name)

def judge_loop(c, tk):
    judge = Ask("judge", "verdict", as_json, criteria=c["criteria"])
    return loop("judge_loop", inner_piece(c, tk, "judge_loop"), judged, c["max_iters"], judge)

def best_of(c, tk):
    inner = inner_piece(c, tk, "best_of")
    if not isinstance(inner, Ask):
        raise PlanError("best_of solo envuelve prompts")
    return BestOf(inner, c["k"])

def default_toolkit():
    tk = Toolkit()
    tk.add(
        Piece("answer", "prompt", "tarea simple", ("task",), ("draft",),
              lambda c, tk: Ask("worker", "draft", instructions=c["instructions"]),
              {"instructions": "Respondé claro y correcto."}),
        Piece("ask_human", "human", "falta información que solo tiene un humano", ("task",), ("guidance",),
              lambda c, tk: AskHuman(c["question"]),
              {"question": "¿Qué debería saber antes de empezar?"}),
        Piece("decompose", "workflow", "tarea con partes independientes", ("task",), ("subtasks",),
              lambda c, tk: Ask("splitter", "subtasks", lambda r: as_json(r)["subtasks"])),
        Piece("spawn", "subagent", "resolver cada subtarea con un agente hijo, en paralelo", ("subtasks",), ("subresults",),
              lambda c, tk: Spawn()),
        Piece("synthesize", "skill", "unir resultados de subagentes", ("task", "subresults"), ("draft",),
              lambda c, tk: Ask("merger", "draft")),
        Piece("judge_loop", "loop", "reintentar una pieza con feedback de un juez (secuencial)", ("task",), ("draft",),
              judge_loop, {"inner": "answer", "max_iters": 3, "criteria": "correcto, completo, concreto"}),
        Piece("best_of", "parallel", "k borradores de un prompt en paralelo y un juez elige (más rápido)", ("task",), ("draft",),
              best_of, {"inner": "answer", "k": 3}),
        Piece("until_dry", "loop", "pulir hasta que el texto deje de cambiar", ("draft",), ("draft",),
              lambda c, tk: loop("until_dry", Ask("refiner", "draft"), dried, c["max_iters"]),
              {"max_iters": 4}),
    )
    return tk


# ── F8 · Flujo de control propio: compilador determinista ────────────
def compile_plan(plan, tk, budget):
    if plan.get("new"):
        tk.adapt(**plan["new"])
    have, nodes, used = {"task"}, [], []
    for step in plan["steps"]:
        if step["piece"] not in tk:
            raise PlanError(f"no existe la pieza '{step['piece']}'")
        piece, config = tk[step["piece"]], step.get("config", {})
        if piece.status == "rejected":
            raise PlanError(f"'{piece.name}' fue rechazada")
        if piece.kind == "subagent" and budget.depth >= budget.max_depth:
            raise PlanError("profundidad máxima: sin subagentes")
        if missing := set(piece.needs) - have:
            raise PlanError(f"'{piece.name}' necesita {sorted(missing)}")
        have |= set(piece.gives)
        nodes.append(tk.build(piece.name, config))
        used += [piece.name] + ([config["inner"]] if "inner" in config else [])
    if "draft" not in have:
        raise PlanError("el plan no produce 'draft'")
    for a, b in zip(nodes, nodes[1:]):
        a >> b
    return AsyncFlow(start=nodes[0]), used


# ── El nodo fractal: planear → compilar y correr → verificar ─────────
def retry(s, error, limit=3):
    """F9: el error compacto vuelve al planificador; tras 3 seguidos, se escala a un humano."""
    s.setdefault("errors", []).append(error[:200])
    log(s, f"✗ {error}")
    return "plan" if len(s["errors"]) < limit else "human"

class Plan(Ask):
    def view(self, s):
        b = s["budget"]
        return {**s, "catalog": s["toolkit"].catalog(b),
                "status": f"profundidad {b.depth}/{b.max_depth}, quedan ~{b.left} tokens"}

class Run(AsyncNode):
    async def prep_async(self, s): return s

    async def exec_async(self, s):
        plan = s["plan"]
        try:
            log(s, f"plan [{plan.get('mode')}]: " + " → ".join(
                st["piece"] + (f" {st['config']}" if st.get("config") else "") for st in plan["steps"]))
            if plan.get("new"):
                log(s, f"✚ adapta '{plan['new']['base']}' → '{plan['new']['name']}'")
            flow, s["used"] = compile_plan(plan, s["toolkit"], s["budget"])
        except (PlanError, KeyError, TypeError, AttributeError) as e:
            return str(e)
        await flow.run_async(s)

    async def post_async(self, s, _, error):
        return retry(s, f"El plan no compiló: {error}") if error else "verify"

class Decide(Node):
    def post(self, s, *_):
        ok = s["review"]["ok"]
        for name in dict.fromkeys(s["used"]):
            if change := s["toolkit"].record(name, ok):
                log(s, f"★ '{name}' {change}")
        if not ok:
            return retry(s, f"El verificador rechazó: {s['review']['feedback']}")
        s["result"] = s["draft"]
        log(s, f"✔ listo, quedan {s['budget'].left} tokens")
        return "done"

def make_agent():
    plan = Plan("planner", "plan", as_json, {"mode": "use", "steps": [{"piece": "answer"}]})
    verify = Ask("verifier", "review", as_json, {"ok": False, "feedback": "respuesta inválida"})
    run, decide, human = Run(), Decide(), AskHuman()

    plan >> run
    run - "verify" >> verify >> decide
    run - "plan" >> plan
    decide - "plan" >> plan
    run - "human" >> human
    decide - "human" >> human
    human >> plan
    decide - "done" >> Node()
    return AsyncFlow(start=plan)


# ── F5 · F6 · El agente es un workflow durable ───────────────────────
@DBOS.workflow(name="agent", max_recovery_attempts=20)  # cada proceso que lo retoma cuenta un intento
async def agent(task, tokens=20_000, depth=0, parent="", guidance="", known=None, meta=None):
    meta = {"root": DBOS.workflow_id, **(meta or {})}
    known = await load_outcomes() if known is None else known  # paso durable: al retomar ve el mismo catálogo
    tk = default_toolkit().restore(known)
    s = {"task": task, "parent": parent, "guidance": guidance, "known": known,
         "toolkit": tk, "budget": Budget(tokens, depth), "meta": meta}
    try:
        await make_agent().run_async(s)
    except BudgetExceeded as e:
        s["result"] = f"[sin presupuesto: {e}]"
    except Exception as e:
        if depth == 0:
            await tell(s, "error", error=repr(e))
        raise
    if depth == 0:
        await tell(s, "done", result=s["result"])
    return {"result": s["result"], "outcomes": tk.log, "left": s["budget"].left}


# ── F11 · Lanzar, consultar y responder: lo usan la CLI y server.py ──
def start():
    """Retoma lo que quedó a medias y registra la cola (4 tareas a la vez por proceso)."""
    DBOS.launch()
    DBOS.register_queue("agents", worker_concurrency=4, polling_interval_sec=0.2)

def launch(task, callback=None):
    root = uuid.uuid4().hex[:8]
    with SetWorkflowID(root):
        DBOS.enqueue_workflow("agents", agent, task, meta={"callback": callback})
    return root

def pending(root):
    """El workflow (raíz o hijo) que espera a un humano, y su pregunta."""
    alive = DBOS.list_workflows(workflow_id_prefix=root, status=["PENDING", "ENQUEUED"], load_input=False, load_output=False)
    for w in alive:  # ENQUEUED: puede que este proceso todavía no lo haya retomado
        if question := DBOS.get_event(w.workflow_id, "pending", timeout_seconds=0):
            return w.workflow_id, question
    return None, None

def summary(root):
    w = DBOS.get_workflow_status(root)
    if w is None:
        return None
    if w.status == "SUCCESS":
        return {"id": root, "status": "done", "result": w.output["result"]}
    if w.status in ("ENQUEUED", "PENDING"):
        question = pending(root)[1]
        return {"id": root, "status": "paused" if question else "running", "pending": question}
    return {"id": root, "status": "error", "error": str(w.error)}

def reply(root, answer):
    wid, question = pending(root)
    if wid:
        DBOS.send(wid, answer, "answer")
    return question

def wait(root, answered=None):
    """Espera a que la tarea termine o haga una pregunta nueva."""
    while True:
        st = summary(root)
        if st["status"] != "running" and not (answered and st.get("pending") == answered):
            return st
        time.sleep(0.2)


if __name__ == "__main__":
    # python fractal_agent.py "tarea"                  → lanza
    # python fractal_agent.py --resume ID "respuesta"  → responde y retoma
    start()
    if sys.argv[1] == "--resume":
        root = sys.argv[2]
        st = wait(root, reply(root, sys.argv[3]))
    else:
        root = launch(sys.argv[1])
        st = wait(root)
    if st["status"] == "paused":
        print(f"\nPREGUNTA: {st['pending']}\n→ python fractal_agent.py --resume {root} \"tu respuesta\"")
    else:
        print(f"\n{st['status'].upper()}:\n{st.get('result') or st.get('error')}")
    DBOS.destroy()
