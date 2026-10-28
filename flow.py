from pocketflow import Flow

from nodes import (
    AgentStep,
    Cierre,
    Contexto,
    DirectAnswer,
    ExecuteTools,
    ExitChat,
    GetQuestion,
    LayaRouter,
    Observar,
    PreFetch,
    VerificarCitas,
)


def create_agent_flow():
    ask = GetQuestion()
    prefetch = PreFetch()
    contexto = Contexto()  # compacta antes de CADA llamada al modelo
    step = AgentStep(max_retries=3, wait=5)
    tools = ExecuteTools()
    observar = Observar()  # cuenta la ronda: no-progreso, novedad, notas
    cierre = Cierre(max_retries=3, wait=5)  # la última llamada, sin tools
    bye = ExitChat()
    # la respuesta pasa por la verificación de citas antes de la próxima
    # pregunta: un nodo propio (con retry), no un paso escondido en post
    citas = VerificarCitas(max_retries=2, wait=2)

    from utils.call_llm import _setting

    if _setting("USE_LAYA_ROUTER", "1") == "1":
        # If inteligente: Laya decide localmente la primera arista
        router = LayaRouter()
        directo = DirectAnswer(max_retries=3, wait=5)
        # exp/50: el pre-fetch corre UNA vez por pregunta nueva, entre la
        # entrada y la decisión — así el mensaje [pre-fetch] entra ANTES del
        # router (que saltea el prefetch para leer la pregunta real).
        ask - "continue" >> prefetch
        prefetch - "continue" >> router
        router - "directo" >> contexto
        router - "herramientas" >> contexto
        contexto - "directo" >> directo
        # DirectAnswer hereda el post de AgentStep: devuelve "answer" (nunca
        # "tool", va sin tools) — la arista correcta es esa, no la default.
        directo - "answer" >> citas
        directo - "tool" >> tools
    else:
        ask - "continue" >> prefetch
        prefetch - "continue" >> contexto

    step - "answer" >> citas  # respuesta entregada: se verifican sus citas
    citas >> ask              # y vuelve a la siguiente pregunta
    contexto - "herramientas" >> step
    contexto - "cierre" >> cierre  # el presupuesto se acabó: la última llamada
    cierre - "answer" >> citas
    # Cierre hereda el post de AgentStep, que puede devolver "tool": nunca
    # pasa (las tools van retiradas) pero la arista existe, como en DirectAnswer
    cierre - "tool" >> tools
    step - "tool" >> tools  # pidió herramientas: ejecutarlas y volver a pensar
    tools >> observar       # la ronda se cuenta
    observar >> contexto    # y antes de pensar, el contexto otra vez
    ask - "exit" >> bye

    return Flow(start=ask)
