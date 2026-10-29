"""El comparador del A/B de la fase 3, con datos sintéticos (sin red)."""
import json

import pytest

from banco.probes import comparar_fase3 as cf


def _brazo(tmp_path, nombre, filas, usos):
    """filas: [(escenario, ca)]; usos: por corrida, [(prompt, hit, completion)]."""
    res = tmp_path / f"{nombre}.jsonl"
    res.write_text("".join(json.dumps({"escenario": e, "correct_action": ca}) + "\n" for e, ca in filas),
                   encoding="utf-8")
    runs = tmp_path / f"runs_{nombre}"
    runs.mkdir()
    for i, llamadas in enumerate(usos):
        eventos = [{"nodo": "GetQuestion", "accion": "continue"}]
        eventos += [{"nodo": "llm", "accion": "usage", "prompt_tokens": p, "cache_hit": h,
                     "completion_tokens": c} for p, h, c in llamadas]
        (runs / f"2026_{i:03d}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in eventos),
                                                  encoding="utf-8")
    (runs / "2026_999.jsonl").write_text(json.dumps({"nodo": "Sintetizar", "accion": "None"}) + "\n",
                                         encoding="utf-8")  # traza que no es de chat: se ignora
    return str(res), str(runs)


ESC = ["s17-scale-audit", "s18-real-audit", "s19-real-audit-2"]


def test_pasa_cuando_s17_s18_suben_y_el_costo_entra(tmp_path, capsys):
    base = _brazo(tmp_path, "a", [(e, 1) for e in ESC], [[(1_000_000, 0, 0)]] * 3)
    # 50k de completion: 0,15 → 0,18 USD (1,2×), dentro de la tolerancia
    pensar = _brazo(tmp_path, "e", [(ESC[0], 2), (ESC[1], 2), (ESC[2], 1)], [[(1_000_000, 0, 50_000)]] * 3)
    assert cf.main(["--base", base[0], "--runs-base", base[1],
                    "--pensar", pensar[0], "--runs-pensar", pensar[1]]) == 0
    assert "FASE 3a: PASA" in capsys.readouterr().out


@pytest.mark.parametrize(("pensar_ca", "completion", "motivo"), [
    ([1, 1, 1], 0, "s17+s18 suben 0"),            # sin ganancia no entra
    ([2, 2, 0], 0, "la calidad baja"),            # s19 empeora
    ([2, 2, 1], 2_000_000, "USD"),                # 0,15 → 1,35 USD: 9×
])
def test_no_pasa_y_dice_por_que(tmp_path, capsys, pensar_ca, completion, motivo):
    base = _brazo(tmp_path, "a", [(e, 1) for e in ESC], [[(1_000_000, 0, 0)]] * 3)
    pensar = _brazo(tmp_path, "e", list(zip(ESC, pensar_ca, strict=True)), [[(1_000_000, 0, completion)]] * 3)
    assert cf.main(["--base", base[0], "--runs-base", base[1],
                    "--pensar", pensar[0], "--runs-pensar", pensar[1]]) == 1
    salida = capsys.readouterr().out
    assert motivo in salida and "NO PASA" in salida


def test_el_cache_hit_abarata_y_sin_dato_cuenta_como_miss():
    tarifa = (0.003, 0.15, 0.60)
    con_hit = cf.usd([{"accion": "usage", "prompt_tokens": 1_000_000, "cache_hit": 1_000_000}], tarifa)
    sin_dato = cf.usd([{"accion": "usage", "prompt_tokens": 1_000_000}], tarifa)
    assert con_hit == pytest.approx(0.003) and sin_dato == pytest.approx(0.15)


def test_se_niega_si_resultados_y_trazas_no_se_emparejan(tmp_path):
    res, runs = _brazo(tmp_path, "a", [(e, 1) for e in ESC], [[(10, 0, 0)]] * 2)
    with pytest.raises(ValueError, match="no se emparejan"):
        cf.por_escenario(cf.resultados(res), cf.trazas_de_chat(runs), (0.003, 0.15, 0.60))
