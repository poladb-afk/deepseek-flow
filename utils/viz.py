"""Export de los grafos a mermaid: `python3 main.py grafo`.

Camina los sucesores desde el nodo inicial y emite las aristas con sus
acciones — el diagrama real que ejecuta el framework, no el dibujado."""
import argparse


def mermaid(flow, titulo="flujo"):
    lineas = [f"flowchart TD"]
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

    rec(flow.start_node)
    return "\n".join(lineas)


FLOWS = {
    "chat": lambda: __import__("flow").create_agent_flow(),
    "informe": lambda: __import__("informe").create_informe_flow(),
    "juez": lambda: __import__("juez").create_juez_flow(),
    "auditoria": lambda: __import__("auditoria").create_auditoria_flow(),
    "research": lambda: __import__("research").create_research_flow(),
    "supervisor": lambda: __import__("supervisor").create_supervisor_flow(),
    "effective_n": lambda: __import__("effective_n").create_effective_n_flow(),
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
