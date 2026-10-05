#!/usr/bin/env bash
# Deja el harness entero andando en una clonación nueva: baja los dos
# checkpoints de Laya desde la release del repo (GitHub, público), verifica
# el sha256 y los instala en .modelos/. Sin ellos el harness funciona igual
# (todo cae al lado DeepSeek); con ellos vuelven los ifs locales.
set -euo pipefail
cd "$(dirname "$0")"

URL=https://github.com/poladb-afk/deepseek-flow/releases/download/laya-v1/laya-checkpoints.tar.gz
SHA=441c2715264b978b3352c333147e7b04c3fd668f12189aa36e49352f223a3915
DEST=/tmp/laya-checkpoints.tar.gz

echo "→ bajando $URL (1.2 GB)…"
curl -L --fail --progress-bar -o "$DEST" "$URL"
echo "$SHA  $DEST" | sha256sum -c -

mkdir -p .modelos
tar -xzf "$DEST" -C .modelos
rm "$DEST"
echo "✓ checkpoints: .modelos/router_flow-1k y .modelos/supervisor_dispatch-1k"

if [ ! -f .env ]; then
    cp .env.example .env
    printf '\nLAYA_MODEL=%s/.modelos/router_flow-1k\nLAYA_MODEL_SUPERVISOR=%s/.modelos/supervisor_dispatch-1k\n' "$PWD" "$PWD" >> .env
    echo "✓ .env creado con los checkpoints (falta la API: export DEEPSEEK_API_KEY=sk-…)"
fi
echo "✓ listo: python3 main.py"
