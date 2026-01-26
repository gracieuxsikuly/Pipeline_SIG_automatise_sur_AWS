import os
import logging
import tempfile
import boto3
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from dotenv import load_dotenv
from shapely.validation import make_valid
from tabulate import tabulate
from matplotlib.backends.backend_pdf import PdfPages
from shapely.geometry import Point

# ================== CONFIG ENV ==================
load_dotenv()

BUCKET = os.getenv("BUCKET_NAME")
AWS_PROFILE = os.getenv("AWS_PROFIL")
AWS_REGION = os.getenv("AWS_REGION")

RAW = "raw/"
PROCESSED = "processed/"
OUT_GEOJSON = "outputs/geojson/"
OUT_MAP = "outputs/carte/"

TARGET_CRS = "EPSG:32735"

FILES = {
    "palmiers": "basedadaptationgeneralemutwangamangina.geojson",
    "routes": "routes.geojson",
    "zones": "Zoneculture.geojson"
}

# ================== LOG ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s"
)

# ================== S3 ==================
session = boto3.Session(
    profile_name=AWS_PROFILE,
    region_name=AWS_REGION
)
s3 = session.client("s3")

def download(key, path):
    """Télécharge un fichier depuis S3. Retourne True si succès, False sinon."""
    try:
        res = s3.list_objects_v2(Bucket=BUCKET, Prefix=key)
        if "Contents" not in res or not any(obj["Key"] == key for obj in res["Contents"]):
            logging.warning(f"⚠️ Fichier introuvable : s3://{BUCKET}/{key}")
            print(f"⚠️ Fichier introuvable : {key}")
            return False
        s3.download_file(BUCKET, key, path)
        logging.info(f"Téléchargé : {key}")
        return True
    except Exception as e:
        logging.error(f"Erreur téléchargement {key} : {e}")
        return False

def upload(path, key):
    """Upload un fichier vers S3."""
    try:
        s3.upload_file(path, BUCKET, key)
        logging.info(f"Upload OK : {key}")
    except Exception as e:
        logging.error(f"Erreur upload {key} : {e}")

# ================== VALIDATION ==================
def process_layer(path, name):
    """Lit et valide un GeoDataFrame, retourne CRS métrique."""
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logging.warning(f"{name} : CRS manquant → EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)

    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if not g.is_valid else g)
    return gdf.to_crs(TARGET_CRS)

# ================== CARTOGRAPHIE SIMPLIFIÉE ==================
def generate_map(zones, palmiers, routes, out_path):
    """Génère une carte sans contextily."""
    fig, ax = plt.subplots(figsize=(14, 14))
    
    # Zones avec densité
    zones.plot(ax=ax, column="densite_palmiers_km2", cmap="YlGn", legend=True,
               edgecolor="black", linewidth=0.5, alpha=0.6,
               legend_kwds={'label': "Densité (palmiers/km²)", 'orientation': "horizontal"})
    
    # Routes
    routes.plot(ax=ax, color="red", linewidth=1.5, label="Routes")
    
    # Palmiers
    palmiers.plot(ax=ax, color="darkgreen", markersize=6, label="Palmiers", alpha=0.7)
    
    # Fond de carte simple
    ax.set_facecolor('#e8f4f8')  # Bleu très clair
    
    # Améliorer la légende
    legend_elements = [
        Patch(facecolor='darkgreen', edgecolor='black', label='Palmiers'),
        Line2D([0], [0], color='red', linewidth=1.5, label='Routes')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    ax.set_title("Carte de densité des palmiers", fontsize=16, fontweight='bold')
    ax.set_xlabel("Coordonnées Est (m)", fontsize=10)
    ax.set_ylabel("Coordonnées Nord (m)", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

def generate_pdf(map_path, resultat, pdf_path):
    with PdfPages(pdf_path) as pdf:
        # Page 1 : Carte
        fig, ax = plt.subplots(figsize=(14, 14))
        ax.imshow(plt.imread(map_path))
        ax.axis("off")
        ax.set_title("Carte de densité des palmiers", fontsize=14, fontweight='bold')
        pdf.savefig(fig)
        plt.close()

        # Page 2 : Tableau
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.axis("off")
        
        # Créer le tableau
        table_data = []
        for idx, row in resultat.iterrows():
            table_data.append([
                row["Designation"],
                f"{row['nb_palmiers']:.0f}",
                f"{row['surface_km2']:.2f}",
                f"{row['densite_palmiers_km2']:.2f}"
            ])
        
        # Ajouter une ligne de total
        table_data.append([
            "TOTAL / MOYENNE",
            f"{resultat['nb_palmiers'].sum():.0f}",
            f"{resultat['surface_km2'].sum():.2f}",
            f"{resultat['densite_palmiers_km2'].mean():.2f}"
        ])
        
        columns = ["Zone", "Nombre de palmiers", "Surface (km²)", "Densité (palmiers/km²)"]
        
        table = ax.table(cellText=table_data,
                         colLabels=columns,
                         loc="center",
                         cellLoc='center')
        
        # Mise en forme du tableau
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        # Colorer la dernière ligne
        for j in range(len(columns)):
            table[(len(table_data), j)].set_facecolor('#f2f2f2')
            table[(len(table_data), j)].set_text_props(weight='bold')
        
        ax.set_title("Rapport de densité des palmiers", fontsize=16, fontweight='bold', pad=30)
        pdf.savefig(fig)
        plt.close()

# ================== FONCTIONS ALTERNATIVES À SJOIN ==================
def find_nearest_route(palmier_point, routes_gdf):
    """Trouve la distance à la route la plus proche (méthode manuelle)."""
    if routes_gdf.empty:
        return np.nan
    
    distances = routes_gdf.geometry.distance(palmier_point)
    return distances.min()

def count_palmiers_in_zones_manual(palmiers_gdf, zones_gdf):
    """Compte les palmiers dans chaque zone sans utiliser sjoin."""
    zones_with_count = zones_gdf.copy()
    zones_with_count["nb_palmiers"] = 0
    
    # Pour chaque zone, compter les palmiers qui sont à l'intérieur
    for idx, zone in zones_with_count.iterrows():
        # Créer un masque pour les palmiers dans cette zone
        mask = palmiers_gdf.geometry.within(zone.geometry)
        zones_with_count.at[idx, "nb_palmiers"] = mask.sum()
    
    return zones_with_count

# ================== PIPELINE ==================
def run_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        logging.info("Pipeline SIG démarré")
        local = {}

        # --- DOWNLOAD + PROCESS ---
        for k, f in FILES.items():
            path = os.path.join(tmp, f)
            success = download(RAW + f, path)
            if not success:
                logging.warning(f"⚠️ Ignoré : {f}")
                print(f"⚠️ Ignoré : {f}")
                continue
            local[k] = process_layer(path, k)

        # Vérification des fichiers essentiels
        for required in ["palmiers", "routes", "zones"]:
            if required not in local:
                logging.error(f"❌ Fichier requis manquant : {required}. Pipeline stoppé.")
                print(f"❌ Pipeline stoppé, fichier manquant : {required}")
                return

        palmiers = local["palmiers"]
        routes = local["routes"]
        zones = local["zones"]

        # --- DISTANCE AUX ROUTES (méthode alternative) ---
        logging.info("Calcul des distances aux routes...")
        palmiers["distance_route_m"] = palmiers.geometry.apply(
            lambda p: find_nearest_route(p, routes)
        )
        palmiers["distance_route_km"] = palmiers["distance_route_m"] / 1000

        # --- DENSITÉ PALMIERS PAR ZONE (méthode alternative) ---
        logging.info("Calcul de la densité des palmiers par zone...")
        
        # Méthode manuelle sans sjoin
        zones_with_counts = count_palmiers_in_zones_manual(palmiers, zones)
        
        # Calcul de la surface
        zones_with_counts["surface_km2"] = zones_with_counts.geometry.area / 1_000_000
        
        # Calcul de la densité
        zones_with_counts["densite_palmiers_km2"] = zones_with_counts["nb_palmiers"] / zones_with_counts["surface_km2"]
        
        # Remplacer les valeurs infinies par 0 (si surface = 0)
        zones_with_counts["densite_palmiers_km2"] = zones_with_counts["densite_palmiers_km2"].replace([np.inf, -np.inf], 0)
        
        # Sélection et formatage des résultats
        if "Designation" in zones_with_counts.columns:
            resultat_cols = ["Designation", "nb_palmiers", "surface_km2", "densite_palmiers_km2"]
        else:
            # Si pas de colonne Designation, utiliser l'index
            zones_with_counts["Designation"] = [f"Zone_{i+1}" for i in range(len(zones_with_counts))]
            resultat_cols = ["Designation", "nb_palmiers", "surface_km2", "densite_palmiers_km2"]
        
        resultat = zones_with_counts[resultat_cols]
        
        # --- LOG ---
        logging.info("\n" + tabulate(resultat, headers="keys", tablefmt="grid", floatfmt=".2f"))

        # --- EXPORTS ---
        map_img = os.path.join(tmp, "carte_palmiers.png")
        pdf = os.path.join(tmp, "rapport_palmiers.pdf")
        
        # Générer la carte simplifiée
        generate_map(zones_with_counts, palmiers, routes, map_img)
        generate_pdf(map_img, resultat, pdf)

        zones_path = os.path.join(tmp, "zones.geojson")
        zones_with_counts.to_file(zones_path, driver="GeoJSON")
        
        # Exporter aussi les palmiers avec distances
        palmiers_path = os.path.join(tmp, "palmiers_avec_distances.geojson")
        palmiers.to_file(palmiers_path, driver="GeoJSON")

        upload(zones_path, PROCESSED + "zones.geojson")
        upload(zones_path, OUT_GEOJSON + "zones.geojson")
        upload(palmiers_path, PROCESSED + "palmiers_avec_distances.geojson")
        upload(map_img, OUT_MAP + "carte_palmiers.png")
        upload(pdf, OUT_MAP + "rapport_palmiers.pdf")

        logging.info("Pipeline terminé ✅")
        print("✅ Pipeline terminé")
        print(f"📊 Résumé: {len(zones_with_counts)} zones, {len(palmiers)} palmiers")
        print(f"📈 Densité moyenne: {zones_with_counts['densite_palmiers_km2'].mean():.2f} palmiers/km²")
        print(f"📏 Distance moyenne aux routes: {palmiers['distance_route_km'].mean():.2f} km")

# ================== RUN ==================
if __name__ == "__main__":
    run_pipeline()