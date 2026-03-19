#!/bin/bash
# Boot Brev NemoClaw instances for AgentsForImpact demo
set -e

INSTANCES=("nemoclaw-1" "nemoclaw-2")

for NAME in "${INSTANCES[@]}"; do
  echo "→ Creating $NAME..."
  brev create "$NAME" --provider gcp --min-disk 256 --type n1-standard-4

  echo "→ Setting up NemoClaw on $NAME..."
  brev run "$NAME" -- bash -c '
    curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | OPENSHELL_VERSION=v0.0.10 sh || true
    export PATH="$HOME/.local/bin:$PATH"
    curl -fsSL https://nvidia.com/nemoclaw.sh | bash
  '

  echo "✓ $NAME ready"
done

echo ""
echo "Connect with: brev shell nemoclaw-1"
