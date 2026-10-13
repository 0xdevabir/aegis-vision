"""
HUD Visualization Module
=========================
Extracted from main.py — all sci-fi HUD drawing code in one place.
Provides individual drawing functions and a high-level `render_hud()`.
"""

import cv2
import math
import numpy as np
from core.pipeline.base import FrameContext


# ---------------------------------------------------------------------------
# Bounding Boxes
# ---------------------------------------------------------------------------

def draw_box(frame, x1, y1, x2, y2, label, color):
    """Draw bounding box with label."""
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
    cv2.rectangle(frame, (x1, y1 - lh - 10), (x1 + lw + 10, y1), color, -1)
    cv2.putText(frame, label, (x1 + 5, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return frame


def draw_sci_fi_box(frame, x1, y1, x2, y2, color, thickness=1, length=20):
    """Draw corner-bracket style bounding box."""
    # Corners
    cv2.line(frame, (x1, y1), (x1 + length, y1), color, thickness + 1)
    cv2.line(frame, (x1, y1), (x1, y1 + length), color, thickness + 1)
    cv2.line(frame, (x2, y1), (x2 - length, y1), color, thickness + 1)
    cv2.line(frame, (x2, y1), (x2, y1 + length), color, thickness + 1)
    cv2.line(frame, (x1, y2), (x1 + length, y2), color, thickness + 1)
    cv2.line(frame, (x1, y2), (x1, y2 - length), color, thickness + 1)
    cv2.line(frame, (x2, y2), (x2 - length, y2), color, thickness + 1)
    cv2.line(frame, (x2, y2), (x2, y2 - length), color, thickness + 1)
    # Thin full box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
    return frame


# ---------------------------------------------------------------------------
# HUD Panel (right side — face recognition info)
# ---------------------------------------------------------------------------

def draw_hud_panel(frame, person_name, status, is_criminal, confidence, face_crop, panel_index=0, total_panels=1):
    """Draw the facial recognition HUD panel on the right side."""
    fh, fw = frame.shape[:2]
    panel_w = 300
    
    # Determine mode
    is_compact = total_panels > 1
    panel_h = 160 if is_compact else 450
    
    panel_x = fw - panel_w - 20
    panel_y = 20 + panel_index * (panel_h + 10)
    
    # If the panel would be drawn off-screen, skip it to prevent crashing or hiding
    if panel_y + panel_h > fh:
        return frame

    # Semi-transparent panel
    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (10, 15, 10), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    # Border
    cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (50, 150, 50), 1)

    # Header
    cv2.putText(frame, "AI FACIAL RECOGNITION", (panel_x + 15, panel_y + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 255, 150), 1)

    # Face crop
    if face_crop is not None and face_crop.size > 0:
        crop_size = 100 if is_compact else 180
        ch, cw = face_crop.shape[:2]
        scale = crop_size / min(ch, cw)
        resized_crop = cv2.resize(face_crop, (int(cw * scale), int(ch * scale)))
        rch, rcw = resized_crop.shape[:2]
        start_y = (rch - crop_size) // 2
        start_x = (rcw - crop_size) // 2
        final_crop = resized_crop[start_y:start_y + crop_size, start_x:start_x + crop_size]

        if is_compact:
            crop_x = panel_x + 15
            crop_y = panel_y + 45
        else:
            crop_x = panel_x + (panel_w - crop_size) // 2
            crop_y = panel_y + 60

        frame[crop_y:crop_y + crop_size, crop_x:crop_x + crop_size] = final_crop
        draw_sci_fi_box(frame, crop_x - 5, crop_y - 5,
                        crop_x + crop_size + 5, crop_y + crop_size + 5,
                        (100, 200, 100), length=15 if not is_compact else 8)

    # Details
    if is_compact:
        text_x = panel_x + 130
        text_y = panel_y + 60
        
        cv2.putText(frame, "NAME:", (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        cv2.putText(frame, person_name, (text_x, text_y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)

        cv2.putText(frame, "STATUS:", (text_x, text_y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        color = (0, 0, 255) if is_criminal else (150, 255, 150)
        cv2.putText(frame, status, (text_x, text_y + 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        cv2.putText(frame, f"CONFIDENCE: {confidence:.1f}%",
                    (text_x, text_y + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)
    else:
        text_y = panel_y + 280
        cv2.putText(frame, "NAME:", (panel_x + 20, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        cv2.putText(frame, person_name, (panel_x + 20, text_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 255, 150), 2)

        cv2.putText(frame, "STATUS:", (panel_x + 20, text_y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        color = (0, 0, 255) if is_criminal else (150, 255, 150)
        cv2.putText(frame, status, (panel_x + 20, text_y + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Match confidence bar
        cv2.putText(frame, f"MATCH CONFIDENCE:    {confidence:.1f}%",
                    (panel_x + 20, text_y + 190), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        bar_w = 260
        bar_h = 10
        bar_x = panel_x + 20
        bar_y = text_y + 200
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), 1)
        fill_w = int(bar_w * (confidence / 100.0))
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), (50, 200, 50), -1)

    return frame


# ---------------------------------------------------------------------------
# HUD Elements
# ---------------------------------------------------------------------------

def draw_rec_indicator(frame, time_elapsed):
    """Draw blinking REC indicator."""
    if int(time_elapsed * 2) % 2 == 0:
        cv2.circle(frame, (40, 40), 6, (0, 0, 255), -1)
    cv2.putText(frame, "SECURE FEED / REC", (55, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return frame


def draw_threat_level(frame, score):
    """Draw global threat level bar at the top."""
    h, w = frame.shape[:2]
    bar_h = 25
    cv2.rectangle(frame, (0, 0), (w, bar_h), (10, 10, 10), -1)

    if score >= 75:
        level, color = "CRITICAL", (0, 0, 255)
    elif score >= 40:
        level, color = "ELEVATED", (0, 165, 255)
    else:
        level, color = "LOW", (50, 200, 50)

    text = f"GLOBAL THREAT LEVEL: {level} | AI-SSS v5.0 ACTIVE"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.putText(frame, text, (w // 2 - tw // 2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.rectangle(frame, (0, bar_h), (w, bar_h + 3), (30, 30, 30), -1)
    fill_w = int(w * (score / 100.0))
    cv2.rectangle(frame, (0, bar_h), (fill_w, bar_h + 3), color, -1)
    return frame


def draw_radar(frame, tracks, frame_w, frame_h, time_elapsed, criminal_ids):
    """Draw tactical mini-radar in the bottom right corner."""
    radar_r = 70
    radar_cx = frame_w - radar_r - 20
    radar_cy = frame_h - radar_r - 20

    overlay = frame.copy()
    cv2.circle(overlay, (radar_cx, radar_cy), radar_r, (10, 20, 10), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    cv2.circle(frame, (radar_cx, radar_cy), radar_r, (0, 150, 0), 1)
    cv2.circle(frame, (radar_cx, radar_cy), radar_r // 2, (0, 150, 0), 1)
    cv2.line(frame, (radar_cx - radar_r, radar_cy), (radar_cx + radar_r, radar_cy), (0, 100, 0), 1)
    cv2.line(frame, (radar_cx, radar_cy - radar_r), (radar_cx, radar_cy + radar_r), (0, 100, 0), 1)

    angle = (time_elapsed * 2) % (2 * math.pi)
    end_x = int(radar_cx + radar_r * math.cos(angle))
    end_y = int(radar_cy + radar_r * math.sin(angle))
    cv2.line(frame, (radar_cx, radar_cy), (end_x, end_y), (0, 255, 0), 2)

    for track in tracks:
        if not track.is_confirmed():
            continue
        x1, y1, x2, y2 = map(int, track.to_ltrb())
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        rel_x = (cx - frame_w / 2) / (frame_w / 2)
        rel_y = (cy - frame_h / 2) / (frame_h / 2)

        dot_x = int(radar_cx + rel_x * radar_r)
        dot_y = int(radar_cy + rel_y * radar_r)

        dist = math.hypot(dot_x - radar_cx, dot_y - radar_cy)
        if dist > radar_r - 3:
            continue

        color = (0, 0, 255) if track.track_id in criminal_ids else (50, 255, 50)
        if track.track_id in criminal_ids and int(time_elapsed * 5) % 2 == 0:
            color = (255, 255, 255)

        cv2.circle(frame, (dot_x, dot_y), 3, color, -1)

    return frame


def draw_flash_effect(frame, flash_time, current_time):
    """White flash fading out over 0.5 seconds."""
    if flash_time > 0:
        elapsed = current_time - flash_time
        if elapsed < 0.5:
            alpha = max(0, 1.0 - (elapsed / 0.5))
            overlay = np.full_like(frame, 255)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    return frame


# ---------------------------------------------------------------------------
# High-Level Render (uses FrameContext)
# ---------------------------------------------------------------------------

def render_full_hud(frame, ctx: FrameContext, start_time: float,
                    criminal_names: set, perf_stats: dict = None,
                    thermal_mode: bool = False):
    """
    Render the complete HUD overlay on a frame using pipeline context.
    Returns the annotated frame.
    """
    now = ctx.timestamp
    elapsed = now - start_time
    fh, fw = frame.shape[:2]
    # Only people the detector sees right now. DeepSORT keeps lost tracks alive (max_age) on a
    # predicted box that drifts onto chairs, screens and walls; unconfirmed tracks are one-frame
    # blips. Both looked like "detecting every object".
    tracks = [t for t in ctx.tracks if t.is_confirmed() and getattr(t, "time_since_update", 0) == 0]

    # Background elements
    frame = draw_rec_indicator(frame, elapsed)

    # Weapon boxes
    for w in ctx.weapon_detections:
        wx1, wy1, wx2, wy2 = w["bbox"]
        frame = draw_box(frame, wx1, wy1, wx2, wy2, f"WEAPON {w['score']:.0%}", (0, 0, 255))

    # Vehicle boxes + plate annotations
    for v in ctx.vehicle_detections:
        vx1, vy1, vx2, vy2 = v["bbox"]
        cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (255, 165, 0), 2)
        label = f"{v['class_name'].upper()} {v['score']:.0%}"
        cv2.putText(frame, label, (vx1, vy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

    # Plate annotations
    for plate in ctx.plate_detections:
        px1, py1, px2, py2 = plate["bbox"]
        cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 255, 255), 2)
        cv2.putText(frame, plate["plate_number"], (px1, py1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    for plate in ctx.watchlisted_plates:
        px1, py1, px2, py2 = plate["bbox"]
        cv2.putText(frame, "WATCHLISTED", (px1, py2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Count total panels needed for POIs
    poi_count = sum(1 for t in tracks if (t.track_id in ctx.criminal_ids or t.track_id in ctx.suspicious_tracks))
    current_panel_index = 0

    # Person boxes + HUD panels
    for track in tracks:
        track_id = track.track_id
        x1, y1, x2, y2 = map(int, track.to_ltrb())
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(fw, x2), min(fh, y2)

        name = ctx.identities.get(track_id, "Unknown")
        is_criminal = track_id in ctx.criminal_ids
        is_suspicious = track_id in ctx.suspicious_tracks

        # Determine color and status
        if is_criminal:
            color, status = (0, 0, 255), "WATCHLIST MATCH"
        elif track_id in ctx.confirmed_weapons:
            color, status = (0, 0, 255), "Weapon (confirmed)"
        elif is_suspicious:
            color, status = (0, 165, 255), "Suspicious"
        else:
            color, status = (50, 200, 50), "Clear"

        # Draw sci-fi box
        frame = draw_sci_fi_box(frame, x1, y1, x2, y2, color, thickness=1)

        # Label
        label = "PERSON OF INTEREST" if is_criminal else f"ID: {track_id}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - 25), (x1 + lw + 10, y1), color, -1)
        cv2.putText(frame, label, (x1 + 5, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # HUD panel for persons of interest
        if is_criminal or is_suspicious:
            roi = frame[y1:y2, x1:x2]
            if roi.size > 0:
                real = ctx.identity_conf.get(track_id)
                conf = real * 100.0 if real is not None else 0.0   # never fabricate a score
                frame = draw_hud_panel(frame, name, status, is_criminal, conf, roi, current_panel_index, poi_count)
                current_panel_index += 1

    # Global HUD elements
    frame = draw_threat_level(frame, ctx.threat_score)
    frame = draw_radar(frame, tracks, fw, fh, elapsed, ctx.criminal_ids)

    if ctx.active_criminals:
        flash = int(elapsed * 4) % 2 == 0
        banner_color = (0, 0, 255) if flash else (0, 0, 180)
        cv2.rectangle(frame, (0, fh - 60), (fw, fh), banner_color, -1)
        names = ", ".join(ctx.active_criminals[:3])
        alert_line = f"!!! CRIMINAL ALERT: {names} @ {ctx.camera_location} !!!"
        cv2.putText(
            frame, alert_line,
            (20, fh - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )
        if ctx.camera_lat is not None and ctx.camera_lng is not None:
            gps_line = f"PINPOINT GPS: {ctx.camera_lat:.5f}, {ctx.camera_lng:.5f}  (Cam: {ctx.camera_id})"
            cv2.putText(
                frame, gps_line,
                (20, fh - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 255), 1,
            )

    # Stats overlay
    fps = ctx.frame_number / elapsed if elapsed > 0 else 0
    hud_h = 30 + 20 * max(1, len(ctx.active_criminals) + 3)
    if perf_stats:
        hud_h += 20

    cv2.rectangle(frame, (0, 0), (350, hud_h), (0, 0, 0), -1)

    cv2.putText(frame, f"AI: {fps:.1f}/s  |  People: {len(tracks)}",
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"Weapon: {'CONFIRMED' if ctx.confirmed_weapons else 'candidate' if ctx.weapon_present else 'NO'}  |  "
                       f"Anomalies: {len(ctx.anomalies)}",
                (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 0, 255) if ctx.confirmed_weapons else (0, 165, 255) if ctx.weapon_present else (0, 255, 0), 1)
    cv2.putText(frame, f"Criminals in frame: {len(ctx.active_criminals)}",
                (10, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 255) if ctx.active_criminals else (200, 200, 200), 1)

    if perf_stats and "error" not in perf_stats:
        cv2.putText(frame, f"CPU: {perf_stats.get('cpu_percent', 0):.1f}%  "
                           f"MEM: {perf_stats.get('memory_mb', 0):.0f}MB",
                    (10, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    for i, cname in enumerate(ctx.active_criminals):
        cv2.putText(frame, f"  >> {cname}",
                    (10, 84 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    cv2.putText(frame, f"Cam: {ctx.camera_location}",
                (10, hud_h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    return frame

