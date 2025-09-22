#!/usr/bin/env bash
set -euo pipefail

# Skript pre vyčistenie pracovného adresára projektu od dočasných súborov.
#
# Čo robí:
# - zmaže koreňové adresáre: .mypy_cache, .pytest_cache, .ruff_cache
# - vyprázdni obsah všetkých adresárov s názvom __pycache__ v celom projekte
# - zmaže súbor .env v koreňovom adresári projektu
#
# Pozn.: Skript nemení git históriu a nespúšťa žiadne git príkazy.

# Nájdeme koreň projektu podľa umiestnenia skriptu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "[clear] Projektový koreň: ${REPO_ROOT}"

# 1) Vymazanie hlavných cache adresárov v koreňi
for CACHE_DIR in .mypy_cache .pytest_cache .ruff_cache; do
  if [ -d "${CACHE_DIR}" ]; then
    echo "[clear] Mažem ${CACHE_DIR}"
    rm -rf "${CACHE_DIR}"
  else
    echo "[clear] Preskakujem ${CACHE_DIR} (neexistuje)"
  fi
done

# 2) Vyprázdniť obsah všetkých __pycache__ adresárov (ponechať prázdne adresáre)
echo "[clear] Vyprázdňujem obsah všetkých __pycache__ adresárov"
while IFS= read -r -d '' PYCACHE_DIR; do
  rm -rf "${PYCACHE_DIR}"/* "${PYCACHE_DIR}"/.[!.]* "${PYCACHE_DIR}"/..?* 2>/dev/null || true
  echo "[clear] Vyprázdnené: ${PYCACHE_DIR}"
done < <(find "${REPO_ROOT}" -type d -name "__pycache__" -print0 || true)

# 3) Zmazať .env v koreňi projektu
if [ -f .env ]; then
  echo "[clear] Mažem .env"
  rm -f .env
else
  echo "[clear] Preskakujem .env (neexistuje)"
fi

echo "[clear] Hotovo."


