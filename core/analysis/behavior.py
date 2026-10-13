
import math


SUSPICIOUS_SPEED_THRESHOLD = 150
SUSPICIOUS_LOITER_SECONDS = 15
SUSPICIOUS_ERRATIC_ANGLE = 60


MIN_STEP_PX = 3.0

# Metric thresholds, used when the track history carries the person's box height. A standing
# person is ~1.7 m tall, so that height gives metres-per-pixel at their distance from the camera:
# the same walk is no longer "fast" close to the lens and "slow" far away.
PERSON_HEIGHT_M = 1.7
SUSPICIOUS_SPEED_MPS = 3.0        # walking ~1.4 m/s, running > 3 m/s
LOITER_RADIUS_M = 0.6
MIN_STEP_M = 0.04


def configure_behavior(cfg=None) -> None:
    """Apply behavior thresholds from config.yaml."""
    global SUSPICIOUS_SPEED_THRESHOLD, SUSPICIOUS_LOITER_SECONDS, SUSPICIOUS_ERRATIC_ANGLE
    global SUSPICIOUS_SPEED_MPS, LOITER_RADIUS_M
    if not cfg:
        return
    SUSPICIOUS_SPEED_MPS = cfg.get("speed_threshold_mps", SUSPICIOUS_SPEED_MPS)
    LOITER_RADIUS_M = cfg.get("loiter_radius_m", LOITER_RADIUS_M)
    SUSPICIOUS_SPEED_THRESHOLD = cfg.get("speed_threshold", SUSPICIOUS_SPEED_THRESHOLD)
    SUSPICIOUS_LOITER_SECONDS = cfg.get("loiter_seconds", SUSPICIOUS_LOITER_SECONDS)
    SUSPICIOUS_ERRATIC_ANGLE = cfg.get("erratic_angle", SUSPICIOUS_ERRATIC_ANGLE)


def is_suspicious_behavior(track_history, pose_landmarks=None):
    """`track_history`: [(t, cx, cy)] in pixels, or [(t, cx, cy, box_height)] to judge in metres."""
    reasons = []
    if len(track_history) < 5:
        return False, reasons

    speed_threshold, loiter_spread, min_step = SUSPICIOUS_SPEED_THRESHOLD, 50, MIN_STEP_PX
    heights = sorted(p[3] for p in track_history if len(p) > 3 and p[3] > 0)
    if heights:
        # Median height: a box cut short by occlusion or the frame edge must not inflate the scale.
        unit = PERSON_HEIGHT_M / heights[len(heights) // 2]
        speed_threshold, loiter_spread, min_step = SUSPICIOUS_SPEED_MPS, LOITER_RADIUS_M, MIN_STEP_M
        track_history = [(p[0], p[1] * unit, p[2] * unit) for p in track_history]

    recent = track_history[-10:]
    speeds = []
    for i in range(1, len(recent)):
        _, cx1, cy1 = recent[i - 1]
        _, cx2, cy2 = recent[i]
        dt = recent[i][0] - recent[i - 1][0]
        if dt > 0:
            speed = math.hypot(cx2 - cx1, cy2 - cy1) / dt
            speeds.append(speed)

    # Median, not max: one tracker jitter / box-resize spike must not flag a person.
    if len(speeds) >= 3 and sorted(speeds)[len(speeds) // 2] > speed_threshold:
        reasons.append("rapid_movement")

    if len(track_history) >= 5:
        duration = track_history[-1][0] - track_history[0][0]
        xs = [p[1] for p in track_history]
        ys = [p[2] for p in track_history]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        if duration > SUSPICIOUS_LOITER_SECONDS and spread < loiter_spread:
            reasons.append("loitering")

    if len(track_history) >= 15:
        direction_changes = 0
        for i in range(2, len(track_history)):
            _, px, py = track_history[i - 2]
            _, cx, cy = track_history[i - 1]
            _, nx, ny = track_history[i]
            v1 = (cx - px, cy - py)
            v2 = (nx - cx, ny - cy)
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            mag1 = math.hypot(*v1)
            mag2 = math.hypot(*v2)
            if mag1 >= min_step and mag2 >= min_step:     # ignore detector jitter on standing people
                angle = math.degrees(math.acos(max(-1, min(1, dot / (mag1 * mag2)))))
                if angle > SUSPICIOUS_ERRATIC_ANGLE:
                    direction_changes += 1
        if direction_changes >= 4:
            reasons.append("erratic_movement")

    if pose_landmarks:
        # Raised arms: a wrist clearly above the shoulder line, scaled by torso length
        # so the test holds at any camera distance/resolution.
        ls, rs = pose_landmarks.get("left_shoulder"), pose_landmarks.get("right_shoulder")
        lw, rw = pose_landmarks.get("left_wrist"), pose_landmarks.get("right_wrist")
        if ls and rs and (lw or rw):
            shoulder_y = (ls[1] + rs[1]) / 2
            lh, rh = pose_landmarks.get("left_hip"), pose_landmarks.get("right_hip")
            torso = abs(((lh[1] + rh[1]) / 2) - shoulder_y) if lh and rh else 0.0
            margin = max(10.0, 0.4 * torso)
            if any(w and w[1] < shoulder_y - margin for w in (lw, rw)):
                reasons.append("raised_arms")

    return len(reasons) > 0, reasons

