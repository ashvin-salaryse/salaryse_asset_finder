#!/usr/bin/env bash
# Regenerate the asset gallery from the app's app_images.dart.
#   1. fingerprints + thumbnails + lottie signatures (needs Google Chrome)
#   2. builds the self-contained asset_gallery.html
#
# Point SALARYSE_APP at your salary_se_app checkout if it isn't the default:
#   SALARYSE_APP=/path/to/salary_se_app ./refresh.sh
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv 2>/dev/null || true
./venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

./venv/bin/python precompute_hashes.py
./venv/bin/python build_gallery.py

echo ""
echo "Done. Open the gallery:"
echo "  open asset_gallery.html"
