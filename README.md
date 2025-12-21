---
title: Trendsmapp
emoji: 📚
colorFrom: pink
colorTo: red
sdk: docker
pinned: false
license: mit
short_description: Provides trendmaps for spatial visualization of data.
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# Trendsmapp

**Short description.** Trendsmapp is an open source interactive Quart + Leaflet application for spatiotemporal analysis of geographical observations. It ingests CSV/Excel measurements, interpolates heatmaps within a GeoJSON boundary, and exports static or animated visualizations suitable for ecological monitoring studies, data intensity visualization on a map, and spatial trends monitoring.

## Statement of Need

This project was primarily developed as a part of project concerning coastal lagoons such as Chilika, which experience rapid ecological shifts that are hard to monitor with sparse in-situ stations. Scientists typically receive semi-structured spreadsheets containing station coordinates and timestamped measurements; turning those data into defensible spatial products requires a reproducible workflow that handles cleaning, interpolation, and visual QA. Trendsmapp addresses this gap by combining well-tested interpolation (inverse distance weighting, Gaussian kernels, and RBF+cubic splines for animation) with a map-first UI, enabling researchers to iterate on spatial hypotheses, archive runs, and share reproducible figures for publications such as lagoon health bulletins or environmental impact assessments.

But it is not limited to that. Although the default map is that of Chilika lagoon, users can import their own `.geojson` files (from sources such as openstreetmap) concerning their geographical area of interest, and provide data for various co-ordinates and analyze the data distribution. It can also be helpful for other fields such as news reporting or weather forecasting services, where heatmaps are frequently used to convey poll distribution, population density, temperature and humidity distribution. 

## Implemented Features

1. **File ingestion and validation.** Upload CSV/Excel files, auto-detect latitude/longitude columns, melt wide timestamp tables into long form, and run schema/value checks before visualization (@app.py#152-310).
2. **Heatmap generation.** Generate masked PNG heatmaps per timestamp using IDW or KDE within a supplied GeoJSON boundary, store them as base64 tiles, and manage layer navigation/downloads on the client (@app.py#340-566, @static/js/app.js#667-1177).
3. **Interactive map UI.** Leaflet front-end toggles between markers (these represent dots of relative sizes, corresponding to the co-ordinate the data is provided) and heatmaps, adjusts opacity /bandwidth (typically, the radius upto which interpolation is to be done. Higher the density of data, the lower the bandwidth is to be selected), shows station markers (dots showing the input co-ordinates), and supports copy-to-clipboard / white-background downloads (@static/js/app.js).
4. **Video synthesis.** `/api/animate` plus `utils/animation_generator.py` build smooth MP4 animations via radial basis spatial interpolation and cubic temporal interpolation clipped to the lagoon mask.
5. **Data entry and persistence.** Async SQLAlchemy models with CRUD APIs (`routes/data_api.py`) power the spreadsheet UI, enabling collaborative edits that persist to PostgreSQL.
6. **Legend + boundary tooling.** Server-side legend endpoint and boundary uploader keep rendered products consistent throughout the session.

## Installation

**If you just want the results**; don't bother with all the technalities below, just visit the [hosted_site](https://huggingface.co/spaces/Takerupandclose/Trendsmapp), and test your data by following the procedures mentioned under `Usage` section.


**If you want to run locally:**

1. **Clone and set up Python environment**
```bash
git clone https://github.com/adhirajmuduli/Trendmapp.git
cd Trendmapp
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```
2. **Configure environment variables (Option B).** Create a `.env` (or reuse `oink.env`) containing at minimum:
```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<db>?sslmode=require
```
For the managed NeonDB instance, paste the provided connection string exactly as issued by Neon (e.g., `postgresql+asyncpg://neondb_owner:...@.../neondb?sslmode=require`). Do **not** hardcode secrets in the codebase; keep them in your environment file.
3. **Install geospatial system deps.** On Debian/Ubuntu use `sudo apt-get install gdal-bin libproj-dev`. On Windows, install GDAL wheels compatible with your Python version (see [https://www.lfd.uci.edu/~gohlke/pythonlibs/](https://www.lfd.uci.edu/~gohlke/pythonlibs/)).
4. **Run the server**
```bash
hypercorn app:app --bind 0.0.0.0:7860 --reload
```
or `python app.py` for Quart’s dev server.


## Usage (with Example Data)

1. Launch the app and navigate to `http://localhost:7860`.
2. Click **Upload Data**, select `Testfile.xlsx` (ships with repo), and wait for the success toast indicating parsed rows and global min/max.
3. Adjust **Bandwidth** (km) and **Opacity**, then click **Generate Visualization** → **Generate Heatmaps**. Use the **Prev/Next** buttons or gallery tiles to cycle through timestamps.
4. Toggle **Show Markers** or **Show Heatmap** to compare raw station values with interpolated rasters.
5. Press the download button (map toolbar) to save the current heatmap (PNG with white background) or the **Copy** button to place the figure on your clipboard.
6. Switch to the **Animation** card, fill the parameter/date range, FPS, and smoothing, and submit to receive an MP4 download generated by `/api/animate`.

## Input Data Format

Trendsmapp accepts two equivalent schemas:

| Column | Description | Required |
| --- | --- | --- |
| `latitude`, `longitude` | Decimal degrees (WGS84) | Yes |
| `timestamp` | ISO 8601 string or Excel-style column header | Required (long format) |
| `value` | Numeric measurement | Yes |
| `measurement` / `parameter` | Optional label | Optional |

For **wide** spreadsheets (default export from lagoon monitoring campaigns):

```
latitude,longitude,2023-08-01,2023-08-15,2023-09-01
19.75,85.32,12.5,13.1,12.2
```

The uploader renames the first two columns to latitude/longitude and melts each timestamp column into long form automatically (@app.py#176-223). Missing or non-numeric values are dropped during cleaning.

## Example Workflow

1. **Data ingestion.** Field team exports an Excel workbook (`.xlsx` file) of say a parameter -- nutrient concentrations; scientists verify headers match the latitude/longitude/timestamps convention. (See the `testfile.xlsx` provided in the repo for clarity - it was also the test-data used.)
2. **Upload + QA.** The upload endpoint validates ranges, reports counts, and stores the cleaned dataset plus global minima and maxima in the server session for reuse (generating the legened, as well as heatmap color assignment).
3. **Boundary management.** Analysts upload a study-area GeoJSON (or rely on `static/data/export.geojson`) and fit the Leaflet map to its bounds. These files define the area over which the heatmap mask is to be clipped. 
One can search for their area and obtain their geojson via ***openstreetmap*** or other related databases for larger files.
4. **Heatmap iteration.** Researchers can try multiple interpolation methods (IDW/KDE), coloring schemas (turbo, inferno, etc.), bandwith and opacity as they see fit according to their density of data. For denser data distribution, it is recommended to use lower bandwidth and color schemes with lesser variation over the gradient.
Bookmarking visualizations with the gallery and then downloading it, one can save their results.
5. **Temporal storytelling.** `/api/animate` interpolates intermediate frames, producing MP4s that summarize eutrophication trends over the sampled months.
6. **Data stewardship.** Via `/api/table`, teams correct outliers or add late measurements through the AG Grid UI, backed by PostgreSQL for multi-user persistence.

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Frontend (Leaflet + vanilla JS)                                            │
│  • static/js/app.js: map, UI handlers, heatmap tiles, downloads            │
│  • static/js/data_entry.js: AG Grid CRUD over REST endpoints               │
│  • templates/index.html / data-entry.html: layout + controls               │
└────────────────────────────────────────────────────────────────────────────┘
            │ fetch/upload (JSON, multipart)
┌────────────────────────────────────────────────────────────────────────────┐
│ Backend (Quart)                                                            │
│  • app.py: upload parsing, heatmap generation, legend, boundary uploads    │
│  • routes/data_api.py: parameter/timestamp/table CRUD                      │
│  • routes/animation_api.py: animation orchestration                        │
└────────────────────────────────────────────────────────────────────────────┘
            │ async ORM
┌────────────────────────────────────────────────────────────────────────────┐
│ Persistence                                                                │
│  • db.py: Async SQLAlchemy engine + models (Station, Parameter, Measurement)│
│  • PostgreSQL (NeonDB connection via DATABASE_URL)                         │
└────────────────────────────────────────────────────────────────────────────┘
            │ offline utilities
┌────────────────────────────────────────────────────────────────────────────┐
│ Utils                                                                       │
│  • utils/animation_generator.py: RBF + cubic spline animation pipeline      │
│  • utils/video_generator.py: alternative OpenCV scatter renderer            │
│  • utils/animation_worker.py: (optional) async DB-driven animator           │
└────────────────────────────────────────────────────────────────────────────┘

External dependencies include Quart, SQLAlchemy async stack, pandas, numpy, scipy, scikit-learn, shapely, geopandas, imageio, matplotlib, and Leaflet/OpenCV on the frontend/backend respectively (`requirements.txt`).

## License

This project is distributed under the MIT License (see [LICENSE](./LICENSE)).

## Citation

If you use Trendsmapp in academic work, please cite it as:

```

```

Muduli A., Muduli PK. (2025). Trendsmapp: Spatiotemporal heatmaps for lagoon monitoring (Version 1.0) [Computer software]. https://github.com/adhirajmuduli/Trendmapp

```

For JOSS citations, DOI will be updated herein once issued.

## NOTE

