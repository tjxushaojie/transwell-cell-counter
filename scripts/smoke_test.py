from __future__ import annotations

import numpy as np
import sys
from PIL import Image, ImageDraw

sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from transwell_counter import CounterParams, auto_tune_params, count_cells


def make_synthetic_transwell() -> Image.Image:
    image = Image.new("RGB", (360, 260), (211, 219, 202))
    draw = ImageDraw.Draw(image)

    # Hollow membrane pores.
    for x in range(25, 350, 34):
        for y in range(24, 250, 32):
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(95, 83, 105), width=1)
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(232, 236, 226))

    # Solid stained cells.
    cells = [(55, 58), (128, 74), (190, 92), (262, 66), (310, 116), (82, 172), (160, 182), (248, 196)]
    for x, y in cells:
        draw.ellipse((x - 10, y - 9, x + 10, y + 9), fill=(94, 22, 155))

    rng = np.random.default_rng(7)
    arr = np.asarray(image).astype(np.int16)
    arr += rng.normal(0, 5, arr.shape).astype(np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def main() -> None:
    image = make_synthetic_transwell()
    result = count_cells(
        image,
        CounterParams(sensitivity=0.45, min_area=80, max_area=800, min_center_score=0.25),
    )
    print(f"synthetic_count={result.count}")
    assert result.count >= 6, "Synthetic stained cells were not detected."
    assert result.count <= 12, "Synthetic hollow pores may be over-counted."

    tuned = auto_tune_params(image)
    tuned_result = count_cells(image, tuned.params)
    print(f"synthetic_auto_tuned_count={tuned_result.count}")
    assert 6 <= tuned_result.count <= 12, "Auto tune did not find a useful parameter set."


if __name__ == "__main__":
    main()
