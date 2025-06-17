import requests
import time
from datetime import datetime
import platform
import os
import json
from shapely.geometry import Point, shape, MultiPolygon
import matplotlib
matplotlib.use('Qt5Agg')  # Use Qt5Agg backend for better window management
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
import contextily as ctx
import numpy as np
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
import sys
import random

API_URL = "https://opensky-network.org/api/states/all"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
JORDAN_GEOJSON_URL = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/JOR/ADM0/geoBoundaries-JOR-ADM0.geojson"

# Bounding box for Jordan (tight fit to polygon)
BBOX = {
    "lamin": 29.183,  # min latitude
    "lamax": 33.375,  # max latitude
    "lomin": 34.958,  # min longitude
    "lomax": 39.302   # max longitude
}

# Padding for the bounding box (in degrees)
PADDING = 1  # 0.5 degrees of padding

# Arrow visualization settings
ARROW_LENGTH = 0.1    # Length of the arrow in degrees
ARROW_WIDTH = 0.05    # Width of the arrow head
ARROW_HEAD_LENGTH = 0.1  # Length of the arrow head

# Apply padding to BBOX
BBOX = {
    "lamin": BBOX["lamin"] - PADDING,
    "lamax": BBOX["lamax"] + PADDING,
    "lomin": BBOX["lomin"] - PADDING,
    "lomax": BBOX["lomax"] + PADDING
}

INTERVAL = 1  # Minutes between API requests

# Load OpenSky OAuth2 credentials
with open('credentials.json', 'r') as f:
    creds = json.load(f)
    OPENSKY_CLIENT_ID = creds['clientId']
    OPENSKY_CLIENT_SECRET = creds['clientSecret']
    print(f"[DEBUG] Loaded clientId: {OPENSKY_CLIENT_ID}")
    print(f"[DEBUG] Loaded clientSecret: {OPENSKY_CLIENT_SECRET}")

def get_oauth2_token():
    data = {
        'grant_type': 'client_credentials',
        'client_id': OPENSKY_CLIENT_ID,
        'client_secret': OPENSKY_CLIENT_SECRET
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    print(f"[DEBUG] Token request payload: {data}")
    try:
        response = requests.post(TOKEN_URL, data=data, headers=headers)
        print(f"[DEBUG] Token response status: {response.status_code}")
        print(f"[DEBUG] Token response content: {response.text}")
        response.raise_for_status()
        token_data = response.json()
        return token_data['access_token'], token_data.get('expires_in', 3600)
    except Exception as e:
        print(f"[DEBUG] Exception during token request: {e}")
        if 'response' in locals():
            print(f"[DEBUG] Response content: {response.text}")
        raise

# Token cache
_token = None
_token_expiry = 0

def get_token():
    global _token, _token_expiry
    if _token is None or time.time() > _token_expiry - 60:
        print("[AUTH] Fetching new OAuth2 token...")
        _token, expires_in = get_oauth2_token()
        _token_expiry = time.time() + expires_in
    return _token

def get_jordan_polygon():
    """Get Jordan's boundary polygon from geoBoundaries"""
    try:
        response = requests.get(JORDAN_GEOJSON_URL)
        response.raise_for_status()
        data = response.json()
        
        # Extract the polygon from the GeoJSON
        if not data.get('features'):
            raise ValueError("No boundary data found for Jordan")
            
        # Get the first feature's geometry
        geometry = data['features'][0]['geometry']
        return shape(geometry)
    except Exception as e:
        print(f"Error getting Jordan polygon: {e}")
        return None

def is_point_in_jordan(point, polygon):
    """Check if a point is inside Jordan's polygon or multipolygon"""
    if polygon is None:
        return False
    if polygon.geom_type == 'Polygon':
        return polygon.contains(point)
    elif polygon.geom_type == 'MultiPolygon':
        return any(poly.contains(point) for poly in polygon.geoms)
    return False

def draw_polygon_live(ax, polygon, bbox_flights, jordan_flights, debug=False):
    """Draw or update the polygon and airplanes for debugging (live plot)"""
    ax.clear()
    if polygon is None:
        ax.set_title('No polygon to draw.')
        return
        
    # Draw the polygon
    x, y = polygon.exterior.xy
    ax.plot(x, y, color='blue', linewidth=2, label='Jordan Border')
    
    # Add OpenStreetMap basemap
    try:
        ctx.add_basemap(ax, crs="epsg:4326", source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception as e:
        print(f"Basemap error: {e}")
    
    # Plot each flight exactly once with its correct color and direction
    for flight in bbox_flights:
        if flight[5] is not None and flight[6] is not None:  # lon, lat
            point = Point(flight[5], flight[6])
            heading = flight[10]  # heading in degrees
            if heading is not None:
                # Convert heading to radians for matplotlib
                heading_rad = np.radians(heading)
                # Calculate arrow components
                dx = ARROW_LENGTH * np.sin(heading_rad)
                dy = ARROW_LENGTH * np.cos(heading_rad)
                
                if flight in jordan_flights:
                    # Inside polygon - red
                    ax.arrow(flight[5], flight[6], dx, dy, 
                            head_width=ARROW_WIDTH, head_length=ARROW_HEAD_LENGTH, 
                            fc='red', ec='black', lw=1.5,
                            label='Inside Polygon' if 'Inside Polygon' not in ax.get_legend_handles_labels()[1] else "")
                else:
                    # Outside polygon - green
                    ax.arrow(flight[5], flight[6], dx, dy, 
                            head_width=ARROW_WIDTH, head_length=ARROW_HEAD_LENGTH, 
                            fc='green', ec='black', lw=1.5,
                            label='Outside Polygon' if 'Outside Polygon' not in ax.get_legend_handles_labels()[1] else "")
            else:
                # If no heading data, plot as a dot
                if flight in jordan_flights:
                    ax.scatter(flight[5], flight[6], color='red', s=50, 
                             label='Inside Polygon' if 'Inside Polygon' not in ax.get_legend_handles_labels()[1] else "")
                else:
                    ax.scatter(flight[5], flight[6], color='green', s=50, 
                             label='Outside Polygon' if 'Outside Polygon' not in ax.get_legend_handles_labels()[1] else "")
    
    ax.set_title('Jordan Polygon and Airplanes')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    # Use the same bounding box as the API call
    ax.set_xlim(BBOX["lomin"], BBOX["lomax"])
    ax.set_ylim(BBOX["lamin"], BBOX["lamax"])
    
    # Always show legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc='upper right')
    
    # Force redraw
    ax.figure.canvas.draw()
    ax.figure.canvas.flush_events()

# Beep sound customization
BEEP_MODE = "beep"  # Options: "random", "beep", or one of the sample names below
BEEP_SAMPLES = [
    "Blow.aiff",
    "Glass.aiff",
    "Hero.aiff",
    "Submarine.aiff",
    "Funk.aiff",
    "Ping.aiff",
    "Pop.aiff"
]
BEEP_SAMPLE_PATH = "/System/Library/Sounds/"

def beep(n=1, sleep=1):
    system = platform.system()
    sound = None
    if system == "Darwin":
        if BEEP_MODE == "random":
            sound = random.choice(BEEP_SAMPLES)
        elif BEEP_MODE in [s.replace('.aiff','') for s in BEEP_SAMPLES]:
            sound = BEEP_MODE + ".aiff"
    for _ in range(n):
        if system == "Darwin":  # macOS
            if BEEP_MODE == "random" and sound:
                os.system(f'afplay {BEEP_SAMPLE_PATH}{sound}')
            elif BEEP_MODE == "beep":
                os.system('say beep')
            elif sound:
                os.system(f'afplay {BEEP_SAMPLE_PATH}{sound}')
            else:
                os.system(f'afplay {BEEP_SAMPLE_PATH}Blow.aiff')
        else:  # Linux or fallback
            print("\a", end='', flush=True)
        time.sleep(sleep)

def get_flights(params=None):
    try:
        print(f"[DEBUG] Requesting flights with params: {params}")
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            API_URL,
            params=params,
            timeout=10,
            headers=headers
        )
        # Always print rate limit info
        remaining = response.headers.get('x-rate-limit-remaining', 'unknown')
        print(f"\n[RATE LIMIT] Remaining API calls: {remaining}\n")
        response.raise_for_status()
        data = response.json()
        # Handle case where states is None or empty
        if not data or 'states' not in data or not data['states']:
            print(f"[{datetime.now()}] No flight data available")
            return []
        return data['states']
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Error fetching flights: {e}")
        if hasattr(e.response, 'status_code'):
            print(f"[DEBUG] Status code: {e.response.status_code}")
            # Try to get rate limit even on error
            remaining = e.response.headers.get('x-rate-limit-remaining', 'unknown')
            print(f"\n[RATE LIMIT] Remaining API calls: {remaining}\n")
        return []
    except (ValueError, KeyError) as e:
        print(f"[{datetime.now()}] Error parsing flight data: {e}")
        return []
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error: {e}")
        return []

def main():
    print("Starting airplane monitoring loop...\n")
    beep(2)
    print("You should have heard 2 beeps!\n")
    print(f"Using BBOX: {BBOX}")
    jordan_polygon = get_jordan_polygon()
    if jordan_polygon is None:
        print("Warning: Could not load Jordan's polygon. Falling back to bounding box.")
    else:
        print(f"Jordan polygon type: {jordan_polygon.geom_type}")
    
    # Initialize Qt application
    app = QApplication(sys.argv)
    
    plt.ion()
    # Create a larger figure
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    # Set window title
    fig.canvas.manager.set_window_title('Jordan Air Traffic Monitor')
    
    def update_flights():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bbox_flights = get_flights(BBOX)
        if bbox_flights is None:
            print(f"[{now}] Error: Could not fetch flights data")
            return
            
        print(f"[{now}] Flights in bounding box: {len(bbox_flights)}")
        print(f"[{now}] Flight Table:")
        print(f"{'Callsign':<10} {'Airline':<10} {'Country':<20} {'Longitude':>10} {'Latitude':>10} {'InsidePolygon':>15}")
        print('-' * 80)
        lats, lons = [], []
        jordan_flights = []
        for flight in bbox_flights:
            callsign = flight[1].strip() if flight[1] is not None else ''
            airline = callsign[:3] if len(callsign) >= 3 else ''
            country = flight[2] if flight[2] is not None else ''
            lon = flight[5]
            lat = flight[6]
            inside = False
            if lon is not None and lat is not None:
                lats.append(lat)
                lons.append(lon)
                point = Point(lon, lat)
                inside = is_point_in_jordan(point, jordan_polygon)
                status = 'YES' if inside else 'NO'
                print(f"{callsign:<10} {airline:<10} {country:<20} {lon:10.4f} {lat:10.4f} {status:>15}")
                if inside:
                    jordan_flights.append(flight)
            else:
                print(f"{callsign:<10} {airline:<10} {country:<20} {'N/A':>10} {'N/A':>10} {'N/A':>15}")
        if lats and lons:
            print('-' * 80)
            print(f"Lat range: {min(lats):.4f} to {max(lats):.4f}")
            print(f"Lon range: {min(lons):.4f} to {max(lons):.4f}")
        print(f"[{now}] Flights in Jordan polygon: {len(jordan_flights)}")
        print(f"[{now}] 📍 Flights over Jordan (polygon): {len(jordan_flights)}")
        draw_polygon_live(ax, jordan_polygon, bbox_flights, jordan_flights)
        plt.pause(0.5)
        # Beeping logic based on the count
        if len(jordan_flights) == 3:
            beep(1)
        elif len(jordan_flights) == 2:
            beep(2)
        elif len(jordan_flights) == 1:
            beep(3)
        elif len(jordan_flights) == 0:
            print("No airplanes detected over Jordan. Beeping 10 times...")
            beep(10)
    
    # Create a timer that calls update_flights every INTERVAL minutes
    timer = QTimer()
    timer.timeout.connect(update_flights)
    timer.start(INTERVAL * 60 * 1000)  # Convert minutes to milliseconds
    
    # Run initial update
    update_flights()
    
    # Start the Qt event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()