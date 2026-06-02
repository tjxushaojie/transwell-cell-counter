from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from skimage import color, exposure, feature, filters, measure, morphology, segmentation, util


ImageSource = str | Path | bytes | BinaryIO


@dataclass(frozen=True)
class CounterParams:
    sensitivity: float = 0.50
    min_area: int = 70
    max_area: int = 1800
    min_solidity: float = 0.48
    max_hole_ratio: float = 0.32
    min_center_score: float = 0.22
    split_distance: int = 11
    smooth_sigma: float = 1.0
    background_sigma: float = 28.0
    fill_holes_area: int = 80
    exclude_border: bool = False


@dataclass(frozen=True)
class CountResult:
    count: int
    detections: pd.DataFrame
    annotated_image: Image.Image
    mask_image: Image.Image
    score_image: Image.Image
    labels: np.ndarray
    threshold: float


@dataclass(frozen=True)
class AutoTuneResult:
    params: CounterParams
    score: float
    candidates_evaluated: int
    estimated_count: int
    summary: dict[str, float]


def load_rgb_image(source: ImageSource) -> Image.Image:
    if isinstance(source, bytes):
        image = Image.open(BytesIO(source))
    else:
        image = Image.open(source)
    return image.convert("RGB")


def image_to_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _robust01(channel: np.ndarray, p_low: float = 1.0, p_high: float = 99.0) -> np.ndarray:
    low, high = np.percentile(channel, [p_low, p_high])
    if high <= low:
        return np.zeros_like(channel, dtype=np.float32)
    scaled = (channel - low) / (high - low)
    return np.clip(scaled, 0.0, 1.0).astype(np.float32)


def build_stain_score(rgb: np.ndarray, params: CounterParams) -> np.ndarray:
    rgb_float = util.img_as_float(rgb)
    lab = color.rgb2lab(rgb_float)
    hsv = color.rgb2hsv(rgb_float)

    # Purple/crystal-violet cells are solid, saturated, blue-magenta, and locally dark.
    purple_blue = _robust01(-lab[:, :, 2], 1, 99)
    magenta = _robust01(lab[:, :, 1], 1, 99)
    saturation = _robust01(hsv[:, :, 1], 1, 99)
    darkness = _robust01(1.0 - hsv[:, :, 2], 1, 99)

    raw = 0.44 * purple_blue + 0.26 * saturation + 0.20 * darkness + 0.10 * magenta
    if params.background_sigma > 0:
        background = filters.gaussian(raw, sigma=params.background_sigma, preserve_range=True)
        local = raw - background
        score = 0.62 * _robust01(raw, 1, 99) + 0.38 * _robust01(local, 1, 99)
    else:
        score = _robust01(raw, 1, 99)

    if params.smooth_sigma > 0:
        score = filters.gaussian(score, sigma=params.smooth_sigma, preserve_range=True)
    return _robust01(score, 1, 99.5)


def make_candidate_mask(score: np.ndarray, params: CounterParams) -> tuple[np.ndarray, float]:
    otsu = filters.threshold_otsu(score)
    li = filters.threshold_li(score)
    base_threshold = 0.62 * otsu + 0.38 * li

    # Sensitivity is centered at 0.5. Higher values lower the threshold.
    threshold = float(np.clip(base_threshold - (params.sensitivity - 0.5) * 0.34, 0.05, 0.95))
    mask = score > threshold
    mask = morphology.binary_opening(mask, morphology.disk(1))
    mask = morphology.binary_closing(mask, morphology.disk(1))
    mask = morphology.remove_small_holes(mask, area_threshold=params.fill_holes_area)
    mask = morphology.remove_small_objects(mask, min_size=max(4, params.min_area // 3))
    if params.exclude_border:
        mask = segmentation.clear_border(mask)
    return mask, threshold


def watershed_cells(mask: np.ndarray, params: CounterParams) -> np.ndarray:
    distance = ndi.distance_transform_edt(mask)
    min_distance = max(2, int(params.split_distance))
    peak_coords = feature.peak_local_max(
        distance,
        labels=mask,
        min_distance=min_distance,
        threshold_abs=max(2.0, min_distance * 0.35),
        exclude_border=False,
    )

    markers = np.zeros(mask.shape, dtype=np.int32)
    if peak_coords.size:
        markers[tuple(peak_coords.T)] = np.arange(1, len(peak_coords) + 1)
    else:
        markers = measure.label(mask)

    return segmentation.watershed(-distance, markers=markers, mask=mask)


def _center_score(score: np.ndarray, centroid: tuple[float, float], radius: float) -> float:
    row, col = centroid
    radius = max(2.0, radius)
    r0 = max(0, int(np.floor(row - radius)))
    r1 = min(score.shape[0], int(np.ceil(row + radius + 1)))
    c0 = max(0, int(np.floor(col - radius)))
    c1 = min(score.shape[1], int(np.ceil(col + radius + 1)))
    yy, xx = np.ogrid[r0:r1, c0:c1]
    disk = (yy - row) ** 2 + (xx - col) ** 2 <= radius**2
    if not np.any(disk):
        return 0.0
    return float(score[r0:r1, c0:c1][disk].mean())


def filter_segments(labels: np.ndarray, score: np.ndarray, params: CounterParams) -> tuple[np.ndarray, pd.DataFrame]:
    accepted = np.zeros(labels.shape, dtype=np.int32)
    rows: list[dict[str, float | int]] = []
    next_label = 1

    for prop in measure.regionprops(labels, intensity_image=score):
        area = float(prop.area)
        if area < params.min_area or area > params.max_area:
            continue

        filled_area = float(prop.filled_area) if prop.filled_area else area
        hole_ratio = max(0.0, (filled_area - area) / filled_area)
        equiv_diameter = float(prop.equivalent_diameter)
        center = _center_score(score, prop.centroid, equiv_diameter * 0.22)

        if prop.solidity < params.min_solidity:
            continue
        if hole_ratio > params.max_hole_ratio:
            continue
        if center < params.min_center_score:
            continue

        accepted[labels == prop.label] = next_label
        minr, minc, maxr, maxc = prop.bbox
        rows.append(
            {
                "id": next_label,
                "x": round(float(prop.centroid[1]), 2),
                "y": round(float(prop.centroid[0]), 2),
                "area_px": int(prop.area),
                "diameter_px": round(equiv_diameter, 2),
                "mean_score": round(float(prop.mean_intensity), 4),
                "center_score": round(center, 4),
                "solidity": round(float(prop.solidity), 4),
                "hole_ratio": round(hole_ratio, 4),
                "bbox_x1": int(minc),
                "bbox_y1": int(minr),
                "bbox_x2": int(maxc),
                "bbox_y2": int(maxr),
            }
        )
        next_label += 1

    return accepted, pd.DataFrame(rows)


def _safe_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def draw_annotations(
    rgb: np.ndarray,
    labels: np.ndarray,
    detections: pd.DataFrame,
    show_numbers: bool = False,
) -> Image.Image:
    overlay = rgb.copy()
    boundaries = segmentation.find_boundaries(labels, mode="outer")
    overlay[boundaries] = np.array([0, 255, 255], dtype=np.uint8)

    image = Image.fromarray(overlay)
    draw = ImageDraw.Draw(image)
    font = _safe_font(13)

    for row in detections.itertuples(index=False):
        x = float(row.x)
        y = float(row.y)
        radius = max(6.0, min(34.0, float(row.diameter_px) * 0.72))
        box = [x - radius, y - radius, x + radius, y + radius]
        draw.ellipse(box, outline=(255, 255, 0), width=2)
        if show_numbers:
            draw.text((x + radius + 2, y - radius), str(int(row.id)), fill=(255, 255, 0), font=font)

    return image


def labels_to_mask(labels: np.ndarray) -> Image.Image:
    mask = (labels > 0).astype(np.uint8) * 255
    return Image.fromarray(mask, mode="L")


def score_to_image(score: np.ndarray) -> Image.Image:
    return Image.fromarray(exposure.rescale_intensity(score, out_range=(0, 255)).astype(np.uint8), mode="L")


def count_cells(image: Image.Image | np.ndarray, params: CounterParams, show_numbers: bool = False) -> CountResult:
    if isinstance(image, Image.Image):
        rgb = image_to_array(image)
    else:
        rgb = np.asarray(image, dtype=np.uint8)

    score = build_stain_score(rgb, params)
    mask, threshold = make_candidate_mask(score, params)
    raw_labels = watershed_cells(mask, params)
    labels, detections = filter_segments(raw_labels, score, params)
    annotated = draw_annotations(rgb, labels, detections, show_numbers=show_numbers)

    return CountResult(
        count=int(len(detections)),
        detections=detections,
        annotated_image=annotated,
        mask_image=labels_to_mask(labels),
        score_image=score_to_image(score),
        labels=labels,
        threshold=threshold,
    )


def _scale_params(params: CounterParams, scale: float) -> CounterParams:
    area_scale = scale * scale
    return CounterParams(
        sensitivity=params.sensitivity,
        min_area=max(5, int(round(params.min_area * area_scale))),
        max_area=max(20, int(round(params.max_area * area_scale))),
        min_solidity=params.min_solidity,
        max_hole_ratio=params.max_hole_ratio,
        min_center_score=params.min_center_score,
        split_distance=max(2, int(round(params.split_distance * scale))),
        smooth_sigma=max(0.5, params.smooth_sigma * scale),
        background_sigma=max(8.0, params.background_sigma * scale),
        fill_holes_area=max(5, int(round(params.fill_holes_area * area_scale))),
        exclude_border=params.exclude_border,
    )


def _resize_for_tuning(image: Image.Image, max_side: int) -> tuple[np.ndarray, float]:
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    scale = max_side / max(width, height)
    if scale < 1.0:
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        rgb_image = rgb_image.resize(new_size, Image.Resampling.BILINEAR)
    elif scale > 1.0:
        scale = 1.0
    return image_to_array(rgb_image), scale


def _evaluate_tune_candidate(
    score_image_array: np.ndarray,
    params: CounterParams,
    median_count: float | None = None,
) -> tuple[float, pd.DataFrame]:
    mask, _ = make_candidate_mask(score_image_array, params)
    raw_labels = watershed_cells(mask, params)
    _, detections = filter_segments(raw_labels, score_image_array, params)
    count = len(detections)

    if count < 3:
        return -1e9, detections

    area = detections["area_px"].to_numpy(dtype=float)
    center = detections["center_score"].to_numpy(dtype=float)
    solidity = detections["solidity"].to_numpy(dtype=float)
    holes = detections["hole_ratio"].to_numpy(dtype=float)

    area_cv = float(np.std(area) / (np.mean(area) + 1e-6))
    small_fraction = float(np.mean(area < np.percentile(area, 20)))
    quality = (
        2.4 * float(np.median(center))
        + 0.9 * float(np.median(solidity))
        - 1.4 * float(np.mean(holes))
        - 0.30 * min(area_cv, 3.0)
        - 0.10 * small_fraction
    )

    if median_count is not None and median_count > 0:
        quality -= 0.55 * abs(float(np.log((count + 1) / (median_count + 1))))

    return quality, detections


def auto_tune_params(
    image: Image.Image | np.ndarray,
    base_params: CounterParams | None = None,
    max_side: int = 360,
) -> AutoTuneResult:
    base = base_params or CounterParams()
    pil_image = Image.fromarray(np.asarray(image, dtype=np.uint8)) if not isinstance(image, Image.Image) else image
    rgb, scale = _resize_for_tuning(pil_image, max_side=max_side)

    scaled_base = _scale_params(base, scale)
    score_image_array = build_stain_score(rgb, scaled_base)

    first_pass: list[tuple[CounterParams, float, pd.DataFrame]] = []
    candidate_settings = [
        (0.44, 0.24, 0.24, 11),
        (0.50, 0.24, 0.28, 11),
        (0.56, 0.24, 0.28, 11),
        (0.62, 0.24, 0.32, 11),
        (0.50, 0.30, 0.20, 11),
        (0.58, 0.30, 0.20, 11),
        (0.50, 0.24, 0.28, 8),
        (0.56, 0.24, 0.28, 8),
        (0.50, 0.20, 0.32, 14),
    ]

    for sensitivity, center_score, hollow_ratio, split_distance in candidate_settings:
        candidate = CounterParams(
            sensitivity=sensitivity,
            min_area=base.min_area,
            max_area=base.max_area,
            min_solidity=base.min_solidity,
            max_hole_ratio=hollow_ratio,
            min_center_score=center_score,
            split_distance=split_distance,
            smooth_sigma=base.smooth_sigma,
            background_sigma=base.background_sigma,
            fill_holes_area=base.fill_holes_area,
            exclude_border=base.exclude_border,
        )
        scaled_candidate = _scale_params(candidate, scale)
        _, detections = _evaluate_tune_candidate(score_image_array, scaled_candidate)
        first_pass.append((candidate, float(len(detections)), detections))

    viable_counts = [count for _, count, detections in first_pass if len(detections) >= 3]
    median_count = float(np.median(viable_counts)) if viable_counts else 0.0

    best_params = base
    best_score = -1e9
    best_detections = pd.DataFrame()

    for candidate, _, _ in first_pass:
        scaled_candidate = _scale_params(candidate, scale)
        candidate_score, detections = _evaluate_tune_candidate(score_image_array, scaled_candidate, median_count)
        if candidate_score > best_score:
            best_params = candidate
            best_score = candidate_score
            best_detections = detections

    if best_detections.empty:
        summary = {"median_center_score": 0.0, "median_solidity": 0.0, "mean_hole_ratio": 0.0}
        estimated_count = 0
    else:
        summary = {
            "median_center_score": float(best_detections["center_score"].median()),
            "median_solidity": float(best_detections["solidity"].median()),
            "mean_hole_ratio": float(best_detections["hole_ratio"].mean()),
        }
        estimated_count = int(len(best_detections))

    return AutoTuneResult(
        params=best_params,
        score=float(best_score),
        candidates_evaluated=len(first_pass),
        estimated_count=estimated_count,
        summary=summary,
    )
