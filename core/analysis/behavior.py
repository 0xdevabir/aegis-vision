
import math


SUSPICIOUS_SPEED_THRESHOLD = 150
SUSPICIOUS_LOITER_SECONDS = 15
SUSPICIOUS_ERRATIC_ANGLE = 60


MIN_STEP_PX = 3.0


def configure_behavior(cfg=None) -> None:
    """Apply behavior thresholds from config.yaml."""
    global SUSPICIOUS_SPEED_THRESHOLD, SUSPICIOUS_LOITER_SECONDS, SUSPICIOUS_ERRATIC_ANGLE
    if not cfg:
        return
    SUSPICIOUS_SPEED_THRESHOLD = cfg.get("speed_threshold", SUSPICIOUS_SPEED_THRESHOLD)
    SUSPICIOUS_LOITER_SECONDS = cfg.get("loiter_seconds", SUSPICIOUS_LOITER_SECONDS)
    SUSPICIOUS_ERRATIC_ANGLE = cfg.get("erratic_angle", SUSPICIOUS_ERRATIC_ANGLE)


def is_suspicious_behavior(track_history, pose_landmarks=None):
    reasons = []
    if len(track_history) < 5:
        return False, reasons

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
    if len(speeds) >= 3 and sorted(speeds)[len(speeds) // 2] > SUSPICIOUS_SPEED_THRESHOLD:
        reasons.append("rapid_movement")

    if len(track_history) >= 5:
        duration = track_history[-1][0] - track_history[0][0]
        xs = [p[1] for p in track_history]
        ys = [p[2] for p in track_history]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        if duration > SUSPICIOUS_LOITER_SECONDS and spread < 50:
            reasons.append("loitering")

    if len(track_history) >= 15:
        mid = len(track_history) // 2
        _, fx, fy = track_history[mid]
        _, lx, ly = track_history[-1]
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
            if mag1 >= MIN_STEP_PX and mag2 >= MIN_STEP_PX:     # ignore detector jitter on standing people
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

