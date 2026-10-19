"""Utilidades compartidas extraídas del paydown de ruido (2026-10-19).

Tres helpers que vivían copiados en varias piezas de la CLI:

- `utils.git.sha_corto/sha_largo/sha_o_motivo`: ancla de informes y baselines
  (antes: 4 definiciones de `_git_sha` con dos semánticas distintas, y un
  import privado `from evals import _git_sha` en dos piezas).
- `utils.formato.pct`: formato de fracciones para markdown (antes: 4 copias
  de `_fmt_pct`, una con la unidad equivocada).
- `utils.trazas.leer_eventos`: parseo tolerante de `.jsonl` (antes: definido
  en evals + wrapper en replay + import privado en triaje/minar).
"""
import json

from utils import git as git_utils
from utils.formato import pct
from utils.trazas import leer_eventos

# formato

def test_pct_formatea_fraccion_y_admite_cero():
    assert pct(0.734) == "73.4%"
    assert pct(0) == "0.0%"
    assert pct(1) == "100.0%"


def test_pct_none_es_guion():
    assert pct(None) == "—"


# git

def test_sha_corto_y_largo_son_hex_del_repo():
    corto, largo = git_utils.sha_corto(), git_utils.sha_largo()
    assert corto and largo
    assert len(corto) < len(largo)
    assert largo.startswith(corto)


def test_sha_es_best_effort_si_git_no_esta(monkeypatch):
    """git no es dependencia: sin git, el informe sale igual."""
    def explotar(*args, **kwargs):
        raise OSError("git no está")

    monkeypatch.setattr(git_utils.subprocess, "run", explotar)
    assert git_utils.sha_corto() == ""
    assert git_utils.sha_largo() == ""
    assert git_utils.sha_o_motivo() == "(git no disponible: OSError)"


# trazas

def test_leer_eventos_linea_rota_descarta_el_archivo(tmp_path):
    """Contrato histórico: una traza corrupta es un artefacto a saltear."""
    ruta = tmp_path / "traza.jsonl"
    ruta.write_text('{"a": 1}\nno-es-json\n{"b": 2}\n', encoding="utf-8")
    assert leer_eventos(ruta) == []


def test_leer_eventos_archivo_inexistente_es_vacio(tmp_path):
    assert leer_eventos(tmp_path / "no-existe.jsonl") == []


def test_leer_eventos_jsonl_valido(tmp_path):
    ruta = tmp_path / "ok.jsonl"
    ruta.write_text(json.dumps({"nodo": "A"}) + "\n" + json.dumps({"nodo": "B"}) + "\n", encoding="utf-8")
    assert leer_eventos(ruta) == [{"nodo": "A"}, {"nodo": "B"}]
