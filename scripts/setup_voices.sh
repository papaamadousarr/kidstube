#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICES_DIR="$SCRIPT_DIR/../pipeline/assets/voices"
mkdir -p "$VOICES_DIR"

BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

download_voice() {
  local lang_dir="$1" voice_name="$2"
  local remote="$BASE_URL/fr/fr_FR/$lang_dir/medium"
  echo "Téléchargement de $voice_name..."
  curl -L -o "$VOICES_DIR/$voice_name.onnx" "$remote/$voice_name.onnx"
  curl -L -o "$VOICES_DIR/$voice_name.onnx.json" "$remote/$voice_name.onnx.json"
}

download_voice "siwis" "fr_FR-siwis-medium"
download_voice "upmc" "fr_FR-upmc-medium"

echo "Voix téléchargées dans $VOICES_DIR"
echo "Licences : vérifier le fichier MODEL_CARD associé à chaque voix sur"
echo "https://huggingface.co/rhasspy/piper-voices avant publication (attribution requise pour siwis, CC BY 4.0)."
