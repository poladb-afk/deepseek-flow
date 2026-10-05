from pocketflow import Flow

from nodes import AgentStep, DirectAnswer, ExecuteTools, ExitChat, GetQuestion, LayaRouter


def create_agent_flow():
    ask = GetQuestion()
    step = AgentStep(max_retries=3, wait=5)
    tools = ExecuteTools()
    bye = ExitChat()

    from utils.call_llm import _setting

    if _setting("USE_LAYA_ROUTER", "1") == "1":
        # If inteligente: Laya decide localmente la primera arista
        router = LayaRouter()
        directo = DirectAnswer(max_retries=3, wait=5)
        ask - "continue" >> router
        router - "directo" >> directo
        router - "herramientas" >> step
        # DirectAnswer hereda el post de AgentStep: devuelve "answer" (nunca
        # "tool", va sin tools) — la arista correcta es esa, no la default.
        directo - "answer" >> ask
        directo - "tool" >> tools
    else:
        ask - "continue" >> step

    step - "answer" >> ask  # respuesta entregada: siguiente pregunta
    step - "tool" >> tools  # pidió herramientas: ejecutarlas y volver a pensar
    tools >> step
    ask - "exit" >> bye

    return Flow(start=ask)
