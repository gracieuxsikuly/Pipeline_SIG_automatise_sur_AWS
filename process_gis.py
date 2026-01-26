import os
import sys
import boto3
import geopandas as gpd
from sqlalchemy import create_engine
from db import get_connection
from datetime import datetime

# ==========================
# Paramètres depuis la Lambda
# ==========================
if len(sys.argv) != 3:
    print("Usage: python load_s3_to_postgis.py <bucket> <key>")
    sys.exit(1)

BUCKET = sys.argv[1]
KEY = sys.argv[2]
SCHEMA = "groupe2"

# ==========================
# Téléchargement depuis S3
# ==========================
s3 = boto3.client("s3")

import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    local_file = os.path.join(tmpdir, os.path.basename(KEY))
    
    try:
        s3.download_file(BUCKET, KEY, local_file)
        print(f"✅ Fichier téléchargé depuis S3 : {local_file}")
    except Exception as e:
        print("❌ Erreur téléchargement S3 :", e)
        sys.exit(1)
    
    # ==========================
    # Lecture GeoDataFrame
    # ==========================
    try:
        gdf = gpd.read_file(local_file)
        print(f"✅ Fichier chargé en GeoDataFrame ({len(gdf)} lignes)")
    except Exception as e:
        print("❌ Erreur lecture GeoDataFrame :", e)
        sys.exit(1)
    
    # ==========================
    # Calcul surface_km2 si Polygone
    # ==========================
    if gdf.geom_type.isin(["Polygon", "MultiPolygon"]).any():
        # Reprojection en métrique pour calcul de surface (m²)
        if gdf.crs is None:
            print("⚠️ CRS inconnu, on suppose EPSG:4326")
            gdf = gdf.set_crs("EPSG:4326")
        
        gdf_metric = gdf.to_crs(epsg=3857)  # projection métrique pour surface
        gdf["surface_km2"] = gdf_metric["geometry"].area / 10**6  # m² → km²
        print("✅ Colonne surface_km2 ajoutée")
    
    else:
        print("ℹ️ Géométrie non polygonale, pas de surface calculée")
    
    # ==========================
    # Ajout de la date de traitement
    # ==========================
    gdf["date_traitement"] = datetime.now()
    print("✅ Colonne date_traitement ajoutée")
    
    # ==========================
    # Connexion à PostgreSQL/PostGIS
    # ==========================
    try:
        con = get_connection()
        print("✅ Connexion à la base établie")
        
        # Convertir psycopg2 connection en SQLAlchemy engine
        engine = create_engine(
            f"postgresql+psycopg2://{con.info.user}:{con.info.password}@{con.info.host}:{con.info.port}/{con.info.dbname}"
        )
        
        # ==========================
        # Création / insertion table
        # ==========================
        table_name = os.path.splitext(os.path.basename(KEY))[0].lower()
        print(f"📂 Insertion dans la table '{SCHEMA}.{table_name}'")
        
        gdf.to_postgis(
            name=table_name,
            con=engine,
            schema=SCHEMA,
            if_exists="replace",
            index=False
        )
        
        print(f"✅ Table '{SCHEMA}.{table_name}' créée et données insérées ({len(gdf)} lignes)")
    
    except Exception as e:
        print("❌ Erreur base de données :", e)
        sys.exit(1)
    
    finally:
        if con:
            con.close()
            print("🔒 Connexion fermée")
