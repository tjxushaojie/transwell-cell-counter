from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from transwell_counter import CounterParams, auto_tune_params, count_cells, load_rgb_image


SUPPORTED_TYPES = ["tif", "tiff", "png", "jpg", "jpeg", "bmp"]
PARAM_DEFAULTS = {
    "sensitivity": 0.50,
    "min_area": 70,
    "max_area": 1800,
    "min_solidity": 0.48,
    "min_center_score": 0.22,
    "max_hole_ratio": 0.32,
    "split_distance": 11,
    "show_numbers": False,
    "exclude_border": False,
}


def ensure_param_state() -> None:
    for key, value in PARAM_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def apply_params_to_state(params: CounterParams) -> None:
    st.session_state["sensitivity"] = float(params.sensitivity)
    st.session_state["min_area"] = int(params.min_area)
    st.session_state["max_area"] = int(params.max_area)
    st.session_state["min_solidity"] = float(params.min_solidity)
    st.session_state["min_center_score"] = float(params.min_center_score)
    st.session_state["max_hole_ratio"] = float(params.max_hole_ratio)
    st.session_state["split_distance"] = int(params.split_distance)
    st.session_state["exclude_border"] = bool(params.exclude_border)


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_data_uri(image: Image.Image) -> str:
    encoded = base64.b64encode(png_bytes(image)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def read_uploaded_image(uploaded_file) -> Image.Image:
    return load_rgb_image(uploaded_file.getvalue())


def sidebar_params() -> tuple[CounterParams, bool]:
    ensure_param_state()
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
    if st.sidebar.button("Reset defaults", use_container_width=True):
        for key, value in PARAM_DEFAULTS.items():
            st.session_state[key] = value
        st.rerun()
    sensitivity = st.sidebar.slider(
        "Sensitivity",
        0.0,
        1.0,
        key="sensitivity",
        step=0.01,
        help="Higher values detect fainter cells, but may increase false positives.",
    )
    min_area = st.sidebar.slider("Minimum area (px)", 10, 500, key="min_area", step=5)
    max_area = st.sidebar.slider("Maximum area (px)", 300, 5000, key="max_area", step=50)
    min_solidity = st.sidebar.slider(
        "Minimum solidity",
        0.10,
        1.00,
        key="min_solidity",
        step=0.01,
        help="Higher values reject hollow or fragmented membrane pores.",
    )
    min_center_score = st.sidebar.slider(
        "Minimum center stain",
        0.00,
        1.00,
        key="min_center_score",
        step=0.01,
        help="Rejects ring-like objects whose centers are not stained.",
    )
    max_hole_ratio = st.sidebar.slider(
        "Maximum hollow ratio",
        0.00,
        0.90,
        key="max_hole_ratio",
        step=0.01,
        help="Lower values reject more ring-shaped pores.",
    )
    split_distance = st.sidebar.slider(
        "Cell splitting distance (px)",
        3,
        35,
        key="split_distance",
        step=1,
        help="Smaller values split close/touching cells more aggressively.",
    )
    show_numbers = st.sidebar.checkbox("Show cell IDs", key="show_numbers")
    exclude_border = st.sidebar.checkbox("Exclude border objects", key="exclude_border")

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


def render_hold_compare(original: Image.Image, annotated: Image.Image) -> None:
    original_uri = image_data_uri(original)
    annotated_uri = image_data_uri(annotated)
    components.html(
        f"""
        <style>
          .tw-compare {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            max-width: 100%;
          }}
          .tw-frame {{
            position: relative;
            border: 1px solid #d8dde6;
            border-radius: 8px;
            overflow: hidden;
            background: #f7f8fa;
          }}
          .tw-frame img {{
            width: 100%;
            display: block;
            user-select: none;
            -webkit-user-drag: none;
          }}
          .tw-badge {{
            position: absolute;
            left: 12px;
            top: 12px;
            background: rgba(17, 24, 39, 0.82);
            color: #fff;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 14px;
            line-height: 1.2;
          }}
          .tw-button {{
            margin-top: 10px;
            border: 1px solid #c9ced8;
            border-radius: 6px;
            background: #ffffff;
            color: #111827;
            cursor: pointer;
            font-size: 15px;
            font-weight: 600;
            padding: 8px 13px;
          }}
          .tw-button:active {{
            background: #eef2f7;
          }}
          .tw-hint {{
            color: #5b6472;
            font-size: 13px;
            margin-top: 7px;
          }}
        </style>
        <div class="tw-compare">
          <div class="tw-frame">
            <img id="tw-image" src="{annotated_uri}" alt="Annotated Transwell image">
            <div id="tw-badge" class="tw-badge">Annotated image</div>
          </div>
          <button id="tw-toggle" class="tw-button" type="button">Hold to view original</button>
          <div class="tw-hint">Press and hold the button to hide circles. Release to return to the annotated result.</div>
        </div>
        <script>
          const img = document.getElementById("tw-image");
          const badge = document.getElementById("tw-badge");
          const button = document.getElementById("tw-toggle");
          const annotated = "{annotated_uri}";
          const original = "{original_uri}";

          function showOriginal() {{
            img.src = original;
            badge.textContent = "Original image";
          }}
          function showAnnotated() {{
            img.src = annotated;
            badge.textContent = "Annotated image";
          }}

          button.addEventListener("mousedown", showOriginal);
          button.addEventListener("mouseup", showAnnotated);
          button.addEventListener("mouseleave", showAnnotated);
          button.addEventListener("touchstart", function(event) {{
            event.preventDefault();
            showOriginal();
          }}, {{ passive: false }});
          button.addEventListener("touchend", showAnnotated);
          button.addEventListener("touchcancel", showAnnotated);
        </script>
        """,
        height=760,
        scrolling=True,
    )


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
        render_hold_compare(image, result.annotated_image)
    with tabs[1]:
        st.image(result.annotated_image, use_column_width=True)
        st.download_button(
            "Download annotated image",
            data=png_bytes(result.annotated_image),
            file_name=f"{file_stem}_annotated.png",
            mime="image/png",
        )
    with tabs[2]:
        st.image(result.mask_image, use_column_width=True)
        st.download_button(
            "Download mask",
            data=png_bytes(result.mask_image),
            file_name=f"{file_stem}_mask.png",
            mime="image/png",
        )
    with tabs[3]:
        st.image(result.score_image, use_column_width=True)
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

    tune_cols = st.columns([1, 3])
    with tune_cols[0]:
        auto_tune_clicked = st.button("Auto tune current image", type="secondary", use_container_width=True)
    with tune_cols[1]:
        st.caption("Auto tune tries several parameter sets and picks a conservative starting point. Inspect the overlay after tuning.")

    if auto_tune_clicked:
        with st.spinner("Auto tuning parameters..."):
            tuned = auto_tune_params(image, params)
        apply_params_to_state(tuned.params)
        st.session_state["last_auto_tune"] = (
            f"Auto tune evaluated {tuned.candidates_evaluated} options; "
            f"estimated {tuned.estimated_count} cells on a preview image."
        )
        st.rerun()

    if "last_auto_tune" in st.session_state:
        st.success(st.session_state["last_auto_tune"])

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
    st.set_page_config(page_title="Transwell Counter", page_icon=".", layout="wide")

    st.title("Transwell Cell Counter")
    st.caption("Upload stained Transwell images, count cells, and download annotated evidence images.")
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
            Use **Compare** to hold-toggle between the original image and the annotated result.
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
