from animation_worker import generate_interpolated_video
from quart import Blueprint, request, jsonify, send_file, current_app
from datetime import datetime
from io import BytesIO
import logging

from generate_video import generate_interpolated_video

bp_animate = Blueprint("animate", __name__, url_prefix="/api/animate")

@bp_animate.route("/video", methods=["POST"])
async def generate_video_route():
    """
    POST /api/animate/video
    Expects JSON:
    {
        "parameter": "Chlorophyll",
        "start_date": "2024-01-01",
        "end_date": "2024-12-01",
        "fps": 24,
        "frames_per_transition": 10,
        "cmap": "viridis"
    }
    Returns:
        MP4 video file.
    """
    try:
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        parameter = data.get("parameter")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        fps = int(data.get("fps", 24))
        frames_per_transition = int(data.get("frames_per_transition", 10))
        cmap = data.get("cmap", "viridis")

        if not parameter or not start_date or not end_date:
            return jsonify({"error": "Missing required fields"}), 400

        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            return jsonify({"error": "Invalid date format (expected YYYY-MM-DD)"}), 400

        current_app.logger.info(
            f"Generating animation: parameter={parameter}, range=({start_date} → {end_date}), "
            f"fps={fps}, frames/transition={frames_per_transition}, cmap={cmap}"
        )

        # Generate the interpolated video bytes
        video_bytes = await generate_interpolated_video(
            parameter=parameter,
            start_date=start_dt,
            end_date=end_dt,
            fps=fps,
            frames_per_transition=frames_per_transition,
            cmap=cmap,
        )

        # Serve the video as a downloadable file
        return await send_file(
            BytesIO(video_bytes),
            mimetype="video/mp4",
            as_attachment=True,
            download_name=f"{parameter}_animation.mp4"
        )

    except Exception as e:
        current_app.logger.exception(f"Animation route failed: {str(e)}")
        return jsonify({"error": "Server failed to generate animation"}), 500
