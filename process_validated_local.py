import os
import logging
import tempfile
import boto3
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.validation import make_valid
from dotenv import load_dotenv

# ================== CONFIG ENV ==================
load_dotenv()

BUCKET = os.getenv("BUCKET_NAME")
AWS_PROFILE = os.getenv("AWS_PROFIL")
AWS_REGION = os.getenv("AWS_REGION")

RAW = "raw/"
PROCESSED = "processed/"
OUT_MAP = "outputs/carte/"

FILES = {
    "palmiers": "basedadaptationgeneralemutwangamangina.geojson",
    "routes": "routes.geojson",
    "zones": "Zoneculture.geojson"
}

TARGET_CRS = "EPSG:32735"

# ================== LOG ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

# ================== S3 ==================
session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
s3 = session.client("s3")

def download(key, path):
    try:
        res = s3.list_objects_v2(Bucket=BUCKET, Prefix=key)
        if "Contents" not in res or not any(obj["Key"] == key for obj in res["Contents"]):
            logging.warning(f"⚠️ Fichier introuvable : s3://{BUCKET}/{key}")
            return False
        s3.download_file(BUCKET, key, path)
        logging.info(f"Téléchargé : {key}")
        return True
    except Exception as e:
        logging.error(f"Erreur téléchargement {key} : {e}")
        return False

def upload(path, key):
    try:
        s3.upload_file(path, BUCKET, key)
        logging.info(f"Upload OK : {key}")
    except Exception as e:
        logging.error(f"Erreur upload {key} : {e}")

# ================== VALIDATION ==================
def validate_geometry(path, name):
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logging.warning(f"{name} : CRS manquant → EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)

    # Valider les géométries
    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if not g.is_valid else g)
    gdf = gdf.to_crs(TARGET_CRS)
    
    # Supprimer les géométries vides ou invalides restantes
    gdf = gdf[gdf.geometry.notnull()]
    
    return gdf

# ================== CARTOGRAPHIE ==================
def plot_layer(gdf, name, out_path):
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Couleur simple selon type géométrie
    geom_type = gdf.geom_type.unique()
    if "Point" in geom_type:
        gdf.plot(ax=ax, color="darkgreen", markersize=6, alpha=0.7)
    elif "LineString" in geom_type or "MultiLineString" in geom_type:
        gdf.plot(ax=ax, color="red", linewidth=1.5)
    elif "Polygon" in geom_type or "MultiPolygon" in geom_type:
        gdf.plot(ax=ax, color="lightblue", edgecolor="black", alpha=0.5)
    else:
        gdf.plot(ax=ax, color="grey", edgecolor="black")
    
    ax.set_title(f"Carte : {name}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Coordonnées Est (m)")
    ax.set_ylabel("Coordonnées Nord (m)")
    ax.grid(True, linestyle="--", alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info(f"Carte générée pour {name} → {out_path}")

# ================== PIPELINE ==================
def run_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        local = {}
        for k, f in FILES.items():
            path = os.path.join(tmp, f)
            if not download(RAW + f, path):
                logging.warning(f"⚠️ Ignoré : {f}")
                continue

            gdf = validate_geometry(path, k)
            if gdf.empty:
                logging.warning(f"⚠️ {k} vide après validation. Ignoré.")
                continue

            # Sauvegarder GeoJSON validé localement et upload
            out_geojson = os.path.join(tmp, f"{k}_valid.geojson")
            gdf.to_file(out_geojson, driver="GeoJSON")
            upload(out_geojson, PROCESSED + f"{k}_valid.geojson")
            
            # Générer carte
            out_map = os.path.join(tmp, f"{k}_map.png")
            plot_layer(gdf, k, out_map)
            upload(out_map, OUT_MAP + f"{k}_map.png")
            
            logging.info(f"✅ {k} traité avec succès")
            print(f"✅ {k} traité avec succès, {len(gdf)} géométries valides")

# ================== RUN ==================
if __name__ == "__main__":
    run_pipeline()
