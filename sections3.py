import os
import boto3
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
from db import get_connection
from dotenv import load_dotenv
from io import BytesIO
import shutil
from shapely.validation import make_valid
from shapely.geometry import shape

# Config
S3_KEY = "processed/basedadaptationgeneralemutwangamangina_valid.geojson"
SCHEMA = "groupe2"
TABLE_NAME = "palmiers"
LOCAL_DATA_DIR = "data"
LOCAL_FILE_PATH = f"{LOCAL_DATA_DIR}/{TABLE_NAME}.geojson"

load_dotenv()

# Création du dossier data s'il n'existe pas
os.makedirs(LOCAL_DATA_DIR, exist_ok=True)

# Initialisation du client S3
s3 = boto3.client("s3")

try:
    # 📥 Lecture directe depuis S3 (sans téléchargement)
    response = s3.get_object(
        Bucket=os.getenv("BUCKET_NAME"),
        Key=S3_KEY
    )

    geojson_bytes = response["Body"].read()
    geojson_buffer = BytesIO(geojson_bytes)

    print("✅ Fichier GeoJSON lu depuis S3 (en mémoire)")

except Exception as e:
    raise RuntimeError(f"❌ Erreur lecture S3 : {e}")

try:
    # 📍 Chargement GeoDataFrame depuis le buffer mémoire
    gdf = gpd.read_file(geojson_buffer)
    print(f"✅ GeoDataFrame chargé ({len(gdf)} lignes)")

except Exception as e:
    raise RuntimeError(f"❌ Erreur lecture GeoDataFrame : {e}")

# Ajout métadonnée
gdf["date_traitement"] = datetime.utcnow()

# 🔍 Étape 1: Vérification des géométries
print("🔍 Vérification des géométries...")
initial_count = len(gdf)

# Vérifier si la colonne de géométrie existe
if gdf.geometry.name not in gdf.columns:
    raise ValueError(f"❌ Colonne de géométrie '{gdf.geometry.name}' non trouvée dans le GeoDataFrame")

# Identifier les géométries invalides
invalid_geometries = ~gdf.geometry.is_valid
invalid_count = invalid_geometries.sum()

if invalid_count > 0:
    print(f"⚠️  {invalid_count} géométries invalides trouvées")
    
    # Option 1: Corriger les géométries invalides
    print("🛠️  Correction des géométries invalides...")
    
    # Créer une copie pour éviter les avertissements
    corrected_gdf = gdf.copy()
    
    # Corriger uniquement les géométries invalides
    mask_invalid = corrected_gdf.geometry.is_valid == False
    corrected_gdf.loc[mask_invalid, 'geometry'] = corrected_gdf.loc[mask_invalid, 'geometry'].apply(
        lambda geom: make_valid(geom) if geom is not None else geom
    )
    
    # Vérifier après correction
    still_invalid = ~corrected_gdf.geometry.is_valid
    if still_invalid.sum() > 0:
        print(f"⚠️  {still_invalid.sum()} géométries toujours invalides après correction - elles seront exclues")
        corrected_gdf = corrected_gdf[~still_invalid]
    
    gdf = corrected_gdf

print(f"✅ Géométries validées : {len(gdf)}/{initial_count} lignes restantes")

# 🔍 Étape 2: Élimination des doublons par géométrie
print("🔍 Recherche et élimination des doublons par géométrie...")

# Méthode améliorée avec tolérance
print("   Méthode: equals_exact avec tolérance de 0.01 mètres")

# Créer une liste pour stocker les indices à garder
indices_to_keep = []
seen_geometries = []
duplicate_geometries = []  # Pour stocker les géométries en double détectées

# Tolérance en mètres (vos données semblent être en mètres, pas en degrés)
tolerance = 0.01  # 1 cm de tolérance

for idx, row in gdf.iterrows():
    current_geom = row.geometry
    
    if current_geom is None:
        # Si la géométrie est None, on la garde quand même
        indices_to_keep.append(idx)
        continue
    
    # Vérifier si cette géométrie est déjà vue
    is_duplicate = False
    matching_geom = None
    
    for seen_geom in seen_geometries:
        if seen_geom is not None:
            try:
                if current_geom.equals_exact(seen_geom, tolerance):
                    is_duplicate = True
                    matching_geom = seen_geom
                    break
            except:
                # Si equals_exact échoue, essayer avec equals
                try:
                    if current_geom.equals(seen_geom):
                        is_duplicate = True
                        matching_geom = seen_geom
                        break
                except:
                    continue
    
    if not is_duplicate:
        indices_to_keep.append(idx)
        seen_geometries.append(current_geom)
    else:
        duplicate_geometries.append((current_geom, matching_geom))

# Créer un nouveau GeoDataFrame sans doublons
gdf_clean = gdf.loc[indices_to_keep].copy()
duplicate_count = len(gdf) - len(gdf_clean)

if duplicate_count > 0:
    print(f"⚠️  {duplicate_count} doublons identifiés (géométries identiques)")
    
    # Afficher quelques exemples de doublons trouvés
    if duplicate_geometries:
        print(f"   Exemples de géométries en double :")
        for i, (dup_geom, orig_geom) in enumerate(duplicate_geometries[:3]):  # Montrer les 3 premiers doublons
            if hasattr(dup_geom, 'geom_type'):
                if dup_geom.geom_type == 'Point':
                    print(f"     - Point doublon à ({dup_geom.x:.3f}, {dup_geom.y:.3f})")
                    print(f"       Original à     ({orig_geom.x:.3f}, {orig_geom.y:.3f})")
                else:
                    print(f"     - {dup_geom.geom_type} (centre: {dup_geom.centroid.x:.3f}, {dup_geom.centroid.y:.3f})")
    
    print(f"✅ Doublons éliminés : {len(gdf_clean)}/{len(gdf)} géométries uniques")
    gdf = gdf_clean
else:
    print("✅ Aucun doublon géométrique trouvé")
    
    # Afficher quelques géométries uniques
    print(f"   Exemples de géométries uniques :")
    for i, geom in enumerate(seen_geometries[:3]):
        if hasattr(geom, 'geom_type'):
            if geom.geom_type == 'Point':
                print(f"     - Point à ({geom.x:.3f}, {geom.y:.3f})")
            else:
                print(f"     - {geom.geom_type} (centre: {geom.centroid.x:.3f}, {geom.centroid.y:.3f})")

# 💾 Étape 3: Sauvegarde locale
print("💾 Sauvegarde locale du fichier nettoyé...")
try:
    # Sauvegarder en GeoJSON
    gdf.to_file(LOCAL_FILE_PATH, driver='GeoJSON')
    print(f"✅ Fichier sauvegardé localement : {LOCAL_FILE_PATH}")
    
    # Option: Sauvegarder aussi en Shapefile
    # shp_path = f"{LOCAL_DATA_DIR}/{TABLE_NAME}.shp"
    # gdf.to_file(shp_path)
    # print(f"✅ Fichier sauvegardé localement (SHP) : {shp_path}")
    
except Exception as e:
    print(f"⚠️  Erreur lors de la sauvegarde locale : {e}")
    print("⏭️  Continuation sans sauvegarde locale...")

con = None
try:
    # 🔌 Connexion PostgreSQL
    print("🔌 Connexion à PostgreSQL...")
    con = get_connection()
    print("✅ Connexion PostgreSQL établie")

    engine = create_engine(
        f"postgresql+psycopg2://{con.info.user}:"
        f"{con.info.password}@"
        f"{con.info.host}:"
        f"{con.info.port}/"
        f"{con.info.dbname}"
    )

    # 🗄️ Insertion PostGIS
    print(f"🗄️  Insertion dans {SCHEMA}.{TABLE_NAME}...")
    gdf.to_postgis(
        name=TABLE_NAME,
        con=engine,
        schema=SCHEMA,
        if_exists="replace",
        index=False
    )

    print(f"✅ Données nettoyées chargées dans {SCHEMA}.{TABLE_NAME}")
    print(f"📊 Statistiques finales :")
    print(f"   - Lignes initiales : {initial_count}")
    print(f"   - Géométries invalides : {invalid_count}")
    print(f"   - Doublons géométriques : {duplicate_count}")
    print(f"   - Lignes finales : {len(gdf)}")
    print(f"   - Pourcentage de réduction : {((initial_count - len(gdf)) / initial_count * 100):.1f}%")

except Exception as e:
    raise RuntimeError(f"❌ Erreur base de données : {e}")

finally:
    if con:
        con.close()
        print("🔒 Connexion PostgreSQL fermée")

print("✨ Traitement terminé avec succès!")