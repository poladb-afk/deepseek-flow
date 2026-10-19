#!/usr/bin/env bash
# Base de calidad de deepseek-flow: higiene (ruff) + complejidad de las
# fronteras + ratchet (métricas vs baseline) + funcional (pytest).
#
# El gate determinista — sin LLM, mismo comando ⇒ mismo resultado:
#   ./calidad.sh          → corre las cuatro palancas, exit 0 si TODO verde
#   (usarlo antes de commit; y como paso de CI: .github/workflows/calidad.yml)
set -u
cd "$(dirname "$0")"

fallo=0

echo "═══ 1/4 higiene — ruff check ═══"
if ruff check .; then
    echo "✅ higiene verde"
else
    echo "❌ higiene roja"
    fallo=1
fi

echo
echo "═══ 2/4 complejidad — C901 ≤ 12 en las fronteras de seguridad ═══"
# Solo las dos fronteras del PR 6 (shell y lectura de archivos): el resto del
# repo tiene funciones largas a propósito (evals.linter_traza, banco.correr…).
if ruff check --select C901 --config 'lint.mccabe.max-complexity=12' modules/coding.py utils/fs_tools.py; then
    echo "✅ complejidad verde"
else
    echo "❌ complejidad roja: una frontera volvió a crecer"
    fallo=1
fi

echo
echo "═══ 3/4 ratchet — las métricas no empeoran (baseline versionado) ═══"
# Mecanismo de git-agent-ratchet: helpers privados duplicados (baja = mejora) y
# tests definidos (sube = mejora) contra ratchets/baseline.json. La métrica puede
# mejorar o quedar igual; empeorar exige que el operador humano corra --actualizar.
if python3 ratchet.py; then
    echo "✅ ratchet verde"
else
    echo "❌ ratchet rojo: una métrica empeoró (o el baseline es un bypass)"
    fallo=1
fi

echo
echo "═══ 4/4 funcional — pytest ═══"
if python3 -m pytest tests/ -q; then
    echo "✅ funcional verde"
else
    echo "❌ funcional roja"
    fallo=1
fi

echo
if [ "$fallo" -eq 0 ]; then
    echo "✅ BASE DE CALIDAD VERDE"
else
    echo "❌ BASE DE CALIDAD ROJA"
fi
exit "$fallo"
