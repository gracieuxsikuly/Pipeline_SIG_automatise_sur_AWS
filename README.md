# creation de la varibale d'environnement
py -m venv env
# activation de la variable d'environnement
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
env\Scripts\activate.ps1
# installation de dependendace
pip install -r requirements.txt