from pocketflow import Flow

from nodes import (
    AgentStep,
    Cierre,
    Contexto,
    ExecuteTools,
    ExitChat,
    GetQuestion,
    Observar,
    PreFetch,
    Skills,
    VerificarCitas,
)


def create_agent_flow():
    """Un solo camino (fase 3b, X106): toda pregunta llega al modelo con las
    tools ofrecidas y él decide si usarlas. Antes un router (Laya + voto +
    reglas de palabras) mandaba algunas a una llamada sin tools."""
    ask = GetQuestion()
    prefetch = PreFetch()
    skills = Skills()  # el skill de la pregunta, una vez, a la entrada
    contexto = Contexto()  # compacta antes de CADA llamada al modelo
    step = AgentStep(max_retries=3, wait=5)
    tools = ExecuteTools()
    observar = Observar()  # cuenta la ronda: no-progreso, novedad, notas
    cierre = Cierre(max_retries=3, wait=5)  # la última llamada, sin tools
    bye = ExitChat()
    # la respuesta pasa por la verificación de citas antes de la próxima
    # pregunta: un nodo propio (con retry), no un paso escondido en post
    citas = VerificarCitas(max_retries=2, wait=2)

    ask - "continue" >> prefetch
    prefetch - "continue" >> skills
    skills - "continue" >> contexto
    contexto - "herramientas" >> step
    contexto - "cierre" >> cierre  # el presupuesto se acabó: la última llamada
    step - "answer" >> citas  # respuesta entregada: se verifican sus citas
    citas >> ask              # y vuelve a la siguiente pregunta
    cierre - "answer" >> citas
    # Cierre hereda el post de AgentStep, que puede devolver "tool": nunca
    # pasa (las tools van retiradas) pero la arista existe
    cierre - "tool" >> tools
    step - "tool" >> tools  # pidió herramientas: ejecutarlas y volver a pensar
    tools >> observar       # la ronda se cuenta
    observar >> contexto    # y antes de pensar, el contexto otra vez
    ask - "exit" >> bye

    return Flow(start=ask)
