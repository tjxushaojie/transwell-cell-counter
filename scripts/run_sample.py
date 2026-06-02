from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from transwell_counter import CounterParams, count_cells, load_rgb_image


SAMPLE = Path(r"E:\Labdata\F\data\体外功能实验\transwell\勿动原始数据\20240726\I40\I40_1_1.tif")
OUT = Path("sample_result")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    image = load_rgb_image(SAMPLE)
    params = CounterParams()
    result = count_cells(image, params, show_numbers=False)

    result.annotated_image.save(OUT / "I40_1_1_annotated.png")
    result.mask_image.save(OUT / "I40_1_1_mask.png")
    result.score_image.save(OUT / "I40_1_1_score.png")
    result.detections.to_csv(OUT / "I40_1_1_cells.csv", index=False, encoding="utf-8-sig")
    print("count", result.count)
    print("threshold", round(result.threshold, 4))
    print(result.detections.describe(include="all").to_string())


if __name__ == "__main__":
    main()
