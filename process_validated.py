import os
import logging
import tempfile
import boto3
import geopandas as gpd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from shapely.validation import make_valid
from tabulate import tabulate
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
load_dotenv()

BUCKET = os.getenv("BUCKET_NAME")
AWS_PROFILE = os.getenv("AWS_PROFIL")
AWS_REGION = os.getenv("AWS_REGION")

RAW = "raw/"
PROCESSED = "processed/"
OUT_GEOJSON = "outputs/geojson/"
OUT_MAP = "outputs/carte/"

TARGET_CRS = "EPSG:3857"


session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
s3 = session.client("s3")

def list_geojson_files():
    res = s3.list_objects_v2(Bucket=BUCKET, Prefix=RAW)
    if "Contents" not in res:
        return []
    return [o["Key"] for o in res["Contents"] if o["Key"].endswith(".geojson")]

def download(key, path):
    s3.download_file(BUCKET, key, path)

def upload(path, key):
    s3.upload_file(path, BUCKET, key)

def process_layer(path, layer_name):
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logging.warning(f"{layer_name} : CRS manquant → EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)

    gdf["geometry"] = gdf.geometry.apply(
        lambda g: make_valid(g) if not g.is_valid else g
    )

    gdf = gdf.to_crs(TARGET_CRS)
    gdf["surface_km2"] = gdf.area / 1_000_000

    return gdf

def export_map(gdf, img_path, title):
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf.plot(ax=ax, color="lightgreen", edgecolor="black")
    ax.set_title(title)
    ax.axis("off")
    plt.savefig(img_path, dpi=300, bbox_inches="tight")
    plt.close()

def export_pdf(layer_name, stats, img_path, pdf_path):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 40, f"Rapport couche : {layer_name}")

    c.setFont("Helvetica", 10)
    y = height - 80

    table = tabulate(
        stats,
        headers=["Nb entités", "Surface totale (km²)"],
        tablefmt="plain"
    ).split("\n")

    for line in table:
        c.drawString(40, y, line)
        y -= 14

    c.showPage()
    c.drawImage(img_path, 40, 80, width=500, preserveAspectRatio=True)
    c.save()

def run_pipeline():
    files = list_geojson_files()

    if not files:
        logging.warning("Aucun GeoJSON trouvé dans raw/")
        return

    with tempfile.TemporaryDirectory() as tmp:
        for key in files:
            layer = os.path.basename(key).replace(".geojson", "")
            local_raw = os.path.join(tmp, os.path.basename(key))

            download(key, local_raw)
            gdf = process_layer(local_raw, layer)

            # ---- STATISTIQUES
            stats = [[
                len(gdf),
                gdf["surface_km2"].sum()
            ]]

            # ---- LOG TABULATE
            logging.info(
                f"\nCouche : {layer}\n" +
                tabulate(
                    stats,
                    headers=["Nb entités", "Surface totale (km²)"],
                    tablefmt="grid"
                )
            )

            # ---- EXPORTS
            processed = os.path.join(tmp, f"{layer}_processed.geojson")
            final_geojson = os.path.join(tmp, f"{layer}.geojson")
            map_img = os.path.join(tmp, f"{layer}.png")
            pdf = os.path.join(tmp, f"{layer}_rapport.pdf")

            gdf.to_file(processed, driver="GeoJSON")
            gdf.to_file(final_geojson, driver="GeoJSON")
            export_map(gdf, map_img, layer)
            export_pdf(layer, stats, map_img, pdf)

            # ---- UPLOAD S3
            upload(processed, PROCESSED + f"{layer}.geojson")
            upload(final_geojson, OUT_GEOJSON + f"{layer}.geojson")
            upload(map_img, OUT_MAP + f"{layer}.png")
            upload(pdf, OUT_MAP + f"{layer}_rapport.pdf")

    logging.info("Pipeline terminé ✅")


if __name__ == "__main__":
    run_pipeline()
