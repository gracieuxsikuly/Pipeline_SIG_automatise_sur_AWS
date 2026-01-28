import os
import json
import math
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import psycopg2
import psycopg2.extras
from shapely import wkb
from shapely.geometry import shape
from tqdm import tqdm
from dotenv import load_dotenv
import boto3
import ijson

# =============================
# CONFIG
# =============================
load_dotenv()

# S3
S3_BUCKET = os.getenv("BUCKET_NAME")
S3_KEY = "processed/basedadaptationgeneralemutwangamangina_valid.geojson"

# PostgreSQL
SCHEMA = "groupe2"
TABLE = "palmiers_v2"
CHUNK_SIZE = 20_000
SRID = 4326

PG_CONN = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", 5432),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# =============================
# UTIL
# =============================
def clean_json(obj):
    """Nettoie NaN / Inf et convertit Decimal pour JSON"""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

# =============================
# INSERT UTIL
# =============================
def insert_chunk(cur, rows):
    template = f"(ST_SetSRID(ST_GeomFromWKB(decode(%s,'hex')), {SRID}), %s::jsonb, %s)"
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO {SCHEMA}.{TABLE} (geom, properties, date_traitement) VALUES %s",
        rows,
        template=template,
        page_size=CHUNK_SIZE
    )

# =============================
# MAIN
# =============================
def main():
    # Vérification variables S3
    if not S3_BUCKET:
        raise ValueError("❌ La variable BUCKET_NAME n'est pas définie dans le .env !")
    if not S3_KEY:
        raise ValueError("❌ La variable S3_KEY n'est pas définie !")

    # Connexion S3
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
    body = obj['Body']

    # Connexion PostgreSQL
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()

    # Préparer table
    cur.execute(f"""
        DROP TABLE IF EXISTS {SCHEMA}.{TABLE};
        CREATE TABLE {SCHEMA}.{TABLE} (
            id BIGSERIAL PRIMARY KEY,
            geom geometry(GEOMETRY, {SRID}),
            properties JSONB,
            date_traitement TIMESTAMPTZ
        );
    """)
    conn.commit()
    print(f"✅ Table {SCHEMA}.{TABLE} prête")

    # Timestamp UTC
    traitement_date = datetime.now(timezone.utc).isoformat()

    # =============================
    # STREAMING PARSE DU GEOJSON
    # =============================
    rows = []
    count = 0
    features = ijson.items(body, "features.item")  # itérateur des features

    pbar = tqdm(desc="Chargement palmiers", unit="feat")

    for feature in features:
        geom = shape(feature["geometry"])
        props = clean_json(feature.get("properties", {}))
        geom_wkb = wkb.dumps(geom, hex=True)
        rows.append((
            geom_wkb,
            json.dumps(props, ensure_ascii=False),
            traitement_date
        ))
        count += 1
        pbar.update(1)

        # Insert en chunk
        if len(rows) >= CHUNK_SIZE:
            insert_chunk(cur, rows)
            conn.commit()
            rows = []

    # Insérer le dernier chunk
    if rows:
        insert_chunk(cur, rows)
        conn.commit()

    pbar.close()
    cur.close()
    conn.close()

    print(f"🔒 Connexion fermée, total features chargées: {count}")
    print("✅ Chargement terminé")

# =============================
# RUN
# =============================
if __name__ == "__main__":
    main()
