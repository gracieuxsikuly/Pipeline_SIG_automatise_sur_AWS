# run_upload.ps1
# Autoriser l'exécution temporaire pour ce script
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# Aller dans le dossier du projet
cd "D:\python_Exercice\datalake_gis_1\Pipeline_SIG_automatise_sur_AWS\groupe_2"
# Activer l'environnement virtuel
.\env\Scripts\Activate.ps1
# Exécuter le script Python
python uploadfile.py
