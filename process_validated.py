import sys
import os
import logging
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

# ================== CONFIG ENV ==================
load_dotenv()

PROCESSED = "processed/"
OUT_MAP = "outputs/carte/"
TARGET_CRS = "EPSG:32735"

# ================== LOG ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

s3 = boto3.client("s3")

# ================== FONCTIONS ==================
def download_file(bucket, key, path):
    """Télécharge un fichier depuis S3"""
    try:
        s3.download_file(bucket, key, path)
        logging.info(f"Téléchargé : s3://{bucket}/{key}")
        return True
    except Exception as e:
        logging.error(f"Erreur téléchargement {key} : {e}")
        return False

def validate_geometry(path, name):
    """Valide les géométries d'un GeoDataFrame et reprojette en CRS métrique"""
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logging.warning(f"{name} : CRS manquant → EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)

    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if not g.is_valid else g)
    gdf = gdf.to_crs(TARGET_CRS)
    
    # Supprimer les géométries vides ou invalides restantes
    gdf = gdf[gdf.geometry.notnull()]
    
    return gdf

def plot_layer(gdf, name, out_path):
    """Génère une carte simple pour la couche"""
    fig, ax = plt.subplots(figsize=(10, 10))
    
    geom_type = gdf.geom_type.unique()
    if "Point" in geom_type:
        gdf.plot(ax=ax, color="darkgreen", markersize=6, alpha=0.7, label="Points")
    elif "LineString" in geom_type or "MultiLineString" in geom_type:
        gdf.plot(ax=ax, color="red", linewidth=1.5, label="Lignes")
    elif "Polygon" in geom_type or "MultiPolygon" in geom_type:
        gdf.plot(ax=ax, color="lightblue", edgecolor="black", alpha=0.5, label="Polygones")
    else:
        gdf.plot(ax=ax, color="grey", edgecolor="black")

    # Légende simple
    handles = [Patch(facecolor='lightblue', edgecolor='black', label='Polygones'),
               Line2D([0], [0], color='red', linewidth=1.5, label='Lignes'),
               Patch(facecolor='darkgreen', label='Points')]
    ax.legend(handles=handles, loc='upper right')

    ax.set_title(f"Carte : {name}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Coordonnées Est (m)")
    ax.set_ylabel("Coordonnées Nord (m)")
    ax.grid(True, linestyle="--", alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info(f"Carte générée pour {name} → {out_path}")
# ================== PIPELINE ==================
def run_pipeline(bucket, key):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        local_path = os.path.join(tmp, os.path.basename(key))
        if not download_file(bucket, key, local_path):
            logging.error("❌ Téléchargement échoué, pipeline stoppé")
            return
        # Validation des géométries
        gdf = validate_geometry(local_path, os.path.basename(key))
        if gdf.empty:
            logging.warning("⚠️ Aucune géométrie valide dans le fichier")
            return
        # Sauvegarder GeoJSON validé
        os.makedirs(PROCESSED, exist_ok=True)
        out_geojson = os.path.join(PROCESSED, f"{os.path.splitext(os.path.basename(key))[0]}_valid.geojson")
        gdf.to_file(out_geojson, driver="GeoJSON")
        logging.info(f"✅ Fichier validé sauvegardé : {out_geojson}")

        # Générer la carte
        os.makedirs(OUT_MAP, exist_ok=True)
        out_map = os.path.join(OUT_MAP, f"{os.path.splitext(os.path.basename(key))[0]}_map.png")
        plot_layer(gdf, os.path.basename(key), out_map)
        logging.info(f"✅ Carte générée : {out_map}")

        print(f"✅ Traitement terminé : {len(gdf)} géométries valides")

# ================== RUN ==================
if __name__ == "__main__":
    run_pipeline(BUCKET, S3_KEY)
