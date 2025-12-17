import os
import io
import tempfile
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from PIL import Image
from datetime import datetime
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel

from db import AsyncSessionLocal, Station, Parameter, Measurement
from sqlalchemy import select, and_

VIDEO_WIDTH = 800
VIDEO_HEIGHT = 800


def fetch_lake_boundary():
    gdf = gpd.read_file("static/data/export.geojson")
    return gdf.geometry.iloc[0]


def generate_grid(bounds, res=300):
    minx, miny, maxx, maxy = bounds
    x = np.linspace(minx, maxx, res)
    y = np.linspace(miny, maxy, res)
    grid_x, grid_y = np.meshgrid(x, y)
    return grid_x, grid_y, np.vstack([grid_x.ravel(), grid_y.ravel()]).T


async def fetch_measurements(session, parameter, start, end):
    stmt = select(
        Station.latitude,
        Station.longitude,
        Measurement.sampled_at,
        Measurement.value,
    ).select_from(Measurement).join(Station).join(Parameter).where(
        and_(
            Parameter.name == parameter,
            Measurement.sampled_at >= start,
            Measurement.sampled_at <= end,
            Measurement.value.isnot(None),
        )
    )
    rows = await session.execute(stmt)
    return pd.DataFrame(rows.fetchall(), columns=["lat", "lon", "date", "value"])


async def generate_parameter_animation(parameter: str, start_date: str, end_date: str, fps: int = 30) -> bytes:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    async with AsyncSessionLocal() as session:
        df = await fetch_measurements(session, parameter, start, end)

    if df.empty:
        raise ValueError("No data for selected parameter and date range")

    df["date"] = pd.to_datetime(df["date"])
    df_grouped = df.groupby("date")

    lake = fetch_lake_boundary()
    grid_x, grid_y, grid_pts = generate_grid(lake.bounds)

    dates = sorted(df["date"].unique())
    frames_per_pair = fps

    interpolated_frames = []
    norm = mcolors.Normalize()
    cmap = cm.get_cmap("viridis")

    for i in range(len(dates) - 1):
        t0, t1 = dates[i], dates[i + 1]
        d0 = df_grouped.get_group(t0)
        d1 = df_grouped.get_group(t1)

        for alpha in np.linspace(0, 1, frames_per_pair):
            blend = pd.merge(d0, d1, on=["lat", "lon"], suffixes=("_0", "_1"))
            blend["interp"] = blend["value_0"] * (1 - alpha) + blend["value_1"] * alpha

            kernel = RBF(0.1) + WhiteKernel(0.1)
            gp = GaussianProcessRegressor(kernel=kernel, alpha=1e-2)
            gp.fit(blend[["lon", "lat"]], blend["interp"])
            pred = gp.predict(grid_pts)
            grid_vals = pred.reshape(grid_x.shape)

            fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
            ax.set_axis_off()
            ax.set_xlim(lake.bounds[0], lake.bounds[2])
            ax.set_ylim(lake.bounds[1], lake.bounds[3])
            ax.imshow(
                grid_vals,
                cmap=cmap,
                extent=(lake.bounds[0], lake.bounds[2], lake.bounds[1], lake.bounds[3]),
                origin="lower",
                interpolation="gaussian",
                norm=norm,
            )
            lake.boundary.plot(ax=ax, color="black", linewidth=1)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
            plt.close(fig)
            buf.seek(0)
            interpolated_frames.append(Image.open(buf).convert("RGB"))

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_path = tmp.name

    import imageio
    imageio.mimsave(video_path, interpolated_frames, fps=fps)

    with open(video_path, "rb") as f:
        video_bytes = f.read()
    os.remove(video_path)

    return video_bytes

