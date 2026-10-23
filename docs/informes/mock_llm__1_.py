"""LLM simulado para correr fractal_agent.py sin API. Simula latencia para medir el paralelismo."""
import asyncio, json, os, re

LATENCY = float(os.getenv("MOCK_LATENCY", "0.3"))

def field(user, name):
    m = re.search(f"<{name}>\n(.*?)\n</{name}>", user, re.S)
    return m[1] if m else ""

async def mock(role, user):
    await asyncio.sleep(LATENCY)
    if path := os.getenv("MOCK_LOG"):
        with open(path, "a") as f:
            f.write(role + "\n")
    task, draft = field(user, "task"), field(user, "draft")

    if role == "planner" and not field(user, "parent"):
        return json.dumps({"mode": "compose", "steps": [
            {"piece": "ask_human", "config": {"question": "¿Para qué público es la guía?"}},
            {"piece": "decompose"}, {"piece": "spawn"}, {"piece": "synthesize"}, {"piece": "until_dry"}]})
    if role == "planner":
        return json.dumps({"mode": "adapt",
            "new": {"name": "seccion_concisa", "base": "answer", "when": "secciones cortas con ejemplo",
                    "config": {"instructions": "3 viñetas y un ejemplo concreto"}},
            "steps": [{"piece": "best_of", "config": {"inner": "seccion_concisa", "k": 3}}]})
    if role == "splitter":
        return json.dumps({"subtasks": ["Qué es un harness", "Loops con contexto fresco", "Verificación externa"]})
    if role == "worker":
        extra = " + ejemplo" if field(user, "variant").startswith("2") else ""
        return f"## {task} (para {field(user, 'guidance') or 'todos'})\n• punto A • punto B • punto C{extra}"
    if role == "picker":
        drafts = field(user, "drafts").split("\n- ")
        return json.dumps({"best": next((i for i, d in enumerate(drafts) if "ejemplo" in d), 0)})
    if role == "judge":
        ok = "ejemplo" in draft
        return json.dumps({"done": ok, "feedback": "" if ok else "falta un ejemplo concreto"})
    if role == "merger":
        return f"# {task}\n{field(user, 'subresults')}"
    if role == "refiner":
        return draft if "(pulido)" in draft else draft + "\n(pulido)"
    return json.dumps({"ok": True, "feedback": ""})
