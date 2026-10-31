"""Módulo `skills`: modos de trabajo que el modelo carga cuando el pedido lo pide.

Un skill es un YAML en `skills/` con `id`, `descripcion` (CUÁNDO usarlo) e
`instrucciones`. El catálogo (`id: descripción`) viaja en la descripción de la
tool `usar_skill`, igual en toda la sesión (no rompe el KV-cache); el modelo
la llama si el pedido encaja y recibe las instrucciones como resultado
(divulgación progresiva, Agent Skills). Hasta X110 una regex del YAML decidía
y el loop recortaba las tools: con otro idioma o redacción no se activaba
(fase 5b, `banco/specs/fase5b.md`).

Quitar el mecanismo = borrar este archivo. Un YAML roto se saltea con aviso.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

from yaml import YAMLError, safe_load

from utils.terminal import colorear

DIR_SKILLS = Path(__file__).resolve().parent.parent / "skills"
_CAMPOS = ("id", "descripcion", "instrucciones")


@dataclass(frozen=True)
class Skill:
    id: str
    descripcion: str
    instrucciones: str


def cargar(raiz=DIR_SKILLS):
    """Los skills válidos de `raiz`, en orden de archivo."""
    habilidades = []
    for ruta in sorted(Path(raiz).glob("*.yaml")):
        try:
            datos = safe_load(ruta.read_text(encoding="utf-8")) or {}
            faltan = [campo for campo in _CAMPOS if not datos.get(campo)]
            if faltan:
                raise ValueError("faltan campos: " + ", ".join(faltan))
        except (OSError, YAMLError, ValueError, AttributeError) as e:
            print(f"[skills] {ruta.name} no cargó ({type(e).__name__}: {e}) → se saltea", file=sys.stderr)
            continue
        habilidades.append(Skill(str(datos["id"]), " ".join(str(datos["descripcion"]).split()),
                                 str(datos["instrucciones"]).strip()))
    return habilidades


def esquema(habilidades):
    """La tool `usar_skill` con el catálogo en su descripción. PURA."""
    catalogo = "\n".join(f"- {s.id}: {s.descripcion}" for s in habilidades)
    return {
        "type": "function",
        "function": {
            "name": "usar_skill",
            "description": ("Cargá las instrucciones de un modo de trabajo cuando el pedido encaja en su "
                            "descripción, antes de empezar a trabajar en él. Modos:\n" + catalogo),
            "parameters": {
                "type": "object",
                "properties": {"skill": {"type": "string", "enum": [s.id for s in habilidades]}},
                "required": ["skill"],
            },
        },
    }


SKILLS = {s.id: s for s in cargar()}


def usar_skill(skill):
    elegido = SKILLS.get(str(skill).strip())
    if elegido is None:
        return f"ERROR: no hay un skill '{skill}'. Disponibles: {', '.join(SKILLS) or 'ninguno'}"
    print(colorear(f"  [skill] {elegido.id} activo — {elegido.descripcion}", "info"), flush=True)
    return elegido.instrucciones


TOOLS = [esquema(list(SKILLS.values()))] if SKILLS else []
IMPL = {"usar_skill": usar_skill} if SKILLS else {}
