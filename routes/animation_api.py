from quart import Blueprint, request, jsonify, send_file, current_app
from datetime import datetime
import traceback
import io
from utils.animation_generator import fetch_data_for_animation, generate_spatiotemporal_video

animation_bp = Blueprint("animation_api", __name__)

@animation_bp.route("/api/animate", methods=["POST"])
async def handle_animation_request():
    """Handles the request to generate a spatiotemporal animation."""
    try:
        payload = await request.get_json()
        if not payload:
            return jsonify({"error": "Missing JSON request body."}), 400

        # Validate input parameters
        required_keys = ["parameter", "start_date", "end_date", "fps", "frames_per_transition", "filename"]
        if not all(key in payload for key in required_keys):
            return jsonify({"error": f"Missing required keys: {required_keys}"}), 400

        start_date = datetime.fromisoformat(payload['start_date'])
        end_date = datetime.fromisoformat(payload['end_date'])
        fps = int(payload['fps'])
        frames_per_transition = int(payload['frames_per_transition'])
        cmap = payload.get('colormap', 'viridis')
        parameter = payload.get("parameter", "").strip()
        filename = payload.get("filename", "")
        boundary_path = payload.get("boundary_path", "static/data/export.geojson")

        # 1. Fetch data
        df = await fetch_data_for_animation(parameter, start_date, end_date, filename)
        if df.empty:
            return jsonify({"error": "No data available for the selected parameter and date range."}), 404

        # 2. Generate video
        video_bytes = generate_spatiotemporal_video(df, fps, frames_per_transition, cmap, boundary_path)

        # 3. Send video file as response
        return await send_file(
            io.BytesIO(video_bytes),
            mimetype="video/mp4",
            as_attachment=True,
            download_name=f"{parameter.replace(' ', '_')}_animation.mp4"
        )

    except ValueError as ve:
        current_app.logger.warning(f"Animation generation validation error: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        current_app.logger.error(f"Animation generation failed: {traceback.format_exc()}")
        return jsonify({"error": "An unexpected error occurred while generating the animation."}), 500
