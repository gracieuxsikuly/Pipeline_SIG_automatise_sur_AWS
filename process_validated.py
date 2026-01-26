import sys
import os
import logging
import tempfile
import boto3
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.validation import make_valid
from dotenv import load_dotenv
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

# ================== ARGUMENTS ==================
if len(sys.argv) != 3:
    print("Usage: python process_validated.py <BUCKET> <KEY>")
    sys.exit(1)

BUCKET = sys.argv[1]
S3_KEY = sys.argv[2]

print(f"🚀 Traitement pour s3://{BUCKET}/{S3_KEY}")

# ================== CONFIG ==================
load_dotenv()

PROCESSED_PREFIX = "processed/"
OUT_MAP_PREFIX = "outputs/carte/"
TARGET_CRS = "EPSG:32735"

# ================== LOG ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

# ================== AWS CLIENT ==================
s3 = boto3.client("s3")

# ================== S3 HELPERS ==================
def download_file(bucket, key, local_path):
    try:
        s3.download_file(bucket, key, local_path)
        logging.info(f"📥 Téléchargé : s3://{bucket}/{key}")
        return True
    except Exception as e:
        logging.error(f"❌ Erreur téléchargement {key} : {e}")
        return False

def upload_file(local_path, bucket, key):
    try:
        s3.upload_file(local_path, bucket, key)
        logging.info(f"📤 Upload OK : s3://{bucket}/{key}")
    except Exception as e:
        logging.error(f"❌ Erreur upload {key} : {e}")

# ================== SIG ==================
def validate_geometry(path, name):
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logging.warning(f"{name} : CRS manquant → EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)

    gdf["geometry"] = gdf.geometry.apply(
        lambda g: make_valid(g) if g and not g.is_valid else g
    )

    gdf = gdf[gdf.geometry.notnull()]
    gdf = gdf.to_crs(TARGET_CRS)

    logging.info(f"✔️ {len(gdf)} géométries valides")
    return gdf

def plot_layer(gdf, title, out_path):
    fig, ax = plt.subplots(figsize=(10, 10))

    geom_types = gdf.geom_type.unique()

    if "Point" in geom_types:
        gdf.plot(ax=ax, color="darkgreen", markersize=6, alpha=0.7)
    elif "LineString" in geom_types or "MultiLineString" in geom_types:
        gdf.plot(ax=ax, color="red", linewidth=1.5)
    elif "Polygon" in geom_types or "MultiPolygon" in geom_types:
        gdf.plot(ax=ax, color="lightblue", edgecolor="black", alpha=0.5)
    else:
        gdf.plot(ax=ax, color="grey")

    ax.set_title(f"Carte : {title}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Coordonnées Est (m)")
    ax.set_ylabel("Coordonnées Nord (m)")
    ax.grid(True, linestyle="--", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    logging.info(f"🗺️ Carte générée : {out_path}")

# ================== PIPELINE ==================
def run_pipeline(bucket, key):
    filename = os.path.splitext(os.path.basename(key))[0]

    with tempfile.TemporaryDirectory() as tmp:
        local_input = os.path.join(tmp, os.path.basename(key))

        if not download_file(bucket, key, local_input):
            return

        gdf = validate_geometry(local_input, os.path.basename(key))
        if gdf.empty:
            logging.warning("⚠️ Fichier vide après validation")
            return

        # ---- EXPORT GEOJSON ----
        geojson_local = os.path.join(tmp, f"{filename}_valid.geojson")
        gdf.to_file(geojson_local, driver="GeoJSON")

        upload_file(
            geojson_local,
            bucket,
            f"{PROCESSED_PREFIX}{filename}_valid.geojson"
        )

        # ---- EXPORT MAP ----
        map_local = os.path.join(tmp, f"{filename}_map.png")
        plot_layer(gdf, filename, map_local)

        upload_file(
            map_local,
            bucket,
            f"{OUT_MAP_PREFIX}{filename}_map.png"
        )

        print(f"✅ Traitement terminé : {len(gdf)} géométries valides")

# ================== RUN ==================
if __name__ == "__main__":
    run_pipeline(BUCKET, S3_KEY)
