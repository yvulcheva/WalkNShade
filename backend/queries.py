GET_HEALTH_CENTERS_QUERY_ALL = """
SELECT ST_AsGeoJSON(ST_Transform(geom, 4326)) as geojson, name, type FROM public.sofia_health_centers;
"""

GET_HEALTH_CENTERS_QUERY_TYPE = """
SELECT ST_AsGeoJSON(ST_Transform(geom, 4326)) as geojson, name, type FROM public.sofia_health_centers
WHERE type = %s;
"""

GET_CADASTRE_DATA_QUERY = """
SELECT ST_AsGeoJSON(ST_Transform(geom, 4326)) as geojson, height_m FROM public.sofia_kadastur;
"""

GET_WALKPATH_DATA_QUERY_GEOJSON = """
SELECT ST_AsGeoJSON(ST_Transform(geom, 4326)) as geojson FROM public.peshehodna_mreja_sofia;
"""

GET_WALKPATH_DATA_QUERY_TEXT = """
SELECT ST_AsText(geom) as text FROM public.peshehodna_mreja_sofia;
"""

GET_SHADOWS_QUERY_GEOJSON = """
WITH params AS (
  SELECT radians(%s) AS azimuth_rad, radians(%s) AS altitude_rad
),
orig AS (
  SELECT
    sk.id,
    ST_Transform(sk.geom, 3857) AS geom,
    sk.height_m,
    p.azimuth_rad,
    p.altitude_rad
  FROM public.sofia_kadastur sk
  CROSS JOIN params p
  WHERE sk.height_m > 0 AND abs(p.altitude_rad) > 0.01
),
shadow AS (
  SELECT
    id,
    ST_Translate(
      geom,
      height_m / tan(altitude_rad) * sin(azimuth_rad),
      height_m / tan(altitude_rad) * cos(azimuth_rad)
    ) AS shadow_geom
  FROM orig
),
all_geoms AS (
  SELECT id, geom FROM orig
  UNION ALL
  SELECT id, shadow_geom FROM shadow
),
grouped AS (
  SELECT
    id,
    array_agg(geom) AS geoms,
    COUNT(*) AS geom_count,
    ST_Collect(geom) AS collected
  FROM all_geoms
  GROUP BY id
)
SELECT
  id,
  ST_AsGeoJSON((ST_Dump(
    ST_Transform(
      CASE
        WHEN geom_count = 1 THEN geoms[1]
        WHEN ST_NumGeometries(ST_UnaryUnion(collected)) = 1 THEN ST_UnaryUnion(collected)
        ELSE ST_ConvexHull(collected)
      END, 4326)
  )).geom) AS geojson
FROM grouped;
"""