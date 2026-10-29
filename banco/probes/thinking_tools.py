"""Gate previo de la fase 3 (banco/specs/fase3.md): thinking en las rondas con
tools, con el `reasoning_content` preservado. Llamadas REALES a la API.

Pregunta: con el historial que mandaría el chat si activa la fase 3, ¿la API
devuelve algún 400? Los de la bitácora (2026-10-05, "reasoning_content must be
passed back") salían de flips de modo dentro de la conversación; la regla
documentada es que, con tool calls en el turno, el reasoning de esos mensajes
del asistente tiene que volver COMPLETO en todas las requests siguientes.

Los requests con thinking ON los arma la sonda (`pedido`): la fase 3 se
rechazó en el A/B (banco/specs/fase3.md) y el producto ya no ofrece esa
combinación. Los de thinking OFF salen de `utils.call_llm._kwargs_agente`, el
builder de producción. La sonda queda como documento ejecutable de la
restricción del proveedor (la regla es por pregunta: F da 400, G pasa).

Secuencias (cada una arranca de cero):
  A  ronda de tools y respuesta, reasoning preservado
  B  el cierre: tras las rondas, la última llamada SIN tools (Cierre)
  C  el rechazo (s19-s3): el resultado de la tool es un RECHAZADO del HITL
  D  pregunta nueva después de un turno con tools (el reasoning viejo viaja)
  E  compacción: la zona fría pierde su reasoning, la caliente lo conserva
  F  el flip: un historial armado con thinking OFF (sesión vieja, resume) y la
     ronda siguiente con thinking ON
  G  un turno ENTERO con thinking OFF y tools (sin reasoning en ningún
     mensaje) y la pregunta SIGUIENTE con thinking ON y tools
  H  rondas con thinking ON y reasoning, y el cierre de ESE turno con
     thinking OFF (como lo mandaría Cierre si quedara apagado)

Criterio (redefinido el 2026-10-28 tras la primera corrida, ANTES de correr
G y H — banco/specs/fase3.md): A–E y G sin 400. F dio 400 en la primera
corrida: documenta la restricción del proveedor (el reasoning del turno EN
CURSO tiene que volver) y queda como informativa, igual que H, que no tiene
predicción. Otro error (red, 429) no es 400 pero deja la secuencia SIN
veredicto: se repite.

Costo: ~21 llamadas cortas (max_tokens bajo), centavos.
Uso: python3 banco/probes/thinking_tools.py [--salida salidas/evals/thinking_tools.json]
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from utils.call_llm import _client, _kwargs_agente, _model  # noqa: E402
from utils.fs_tools import TOOLS  # noqa: E402

LEER = [t for t in TOOLS if t["function"]["name"] in ("read_file", "list_files")]
SYSTEM = {"role": "system", "content": "Sos un agente. Usá las tools cuando haga falta; respondé breve."}
PEDIDO = {"role": "user", "content": "Listá los archivos de la carpeta actual con list_files y decime cuántos hay."}
RECHAZO = "RECHAZADO por el usuario: fuera del scope de la tarea"
CIERRE = ("(presupuesto de herramientas agotado) Respondé AHORA con lo que tengas: "
          "hallazgos, límites y qué falta. No emitas tool calls.")


def pedido(mensajes, tools=None, pensar=True):
    """El request de una llamada. ON: thinking habilitado y el reasoning que
    traigan los mensajes viaja tal cual. OFF: el de producción."""
    if not pensar:
        return _kwargs_agente(mensajes, tools)
    kwargs = {"model": _model(), "messages": list(mensajes),
              "extra_body": {"thinking": {"type": "enabled"}}}
    if tools:
        kwargs["tools"] = tools
    return kwargs


def asistente(msg, con_razonamiento=True):
    """El mensaje del asistente como lo guardaría el historial de la fase 3."""
    m = {"role": "assistant", "content": getattr(msg, "content", None)}
    razon = getattr(msg, "reasoning_content", None)
    if con_razonamiento and razon:
        m["reasoning_content"] = razon
    if getattr(msg, "tool_calls", None):
        m["tool_calls"] = [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                           for tc in msg.tool_calls]
    return m


def resultados(msg, contenido="a.py\nb.py\nc.md"):
    return [{"role": "tool", "tool_call_id": tc.id, "content": contenido} for tc in msg.tool_calls]


class Sonda:
    """Corre llamadas y anota cada una: paso, status y si volvió reasoning."""

    def __init__(self, cliente, max_tokens=300):
        self.cliente, self.max_tokens, self.pasos = cliente, max_tokens, []

    def llamar(self, secuencia, paso, mensajes, tools=None, pensar=True):
        kwargs = pedido(mensajes, tools, pensar)
        fila = {"secuencia": secuencia, "paso": paso, "pensar": pensar, "tools": bool(tools)}
        try:
            r = self.cliente.chat.completions.create(**kwargs, max_tokens=self.max_tokens)
        except Exception as e:  # noqa: BLE001 (la sonda registra cualquier error de la API)
            fila.update(ok=False, status=getattr(e, "status_code", None), error=str(e)[:300])
            self.pasos.append(fila)
            return None
        msg = r.choices[0].message
        fila.update(ok=True, status=200, tool_calls=len(msg.tool_calls or []),
                    reasoning=bool(getattr(msg, "reasoning_content", None)))
        self.pasos.append(fila)
        return msg

    def ronda(self, secuencia, mensajes, contenido=None, pensar=True):
        """Una ronda de tools: el modelo pide, se agrega el resultado. None si
        el modelo no pidió tools (la secuencia sigue sin ronda) o falló."""
        msg = self.llamar(secuencia, "pide tools", mensajes, LEER, pensar)
        if msg is None or not msg.tool_calls:
            return None
        mensajes.append(asistente(msg, con_razonamiento=pensar))
        mensajes.extend(resultados(msg, *([contenido] if contenido else [])))
        return msg


def secuencias(s):
    # A: ronda y respuesta
    m = [SYSTEM, PEDIDO]
    if s.ronda("A", m):
        s.llamar("A", "responde con tools ofrecidas", m, LEER)
    # B: el cierre sin tools tras dos rondas
    m = [SYSTEM, PEDIDO]
    if s.ronda("B", m):
        m.append({"role": "user", "content": "Ahora leé el primero con read_file."})
        s.ronda("B", m)
        s.llamar("B", "cierre sin tools", m + [{"role": "user", "content": CIERRE}], None)
    # C: el rechazo del HITL (s19-s3)
    m = [SYSTEM, PEDIDO]
    if s.ronda("C", m, contenido=RECHAZO):
        s.llamar("C", "sigue tras el rechazo", m, LEER)
    # D: pregunta nueva después de un turno con tools
    m = [SYSTEM, PEDIDO]
    if s.ronda("D", m):
        final = s.llamar("D", "cierra el turno", m, LEER)
        if final is not None:
            m.append(asistente(final))
            m.append({"role": "user", "content": "Gracias. ¿Y cuál es el más largo?"})
            s.llamar("D", "pregunta nueva", m, LEER)
    # E: compacción — la zona fría sin reasoning, la caliente con
    m = [SYSTEM, PEDIDO]
    if s.ronda("E", m):
        m.append({"role": "user", "content": "Ahora leé el primero con read_file."})
        if s.ronda("E", m):
            frio = next(i for i, x in enumerate(m) if x.get("tool_calls"))
            m[frio] = {k: v for k, v in m[frio].items() if k != "reasoning_content"}
            s.llamar("E", "tras compactar la zona fría", m, LEER)
    # F: historial con thinking OFF y la ronda siguiente con ON
    m = [SYSTEM, PEDIDO]
    if s.ronda("F", m, pensar=False):
        s.llamar("F", "flip OFF→ON con tools", m, LEER, pensar=True)
    # G: el turno anterior entero sin reasoning; la pregunta nueva, con
    m = [SYSTEM, PEDIDO]
    if s.ronda("G", m, pensar=False):
        final = s.llamar("G", "cierra el turno OFF", m, LEER, pensar=False)
        if final is not None:
            m.append(asistente(final, con_razonamiento=False))
            m.append({"role": "user", "content": "Ahora leé el primero con read_file."})
            if s.ronda("G", m):
                s.llamar("G", "responde con thinking ON", m, LEER)
    # H: el mismo turno, rondas ON y el cierre OFF
    m = [SYSTEM, PEDIDO]
    if s.ronda("H", m):
        s.llamar("H", "cierre OFF tras rondas ON", m + [{"role": "user", "content": CIERRE}],
                 None, pensar=False)


# Las que deciden el gate y las que solo informan (F: la restricción ya medida;
# H: sin predicción, decide si Cierre puede ir con thinking OFF).
GATE = "ABCDEG"
INFORMATIVAS = "FH"


def veredicto(pasos):
    """(pasa, resumen). Pasa si cada secuencia de GATE tiene llamadas y
    ninguna falló; un 400 en cualquiera la marca "400", otro error "sin
    veredicto". Las INFORMATIVAS se reportan y no deciden."""
    por_sec = {}
    for p in pasos:
        por_sec.setdefault(p["secuencia"], []).append(p)
    resumen = {}
    for sec in GATE + INFORMATIVAS:
        filas = por_sec.get(sec, [])
        if any(p["status"] == 400 for p in filas):
            resumen[sec] = "400"
        elif not filas or any(not p["ok"] for p in filas):
            resumen[sec] = "sin veredicto"
        else:
            resumen[sec] = "ok"
    return all(resumen[s] == "ok" for s in GATE), resumen


def main(argv=None):
    parser = argparse.ArgumentParser(prog="thinking_tools", description=__doc__.splitlines()[0])
    parser.add_argument("--salida", default=str(RAIZ / "salidas" / "evals" / "thinking_tools.json"))
    args = parser.parse_args(argv)
    sonda = Sonda(_client())
    secuencias(sonda)
    pasa, resumen = veredicto(sonda.pasos)
    for p in sonda.pasos:
        estado = "ok" if p["ok"] else f"ERROR {p['status']}: {p['error']}"
        print(f"{p['secuencia']} · {p['paso']:<30} pensar={p['pensar']!s:<5} tools={p['tools']!s:<5} {estado}")
    print("veredicto: " + " · ".join(f"{k}={v}" for k, v in resumen.items()))
    print("informativas: " + " · ".join(f"{s}={resumen[s]}" for s in INFORMATIVAS))
    print(f"GATE ({', '.join(GATE)}): " + ("PASA" if pasa else "NO PASA"))
    destino = Path(args.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"pasa": pasa, "resumen": resumen, "pasos": sonda.pasos},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
