# Frontend (HTML, JS, CSS)

## /templates

### templates/index.html
- **Purpose**
  - Main application UI for map-based visualization, uploads, view controls, and video generation launcher (@templates/index.html#1-187).
- **Key components**
  - Controls: file uploads (CSV/Excel, boundary GeoJSON), view mode toggle (Markers/Heatmap), method select (IDW/KDE), bandwidth/opacity sliders, colormap select, station toggle, heatmap tiles, prev/next navigation.
  - Map container `#map` with legend `#map-legend` and overlay `#loading-overlay`.
  - Video panel form for animation parameters (parameter, date range, fps, frames/transition) shown on demand.
  - Loads `static/js/app.js` and third-party CDNs (Leaflet, Handsontable, html2canvas, leaflet-image) (@templates/index.html#7-34, #184-186).
- **Inputs / Outputs / Side effects**
  - Inputs: user file selections; UI control states; interacts with backend endpoints.
  - Outputs: DOM updates; initiates fetches handled in app.js.
  - Side effects: none beyond DOM structure.
- **Assumptions / Constraints / TODOs**
  - Requires backend routes `/upload`, `/generate-heatmap`, `/api/animate`, `/upload-boundary`, `/static/data/export.geojson`.
- **Cross-file dependencies**
  - Works with `static/js/app.js`, `static/css/style.css`, `static/js/data_entry.js` indirectly via `/data-entry` link.

### templates/data-entry.html
- **Purpose**
  - Full-screen data table editor using AG Grid for viewing/editing pivoted measurements (@templates/data-entry.html#1-119).
- **Key components**
  - Toolbar with Back, status, and actions: Add Parameter, Add Timestamp, Save & Return, Cancel.
  - Container `#data-grid` for AG Grid; modal `#inputModal` for prompts.
  - Loads AG Grid CDN, Bootstrap, and `static/js/data_entry.js`.
- **Inputs / Outputs / Side effects**
  - Inputs: user edits, header double-clicks, toolbar actions.
  - Outputs: none directly; data_entry.js handles persistence.
- **Assumptions / Constraints**
  - Requires `/api/table` GET/POST; timestamp format YYYY-MM-DD.
- **Cross-file dependencies**
  - Uses `static/js/data_entry.js` which talks to `routes/data_api.py`.

### templates/animation.html
- **Purpose**
  - Standalone page to generate and preview animated heatmaps (@templates/animation.html#1-226).
- **Key components**
  - Form inputs: parameter, start/end dates, fps, frames per transition, colormap.
  - Video player and download link.
- **Inputs / Outputs / Side effects**
  - Inputs: form submission builds JSON payload.
  - Outputs: sets video source/download URL from `/api/animate` response blob.
  - Side effects: reads `sessionStorage.uploadedFilename`.
- **Assumptions / Constraints**
  - Requires successful prior upload to set `uploadedFilename`.
- **Cross-file dependencies**
  - Talks to `/api/animate`; style from `static/css/style.css`.

## /static/js

### static/js/app.js
- **Purpose**
  - Main frontend controller class `HeatmapApp` for map, uploads, heatmap generation, video overlay, legend, and interactions (@static/js/app.js#1-400, #401-1174).
- **Key classes/functions**
  - `class HeatmapApp` with state (map, layers, data, globalMin/Max, tiles, video overlay) and `dom` refs.
  - `init()`, `initMap()` create Leaflet map, controls, boundary load; `addEventListeners()` wires UI, upload, video, tiles.
  - `uploadFile()` POST `/upload` with FormData; stores response and filename in `sessionStorage`.
  - `generateHeatmap()` POST `/generate-heatmap` with data and rendering params; manages image overlays and tiles.
  - `generateVideo()` POST `/api/animate`; adds `L.videoOverlay` and allows download/play.
  - `showHeatmapAt(index)`, `updateLegend(ts, colormap)` fetches `/legend/<ts>.png?min&max&colormap` and updates labels.
  - Marker management: `displayMarkers`, `clearMarkers`, `showBlackDots`, `clearBlackDots`.
  - Deletion: `deleteMeasurement({latitude, longitude, parameter, timestamp})` DELETE `/api/measurement` and refresh.
  - UX helpers: `showStatus`, `showLoading`, `downloadMapSnapshot`, `copyMapToClipboard`.
- **Inputs / Outputs / Side effects**
  - Inputs: file selection; control values; clicks on tiles and buttons.
  - Outputs: DOM updates, Leaflet layers, sessionStorage (`uploadedFilename`, `uploadedData`, `boundaryPath`).
  - Side effects: network calls to backend; creates object URLs for video; clipboard operations.
- **Assumptions / Constraints / TODOs**
  - Expects backend to return JSON with `data`, `global_min/max`, `timestamp_columns`, `filename`.
  - Uses fixed grid extents from GeoJSON bounds; relies on `leaflet-image` for snapshot.
  - Some methods reference variables (`idx` in `fetchSlice`) that appear undefined, suggesting dead/incomplete code for that path.
- **Cross-file dependencies**
  - Talks to `app.py` endpoints and `routes/data_api.py` delete API; consumes `static/data/export.geojson` or uploaded boundary.

### static/js/data_entry.js
- **Purpose**
  - AG Grid logic to load pivoted data, dynamically generate column groups, handle clipboard, and save unpivoted edits.
- **Key functions**
  - `generateColumnDefs(pivotedData)` builds parameter groups with date children from API keys (@static/js/data_entry.js#9-80).
  - `loadAndConfigureGrid()` GET `/api/table`, set column defs and row data, preloads empty rows (@static/js/data_entry.js#85-116).
  - `initializeGrid()` sets grid options and initializes grid (@static/js/data_entry.js#121-200).
  - `saveTableData()` unpivots grid to array of `{latitude, longitude, parameter, timestamp, value}` and POSTs to `/api/table` (@static/js/data_entry.js#205-286).
  - UI helpers: `showInputModal`, `addParameterColumn`, `addTimestampColumn`, `handleHeaderDoubleClick`, `getContextMenuItems`, `deleteColumnOrGroup`, `setupEventListeners`.
- **Inputs / Outputs / Side effects**
  - Inputs: user edits in grid; header/toolbar actions.
  - Outputs: Grid state updates; POST unpivoted data to backend.
  - Side effects: Navigates back to `/` after save; prompts via Bootstrap modal.
- **Assumptions / Constraints / TODOs**
  - Column naming convention `Parameter_YYYY-MM-DD` assumed; timestamp parsing for sorting.
  - Adds 500 empty rows as a workaround to facilitate editing.
- **Cross-file dependencies**
  - Uses `routes/data_api.py` endpoints; displayed within `templates/data-entry.html`.

## /static/css

### static/css/style.css
- **Purpose**
  - Styling for layout, controls, tiles, legend, loading overlay, responsive design (@static/css/style.css#1-648).
- **Key components**
  - CSS variables, container/layout for control panel and map, heatmap tiles, buttons, toggles, sliders, legend styles, loading overlay.
- **Inputs / Outputs / Side effects**
  - Purely declarative; no runtime side effects.
- **Assumptions / Constraints**
  - Designed to pair with HTML structure from `templates/index.html` and Leaflet map elements.
- **Cross-file dependencies**
  - Used by `index.html` and `animation.html`.
