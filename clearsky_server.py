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

# Import all the existing logic from clearsky.py
from clearsky import (
    get_oauth2_token, get_token, get_jordan_polygon, is_point_in_jordan,
    get_flights, BBOX, SOURCE_MAP, beep, BEEP_MODE, BEEP_SAMPLES, BEEP_SAMPLE_PATH
)

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

# Thread lock for data access
data_lock = threading.Lock()

def update_flight_data():
    """Background thread to continuously update flight data"""
    global current_data
    
    print("[LOG] Starting flight data update thread...")
    jordan_polygon = get_jordan_polygon()
    
    while True:
        try:
            print(f"[LOG] Data refresh at {datetime.now().isoformat()}")
            bbox_flights = get_flights(BBOX)
            if bbox_flights is None:
                print(f"[ERROR] {datetime.now()} Could not fetch flights data")
                time.sleep(60)  # Wait 1 minute before retry
                continue
                
            now = datetime.now()
            lats, lons = [], []
            jordan_flights = []
            
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
                    
                    if inside:
                        jordan_flights.append(flight_data)
                    
                    # Add to all flights
                    if flight_data not in [f for f in current_data['flights'] if f.get('icao24') == flight_data['icao24']]:
                        current_data['flights'].append(flight_data)
            
            # Update global state
            with data_lock:
                current_data['timestamp'] = now.isoformat()
                current_data['jordan_flights'] = jordan_flights
                current_data['stats'] = {
                    'total_flights': len(bbox_flights),
                    'jordan_flights': len(jordan_flights),
                    'lat_range': (min(lats), max(lats)) if lats else None,
                    'lon_range': (min(lons), max(lons)) if lons else None
                }
            
            print(f"[LOG] Updated state: {len(bbox_flights)} flights in bbox, {len(jordan_flights)} over Jordan")
            
        except Exception as e:
            print(f"[ERROR] Exception in update thread: {e}")
        
        time.sleep(60)  # Update every minute

class ClearSkyHTTPHandler(BaseHTTPRequestHandler):
    last_flights_timestamp = None
    def log_api_access(self, endpoint, extra=None):
        client_ip = self.client_address[0]
        msg = f"[LOG] {datetime.now().isoformat()} - {client_ip} accessed {endpoint}"
        if extra:
            msg += f" {extra}"
        print(msg)

    def do_GET(self):
        """Handle HTTP GET requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        # For /api/flights, log update status
        if path == '/api/flights':
            with data_lock:
                current_ts = current_data['timestamp']
            updated = (current_ts != self.last_flights_timestamp)
            self.log_api_access(path, f"({'updated' if updated else 'not updated'})")
            self.last_flights_timestamp = current_ts
        else:
            self.log_api_access(path)
        
        if path == '/':
            self.send_html_response()
        elif path == '/api/flights':
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
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ClearSky - Jordan Air Traffic Monitor</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
            margin: 0;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #ffd700;
        }
        .content-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .map-container {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            overflow: hidden;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            height: 500px;
        }
        #map {
            width: 100%;
            height: 100%;
            border-radius: 10px;
        }
        .flights-table {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            overflow: hidden;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            max-height: 500px;
            overflow-y: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th {
            background: rgba(255,255,255,0.2);
            font-weight: bold;
            position: sticky;
            top: 0;
        }
        .inside-polygon {
            color: #ff6b6b;
            font-weight: bold;
        }
        .outside-polygon {
            color: #51cf66;
        }
        .refresh-btn {
            background: #ffd700;
            color: #333;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover {
            background: #ffed4e;
        }
        .last-update {
            text-align: center;
            margin-top: 20px;
            font-style: italic;
            opacity: 0.8;
        }
        .flight-popup {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #333;
        }
        .flight-popup h3 {
            margin: 0 0 10px 0;
            color: #667eea;
        }
        .flight-popup p {
            margin: 5px 0;
        }
        .flight-popup .inside {
            color: #ff6b6b;
            font-weight: bold;
        }
        .flight-popup .outside {
            color: #51cf66;
        }
        @media (max-width: 768px) {
            .content-grid {
                grid-template-columns: 1fr;
            }
            .map-container {
                height: 400px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛩️ ClearSky</h1>
            <p>Jordan Air Traffic Monitor - Real-time Flight Tracking</p>
        </div>
        
        <button class="refresh-btn" id="refresh-btn">🔄 Refresh Data</button>
        <button class="refresh-btn" id="mute-btn">🔊 Mute</button>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="total-flights">-</div>
                <div>Total Flights</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="jordan-flights">-</div>
                <div>Over Jordan</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="coverage">-</div>
                <div>Coverage Area</div>
            </div>
        </div>
        
        <div class="map-container">
            <div id="map"></div>
        </div>
        
        <div class="flights-table">
            <table id="flights-table">
                <thead>
                    <tr>
                        <th data-col="callsign">Callsign</th>
                        <th data-col="airline">Airline</th>
                        <th data-col="country">Country</th>
                        <th data-col="position">Position</th>
                        <th data-col="altitude">Altitude</th>
                        <th data-col="speed">Speed</th>
                        <th data-col="jordan">Jordan</th>
                        <th data-col="source">Source</th>
                        <th data-col="age">Age</th>
                    </tr>
                </thead>
                <tbody id="flights-tbody">
                    <tr><td colspan="8" style="text-align: center;">Loading flight data...</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="last-update" id="last-update">
            Last update: Never
        </div>
        <div class="log-area" id="log-area" style="background:rgba(0,0,0,0.2);color:#fff;padding:10px 20px;margin-top:20px;border-radius:8px;max-height:180px;overflow-y:auto;font-size:0.95em;"></div>
    </div>
    
    <script>
        // Mute logic for beeps
        let muted = false;
        const muteBtn = document.getElementById('mute-btn');
        function updateMuteBtn() {
            muteBtn.textContent = muted ? '🔇 Unmute' : '🔊 Mute';
        }
        muteBtn.onclick = function() {
            muted = !muted;
            updateMuteBtn();
        };
        updateMuteBtn();
        function beep(times = 1) {
            if (muted) return;
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            let i = 0;
            function playBeep() {
                if (i >= times) { ctx.close(); return; }
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                o.type = 'sine';
                o.frequency.value = 880;
                g.gain.value = 0.2;
                o.connect(g).connect(ctx.destination);
                o.start();
                setTimeout(() => { o.stop(); i++; setTimeout(playBeep, 120); }, 120);
            }
            playBeep();
        }

        // Initialize map
        const map = L.map('map').setView([31.5, 36.5], 7);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        }).addTo(map);
        // Fetch and draw the real Jordan polygon
        let jordanPolygonLayer = null;
        fetch('/api/jordan_polygon')
            .then(response => response.json())
            .then(geojson => {
                if (jordanPolygonLayer) map.removeLayer(jordanPolygonLayer);
                jordanPolygonLayer = L.geoJSON(geojson, {
                    style: {
                        color: 'red',
                        weight: 2,
                        fillColor: '#ff6b6b',
                        fillOpacity: 0.1
                    }
                }).addTo(map);
                try { map.fitBounds(jordanPolygonLayer.getBounds()); } catch (e) {}
            });
        // Flight markers layer
        let flightMarkers = L.layerGroup().addTo(map);
        // Custom airplane icon with heading
        function createAirplaneIcon(heading, color) {
            // SVG airplane with rotation
            const svg = `<svg width="32" height="32" viewBox="0 0 32 32" style="transform:rotate(${heading}deg);">
                <polygon points="16,2 20,24 16,20 12,24" fill="${color}" stroke="black" stroke-width="1.5"/>
            </svg>`;
            return L.divIcon({
                className: '',
                html: svg,
                iconSize: [32, 32],
                iconAnchor: [16, 16]
            });
        }
        function logEvent(msg) {
            const logArea = document.getElementById('log-area');
            const now = new Date();
            const entry = `<div>[${now.toLocaleTimeString()}] ${msg}</div>`;
            logArea.innerHTML = entry + logArea.innerHTML;
        }
        let lastTimestamp = null;
        let flightsData = [];
        let sortCol = null;
        let sortAsc = true;
        function renderTable() {
            const tbody = document.getElementById('flights-tbody');
            tbody.innerHTML = '';
            let data = flightsData.slice();
            if (sortCol) {
                data.sort((a, b) => {
                    let va, vb;
                    if (sortCol === 'position') {
                        va = (a.latitude || 0) + (a.longitude || 0);
                        vb = (b.latitude || 0) + (b.longitude || 0);
                    } else if (sortCol === 'altitude') {
                        va = a.altitude || 0;
                        vb = b.altitude || 0;
                    } else if (sortCol === 'speed') {
                        va = a.velocity || 0;
                        vb = b.velocity || 0;
                    } else if (sortCol === 'age') {
                        va = a.age === 'N/A' ? 99999 : a.age;
                        vb = b.age === 'N/A' ? 99999 : b.age;
                    } else if (sortCol === 'jordan') {
                        va = a.inside_polygon ? 1 : 0;
                        vb = b.inside_polygon ? 1 : 0;
                    } else {
                        va = (a[sortCol] || '').toString().toLowerCase();
                        vb = (b[sortCol] || '').toString().toLowerCase();
                    }
                    if (va < vb) return sortAsc ? -1 : 1;
                    if (va > vb) return sortAsc ? 1 : -1;
                    return 0;
                });
            }
            data.forEach(flight => {
                const row = document.createElement('tr');
                row.className = flight.inside_polygon ? 'inside-polygon' : 'outside-polygon';
                row.innerHTML = `
                    <td>${flight.callsign || 'N/A'}</td>
                    <td>${flight.airline || 'N/A'}</td>
                    <td>${flight.country || 'N/A'}</td>
                    <td>${flight.latitude?.toFixed(4)}, ${flight.longitude?.toFixed(4)}</td>
                    <td>${flight.altitude ? Math.round(flight.altitude) + 'm' : 'N/A'}</td>
                    <td>${flight.velocity ? Math.round(flight.velocity) + 'm/s' : 'N/A'}</td>
                    <td>${flight.inside_polygon ? '🟢 YES' : '🔴 NO'}</td>
                    <td>${flight.source || 'N/A'}</td>
                    <td>${flight.age || 'N/A'}</td>
                `;
                tbody.appendChild(row);
            });
        }
        // Add sort indicators and click handlers
        document.querySelectorAll('#flights-table th').forEach(th => {
            th.style.cursor = 'pointer';
            th.onclick = function() {
                const col = th.getAttribute('data-col');
                if (sortCol === col) sortAsc = !sortAsc;
                else { sortCol = col; sortAsc = true; }
                document.querySelectorAll('#flights-table th').forEach(h => h.textContent = h.textContent.replace(/[▲▼]/g, ''));
                th.textContent = th.textContent.replace(/[▲▼]/g, '') + (sortAsc ? ' ▲' : ' ▼');
                renderTable();
            };
        });
        function updateData(force=false) {
            fetch('/api/flights')
                .then(response => response.json())
                .then(data => {
                    if (!force && data.timestamp === lastTimestamp) return;
                    lastTimestamp = data.timestamp;
                    flightsData = data.flights;
                    document.getElementById('total-flights').textContent = data.stats.total_flights;
                    document.getElementById('jordan-flights').textContent = data.stats.jordan_flights;
                    document.getElementById('coverage').textContent = data.stats.total_flights > 0 ? 'Active' : 'No Data';
                    flightMarkers.clearLayers();
                    let jordanCount = 0;
                    data.flights.forEach(flight => {
                        const markerColor = flight.inside_polygon ? '#ff6b6b' : '#51cf66';
                        const heading = flight.heading || 0;
                        const marker = L.marker([flight.latitude, flight.longitude], {
                            icon: createAirplaneIcon(heading, markerColor)
                        }).addTo(flightMarkers);
                        const popupContent = `
                            <div class="flight-popup">
                                <h3>${flight.callsign || 'N/A'}</h3>
                                <p><strong>Airline:</strong> ${flight.airline || 'N/A'}</p>
                                <p><strong>Country:</strong> ${flight.country || 'N/A'}</p>
                                <p><strong>Position:</strong> ${flight.latitude?.toFixed(4)}, ${flight.longitude?.toFixed(4)}</p>
                                <p><strong>Altitude:</strong> ${flight.altitude ? Math.round(flight.altitude) + 'm' : 'N/A'}</p>
                                <p><strong>Speed:</strong> ${flight.velocity ? Math.round(flight.velocity) + 'm/s' : 'N/A'}</p>
                                <p><strong>Source:</strong> ${flight.source || 'N/A'}</p>
                                <p><strong>Age:</strong> ${flight.age || 'N/A'}</p>
                                <p class="${flight.inside_polygon ? 'inside' : 'outside'}">
                                    <strong>Over Jordan:</strong> ${flight.inside_polygon ? '🟢 YES' : '🔴 NO'}
                                </p>
                            </div>
                        `;
                        marker.bindPopup(popupContent);
                        if (flight.inside_polygon) jordanCount++;
                    });
                    if (jordanCount > 0) beep(jordanCount);
                    document.getElementById('last-update').textContent = 
                        'Last update: ' + new Date(data.timestamp).toLocaleString();
                    renderTable();
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                    document.getElementById('flights-tbody').innerHTML = 
                        '<tr><td colspan="8" style="text-align: center; color: #ff6b6b;">Error loading data</td></tr>';
                });
        }
        updateData(true);
        setInterval(updateData, 60000);
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.onclick = function() { updateData(true); };
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
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