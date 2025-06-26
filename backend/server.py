import yaml
from flask import Flask, jsonify, send_from_directory, request
from psycopg_pool import ConnectionPool
import json
import os
from dotenv import load_dotenv
import requests
import queries
import networkx as nx
from shapely.geometry import LineString
from shapely import wkt
from shapely.geometry import mapping
from shapely.geometry import shape
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint

import math
import datetime

load_dotenv()

frontend_dir = os.path.join(
    os.path.dirname( os.path.abspath(__file__ )), 
    '..', 
    'frontend')


class Server:
    def __init__(self, db_config_path):
        self.db_config_path = db_config_path
        self.db_config = {}
        self.db_pool = None
        self.port = self.__accquire_port()
        self.app = Flask(__name__)
        self.graph = nx.Graph()

        self.shadows_data = None
        self.shadows_data_timestamp = None

        self.__load_db_config()
        self.__connect_to_db()
        self.__fetch_data()
        self.__register_routes()


    def __accquire_port(self):
        try:
            return int(os.getenv('SERVPORT', 8686))
        except ValueError:
            print("Warning: Invalid SERVPORT environment variable. Using default port 8686.")
            return 8686


    def __load_db_config(self):
        try:
            with open(self.db_config_path, 'r') as file:
                self.db_config = yaml.safe_load(file)
        except FileNotFoundError:
            print(f"Configuration file {self.db_config_path} not found.")
            self.db_config = {}
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file: {exc}")
            self.db_config = {}


    def __connect_to_db(self):
        if not self.db_config:
            print("No configuration loaded. Cannot connect to the database.")
            return False

        try:
            db_config = self.db_config['database']
            # If no passowrd in the db config check for environment variable
            if db_config['password'] == "":
                db_config['password'] = os.getenv('DB_PASSWORD', '')
            
            # Create connection pool
            self.db_pool = ConnectionPool(conninfo="user={user} host={host} dbname={dbname} password={password} port={port} client_encoding={client_encoding}".format(**db_config))

            print("PostgreSQL connection pool created successfully!")
        
            # Test the connection
            with self.db_pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SHOW client_encoding")
                    ce_row = cur.fetchone()
                    client_encoding = ce_row[0] if ce_row else None
                    cur.execute("SHOW server_encoding")
                    se_row = cur.fetchone()
                    server_encoding = se_row[0] if se_row else None
                    print(f"Client encoding: {client_encoding}, Server encoding: {server_encoding}")
            return True
        except Exception as error:
            print(f"Error connecting to PostgreSQL database: {error}")
            self.db_pool = None
            return False


    def __fetch_data(self):
        if not self.db_pool:
            print("Database connection pool is not initialized. Cannot fetch data.")
            return False
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cur:
                    print(f"Start fetching data from db")
                
                    # Create graph from walking path data
                    cur.execute(queries.GET_WALKPATH_DATA_QUERY_TEXT)
                    rows = cur.fetchall()

                    for row in rows:
                        geom = wkt.loads(row[0])
                        if geom.geom_type == 'MultiLineString':
                            for linestring in geom.geoms:
                                coords = list(linestring.coords)
                                for i in range(len(coords) - 1):
                                    p1, p2 = coords[i], coords[i+1]
                                    dist = LineString([p1, p2]).length
                                    self.graph.add_edge(p1, p2, weight=dist)
                        else:
                            print(f"Unsupported geometry type: {geom.geom_type}")
            print("Data fetched successfully from the database.")   
        except Exception as e:
            print(f"Error fetching data: {e}")


    def __register_routes(self):
        @self.app.route('/')
        def index():
            return send_from_directory(frontend_dir, 'index.html')

        @self.app.route('/<path:filename>')
        def serve_static(filename):
            return send_from_directory(frontend_dir, filename)

        @self.app.route('/api/cadastre', methods=['GET'])
        def get_cadastre():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_cadaster_data()
        
        @self.app.route('/api/walkpath', methods=['GET'])
        def get_walkpath():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_walkpath_data()

        @self.app.route('/api/shortest-path', methods=['POST'])
        def get_shortest_path():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_shortest_path_data()

        @self.app.route('/api/shortest-shaded-path', methods=['POST'])
        def get_shaded_path():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_shortest_shaded_path()

        @self.app.route('/api/health-centers', methods=['POST'])
        def get_health_centers():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_health_centers_data()

        @self.app.route('/api/shade', methods=['POST'])
        def get_shade():
            if not self.db_pool:
                return jsonify({"error": "Database connection pool is not initialized."}), 500
            return self.__get_shade_data()


    def __get_shortest_path_data(self):
        try:
            data = request.get_json()
            start = data.get('start')
            end = data.get('end')

            if not (start and end ):
                return jsonify({"error": "Missing required parameters"}), 400

            start = tuple(start)
            end = tuple(end)

            # Snap start and end to nearest node in the graph
            def nearest_node(point, nodes):
                return min(nodes, key=lambda n: (n[0] - point[0]) ** 2 + (n[1] - point[1]) ** 2)

            nodes = list(self.graph.nodes)
            start_node = nearest_node(start, nodes)
            end_node = nearest_node(end, nodes)

            print(f"Finding shortest path from {start_node} to {end_node}")
            path = nx.shortest_path(self.graph, source=start_node, target=end_node, weight='weight')

            # Convert path to GeoJSON LineString
            line = LineString(path)
            geojson = {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "length": line.length
                }
            }
            return jsonify(geojson)
        except Exception as e:
            print(f"Error finding shortest path: {e}")
            return None


    def __get_shortest_shaded_path(self):
        try:
            data = request.get_json()
            start = data.get('start')
            end = data.get('end')
            sun_azimuth = data.get('sun_azimuth')
            sun_altitude = data.get('sun_altitude')

            if not (start and end and sun_azimuth and sun_altitude):
                return jsonify({"error": "Missing required parameters"}), 400

            # Shade-favoring path
            start = tuple(start)
            end = tuple(end)

            # Snap start and end to nearest node in the graph
            def nearest_node(point, nodes):
                return min(nodes, key=lambda n: (n[0] - point[0]) ** 2 + (n[1] - point[1]) ** 2)

            nodes = list(self.graph.nodes)
            start_node = nearest_node(start, nodes)
            end_node = nearest_node(end, nodes)

            # Fetch shadows data if not already fetched
            self.__create_shade_polygon(sun_azimuth, sun_altitude)
            shadow_polygons = []

            if self.shadows_data:
                print("Processing shadows data to create polygons")
                for shadow in self.shadows_data:
                    geojson = shadow.get("geojson")
                    if geojson and isinstance(geojson, dict):
                        try:
                            poly = shape(geojson)
                            from shapely.geometry.base import BaseGeometry
                            allowed_types = (Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint)
                            if isinstance(poly, allowed_types) and not poly.is_empty:
                                shadow_polygons.append(poly)
                            else:
                                print(f"Skipped unsupported geometry: {type(poly)} value: {poly}")
                        except Exception as e:
                            print(f"Error creating geometry from geojson: {e}")
                    else:
                        print(f"Malformed shadow entry")

                shadow_polygons = [g for g in shadow_polygons if isinstance(g, allowed_types) and not g.is_empty]
            else:
                print("No shadows data available, cannot find shaded path.")

            def edge_in_shadow(p1, p2):
                edge_line = LineString([p1, p2])
                for poly in shadow_polygons:
                    if edge_line.intersects(poly):
                        return True
                return False

            # Adjust edge weights
            G = self.graph.copy()
            for u, v, data in G.edges(data=True):
                base_weight = data.get('weight', 1)
                if edge_in_shadow(u, v):
                    # Shadow reduce weight
                    G[u][v]['weight'] = base_weight * 0.5
                else:
                    # Sun increase weight
                    G[u][v]['weight'] = base_weight * 2

            print(f"Finding shadest path from {start_node} to {end_node}")
            path = nx.shortest_path(G, source=start_node, target=end_node, weight='weight')

            # Convert path to GeoJSON LineString
            line = LineString(path)
            geojson = {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "length": line.length
                }
            }
            return jsonify(geojson)
        except Exception as e:
            print(f"Error finding shadest path: {e}")
            return jsonify({"error": "Failed to find shadest path"}), 500


    def __get_cadaster_data(self):
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cur:
                    print(f"Start fetching data from db")
                    # Fetch cadastre data
                    cur.execute(queries.GET_CADASTRE_DATA_QUERY)
                    rows = cur.fetchall()
                    cadastre_data = [{"geojson": json.loads(row[0]), "height_m": row[1]} for row in rows]
                    return jsonify(cadastre_data)
        except Exception as e:
            print(f"Error fetching cadastre data: {e}")
            return jsonify({"error": "Failed to fetch cadastre data"}), 500


    def __get_walkpath_data(self):
        try:
            with self.db_pool.connection() as conn:
                    with conn.cursor() as cur:
                        print(f"Start fetching data from db")
                        # Fetch walking path
                        cur.execute(queries.GET_WALKPATH_DATA_QUERY_GEOJSON)
                        rows = cur.fetchall()
                        walking_path_data = [{"geojson": json.loads(row[0])} for row in rows]
                        return jsonify(walking_path_data)
        except Exception as e:
            print(f"Error fetching walking path data: {e}")
            return jsonify({"error": "Failed to fetch walking path data"}), 500


    def __get_health_centers_data(self):
        try:
            data = request.get_json()
            type = data.get('type', 'all')
            # Map health center types to their corresponding queries
            with self.db_pool.connection() as conn:
                with conn.cursor() as cur:
                    # Fetch health centers data
                    if type == 'all':
                        cur.execute(queries.GET_HEALTH_CENTERS_QUERY_ALL)
                    else:
                        cur.execute(queries.GET_HEALTH_CENTERS_QUERY_TYPE, (type,))
                    rows = cur.fetchall()
                    health_centers_data = [{"geojson": json.loads(row[0]), "name": row[1], "type": row[2]} for row in rows]
                    return jsonify(health_centers_data)
        except Exception as e:
            print(f"Error fetching health centers data: {e}")
            return jsonify({"error": "Failed to fetch health centers data"}), 500


    def __get_shade_data(self):
            data = request.get_json()
            sun_azimuth = data.get('sun_azimuth')
            sun_altitude = data.get('sun_altitude')
            if not (sun_azimuth and sun_altitude):
                return jsonify({"error": "Missing required parameters"}), 400
            return jsonify(self.__create_shade_polygon(sun_azimuth, sun_altitude))


    def __create_shade_polygon(self, sun_azimuth, sun_altitude):
        try:
            now = datetime.datetime.now()
            # Only refetch if more than 10 minutes have passed or data is None
            if (self.shadows_data is not None and
                self.shadows_data_timestamp is not None and
                (now - self.shadows_data_timestamp).total_seconds() < 600 ):
                    print(f"Using cached shadows data")
                    return self.shadows_data

            with self.db_pool.connection() as conn:
                with conn.cursor() as cur:
                    print(f"Fetch shadows")
                    cur.execute(queries.GET_SHADOWS_QUERY_GEOJSON, (sun_azimuth, sun_altitude))
                    rows = cur.fetchall()
                    self.shadows_data = []
                    for row in rows:
                        geojson_obj = json.loads(row[1])
                        self.shadows_data.append({"id": row[0], "geojson": geojson_obj})
                    self.shadows_data_timestamp = now
                    print(f"Shadows data fetched successfully")
            return self.shadows_data
        except Exception as e:
            print(f"Error creating shade polygon: {e}")
            return {"error": "Failed to create shade polygon"}, 500

    def run(self):
        if not self.db_pool:
            print("Database connection pool is not initialized. Exiting server.")
            return
        self.app.run(port=self.port, debug=True)


if __name__ == '__main__':
    # Path to database configuration
    db_config_path = os.path.join(os.path.dirname(__file__), 'db_config.yaml')
    server = Server(db_config_path)
    server.run()