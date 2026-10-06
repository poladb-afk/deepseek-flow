"""Sonda del KV-cache de DeepSeek sobre los esquemas de tools (exp/15).

Pregunta que responde: ¿cuánto cuestan HOY los 27 esquemas por ronda de
tools, y cuánto ahorraría un pre-rank que varie la lista? Veredicto de la
medición (2026-10-06): los esquemas viven en el prefijo cacheado — llamada
idéntica: 4096/4311 tokens cacheados (miss 215 ≈ el mensaje del usuario);
lista variada (subset en orden canónico): miss 161. El pre-rank ahorraría
tokens que cuestan ~nada y arriesga sacarle la tool correcta al modelo.
VEREDICTO: descartado por evidencia.

Uso: python3 banco/probes/cache_tools.py  (gasta ~centavos de API)
"""
import os

from openai import OpenAI

from modules import discover
from utils.fs_tools import TOOLS as CORE


def main():
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    mod_tools, _ = discover()
    tools = CORE + mod_tools
    mensajes = [{"role": "user", "content": "¿qué archivos hay acá?"}]

    def llamada(tools_, etiqueta):
        r = client.chat.completions.create(
            model="deepseek-chat", messages=mensajes, tools=tools_, max_tokens=10)
        u = r.usage
        print(f"{etiqueta}: prompt={u.prompt_tokens} cache_hit={u.prompt_cache_hit_tokens} "
              f"miss={u.prompt_cache_miss_tokens}")

    llamada(tools, "1ª (esquemas fríos)")
    llamada(tools, "2ª (idéntica)")
    llamada(tools[:12], "3ª (subset variado)")
    llamada(tools, "4ª (completa de nuevo)")


if __name__ == "__main__":
    main()
