"""Skills declarativas (Mesa 7, exp/55): paquete prompt + tools + disparo.

Un skill es un YAML en `skills/`:

- `id`, `descripcion`
- `condicion`: regex de DISPARO sobre la pregunta (determinística, sin LLM)
- `instrucciones`: el prompt que se inyecta como contexto
- `tools`: subset de tools que el loop anuncia mientras el skill está activo

El disparo lo decide `skill_para` (puro); el `LayaRouter` lo aplica en enforce
—fuerza el lado seguro y anuncia el skill— y `AgentStep` recorta la lista de
tools al subset. **No es un sandbox**: el action space sigue siendo el mismo
(igual que el subset de módulos); el recorte es guía/publicidad para el modelo,
no una frontera de seguridad (esa sigue en HITL/policy).

SKILLS=0 apaga el mecanismo. Un YAML roto se saltea con aviso (como modules).
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PREFIJO_SKILL = "[skill]"

DIR_SKILLS = Path(__file__).resolve().parent.parent / "skills"

_CAMPOS = ("id", "descripcion", "condicion", "instrucciones")


@dataclass(frozen=True)
class Skill:
    """Un skill cargado; la condición ya viene compilada."""

    id: str
    descripcion: str
    condicion: re.Pattern
    instrucciones: str
    tools: tuple[str, ...] = field(default_factory=tuple)
    archivo: str = ""


def cargar_skills(raiz=None):
    """Skills válidos de `raiz` (default `skills/`); los inválidos se saltean
    con aviso a stderr para que un archivo roto no tumbe el chat."""
    from yaml import YAMLError, safe_load

    directorio = Path(raiz or DIR_SKILLS)
    if not directorio.is_dir():
        return []
    habilidades = []
    for ruta in sorted(directorio.glob("*.yaml")):
        try:
            datos = safe_load(ruta.read_text(encoding="utf-8")) or {}
            faltan = [campo for campo in _CAMPOS if not datos.get(campo)]
            if faltan:
                raise ValueError("faltan campos: " + ", ".join(faltan))
            herramienta = Skill(
                id=str(datos["id"]),
                descripcion=str(datos["descripcion"]).strip(),
                condicion=re.compile(str(datos["condicion"])),
                instrucciones=str(datos["instrucciones"]).strip(),
                tools=tuple(str(nombre) for nombre in (datos.get("tools") or ())),
                archivo=ruta.name,
            )
        except (OSError, YAMLError, ValueError, re.error) as e:
            print(f"[skills] {ruta.name} no cargó ({type(e).__name__}: {e}) → se saltea",
                  file=sys.stderr)
            continue
        habilidades.append(herramienta)
    return habilidades


def skill_para(pregunta, habilidades):
    """El PRIMER skill cuya condición matchea la pregunta (o None). Puro."""
    for habilidad in habilidades or ():
        if habilidad.condicion.search(pregunta or ""):
            return habilidad
    return None


def mensaje(skill):
    """El texto que se inyecta al historial (prefijo estable para distinguirlo)."""
    return f"{PREFIJO_SKILL} {skill.id} — {skill.descripcion}\n{skill.instrucciones}"


def filtrar_tools(tools, skill):
    """Subset de `tools` permitidas por el skill; nunca agrega ni expande."""
    permitidas = set(skill.tools)
    return [tool for tool in tools
            if (tool.get("function") or {}).get("name") in permitidas]


_DISPONIBLES = None


def disponibles():
    """Skills del repo, cacheados (se cargan una vez por proceso)."""
    global _DISPONIBLES
    if _DISPONIBLES is None:
        _DISPONIBLES = cargar_skills()
    return _DISPONIBLES
