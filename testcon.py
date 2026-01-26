from db import get_connection
import geopandas as gpd
from psycopg2.extras import execute_values
mon_fichier="data/routes.geojson"
table_name="roads"
schema="raw_gis_data"
try:
    con=get_connection()
    cur=con.cursor()
#    mon code pour insertion dans la base de donnee
    gdf=gpd.read_file(mon_fichier)
    print(gdf)
    srid=gdf.crs.to_epsg()
    # creation de ma table
    sql_create=f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table_name}(
        id SERIAL PRIMARY KEY,
        geometry geometry({gdf.geom_type[0]},{srid})
        );
    """
    cur.execute(sql_create)
    # insertion de mes donnes depuis le fichier
    records=[
       (row.geometry.wkt,) 
       for _, row in gdf.iterrows()
    ]
    sql = f"""
        INSERT INTO {schema}.{table_name} (geometry)
        VALUES %s
        """
    execute_values(
        cur,
        sql,
        records,
        template=f"(ST_GeomFromText(%s, {srid}))"
    )
    con.commit()
    cur.close()
    con.close()
    print(" Table creee et donnees inserees avec succes")
except Exception as e:
    print("Erreur de connexion:",e)
