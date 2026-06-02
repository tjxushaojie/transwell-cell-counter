from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color, exposure, filters, measure, morphology, segmentation


SAMPLE = Path(r"E:\Labdata\F\data\体外功能实验\transwell\勿动原始数据\20240726\I40\I40_1_1.tif")
OUT = Path("analysis_outputs")


def save_bool(mask: np.ndarray, path: Path) -> None:
    Image.fromarray((mask.astype(np.uint8) * 255)).save(path)


def main() -> None:
    OUT.mkdir(exist_ok=True)

    image = np.asarray(Image.open(SAMPLE).convert("RGB"))
    Image.fromarray(image).save(OUT / "sample_preview.png")

    lab = color.rgb2lab(image)
    hsv = color.rgb2hsv(image)
    hed = color.rgb2hed(image)
    gray = color.rgb2gray(image)

    channels = {
        "lab_l": lab[:, :, 0],
        "lab_a": lab[:, :, 1],
        "lab_b": lab[:, :, 2],
        "hsv_h": hsv[:, :, 0],
        "hsv_s": hsv[:, :, 1],
        "hsv_v": hsv[:, :, 2],
        "hed_h": hed[:, :, 0],
        "hed_e": hed[:, :, 1],
        "hed_d": hed[:, :, 2],
        "gray": gray,
    }

    for name, arr in channels.items():
        norm = exposure.rescale_intensity(arr, out_range=(0, 255)).astype(np.uint8)
        Image.fromarray(norm).save(OUT / f"{name}.png")

    # Crystal-violet-like transwell cells are typically darker and more saturated
    # than translucent membrane pores. This explores color-driven masks first.
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    lab_b = lab[:, :, 2]
    lab_a = lab[:, :, 1]

    mask_candidates = {
        "sat_gt_otsu": sat > filters.threshold_otsu(sat),
        "dark_lt_otsu": val < filters.threshold_otsu(val),
        "blue_lab_b_low": lab_b < filters.threshold_otsu(lab_b),
        "purple_a_high_b_low": (lab_a > np.percentile(lab_a, 55)) & (lab_b < np.percentile(lab_b, 45)),
        "sat_dark": (sat > np.percentile(sat, 55)) & (val < np.percentile(val, 70)),
    }

    for name, mask in mask_candidates.items():
        clean = morphology.remove_small_objects(mask, 25)
        clean = morphology.remove_small_holes(clean, 20)
        clean = segmentation.clear_border(clean)
        save_bool(clean, OUT / f"mask_{name}.png")
        labels = measure.label(clean)
        props = measure.regionprops(labels)
        areas = np.array([p.area for p in props])
        if areas.size:
            print(
                name,
                "components",
                len(props),
                "area_p5_p50_p95",
                np.percentile(areas, [5, 50, 95]).round(2).tolist(),
            )
        else:
            print(name, "components", 0)


if __name__ == "__main__":
    main()
