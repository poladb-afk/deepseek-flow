"""Deep research: planner → researcher → synthesizer con loop de cobertura.

El bucle juzga la COBERTURA, no la respuesta (la inversión del juez): el
synthesizer decide si el material alcanza para un informe o hay huecos;
con huecos, el planner re-planifica con el feedback. Presupuesto
MAX_ROUNDS (ley L8): al tope se fuerza el informe con lo reunido.
Structured output en YAML (extraer_yaml + assert): un formato roto
dispara el retry del Node y se re-pregunta.

Uso: python3 main.py research "tema" [--salida research.md]
"""
import argparse
from pathlib import Path

from pocketflow import BatchNode, Flow, Node

from utils.call_llm import call_llm
from utils.estructura import extraer_yaml
from utils.websearch import search_web

MAX_ROUNDS = 2
RESULTADOS_POR_QUERY = 4


class Planner(Node):
    def prep(self, shared):
        return shared["tema"], shared.get("feedback", "")

    def exec(self, inputs):
        tema, feedback = inputs
        if feedback:
            instruccion = (
                f"Investigamos '{tema}'. Huecos detectados en el material:\n{feedback}\n\n"
                "Genera 3 consultas de búsqueda web que llenen ESOS huecos."
            )
        else:
            instruccion = f"Genera 3 consultas de búsqueda web diversas y complementarias para investigar: '{tema}'."
        prompt = f"""{instruccion}

Responde SOLO yaml:
```yaml
queries:
  - "consulta 1"
  - "consulta 2"
  - "consulta 3"
```"""
        plan = extraer_yaml(call_llm(prompt))
        queries = plan["queries"]
        assert isinstance(queries, list) and queries and all(isinstance(q, str) and q.strip() for q in queries), "queries inválidas"
        return queries

    def post(self, shared, prep_res, exec_res):
        shared["queries"] = exec_res
        print(f"\n🔍 Planner: {exec_res}")


class Researcher(BatchNode):
    def prep(self, shared):
        return shared["queries"]

    def exec(self, query):
        print(f"  🌐 buscando: {query}")
        crudos = search_web(query, k=RESULTADOS_POR_QUERY)
        hechos = call_llm(
            f"Extrae hasta 5 hechos concretos y breves relevantes para esta consulta, "
            f"citando la URL de cada uno.\n\nConsulta: {query}\n\nResultados:\n{crudos}"
        )
        return f"### {query}\n{hechos}"

    def post(self, shared, prep_res, exec_res_list):
        if "notes" not in shared:
            shared["notes"] = []
        shared["notes"].extend(exec_res_list)
        print(f"  📚 material total: {len(shared['notes'])} bloques")


class Synthesizer(Node):
    def prep(self, shared):
        return shared["tema"], shared.get("notes", []), shared.get("ronda", 0)

    def exec(self, inputs):
        tema, notes, ronda = inputs
        material = "\n\n".join(notes) or "(sin material)"
        if ronda >= MAX_ROUNDS:
            return {
                "action": "finalize",
                "content": call_llm(
                    f"Escribe en español un informe markdown conciso sobre '{tema}' "
                    f"usando SOLO este material y citando las URLs:\n\n{material}"
                ),
            }
        prompt = f"""Investigamos: "{tema}"

Material reunido:
{material}

¿El material alcanza para un informe completo y balanceado?

Responde SOLO yaml con UNA de las dos formas:
```yaml
action: research
feedback: "qué falta exactamente"
```
```yaml
action: finalize
content: |
  el informe final en markdown (solo el contenido, sin ```yaml)
```"""
        decision = extraer_yaml(call_llm(prompt))
        assert decision["action"] in ("research", "finalize"), "acción inválida"
        if decision["action"] == "finalize":
            assert str(decision.get("content", "")).strip(), "informe vacío"
        return decision

    def post(self, shared, prep_res, exec_res):
        if exec_res["action"] == "research":
            shared["ronda"] = shared.get("ronda", 0) + 1
            shared["feedback"] = exec_res.get("feedback", "")
            print(f"  🤔 huecos (ronda {shared['ronda']}): {shared['feedback'][:120]}")
            return "research"
        salida = Path(shared["salida"])
        salida.write_text(exec_res["content"], encoding="utf-8")
        shared["informe"] = str(salida.resolve())
        print(f"\n✅ informe escrito: {shared['informe']}")
        return "finalize"


class Fin(Node):
    def post(self, shared, prep_res, exec_res):
        pass


def create_research_flow():
    planner = Planner(max_retries=3, wait=5)
    researcher = Researcher(max_retries=3, wait=5)
    synthesizer = Synthesizer(max_retries=3, wait=5)
    fin = Fin()

    planner >> researcher >> synthesizer
    synthesizer - "research" >> planner  # el loop de cobertura
    synthesizer - "finalize" >> fin      # salida limpia (sin warning)

    return Flow(start=planner)


def investigar(tema, salida="research.md"):
    shared = {"tema": tema, "salida": salida}
    create_research_flow().run(shared)
    return shared["informe"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="research", description="Deep research con loop de cobertura"
    )
    parser.add_argument("tema")
    parser.add_argument("--salida", default="research.md")
    args = parser.parse_args(argv)
    investigar(args.tema, args.salida)


if __name__ == "__main__":
    main()
