"""Módulo `vision`: el agente MIRA imágenes y LEE PDFs.

Dos capacidades con dos caminos distintos por una razón medida:

- `ver_imagen(path, pregunta)` manda la imagen como **data-URL base64**
  dentro de un message de USER con `content=[{type:text},{type:image_url}]`.
  El mensaje system/assistant NO puede llevar imágenes: la API responde
  400 (medido). Por eso la imagen viaja en un turno de usuario aislado
  —NO se inyecta en el historial del chat, que arrastraría la imagen en
  cada vuelta siguiente y rompería el contrato—. La llamada es `call_llm`
  (contenido como array), SIN el `extra_body` de thinking: `call_llm_agent`
  agrega thinking y tools, y eso no aplica acá.

  El tipo se valida por CONTENIDO (magic bytes), no por extensión: un
  `.png` que en realidad es un JPEG se acepta como JPEG, y un archivo de
  texto con nombre `.png` se rechaza. Límites: imagen 32 MiB y body
  48 MiB (la imagen crece ~33% al base64) — se chequea ANTES de llamar y
  se devuelve ERROR legible.

- `ver_pdf(path, pregunta)` rasteriza con pdftoppm (poppler) y pregunta
  por visión. Medido: la Files API NO acepta PDFs (solo imágenes, HTTP 400
  'unsupported file'), así que PDF → PNG por página → imágenes al modelo
  (1024 tokens c/u, tope de páginas). Sin estado: rasteriza en /tmp,
  consulta y borra.

Sin dependencias nuevas: `requests` (ya presente). API key/base de los
settings existentes (`LLM_API_KEY`/`LLM_BASE_URL`)."""
import base64
import mimetypes
from pathlib import Path

import requests

from utils.call_llm import _setting, get_api_key
from utils.fs_tools import _resolve

# Límites (se chequean ANTES de llamar; el error es texto, no un crash)
IMAGEN_MAX_BYTES = 32 * 1024 * 1024   # 32 MiB
BODY_MAX_BYTES = 48 * 1024 * 1024     # 48 MiB (base64 crece ~4/3)
PDF_MAX_BYTES = 64 * 1024 * 1024      # 64 MiB vía Files API (file_id)
TIMEOUT_S = 120

# Firma por contenido → MIME real (la extensión NO decide).
# JPEG arranca con FF D8 FF; PNG con los 8 bytes fijos; GIF con GIF87a/GIF89a;
# WebP con RIFF....WEBP (los 4 bytes del formato en offset 8).
MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _mime_por_contenido(data):
    """Devuelve el MIME de imagen según los magic bytes, o None si no es
    una imagen soportada. El nombre del archivo se ignora a propósito."""
    for firma, mime in MAGIC:
        if data.startswith(firma):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _api_base():
    return _setting("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")


def _leer_bytes(path, max_bytes, etiqueta):
    """(data, mime, error): resuelve dentro de los directorios permitidos,
    verifica existencia y tamaño. Devuelve error legible como texto."""
    resolved, err = _resolve(path)
    if err:
        return None, None, f"ERROR: {err}"
    if not resolved.exists():
        return None, None, f"ERROR: no existe: {resolved}"
    if not resolved.is_file():
        return None, None, f"ERROR: no es un archivo regular: {resolved}"
    try:
        size = resolved.stat().st_size
    except OSError as e:
        return None, None, f"ERROR: no se pudo leer el tamaño: {e}"
    if size > max_bytes:
        return None, None, (
            f"ERROR: el archivo pesa {size / (1024 * 1024):.1f} MiB y el "
            f"tope para {etiqueta} es {max_bytes / (1024 * 1024):.0f} MiB. "
            "Achicá el archivo (o extraé lo necesario) antes de reintentar."
        )
    try:
        data = resolved.read_bytes()
    except OSError as e:
        return None, None, f"ERROR: no se pudo leer: {e}"
    return resolved, data, None


def ver_imagen(path, pregunta="¿Qué hay en esta imagen?"):
    """Manda una imagen local al LLM como data-URL base64 y devuelve su
    respuesta. Solo imágenes JPEG/PNG/GIF/WebP (validadas por contenido)."""
    resolved, data, err = _leer_bytes(path, IMAGEN_MAX_BYTES, "una imagen")
    if err:
        return err

    mime = _mime_por_contenido(data)
    if mime is None:
        return (
            f"ERROR: {resolved.name} no es una imagen soportada (JPEG/PNG/GIF/WebP). "
            "El tipo se valida por el contenido del archivo, no por el nombre."
        )

    b64 = base64.b64encode(data).decode("ascii")
    if len(b64) > BODY_MAX_BYTES:
        return (
            f"ERROR: la imagen codificada en base64 ocupa {len(b64) / (1024 * 1024):.1f} MiB "
            f"y supera el tope de body de {BODY_MAX_BYTES / (1024 * 1024):.0f} MiB. Achicá la imagen."
        )

    data_url = f"data:{mime};base64,{b64}"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": str(pregunta)},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    try:
        response = requests.post(
            f"{_api_base()}/chat/completions",
            headers={"Authorization": f"Bearer {get_api_key()}"},
            json={"model": _model(), "messages": messages},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        return f"ERROR: falló la llamada al modelo: {e}"
    if response.status_code != 200:
        return f"ERROR: la API respondió {response.status_code}: {response.text[:400]}"
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        return f"ERROR: respuesta inesperada de la API: {e}"


PDF_PAGINAS_MAX = 8  # cada página es una imagen: 1024 tokens c/u (medido)


def ver_pdf(path, pregunta="¿Qué dice este PDF?"):
    """Pregunta sobre un PDF rasterizando páginas y usándo visión.

    Medido en producción: la Files API de DeepSeek NO acepta PDFs (solo
    webp/png/jpeg/gif — HTTP 400 'unsupported file'); el propósito
    user_data sí, pero el formato no. La ruta que funciona: pdftoppm
    (poppler, presente en el sistema) rasteriza a PNG y cada página va
    como imagen al modelo (1024 tokens c/u — por eso el tope de páginas).

    Sin estado: rasteriza en /tmp, consulta y borra."""
    resolved, data, err = _leer_bytes(path, PDF_MAX_BYTES, "un PDF")
    if err:
        return err
    if not data.startswith(b"%PDF"):
        return (
            f"ERROR: {resolved.name} no es un PDF (no empieza con la firma %PDF). "
            "El tipo se valida por el contenido del archivo."
        )

    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vision_pdf_") as tmp:
        base = str(Path(tmp) / "pag")
        try:
            r = subprocess.run(
                ["pdftoppm", "-png", "-r", "110", str(resolved), base],
                capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return "ERROR: pdftoppm (poppler) no está instalado en este sistema — no puedo rasterizar el PDF."
        except subprocess.TimeoutExpired:
            return "ERROR: timeout rasterizando el PDF (¿demasiadas páginas?)"
        if r.returncode != 0:
            return f"ERROR: pdftoppm falló: {(r.stderr or r.stdout).strip()[:300]}"

        paginas = sorted(Path(tmp).glob("pag-*.png"))
        if not paginas:
            return "ERROR: la rasterización no produjo páginas."
        if len(paginas) > PDF_PAGINAS_MAX:
            return (
                f"ERROR: el PDF tiene {len(paginas)} páginas y el tope es "
                f"{PDF_PAGINAS_MAX} (cada página cuesta ~1024 tokens de imagen). "
                "Extraé las páginas relevantes y reintentá."
            )

        contenido = [{"type": "text", "text": (
            f"{str(pregunta)}\n\nEl PDF tiene {len(paginas)} páginas, "
            "van en orden.")} ]
        for pag in paginas:
            b64 = base64.b64encode(pag.read_bytes()).decode("ascii")
            contenido.append({"type": "image_url",
                              "image_url": {"url": f"data:image/png;base64,{b64}"}})
        messages = [{"role": "user", "content": contenido}]

    try:
        response = requests.post(
            f"{_api_base()}/chat/completions",
            headers={"Authorization": f"Bearer {get_api_key()}"},
            json={"model": _model(), "messages": messages},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        return f"ERROR: falló la consulta del PDF: {e}"
    if response.status_code != 200:
        return f"ERROR: la API respondió {response.status_code}: {response.text[:400]}"
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        return f"ERROR: respuesta inesperada de la API: {e}"


def _model():
    return _setting("LLM_MODEL", "deepseek-flash")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ver_imagen",
            "description": (
                "Mira una imagen local (JPEG, PNG, GIF o WebP) y responde la pregunta sobre "
                "ella. El tipo se valida por el contenido del archivo. Límite de 32 MiB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a una imagen en un directorio permitido"},
                    "pregunta": {"type": "string", "description": "Qué querés saber de la imagen (default: describirla)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_pdf",
            "description": (
                "Lee y responde sobre un PDF local vía la Files API (hasta 64 MiB). Útil para "
                "extraer datos de documentos (facturas, informes) que read_file no puede leer por binarios."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a un PDF en un directorio permitido"},
                    "pregunta": {"type": "string", "description": "Qué querés extraer o saber del PDF"},
                },
                "required": ["path"],
            },
        },
    },
]


IMPL = {"ver_imagen": ver_imagen, "ver_pdf": ver_pdf}