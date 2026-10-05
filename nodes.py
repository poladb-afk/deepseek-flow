from pocketflow import Node

from modules import discover
from utils.call_llm import call_llm_agent
from utils.fs_tools import MAX_TOOL_ROUNDS, TOOLS as CORE_TOOLS, run_tool_call

EXIT_WORDS = {"salir", "exit", "quit"}

# Action space = capacidades base del CORE + lo que aporten los módulos.
MODULE_TOOLS, MODULE_IMPLS = discover()
TOOLS = CORE_TOOLS + MODULE_TOOLS


class GetQuestion(Node):
    def exec(self, _):
        while True:
            try:
                text = input("\nTú: ").strip()
            except EOFError:
                return "exit"
            if text:
                return text

    def post(self, shared, prep_res, exec_res):
        if exec_res.lower() in EXIT_WORDS:
            return "exit"
        shared["messages"].append({"role": "user", "content": exec_res})
        shared["tool_rounds"] = 0
        return "continue"


class AgentStep(Node):
    def prep(self, shared):
        # Al llegar al límite de rondas se retiran las tools: el modelo debe responder ya.
        tools = None if shared.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS else TOOLS
        return shared["messages"], tools

    def exec(self, inputs):
        messages, tools = inputs
        return call_llm_agent(messages, tools)

    def post(self, shared, prep_res, exec_res):
        shared["messages"].append(exec_res)
        if getattr(exec_res, "tool_calls", None):
            return "tool"
        print(f"\nDeepSeek: {exec_res.content}")
        return "answer"


class ExecuteTools(Node):
    def prep(self, shared):
        return shared["messages"][-1].tool_calls

    def exec(self, tool_calls):
        return [run_tool_call(tc, MODULE_IMPLS) for tc in tool_calls]

    def post(self, shared, prep_res, exec_res):
        shared["messages"].extend(exec_res)
        shared["tool_rounds"] = shared.get("tool_rounds", 0) + 1
        return "default"


class ExitChat(Node):
    def post(self, shared, prep_res, exec_res):
        print("\n¡Chao! 👋")


PREGUNTA_ROUTER = {
    "necesita_herramientas": {
        "type": "choice",
        "instructions": "Does answering the request require tools (search/reading files, web, computation) or can it be answered directly?",
        "criteria": {
            "herramientas": "needs local files, documents, current data, or exact computation",
            "directo": "general knowledge, conversation, creativity; no external data needed",
        },
    }
}


class LayaRouter(Node):
    """If inteligente: Laya (local, ms) decide si la pregunta necesita
    herramientas o se responde directa. La confianza aplica los umbrales
    de bmo; 'uncertain' cae al lado SEGURO (herramientas). Si laya no está
    disponible, también cae a herramientas: degrada, no rompe.

    El estado {"pregunta": ...} y PREGUNTA_ROUTER son el contrato del
    fine-tune (task router_flow de bmo): entrenamiento y producción leen
    lo mismo byte a byte."""

    def prep(self, shared):
        return {"pregunta": str(shared["messages"][-1]["content"])[:1000]}

    def exec(self, estado):
        from utils.laya import disponible, preguntar

        if not disponible():
            return ("herramientas", 0.0)
        resp, conf = preguntar(estado, PREGUNTA_ROUTER)["necesita_herramientas"]
        return resp, conf

    def post(self, shared, prep_res, exec_res):
        from utils.laya import veredicto

        eleccion, confianza = exec_res
        print(f"  [laya] {eleccion} (conf {confianza:.2f})")
        if eleccion == "directo" and veredicto(confianza) != "met":
            return "herramientas"  # dudoso: caer al lado seguro
        return eleccion


class DirectAnswer(AgentStep):
    """AgentStep sin herramientas: la pregunta se responde de una."""

    def prep(self, shared):
        return shared["messages"], None
