"""El grafo del chat (S9b A′): el loop es el `kernel.loop`.

El chat aporta `PasoChat`/`CierreChat` y las políticas `Observar`/`Contexto`;
el resto —aristas, saldo, historial canónico— es el del kernel.
"""
from pocketflow import Flow

import nodes as n
from utils.kernel import Ctx, Ledger, loop


def create_agent_flow():
    """Un solo camino (X106): toda pregunta llega al modelo con las tools y él
    decide si usarlas; `PasoChat.prep` resetea saldo y skill por pregunta."""
    ctx, todas = Ctx(n.responder_llm, Ledger(n.presupuesto({}))), n.herramientas_de({})
    paso = n.PasoChat(ctx, todas, max_retries=3, wait=5)
    cerrar = n.CierreChat(ctx, todas, max_retries=3, wait=5)
    agente = loop(ctx, todas, politicas=(n.Observar(), n.Contexto()), paso=paso,
                  actuar=n.ActuarChat(ctx, todas), cierre=cerrar)
    ask, prefetch, skills, contexto = n.GetQuestion(), n.PreFetch(), n.Skills(), n.Contexto()
    citas, bye = n.VerificarCitas(max_retries=2, wait=2), n.ExitChat()

    ask - "continue" >> prefetch
    prefetch - "continue" >> skills
    skills - "continue" >> contexto
    contexto - "default" >> agente
    contexto - "cierre" >> agente  # imposible al entrar (rondas=0); el candado lo exige
    agente >> citas
    citas >> ask
    ask - "exit" >> bye

    return Flow(start=ask)
