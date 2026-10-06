"""Módulo `a2a`: el agente consume OTROS agentes (protocolo agent2agent).

Igual que `mcp` en el eje de servidores, pero del lado de los AGENTES: en
vez de tools dentro de un servidor, hablamos con agentes remotos que
exponen el protocolo A2A (agent2agent):

  - `GET  {base}/.well-known/agent.json`  → el agent card (nombre,
    descripción, skills, capacidades).
  - `POST {base}/`  → JSON-RPC 2.0 `message/send` para enviar una tarea:
    `params = {message: {role: "user", parts: [{type: "text", text: ...}]}}`.

Configuración: `A2A_AGENTS` en `.env` es un JSON `{"nombre": "http://host:puerto"}`
de agentes remotos. Sin setting (o vacío) las tools devuelven un mensaje
claro y no llaman a la red.

Degradación, no crash: un agente caído o un card inaccesible se reportan
como "inaccesible" y el resto sigue funcionando. Los timeouts son cortos
a propósito (5s para un card, 60s para una tarea), y cualquier error de
transporte se vuelve texto.

Sin dependencias nuevas: `requests` (ya presente)."""
import itertools
import json

import requests

from utils.call_llm import _setting

TIMEOUT_CARD_S = 5
TIMEOUT_TAREA_S = 60
_SIN_AGENTES = (
    "No hay agentes remotos A2A configurados. Define en .env:\n"
    '  A2A_AGENTS={"nombre": "http://host:puerto"}'
)

# id JSON-RPC incrementado por proceso (monótono, entero).
_ids = itertools.count(1)


def _agentes():
    """El dict `{nombre: url}` del setting A2A_AGENTS.

    Un JSON inválido se trata como vacío (degradación: el setting roto no
    debe romper el arranque del chat, del que este módulo se descubre)."""
    texto = (_setting("A2A_AGENTS", "") or "").strip()
    if not texto:
        return {}
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).rstrip("/") for k, v in data.items() if v}


def _card(nombre, base):
    """Trae el agent card del agente. Devuelve (card|None, error|None)."""
    try:
        r = requests.get(f"{base}/.well-known/agent.json", timeout=TIMEOUT_CARD_S)
    except requests.RequestException as e:
        return None, f"inaccesible ({type(e).__name__})"
    if r.status_code != 200:
        return None, f"inaccesible (HTTP {r.status_code})"
    try:
        return r.json(), None
    except ValueError:
        return None, "inaccesible (card no es JSON)"


def agentes_remotos():
    """Lista los agentes del setting con su agent card. Un agente caído se
    reporta 'inaccesible' sin cortar el listado (degradación, no crash)."""
    agentes = _agentes()
    if not agentes:
        return _SIN_AGENTES
    lineas = [f"{len(agentes)} agente(s) remoto(s) A2A configurado(s):"]
    for nombre, base in agentes.items():
        lineas.append(f"\n[{nombre}] {base}")
        card, err = _card(nombre, base)
        if err:
            lineas.append(f"  {err}")
            continue
        desc = card.get("description") or card.get("name") or "(sin descripción)"
        lineas.append(f"  {desc}")
        skills = card.get("skills") or []
        for s in skills:
            if isinstance(s, dict):
                sid = s.get("id") or s.get("name") or "?"
                sdesc = (s.get("description") or "")[:120]
                lineas.append(f"  - {sid}: {sdesc}".rstrip(": "))
    return "\n".join(lineas)


def a2a_tarea(nombre, mensaje):
    """Envía una tarea a un agente remoto con JSON-RPC 2.0 `message/send`.

    Devuelve el `result` de la respuesta (serializado) o el error del
    JSON-RPC como texto. Nombre no configurado o transporte caído se
    devuelven como texto: nunca un crash."""
    agentes = _agentes()
    if not agentes:
        return _SIN_AGENTES
    if nombre not in agentes:
        return (
            f"ERROR: agente '{nombre}' no configurado. "
            f"Disponibles: {list(agentes) or 'ninguno'}"
        )
    base = agentes[nombre]
    payload = {
        "jsonrpc": "2.0",
        "id": next(_ids),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": str(mensaje)}],
            }
        },
    }
    try:
        r = requests.post(f"{base}/", json=payload, timeout=TIMEOUT_TAREA_S)
    except requests.RequestException as e:
        return f"ERROR: el agente '{nombre}' está inaccesible ({type(e).__name__}): {e}"
    if r.status_code != 200:
        return f"ERROR: el agente '{nombre}' respondió HTTP {r.status_code}: {r.text[:300]}"
    try:
        data = r.json()
    except ValueError:
        return f"ERROR: la respuesta de '{nombre}' no es JSON: {r.text[:300]}"
    if data.get("error") is not None:
        return f"ERROR JSON-RPC de '{nombre}': {json.dumps(data['error'], ensure_ascii=False)}"
    result = data.get("result")
    if result is None:
        return f"ERROR: la respuesta de '{nombre}' no trae result: {json.dumps(data, ensure_ascii=False)[:300]}"
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "agentes_remotos",
            "description": (
                "Lista los agentes remotos A2A configurados y su agent card (descripción y "
                "skills). Úsalo antes de a2a_tarea para saber qué agentes hay disponibles."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "a2a_tarea",
            "description": (
                "Envía una tarea a un agente remoto compatible con A2A y devuelve su respuesta. "
                "Consulta agentes_remotos primero para conocer nombres y capacidades."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del agente remoto configurado en A2A_AGENTS"},
                    "mensaje": {"type": "string", "description": "La tarea o pedido para el agente remoto"},
                },
                "required": ["nombre", "mensaje"],
            },
        },
    },
]


IMPL = {"agentes_remotos": agentes_remotos, "a2a_tarea": a2a_tarea}