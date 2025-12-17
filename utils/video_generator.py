import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import get_cmap
from matplotlib import cm
import cv2
from datetime import datetime
from scipy.interpolate import interp1d
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import geopandas as gpd

# Path constants
STATIC_VIDEO_DIR = 'static/animations'
LAKE_BOUNDARY_GEOJSON = 'static/data/export.geojson'

# Ensure output directory exists
os.makedirs(STATIC_VIDEO_DIR, exist_ok=True)

def generate_animation_video(df, output_name="animation.mp4", fps=30, duration_seconds=10):
    """
    Generates an interpolated video of heatmap transitions over time.

    Args:
        df (DataFrame): Contains columns [latitude, longitude, sampled_at, value].
        output_name (str): Filename of output video.
        fps (int): Frames per second.
        duration_seconds (int): Total duration of the video in seconds.

    Returns:
        str: Path to generated video.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    df['sampled_at'] = pd.to_datetime(df['sampled_at'])
    df.sort_values('sampled_at', inplace=True)

    frame_count = fps * duration_seconds
    timestamps = df['sampled_at'].sort_values().unique()
    times_numeric = (timestamps - timestamps[0]).astype('timedelta64[s]').astype(float)
    full_time_range = np.linspace(times_numeric.min(), times_numeric.max(), frame_count)

    # Unique coordinates grid
    points = df[['latitude', 'longitude']].drop_duplicates().reset_index(drop=True)

    # Prepare interpolated matrix: for each point, interpolate over time
    interpolated_frames = []
    for _, row in points.iterrows():
        sub_df = df[(df['latitude'] == row.latitude) & (df['longitude'] == row.longitude)]
        if sub_df.empty: continue

        t = (sub_df['sampled_at'] - timestamps[0]).astype('timedelta64[s]').astype(float)
        v = sub_df['value'].values

        if len(np.unique(t)) < 2:
            continue  # Cannot interpolate with <2 time points

        interp_func = interp1d(t, v, kind='linear', bounds_error=False, fill_value="extrapolate")
        v_interp = interp_func(full_time_range)
        for i, val in enumerate(v_interp):
            if len(interpolated_frames) <= i:
                interpolated_frames.append([])
            interpolated_frames[i].append((row.latitude, row.longitude, val))

    # Load lake boundary to use for masking
    lake = gpd.read_file(LAKE_BOUNDARY_GEOJSON).geometry.iloc[0]
    bounds = lake.bounds
    min_lon, min_lat, max_lon, max_lat = bounds

    # Set resolution and canvas size
    grid_res = 400
    width, height = 800, 800
    dpi = 100
    fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)

    video_path = os.path.join(STATIC_VIDEO_DIR, output_name)
    writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

    cmap = get_cmap('plasma')
    norm = Normalize()

    for frame in interpolated_frames:
        ax.clear()
        lat, lon, val = zip(*frame)
        lat = np.array(lat)
        lon = np.array(lon)
        val = np.array(val)
        norm.autoscale(val)

        # Plot background lake
        ax.set_xlim(min_lon, max_lon)
        ax.set_ylim(min_lat, max_lat)
        ax.set_aspect('equal')
        lake_patch = gpd.GeoSeries([lake]).plot(ax=ax, color='#d0f0ff', edgecolor='black', linewidth=0.5)

        # Plot heatmap as scatter for now (can evolve to KDE)
        colors = cmap(norm(val))
        ax.scatter(lon, lat, c=colors, s=30, edgecolor='none')
        ax.axis('off')

        fig.canvas.draw()
        img = np.frombuffer(fig.canvas.tostring_rgb(), dtype='uint8')
        img = img.reshape(fig.canvas.get_width_height()[::-1] + (3,))
        writer.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))

    writer.release()
    plt.close(fig)

    return video_path
