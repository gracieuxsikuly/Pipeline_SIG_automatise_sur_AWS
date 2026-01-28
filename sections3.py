import os
import boto3
import geopandas as gpd
from sqlalchemy import create_engine
from datetime import datetime
from db import get_connection
from dotenv import load_dotenv
from io import BytesIO

# Config
S3_KEY = "processed/basedadaptationgeneralemutwangamangina_valid.geojson"
SCHEMA = "groupe2"
TABLE_NAME = "palmiers"

load_dotenv()

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

con = None
try:
    # 🔌 Connexion PostgreSQL
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
    gdf.to_postgis(
        name=TABLE_NAME,
        con=engine,
        schema=SCHEMA,
        if_exists="replace",
        index=False
    )

    print(f"✅ Données chargées dans {SCHEMA}.{TABLE_NAME}")

except Exception as e:
    raise RuntimeError(f"❌ Erreur base de données : {e}")

finally:
    if con:
        con.close()
        print("🔒 Connexion fermée")
