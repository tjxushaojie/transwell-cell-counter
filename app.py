from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from transwell_counter import CounterParams, count_cells, load_rgb_image


SUPPORTED_TYPES = ["tif", "tiff", "png", "jpg", "jpeg", "bmp"]


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def read_uploaded_image(uploaded_file) -> Image.Image:
    return load_rgb_image(uploaded_file.getvalue())


def resize_for_analysis(image: Image.Image, max_side: int = 1600) -> tuple[Image.Image, float]:
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    if scale >= 1.0:
        return image, 1.0
    resized = image.copy()
    resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return resized, scale


def scale_params_for_image(params: CounterParams, scale: float) -> CounterParams:
    if scale >= 1.0:
        return params
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


def params_to_key(params: CounterParams) -> tuple:
    return (
        round(float(params.sensitivity), 4),
        int(params.min_area),
        int(params.max_area),
        round(float(params.min_solidity), 4),
        round(float(params.max_hole_ratio), 4),
        round(float(params.min_center_score), 4),
        int(params.split_distance),
        round(float(params.smooth_sigma), 4),
        round(float(params.background_sigma), 4),
        int(params.fill_holes_area),
        bool(params.exclude_border),
    )


def key_to_params(key: tuple) -> CounterParams:
    return CounterParams(
        sensitivity=float(key[0]),
        min_area=int(key[1]),
        max_area=int(key[2]),
        min_solidity=float(key[3]),
        max_hole_ratio=float(key[4]),
        min_center_score=float(key[5]),
        split_distance=int(key[6]),
        smooth_sigma=float(key[7]),
        background_sigma=float(key[8]),
        fill_holes_area=int(key[9]),
        exclude_border=bool(key[10]),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def cached_count(image_bytes: bytes, params_key: tuple, show_numbers: bool, high_precision: bool):
    image = load_rgb_image(image_bytes)
    params = key_to_params(params_key)
    analysis_image, scale = (image, 1.0) if high_precision else resize_for_analysis(image)
    analysis_params = scale_params_for_image(params, scale)
    result = count_cells(analysis_image, analysis_params, show_numbers=show_numbers)
    return result, analysis_image.size, scale


def sidebar_params() -> tuple[CounterParams, bool]:
    st.sidebar.header("Detection settings")
    with st.sidebar.expander("How to tune these settings", expanded=False):
        st.markdown(
            """
            Start with the defaults, then adjust only after checking the annotated image.

            - Too many membrane pores counted: raise **Minimum center stain** or lower **Maximum hollow ratio**.
            - Faint cells are missed: raise **Sensitivity** a little.
            - Tiny debris is counted: raise **Minimum area**.
            - Large stained clumps are ignored: raise **Maximum area**.
            - Touching cells are counted as one: lower **Cell splitting distance**.

            Change one setting at a time and re-check the overlay.
            """
        )
    sensitivity = st.sidebar.slider(
        "Sensitivity",
        0.0,
        1.0,
        0.50,
        0.01,
        help="Higher values detect fainter cells, but may increase false positives.",
    )
    min_area = st.sidebar.slider("Minimum area (px)", 10, 500, 70, 5)
    max_area = st.sidebar.slider("Maximum area (px)", 300, 5000, 1800, 50)
    min_solidity = st.sidebar.slider(
        "Minimum solidity",
        0.10,
        1.00,
        0.48,
        0.01,
        help="Higher values reject hollow or fragmented membrane pores.",
    )
    min_center_score = st.sidebar.slider(
        "Minimum center stain",
        0.00,
        1.00,
        0.22,
        0.01,
        help="Rejects ring-like objects whose centers are not stained.",
    )
    max_hole_ratio = st.sidebar.slider(
        "Maximum hollow ratio",
        0.00,
        0.90,
        0.32,
        0.01,
        help="Lower values reject more ring-shaped pores.",
    )
    split_distance = st.sidebar.slider(
        "Cell splitting distance (px)",
        3,
        35,
        11,
        1,
        help="Smaller values split close/touching cells more aggressively.",
    )
    show_numbers = st.sidebar.checkbox("Show cell IDs", value=False)
    exclude_border = st.sidebar.checkbox("Exclude border objects", value=False)
    high_precision = st.sidebar.checkbox(
        "High precision full-size analysis",
        value=False,
        help="Slower. Use full image resolution instead of the faster preview-sized analysis.",
    )

    params = CounterParams(
        sensitivity=sensitivity,
        min_area=min_area,
        max_area=max_area,
        min_solidity=min_solidity,
        max_hole_ratio=max_hole_ratio,
        min_center_score=min_center_score,
        split_distance=split_distance,
        exclude_border=exclude_border,
    )
    st.session_state["high_precision"] = high_precision
    return params, show_numbers


def resize_for_display(image: Image.Image, max_side: int = 1500) -> Image.Image:
    width, height = image.size
    if max(width, height) <= max_side:
        return image
    resized = image.copy()
    resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return resized


def render_result(
    image: Image.Image,
    image_bytes: bytes,
    params: CounterParams,
    file_stem: str,
    show_numbers: bool,
) -> None:
    high_precision = bool(st.session_state.get("high_precision", False))

    with st.spinner("Analyzing image..."):
        result, analysis_size, scale = cached_count(image_bytes, params_to_key(params), show_numbers, high_precision)

    if scale < 1.0:
        st.info(f"Fast mode: analyzed a {analysis_size[0]} x {analysis_size[1]} preview for speed. Enable high precision in the sidebar for full-size analysis.")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Detected cells", f"{result.count}")
    metric_cols[1].metric("Threshold", f"{result.threshold:.3f}")
    metric_cols[2].metric("Mean area", f"{result.detections['area_px'].mean():.0f} px" if result.count else "-")
    metric_cols[3].metric("Median diameter", f"{result.detections['diameter_px'].median():.1f} px" if result.count else "-")

    tabs = st.tabs(["Annotated image", "Mask", "Stain score"])
    with tabs[0]:
        st.image(resize_for_display(result.annotated_image), use_column_width=True)
        st.download_button(
            "Download annotated image",
            data=png_bytes(result.annotated_image),
            file_name=f"{file_stem}_annotated.png",
            mime="image/png",
        )
    with tabs[1]:
        st.image(resize_for_display(result.mask_image), use_column_width=True)
        st.download_button(
            "Download mask",
            data=png_bytes(result.mask_image),
            file_name=f"{file_stem}_mask.png",
            mime="image/png",
        )
    with tabs[2]:
        st.image(resize_for_display(result.score_image), use_column_width=True)
        st.download_button(
            "Download stain score",
            data=png_bytes(result.score_image),
            file_name=f"{file_stem}_score.png",
            mime="image/png",
        )


def render_single_image(params: CounterParams, show_numbers: bool) -> None:
    uploaded = st.file_uploader("Upload a Transwell image", type=SUPPORTED_TYPES)
    if uploaded is None:
        st.info("Upload a TIFF, PNG, JPG, JPEG, or BMP image to start.")
        return

    try:
        image_bytes = uploaded.getvalue()
        image = load_rgb_image(image_bytes)
    except Exception as exc:
        st.error(f"Could not read image: {exc}")
        return

    render_result(image, image_bytes, params, Path(uploaded.name).stem, show_numbers)


def render_batch(params: CounterParams) -> None:
    uploaded_files = st.file_uploader(
        "Upload multiple Transwell images",
        type=SUPPORTED_TYPES,
        accept_multiple_files=True,
    )
    if not uploaded_files:
        st.info("Upload multiple images to generate a count summary.")
        return

    rows = []
    progress = st.progress(0)
    for index, uploaded in enumerate(uploaded_files, start=1):
        try:
            image = read_uploaded_image(uploaded)
            result = count_cells(image, params, show_numbers=False)
            rows.append(
                {
                    "file": uploaded.name,
                    "count": result.count,
                    "threshold": round(result.threshold, 4),
                    "mean_area_px": round(float(result.detections["area_px"].mean()), 2) if result.count else 0,
                    "median_diameter_px": round(float(result.detections["diameter_px"].median()), 2) if result.count else 0,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "file": uploaded.name,
                    "count": "",
                    "threshold": "",
                    "mean_area_px": "",
                    "median_diameter_px": "",
                    "error": str(exc),
                }
            )
        progress.progress(index / len(uploaded_files))

    summary = pd.DataFrame(rows)
    st.dataframe(summary, use_container_width=True)
    st.download_button(
        "Download batch CSV",
        data=csv_bytes(summary),
        file_name="transwell_batch_counts.csv",
        mime="text/csv",
    )


def main() -> None:
    st.set_page_config(page_title="StainSpot Counter", page_icon=".", layout="wide")

    st.title("StainSpot Counter")
    st.caption("Upload stained microscopy images, count solid stained objects, and download annotated evidence images.")
    with st.expander("What this app does", expanded=False):
        st.markdown(
            """
            **How it differs from ImageJ threshold counting:** ImageJ-style workflows often rely on intensity
            thresholds, so hollow membrane pores and stained cells can be confused. This app combines stain color,
            local background correction, object shape, hollow ratio, and center stain intensity to prefer solid
            purple/blue cells while rejecting ring-like pores.

            **Other possible uses:** it may also help count other bright-field objects that are solidly stained
            and visually distinct from hollow/background texture, such as crystal-violet colony spots, stained
            migrated cells, or similar microscopy counting tasks.

            **Not ideal for:** fluorescence nuclei, phase-contrast cells without color staining, overlapping dense
            cell sheets, or images where the target objects and background pores have the same color/shape.
            Use **Annotated image** to visually check whether the circles match the stained objects.
            """
        )

    params, show_numbers = sidebar_params()
    mode = st.radio("Mode", ["Single image", "Batch summary"], horizontal=True)

    if mode == "Single image":
        render_single_image(params, show_numbers)
    else:
        render_batch(params)


if __name__ == "__main__":
    main()
