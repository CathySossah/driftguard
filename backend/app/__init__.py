# Charge backend/.env (s'il existe) avant que les autres modules lisent l'environnement.
from app.env_loader import load_env_file

load_env_file()
