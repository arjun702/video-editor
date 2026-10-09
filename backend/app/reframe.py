"""Choose a 9:16 crop that holds on the main face, one position per camera shot."""

from __future__ import annotations

from bisect import bisect_right

from app.transcript import clamp


def crop_size(frame_w: int, frame_h: int, aspect: float = 9 / 16) -> tuple[int, int]:
    """Even crop width and height that match 9:16 inside the source frame."""
    if frame_w <= 1 or frame_h <= 1:
        return (2, 2)
    if frame_w / frame_h > aspect:
        height = frame_h - frame_h % 2
        width = int(height * aspect)
        width -= width % 2
    else:
        width = frame_w - frame_w % 2
        height = int(round(width / aspect))
        height -= height % 2
        if height > frame_h:
            height = frame_h - frame_h % 2
    return (max(2, width), max(2, height))


def crop_x_expression(
    steps: list[tuple[float, float]],
    crop_w: int,
    frame_w: int,
    min_move: float = 48,
) -> str:
    """FFmpeg `x` expression. `steps` are (time, subject center x) in source pixels:
    from that time on, hold the crop on that center. Moves smaller than
    `min_move` pixels are ignored so the frame doesn't twitch.

    Time is relative to the segment (t = 0 at the first output frame).
    """
    if not steps or crop_w >= frame_w:
        return "(in_w-out_w)/2"
    max_x = max(0, frame_w - crop_w)

    def left_edge(center: float) -> int:
        return int(round(clamp(center - crop_w / 2, 0, max_x)))

    ordered = sorted(steps)
    values = [left_edge(ordered[0][1])]
    times: list[float] = []
    for moment, center in ordered:
        edge = left_edge(center)
        if moment <= 0:
            values[0] = edge
        elif abs(edge - values[-1]) >= min_move:
            times.append(moment)
            values.append(edge)

    expr = str(values[-1])
    for moment, value in reversed(list(zip(times, values[:-1]))):
        expr = f"if(lt(t\\,{moment:.3f})\\,{value}\\,{expr})"
    return expr


def crop_y_expression(frame_h: int, crop_h: int) -> str:
    if frame_h - crop_h < 4:
        return "0"
    return "(in_h-out_h)/2"


def motion_center(prev, gray, min_mass: float = 400):
    """Centroid of pixels that changed. Returns (x, y) or None."""
    import cv2

    diff = cv2.absdiff(prev, gray)
    _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    moments = cv2.moments(mask)
    if moments["m00"] < min_mass:
        return None
    return (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"])


def track_subject(
    path: str,
    start: float,
    end: float,
    cuts: list[float] | None = None,
    sample_every: float = 0.4,
) -> list[tuple[float, float]]:
    """Return (shot start, center_x) steps relative to `start`, one per camera shot.

    Each shot holds on its main face. A shot with no face follows the median of
    what moves; a shot with neither stays centered.
    """
    import cv2

    span = end - start
    bounds = [0.0] + sorted(cut for cut in (cuts or []) if 0 < cut < span)

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        return []
    frame_w = capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0.0
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces: list[list[tuple[float, float, float]]] = [[] for _ in bounds]
    motion: list[list[float]] = [[] for _ in bounds]
    previous = None
    previous_shot = -1
    moment = 0.0
    try:
        while moment <= span + 1e-3:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start + moment) * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            shot = bisect_right(bounds, moment) - 1
            if shot != previous_shot:
                previous = None
                previous_shot = shot
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hits = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40)
            )
            if len(hits):
                x, _, width, height = max(hits, key=lambda face: face[2] * face[3])
                faces[shot].append((moment, float(x + width / 2.0), float(width * height)))
            elif previous is not None:
                center = motion_center(previous, gray)
                if center is not None:
                    motion[shot].append(float(center[0]))
            previous = gray
            moment += sample_every
    finally:
        capture.release()

    radius = max(60.0, frame_w * 0.1)
    steps: list[tuple[float, float]] = []
    for index, shot_start in enumerate(bounds):
        center = lock_to_biggest_face(faces[index], radius=radius)
        if center is None and motion[index]:
            ordered = sorted(motion[index])
            center = ordered[len(ordered) // 2]
        if center is None and frame_w:
            center = frame_w / 2.0
        if center is not None:
            steps.append((shot_start, center))
    if all(not items for items in faces) and all(not items for items in motion):
        return []
    return steps


def lock_to_biggest_face(
    faces: list[tuple[float, float, float]],
    radius: float = 180.0,
) -> float | None:
    """Center x of the face that is both large and keeps showing up.

    Each sample votes with its box area for every sample within `radius`, so one
    big false detection can't beat a face seen all through the shot.
    """
    if not faces:
        return None

    def support(x: float) -> float:
        return sum(area for _, center, area in faces if abs(center - x) <= radius)

    _, anchor, _ = max(faces, key=lambda item: support(item[1]))
    cluster = sorted(center for _, center, _ in faces if abs(center - anchor) <= radius)
    return cluster[len(cluster) // 2]
