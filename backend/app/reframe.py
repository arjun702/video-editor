"""Choose a 9:16 crop that follows a face, or the thing that's moving."""

from __future__ import annotations

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


def smooth_centers(
    points: list[tuple[float, float]],
    window: int = 5,
) -> list[tuple[float, float]]:
    if window < 2 or len(points) < 2:
        return list(points)
    half = window // 2
    values = [point[1] for point in points]
    smoothed: list[tuple[float, float]] = []
    for index, (moment, _) in enumerate(points):
        left = max(0, index - half)
        right = min(len(values), index + half + 1)
        smoothed.append((moment, sum(values[left:right]) / (right - left)))
    return smoothed


def crop_x_expression(
    points: list[tuple[float, float]],
    crop_w: int,
    frame_w: int,
    pan_threshold: float = 48,
) -> str:
    """FFmpeg `x` expression. `points` are (time, subject center x) in source pixels.

    Time is relative to the segment (t = 0 at the first output frame).
    """
    if not points or crop_w >= frame_w:
        return "(in_w-out_w)/2"
    max_x = max(0, frame_w - crop_w)

    def left_edge(center: float) -> int:
        return int(round(clamp(center - crop_w / 2, 0, max_x)))

    edges = [left_edge(center) for _, center in points]
    if max(edges) - min(edges) < pan_threshold:
        middle = sorted(edges)[len(edges) // 2]
        return str(middle)

    duration = points[-1][0] - points[0][0]
    start = left_edge(points[0][1])
    end = left_edge(points[-1][1])
    if duration <= 0.05:
        return str(start)
    return f"{start}+({end - start})*min(max(t/{duration:.3f}\\,0)\\,1)"


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
    sample_every: float = 0.4,
) -> list[tuple[float, float]]:
    """Sample the clip and return smoothed (time, center_x) points, relative to `start`."""
    import cv2

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        return []
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    raw: list[tuple[float, float, str]] = []
    previous = None
    moment = start
    try:
        while moment <= end + 1e-3:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, moment) * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
            )
            if len(faces):
                x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
                raw.append((moment - start, float(x + width / 2.0), "face"))
            elif previous is not None:
                center = motion_center(previous, gray)
                if center is not None:
                    raw.append((moment - start, float(center[0]), "motion"))
            previous = gray
            moment += sample_every
    finally:
        capture.release()

    faces = [(moment, center) for moment, center, kind in raw if kind == "face"]
    series = faces if len(faces) >= 2 else [(moment, center) for moment, center, _ in raw]
    return smooth_centers(series, window=3)
