import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import imageio
import io
import json
from shapely.geometry import shape
from scipy.interpolate import Rbf, interp1d
from PIL import Image
from db import get_db_session, Measurement, Station, Parameter
from sqlalchemy import select

LAKE_BOUNDARY_GEOJSON = 'static/data/export.geojson'

async def fetch_data_for_animation(parameter: str, start_date, end_date, filename):
    """
    Loads user-uploaded Excel/CSV file from disk, reshapes to long format, 
    and filters it for the selected time range. Parameter is used only as a label.
    """
    file_path = f"uploads/{filename}"
    
    # Determine file type and read accordingly
    if filename.lower().endswith(('.xls', '.xlsx')):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # Standardize column names
    df.columns = df.columns.str.strip().str.lower()
    
    # Handle wide format data (first two columns are lat/lon, rest are timestamps)
    # This logic mirrors app.py's processing
    if len(df.columns) > 2 and 'latitude' not in df.columns and 'longitude' not in df.columns:
        # Assume first two columns are lat/lon
        lat_col = df.columns[0]
        lon_col = df.columns[1]
        timestamp_cols = df.columns[2:]
        
        df = df.rename(columns={
            lat_col: 'latitude',
            lon_col: 'longitude'
        })
        
        # Melt to long format
        df = df.melt(
            id_vars=['latitude', 'longitude'],
            value_vars=timestamp_cols,
            var_name='sampled_at',
            value_name='value'
        )
    elif 'latitude' in df.columns and 'longitude' in df.columns:
        # Check if it's already long format or wide format with explicit lat/lon names
        non_timestamp_cols = {'latitude', 'longitude', 'value', 'species', 'count'}
        timestamp_cols = [col for col in df.columns if col not in non_timestamp_cols]
        
        if timestamp_cols and 'value' not in df.columns:
             # It's wide format with labeled lat/lon
            df = df.melt(
                id_vars=['latitude', 'longitude'],
                value_vars=timestamp_cols,
                var_name='sampled_at',
                value_name='value'
            )
        elif 'timestamp' in df.columns:
             df = df.rename(columns={'timestamp': 'sampled_at'})

    # Ensure we have the required columns
    required_cols = {'latitude', 'longitude', 'sampled_at', 'value'}
    if not required_cols.issubset(df.columns):
         # Fallback for 'count' instead of 'value'
        if 'count' in df.columns:
            df = df.rename(columns={'count': 'value'})
        
        if not required_cols.issubset(df.columns):
            raise ValueError(f"Data missing required columns. Found: {df.columns}")

    # Convert date strings to datetime
    df['sampled_at'] = pd.to_datetime(df['sampled_at'], errors='coerce')
    
    # Convert value to numeric and drop invalid
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df.dropna(subset=['sampled_at', 'value', 'latitude', 'longitude'], inplace=True)

    # Filter by date
    mask = (df['sampled_at'] >= start_date) & (df['sampled_at'] <= end_date)
    filtered = df.loc[mask].copy()

    return filtered

def generate_spatiotemporal_video(df: pd.DataFrame, fps: int, frames_per_transition: int, cmap: str, boundary_path: str = 'static/data/export.geojson') -> bytes:
    """Generates a spatiotemporally interpolated video from measurement data."""
    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    df['sampled_at'] = pd.to_datetime(df['sampled_at'])
    unique_dates = sorted(df['sampled_at'].unique())

    if len(unique_dates) < 2:
        raise ValueError("At least two distinct timestamps are required for animation.")

    # --- 1. Spatial Interpolation (RBF) for each time slice ---
    # Handle path: if it starts with /, remove it to make it relative to CWD (project root)
    if boundary_path.startswith('/') or boundary_path.startswith('\\'):
        boundary_path = boundary_path.lstrip('/\\')
        
    with open(boundary_path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    if gj.get('type') == 'FeatureCollection':
        geom_obj = gj['features'][0]['geometry']
    elif gj.get('type') == 'Feature':
        geom_obj = gj['geometry']
    else:
        geom_obj = gj
    lake_boundary = shape(geom_obj)
    min_lon, min_lat, max_lon, max_lat = lake_boundary.bounds
    grid_x, grid_y = np.mgrid[min_lon:max_lon:300j, min_lat:max_lat:300j]

    spatial_fields = []
    for date in unique_dates:
        slice_df = df[df['sampled_at'] == date]
        if slice_df.shape[0] < 4: # RBF needs a minimum number of points
            continue
        
        rbf_interpolator = Rbf(slice_df['longitude'], slice_df['latitude'], slice_df['value'], function='cubic')
        field = rbf_interpolator(grid_x, grid_y)
        spatial_fields.append(field)

    if len(spatial_fields) < 2:
        raise ValueError("Could not generate enough spatial fields for interpolation.")

    # --- 2. Temporal Interpolation (Cubic Spline) between fields ---
    spatial_fields = np.array(spatial_fields)
    time_points = np.arange(len(spatial_fields))
    total_frames = (len(spatial_fields) - 1) * frames_per_transition
    interpolated_time_points = np.linspace(0, len(spatial_fields) - 1, total_frames)

    # Create a cubic interpolator for each pixel in the grid
    interpolator = interp1d(time_points, spatial_fields, axis=0, kind='cubic')
    interpolated_fields = interpolator(interpolated_time_points)

    # --- 3. Render Frames ---
    video_frames = []
    norm = plt.Normalize(vmin=df['value'].min(), vmax=df['value'].max())
    
    for field in interpolated_fields:
        fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
        ax.set_axis_off()
        ax.imshow(field.T, extent=(min_lon, max_lon, min_lat, max_lat), origin='lower', cmap=cmap, norm=norm)
        
        # Clip to lake boundary
        patch = plt.Polygon(lake_boundary.exterior.coords, transform=ax.transData)
        ax.images[0].set_clip_path(patch)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        buf.seek(0)
        video_frames.append(Image.open(buf))

    # --- 4. Encode Video ---
    with io.BytesIO() as video_buffer:
        imageio.mimsave(video_buffer, video_frames, format='mp4', fps=fps)
        video_bytes = video_buffer.getvalue()

    return video_bytes
