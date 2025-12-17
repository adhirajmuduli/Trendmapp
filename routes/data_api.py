from __future__ import annotations

import asyncio
from datetime import datetime

from quart import Blueprint, jsonify, request, render_template, current_app
import pandas as pd
from sqlalchemy import select, insert, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import get_db_session, init_db, Station, Parameter, Measurement

bp = Blueprint("data_api", __name__)

# Quart's before_app_first_request is not supported in newer versions
# We'll use a flag to track initialization
_db_initialized = False

# ---------------------------------------------------------------------------
# Page: full-screen spreadsheet --------------------------------------------
# ---------------------------------------------------------------------------
@bp.route("/data-entry")
async def data_entry_page():
    """Serve the spreadsheet page."""
    return await render_template("data-entry.html")

# ---------------------------------------------------------------------------
# Parameters API ------------------------------------------------------------
# ---------------------------------------------------------------------------
@bp.route("/api/parameters", methods=["GET"])
async def list_parameters():
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Parameter.name).order_by(Parameter.name))
            names = [row[0] for row in result.all()]
            return jsonify(names)
    except Exception as e:
        current_app.logger.error(f"Error in list_parameters: {str(e)}")
        return jsonify({"error": "Failed to fetch parameters"}), 500

@bp.route("/api/parameters", methods=["POST"])
async def add_parameter():
    data = await request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Missing parameter name"}), 400

    try:
        async with get_db_session() as session:
            stmt = insert(Parameter).values(name=data['name'])
            await session.execute(stmt)
            return jsonify({"status": "success"})
    except IntegrityError:
        return jsonify({"error": "Parameter already exists"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Timestamps helper ---------------------------------------------------------
# ---------------------------------------------------------------------------
@bp.route("/api/timestamps", methods=["GET"])
async def list_timestamps():
    """Return sorted list of unique timestamps in ISO format."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Measurement.sampled_at)
                .distinct()
                .order_by(Measurement.sampled_at.desc())
            )
            timestamps = [row[0].isoformat() for row in result.all()]
            return jsonify(timestamps)
    except Exception as e:
        current_app.logger.error(f"Error fetching timestamps: {e}")
        return jsonify({"error": "Failed to fetch timestamps"}), 500

# ---------------------------------------------------------------------------
# Table API: fetch / upsert -------------------------------------------------
# ---------------------------------------------------------------------------
@bp.route("/api/table", methods=["GET"])
async def get_table():
    """Pivots the measurement data to create a wide table format for AG Grid."""
    try:
        async with get_db_session() as session:
            try:
                # Fetch all measurement data required for the pivot
                stmt = select(
                    Station.id,
                    Station.latitude,
                    Station.longitude,
                    Parameter.name,
                    Measurement.sampled_at,
                    Measurement.value
                ).select_from(Station) \
                 .join(Measurement, Measurement.station_id == Station.id) \
                 .join(Parameter, Parameter.id == Measurement.parameter_id)

                result = await session.execute(stmt)
                rows = result.all()

                if not rows:
                    return jsonify([])

                # Convert to pandas DataFrame for easy pivoting
                df = pd.DataFrame(rows, columns=['station_id', 'latitude', 'longitude', 'parameter', 'sampled_at', 'value'])

                # Ensure correct data types and format the date
                df['latitude'] = pd.to_numeric(df['latitude'])
                df['longitude'] = pd.to_numeric(df['longitude'])
                df['value'] = pd.to_numeric(df['value'])
                df['sampled_at'] = pd.to_datetime(df['sampled_at']).dt.strftime('%Y-%m-%d')

                # Create a combined column for the pivot operation
                df['param_date'] = df['parameter'] + '_' + df['sampled_at']

                # Pivot the table to create the desired wide format
                pivot_df = df.pivot_table(
                    index=['station_id', 'latitude', 'longitude'],
                    columns='param_date',
                    values='value'
                ).reset_index()

                # Replace NaN with None for clean JSON output
                pivot_df = pivot_df.where(pd.notnull(pivot_df), None)

                # Convert the final DataFrame to a list of dictionaries
                pivoted_data = pivot_df.to_dict(orient='records')

                return jsonify(pivoted_data)

            except SQLAlchemyError as e:
                current_app.logger.error(f"Database error in get_table: {e}")
                return jsonify({"error": "Database error occurred"}), 500

    except Exception as e:
        current_app.logger.error(f"Error in get_table: {e}")
        return jsonify({"error": "An error occurred while fetching data"}), 500

@bp.route("/api/table", methods=["POST"])
async def post_table():
    try:
        data = await request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Expected array of rows."}), 400

        async with get_db_session() as session:
            try:
                # Cache existing parameters
                param_rows = await session.execute(select(Parameter))
                param_map = {p.name: p.id for p in param_rows.scalars()}

                station_cache: dict[tuple[float, float], int] = {}
                rows_processed = 0

                for row in data:
                    try:
                        lat = float(row["latitude"])
                        lon = float(row["longitude"])
                        param_name = row["parameter"].strip()
                        date_val = datetime.fromisoformat(row["sampled_at"]).date()
                        val = float(row.get("value")) if row.get("value") is not None else None
                    except (KeyError, ValueError) as e:
                        current_app.logger.warning(f"Skipping invalid row: {row}, error: {e}")
                        continue  # skip invalid row

                    try:
                        # ensure parameter exists
                        if param_name not in param_map:
                            prm = Parameter(name=param_name)
                            session.add(prm)
                            await session.flush()
                            param_map[param_name] = prm.id

                        # ensure station exists / cached
                        key = (lat, lon)
                        if key not in station_cache:
                            st = Station(latitude=lat, longitude=lon)
                            session.add(st)
                            await session.flush()
                            station_cache[key] = st.id
                        station_id = station_cache[key]
                        parameter_id = param_map[param_name]

                        # upsert measurement
                        stmt = insert(Measurement).values(
                            station_id=station_id,
                            parameter_id=parameter_id,
                            sampled_at=date_val,
                            value=val,
                        ).on_conflict_do_update(
                            index_elements=[
                                Measurement.station_id, 
                                Measurement.parameter_id, 
                                Measurement.sampled_at
                            ],
                            set_={"value": val},
                        )
                        await session.execute(stmt)
                        rows_processed += 1
                        
                    except SQLAlchemyError as e:
                        await session.rollback()
                        current_app.logger.error(f"Database error processing row {row}: {e}")
                        continue
                    except Exception as e:
                        await session.rollback()
                        current_app.logger.error(f"Error processing row {row}: {e}")
                        continue

                return jsonify({
                    "status": "success",
                    "rows_processed": rows_processed,
                    "total_rows": len(data)
                })
                
            except SQLAlchemyError as e:
                current_app.logger.error(f"Database error in post_table: {e}")
                return jsonify({"error": "Database error occurred"}), 500
                
    except Exception as e:
        current_app.logger.error(f"Error in post_table: {e}")
        return jsonify({"error": "An error occurred while saving data"}), 500

# ---------------------------------------------------------------------------
# Table API: delete measurement ---------------------------------------------
# ---------------------------------------------------------------------------
@bp.route("/api/measurement", methods=["DELETE"])
async def delete_measurement():
    """Deletes a specific measurement record based on its properties."""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Missing JSON request body."}), 400

        required_keys = ["latitude", "longitude", "parameter", "timestamp"]
        if not all(key in data for key in required_keys):
            return jsonify({"error": f"Missing required keys: {required_keys}"}), 400

        lat = float(data["latitude"])
        lon = float(data["longitude"])
        param_name = data["parameter"]
        timestamp = datetime.fromisoformat(data["timestamp"]).date()

        async with get_db_session() as session:
            # Find Station ID from coordinates
            station_stmt = select(Station.id).where(Station.latitude == lat, Station.longitude == lon)
            station_id = (await session.execute(station_stmt)).scalar_one_or_none()
            if not station_id:
                return jsonify({"error": "Station not found at the given coordinates."}), 404

            # Find Parameter ID from name
            param_stmt = select(Parameter.id).where(Parameter.name == param_name)
            parameter_id = (await session.execute(param_stmt)).scalar_one_or_none()
            if not parameter_id:
                return jsonify({"error": "Parameter not found."}), 404

            # Execute delete statement
            delete_stmt = Measurement.__table__.delete().where(
                Measurement.station_id == station_id,
                Measurement.parameter_id == parameter_id,
                Measurement.sampled_at == timestamp
            )
            result = await session.execute(delete_stmt)

            if result.rowcount == 0:
                return jsonify({"error": "Measurement not found for the given details."}), 404

            return jsonify({"status": "success", "message": "Measurement deleted successfully."}), 200

    except (ValueError, TypeError) as e:
        current_app.logger.warning(f"Invalid data for measurement deletion: {e}")
        return jsonify({"error": "Invalid data format provided."}), 400
    except Exception as e:
        current_app.logger.error(f"Error in delete_measurement: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500


# ---------------------------------------------------------------------------
# App-start hook: async DB initialization -----------------------------------
# ---------------------------------------------------------------------------
_db_initialized = False
@bp.before_app_serving
async def _init_async_db():
    """Kick-off asynchronous DB table creation (run once only)."""
    global _db_initialized
    if not _db_initialized:
        try:
            async with get_db_session() as session:
                await init_db()
                _db_initialized = True
                current_app.logger.info("Database initialization completed successfully")
        except Exception as e:
            current_app.logger.error(f"Failed to initialize database: {e}")
            raise