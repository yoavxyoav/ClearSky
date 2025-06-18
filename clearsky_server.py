#!/usr/bin/env python3
"""
ClearSky HTTP Server
A web-based version of the Jordan Air Traffic Monitor
Reuses all existing logic from clearsky.py
"""

import json
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys
import os
from shapely.geometry import Point
import traceback

# Import all the existing logic from clearsky.py
from clearsky import (
    get_oauth2_token, get_token, get_jordan_polygon, is_point_in_jordan,
    get_flights, BBOX, SOURCE_MAP, beep, BEEP_MODE, BEEP_SAMPLES, BEEP_SAMPLE_PATH
)

print("[LOG] Importing clearsky_server.py and loading credentials...")

# Global state to store current flight data
current_data = {
    'timestamp': None,
    'flights': [],
    'jordan_flights': [],
    'stats': {
        'total_flights': 0,
        'jordan_flights': 0,
        'lat_range': None,
        'lon_range': None
    }
}

# Track last sent timestamp globally for accurate logging
last_flights_timestamp_global = None

# Thread lock for data access
data_lock = threading.Lock()

refresh_count = 0

def update_flight_data():
    """Background thread to continuously update flight data"""
    global current_data, refresh_count
    
    print("[LOG] update_flight_data thread starting...")
    print("[LOG] Starting flight data update thread...")
    jordan_polygon = get_jordan_polygon()
    print("[LOG] Jordan polygon loaded: {}".format('OK' if jordan_polygon else 'FAILED'))
    
    while True:
        try:
            print(f"[LOG] Data refresh at {datetime.now().isoformat()}")
            print(f"[LOG] Fetching flights from OpenSky with BBOX: {BBOX}")
            bbox_flights = get_flights(BBOX)
            print(f"[LOG] get_flights returned: {type(bbox_flights)} with {len(bbox_flights) if bbox_flights else 0} flights")
            if bbox_flights is None:
                print(f"[ERROR] {datetime.now()} Could not fetch flights data")
                time.sleep(60)  # Wait 1 minute before retry
                continue
                
            now = datetime.now()
            lats, lons = [], []
            jordan_flights = []
            flights_dict = {}  # ICAO24 -> flight_data
            # Process flights
            for flight in bbox_flights:
                callsign = flight[1].strip() if flight[1] is not None else ''
                airline = callsign[:3] if len(callsign) >= 3 else ''
                country = flight[2] if flight[2] is not None else ''
                lon = flight[5]
                lat = flight[6]
                last_contact = flight[4]
                position_source = flight[16] if len(flight) > 16 else None
                now_ts = now.timestamp()
                age = int(now_ts - last_contact) if last_contact else 'N/A'
                source_name = SOURCE_MAP.get(position_source, str(position_source))
                if lon is not None and lat is not None:
                    lats.append(lat)
                    lons.append(lon)
                    point = Point(lon, lat)
                    inside = is_point_in_jordan(point, jordan_polygon)
                    flight_data = {
                        'callsign': callsign,
                        'airline': airline,
                        'country': country,
                        'longitude': lon,
                        'latitude': lat,
                        'inside_polygon': inside,
                        'source': source_name,
                        'age': age,
                        'icao24': flight[0],
                        'altitude': flight[7],
                        'velocity': flight[9],
                        'heading': flight[10],
                        'on_ground': flight[8]
                    }
                    flights_dict[flight[0]] = flight_data  # Overwrite duplicates
                    if inside:
                        jordan_flights.append(flight_data)
            print(f"[LOG] Processed {len(flights_dict)} flights, {len(jordan_flights)} over Jordan")
            # Update global state
            with data_lock:
                current_data['timestamp'] = now.isoformat()
                current_data['flights'] = list(flights_dict.values())
                current_data['jordan_flights'] = jordan_flights
                refresh_count += 1
                current_data['stats'] = {
                    'total_flights': len(flights_dict),
                    'jordan_flights': len(jordan_flights),
                    'lat_range': (min(lats), max(lats)) if lats else None,
                    'lon_range': (min(lons), max(lons)) if lons else None,
                    'refresh_count': refresh_count
                }
            print(f"[LOG] Updated state: {len(flights_dict)} flights in bbox, {len(jordan_flights)} over Jordan")
        except Exception as e:
            print(f"[ERROR] Exception in update thread: {e}")
            traceback.print_exc()
        time.sleep(60)  # Update every minute

class ClearSkyHTTPHandler(BaseHTTPRequestHandler):
    def log_api_access(self, endpoint, extra=None):
        client_ip = self.client_address[0]
        msg = f"[LOG] {datetime.now().isoformat()} - {client_ip} accessed {endpoint}"
        if extra:
            msg += f" {extra}"
        print(msg)

    def do_GET(self):
        global last_flights_timestamp_global
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        # For /api/flights, log update status
        if path == '/api/flights':
            with data_lock:
                current_ts = current_data['timestamp']
            updated = (current_ts != last_flights_timestamp_global)
            self.log_api_access(path, f"({'updated' if updated else 'not updated'})")
            last_flights_timestamp_global = current_ts
        else:
            self.log_api_access(path)
        
        if path == '/':
            self.send_html_response()
        elif path == '/api/flights':
            print(f"[LOG] /api/flights requested, returning {len(current_data['flights'])} flights at {current_data['timestamp']}")
            self.send_json_response()
        elif path == '/api/stats':
            self.send_stats_response()
        elif path == '/api/jordan':
            self.send_jordan_flights_response()
        elif path == '/api/jordan_polygon':
            self.send_jordan_polygon_response()
        else:
            self.send_error(404, "Not Found")
    
    def send_html_response(self):
        """Send the main HTML page"""
        try:
            with open('index.html', 'r', encoding='utf-8') as f:
                html = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            self.send_error(500, f"Could not load index.html: {e}")
    
    def send_json_response(self):
        """Send flight data as JSON"""
        with data_lock:
            response_data = {
                'timestamp': current_data['timestamp'],
                'flights': current_data['flights'],
                'stats': current_data['stats']
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode('utf-8'))
    
    def send_stats_response(self):
        """Send only statistics as JSON"""
        with data_lock:
            response_data = {
                'timestamp': current_data['timestamp'],
                'stats': current_data['stats']
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode('utf-8'))
    
    def send_jordan_flights_response(self):
        """Send only Jordan flights as JSON"""
        with data_lock:
            response_data = {
                'timestamp': current_data['timestamp'],
                'jordan_flights': current_data['jordan_flights']
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode('utf-8'))
    
    def send_jordan_polygon_response(self):
        """Send the real Jordan polygon as GeoJSON coordinates"""
        polygon = get_jordan_polygon()
        if polygon is None:
            self.send_error(500, "Could not load Jordan polygon")
            return
        # Convert to GeoJSON-like dict
        geojson = polygon.__geo_interface__
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(geojson).encode('utf-8'))
    
    def log_message(self, format, *args):
        """Custom logging to avoid cluttering the console"""
        pass

def main():
    """Main function to start the HTTP server"""
    print("🚀 Starting ClearSky HTTP Server...")
    print("📍 Jordan Air Traffic Monitor - Web Edition")
    print(f"🌐 Using bounding box: {BBOX}")
    
    # Start the background data update thread
    update_thread = threading.Thread(target=update_flight_data, daemon=True)
    update_thread.start()
    
    # Configure server
    port = 8080
    server_address = ('', port)
    
    try:
        httpd = HTTPServer(server_address, ClearSkyHTTPHandler)
        print(f"🌍 Server running at http://localhost:{port}")
        print("📊 Open your browser to view the live flight data")
        print("🔌 Press Ctrl+C to stop the server")
        print("-" * 50)
        
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")

if __name__ == "__main__":
    main() 