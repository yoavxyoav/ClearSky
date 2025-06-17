# ClearSky: Jordan Air Traffic Monitor

ClearSky is a Python application that visualizes real-time air traffic over Jordan using the OpenSky Network API and OpenStreetMap basemaps. It fetches live flight data, highlights flights inside and outside Jordan's borders, and provides a beautiful, interactive map with live updates.

## Features
- **Live Air Traffic Visualization**: See all flights in and around Jordan, updated every minute.
- **Polygonal Border Detection**: Flights are classified as inside or outside Jordan using precise geo-boundary data.
- **OpenStreetMap Basemap**: High-quality map tiles for geographic context.
- **Interactive Plot**: Resize, move, and interact with the window while data updates.
- **OAuth2 Authentication**: Secure access to the OpenSky API.
- **Audible Alerts**: Custom beeps based on the number of flights over Jordan.
- **Debug Output**: Console logs for API rate limits, errors, and flight tables.

## Requirements
- Python 3.8+
- See `requirements.txt` for all dependencies:
  - requests
  - shapely
  - matplotlib
  - contextily
  - pyproj
  - PyQt5

## Installation
1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd ClearSky
   ```
2. **Install dependencies (preferably with [uv](https://github.com/astral-sh/uv))**:
   ```bash
   uv pip install -r requirements.txt
   # or, if you must:
   pip install -r requirements.txt
   ```
3. **Add your OpenSky credentials:**
   - Create a `credentials.json` file in the project root with the following format:
     ```json
     {
       "clientId": "YOUR_CLIENT_ID",
       "clientSecret": "YOUR_CLIENT_SECRET"
     }
     ```

## Usage
Run the main script:
```bash
python clearsky.py
```
- The application will open a window showing Jordan's border and all flights in the bounding box.
- Flights inside the polygon are shown in red, outside in green.
- The console will show a table of flights and API rate limit info.
- Audible beeps indicate the number of flights over Jordan.

## Customization
- **Bounding Box & Padding**: Adjust `PADDING` in `clearsky.py` to change the area of interest.
- **Update Interval**: Change `INTERVAL` (in minutes) for how often data is refreshed.
- **Arrow/Marker Settings**: Tweak `ARROW_LENGTH`, `ARROW_WIDTH`, etc. for visualization style.

- **API Rate Limits**: The OpenSky API enforces rate limits. Watch the console for `[RATE LIMIT]` messages.

## File Structure
- `clearsky.py` — Main application logic
- `requirements.txt` — Python dependencies
- `.gitignore` — Files and folders ignored by git
- `credentials.json` — Your (private) OpenSky credentials (not tracked by git)


*Created for the one and only Ultimate Boss. All bugs are the user's fault.*
