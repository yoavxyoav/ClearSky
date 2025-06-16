import requests
import time
from datetime import datetime
import platform
import os
import json
from shapely.geometry import Point, shape, MultiPolygon
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

API_URL = "https://opensky-network.org/api/states/all"
JORDAN_GEOJSON_URL = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/JOR/ADM0/geoBoundaries-JOR-ADM0.geojson"

# Bounding box for Jordan (tight fit to polygon)
BBOX = {
    "lamin": 29.183,  # min latitude
    "lamax": 33.375,  # max latitude
    "lomin": 34.958,  # min longitude
    "lomax": 39.302   # max longitude
}

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

def draw_polygon_live(ax, polygon, bbox_flights, jordan_flights):
    """Draw or update the polygon and airplanes for debugging (live plot)"""
    ax.clear()
    if polygon is None:
        ax.set_title('No polygon to draw.')
        return
    x, y = polygon.exterior.xy
    ax.plot(x, y, color='blue', linewidth=2)
    # Plot airplanes in the bounding box but outside the polygon in green
    for flight in bbox_flights:
        if flight[5] is not None and flight[6] is not None:
            point = Point(flight[5], flight[6])
            if not is_point_in_jordan(point, polygon):
                ax.scatter(flight[5], flight[6], color='green', s=50)
    # Plot airplanes inside the polygon in red
    for flight in jordan_flights:
        if flight[5] is not None and flight[6] is not None:
            ax.scatter(flight[5], flight[6], color='red', s=50)
    ax.set_title('Jordan Polygon and Airplanes')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.set_xlim(34.5, 39.5)
    ax.set_ylim(28.5, 34.5)
    ax.figure.canvas.draw()
    ax.figure.canvas.flush_events()

def beep(n=1):
    system = platform.system()

    for _ in range(n):
        if system == "Darwin":  # macOS
            os.system('say "beep"')
        else:  # Linux or fallback
            print("\a", end='', flush=True)
        time.sleep(0.5)

def get_flights(params=None):
    try:
        print(f"[DEBUG] Requesting flights with params: {params}")
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("states", [])
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching flights: {e}")
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
    plt.ion()
    fig, ax = plt.subplots()
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bbox_flights = get_flights(BBOX)
        print(f"[{now}] Flights in bounding box: {len(bbox_flights)}")
        print(f"[{now}] Flight Table:")
        print(f"{'Callsign':<10} {'Airline':<10} {'Country':<20} {'Longitude':>10} {'Latitude':>10} {'InsidePolygon':>15}")
        print('-' * 80)
        lats, lons = [], []
        jordan_flights = []
        for flight in bbox_flights:
            callsign = flight[1].strip() if flight[1] else ''
            airline = callsign[:3] if len(callsign) >= 3 else ''
            country = flight[2] if flight[2] else ''
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
        time.sleep(60)

if __name__ == "__main__":
    main()