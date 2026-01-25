@echo off
REM Aller dans le dossier du projet
cd /d "D:\python_Exercice\datalake_gis_1\Pipeline_SIG_automatise_sur_AWS\groupe_2"

REM Activer l'environnement virtuel
call env\Scripts\activate.bat

REM Exécuter le script Python et écrire le log
python uploadfilemanifest.py >> upload.log 2>&1
