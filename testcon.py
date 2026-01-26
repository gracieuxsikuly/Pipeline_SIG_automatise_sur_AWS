import os
import geopandas as gpd
from sqlalchemy import create_engine
from db import get_connection  # ta fonction existante

SCHEMA = "groupe2"

# ==========================
# Chemin local du fichier à tester
# ==========================
local_file = "data/routes.geojson"

if not os.path.exists(local_file):
    print(f"❌ Fichier {local_file} introuvable")
    exit(1)

# ==========================
# Lecture GeoDataFrame
# ==========================
try:
    gdf = gpd.read_file(local_file)
    print(f"✅ Fichier chargé en GeoDataFrame ({len(gdf)} lignes)")
except Exception as e:
    print("❌ Erreur lecture GeoDataFrame :", e)
    exit(1)

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
    table_name = "routes"  # pour tester, on fixe le nom de table
    print(f"📂 Insertion dans la table '{SCHEMA}.{table_name}'")

    gdf.to_postgis(
        name=table_name,
        con=engine,
        schema=SCHEMA,
        if_exists="replace",  # remplace la table si elle existe
        index=False
    )

    print(f"✅ Table '{SCHEMA}.{table_name}' créée et données insérées ({len(gdf)} lignes)")

except Exception as e:
    print("❌ Erreur base de données :", e)
    exit(1)

finally:
    if con:
        con.close()
        print("🔒 Connexion fermée")
