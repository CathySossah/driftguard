"""
Chargeur minimal du fichier backend/.env (sans dépendance supplémentaire).

Pratique en local : on écrit une fois les variables (clé Brevo, adresse expéditrice...) dans
backend/.env au lieu de les retaper à chaque lancement du serveur. Les variables déjà définies dans
l'environnement (Render, terminal...) sont prioritaires et ne sont jamais écrasées.
Format : une ligne CLE=valeur ; les lignes vides et celles qui commencent par # sont ignorées.
Ce fichier ne doit JAMAIS être envoyé sur GitHub (il est dans .gitignore).
"""
import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> dict[str, str]:
    path = path or Path(__file__).resolve().parent.parent / ".env"
    loaded: dict[str, str] = {}
    if os.getenv("DRIFTGUARD_NO_DOTENV") or not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
