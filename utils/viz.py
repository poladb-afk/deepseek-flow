"""Export de los grafos a mermaid: `python3 main.py grafo`.

Camina los sucesores desde el nodo inicial y emite las aristas con sus
acciones — el diagrama real que ejecuta el framework, no el dibujado."""
import argparse


def mermaid(flow, titulo="flujo"):
    lineas = ["flowchart TD"]
    nombres = {}
    vistos = set()

    def nombre(nodo):
        if id(nodo) not in nombres:
            nombres[id(nodo)] = f"{type(nodo).__name__}_{len(nombres)}"
        return nombres[id(nodo)]

    def rec(nodo):
        if id(nodo) in vistos:
            return
        vistos.add(id(nodo))
        for accion, siguiente in nodo.successors.items():
            lineas.append(f"    {nombre(nodo)} -->|{accion}| {nombre(siguiente)}")
            rec(siguiente)

    # Un BatchFlow (o cualquier flujo anidado) tiene como start el pipeline
    # interno; el walk interno lo sigue. Nombres espejo del batch y de su
    # nodo-rama (que no tiene aristas porque es hoja), así el diagrama
    # distingue el batch puro (effective_n multi), el pipeline (single) y la
    # rama async de juez_lote.
    if type(flow).__name__ != "Flow":
        nombres[id(flow.start_node)] = type(flow).__name__
    rec(flow.start_node)
    # si el raíz no tiene aristas (batch puro / rama hoja), igual se declara
    if not flow.start_node.successors:
        lineas.append(f"    {nombre(flow.start_node)}")
    return "\n".join(lineas)


FLOWS = {
    "chat": lambda: __import__("flow").create_agent_flow(),
    "informe": lambda: __import__("informe").create_informe_flow(),
    "juez": lambda: __import__("juez").create_juez_flow(),
    "juez_lote": lambda: __import__("juez_lote").create_juez_lote_flow(),
    "auditoria": lambda: __import__("auditoria").create_auditoria_flow(),
    "research": lambda: __import__("research").create_research_flow(),
    "supervisor": lambda: __import__("supervisor").create_supervisor_flow(),
    "effective_n": lambda: __import__("effective_n").create_effective_n_flow(),
    "effective_n_multi": lambda: __import__("effective_n").EffectiveNMulti(
        [], "*.jsonl", "salidas/effective_n.md"
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grafo", description="Grafos en mermaid")
    parser.add_argument("flujo", nargs="?", choices=FLOWS, help="uno solo, o todos")
    args = parser.parse_args(argv)
    elegidos = [args.flujo] if args.flujo else list(FLOWS)
    for nombre in elegidos:
        print(f"\n### {nombre}\n")
        print(mermaid(FLOWS[nombre]()))


if __name__ == "__main__":
    main()
