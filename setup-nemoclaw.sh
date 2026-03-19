#!/bin/bash
# Run on remote Brev instance to set up NemoClaw
export PATH="$HOME/.local/bin:$PATH"
curl -fsSL https://nvidia.com/nemoclaw.sh | bash
