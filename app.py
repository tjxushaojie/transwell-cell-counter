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
    return params, show_numbers


def resize_for_display(image: Image.Image, max_side: int = 1500) -> Image.Image:
    width, height = image.size
    if max(width, height) <= max_side:
        return image
    resized = image.copy()
    resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return resized


def render_compare(original: Image.Image, annotated: Image.Image) -> None:
    choice = st.radio(
        "View",
        ["Annotated image", "Original image"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.caption("Switch between the annotated result and the original image to check whether the count is reasonable.")
    if choice == "Original image":
        st.image(resize_for_display(original), use_column_width=True)
    else:
        st.image(resize_for_display(annotated), use_column_width=True)


def render_result(image: Image.Image, params: CounterParams, file_stem: str, show_numbers: bool) -> None:
    with st.spinner("Analyzing image..."):
        result = count_cells(image, params, show_numbers=show_numbers)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Detected cells", f"{result.count}")
    metric_cols[1].metric("Threshold", f"{result.threshold:.3f}")
    metric_cols[2].metric("Mean area", f"{result.detections['area_px'].mean():.0f} px" if result.count else "-")
    metric_cols[3].metric("Median diameter", f"{result.detections['diameter_px'].median():.1f} px" if result.count else "-")

    tabs = st.tabs(["Compare", "Annotated image", "Mask", "Stain score"])
    with tabs[0]:
        render_compare(image, result.annotated_image)
    with tabs[1]:
        st.image(resize_for_display(result.annotated_image), use_column_width=True)
        st.download_button(
            "Download annotated image",
            data=png_bytes(result.annotated_image),
            file_name=f"{file_stem}_annotated.png",
            mime="image/png",
        )
    with tabs[2]:
        st.image(resize_for_display(result.mask_image), use_column_width=True)
        st.download_button(
            "Download mask",
            data=png_bytes(result.mask_image),
            file_name=f"{file_stem}_mask.png",
            mime="image/png",
        )
    with tabs[3]:
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
        image = read_uploaded_image(uploaded)
    except Exception as exc:
        st.error(f"Could not read image: {exc}")
        return

    render_result(image, params, Path(uploaded.name).stem, show_numbers)


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
            Use **Compare** to switch between the original image and the annotated result.
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
