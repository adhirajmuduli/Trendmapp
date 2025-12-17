# animation_worker.py

import pandas as pd
from datetime import datetime
from generate_video import generate_animation_video
from db import AsyncSessionLocal, Station, Parameter, Measurement
from sqlalchemy import select, and_

async def generate_interpolated_video(parameter: str, start_date: datetime, end_date: datetime, fps: int, frames_per_transition: int, cmap: str) -> bytes:
    """
    Orchestrates the loading of DB data and generates animated video bytes.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                Station.latitude,
                Station.longitude,
                Measurement.sampled_at,
                Measurement.value
            )
            .join(Measurement, Station.id == Measurement.station_id)
            .join(Parameter, Parameter.id == Measurement.parameter_id)
            .where(
                and_(
                    Parameter.name == parameter,
                    Measurement.sampled_at >= start_date,
                    Measurement.sampled_at <= end_date,
                    Measurement.value.isnot(None),
                )
            )
        )

        result = await session.execute(stmt)
        rows = result.all()

    df = pd.DataFrame(rows, columns=["latitude", "longitude", "sampled_at", "value"])
    if df.empty:
        raise ValueError("No data available for selected range and parameter")

    duration_seconds = (len(df["sampled_at"].unique()) - 1) * frames_per_transition // fps
    output_path = generate_animation_video(
        df,
        output_name="animation.mp4",
        fps=fps,
        duration_seconds=duration_seconds
    )

    with open(output_path, "rb") as f:
        return f.read()
