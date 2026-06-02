---
title: Transwell Cell Counter
emoji: 🔬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
---

# Transwell Cell Counter

Web app for counting stained cells in Transwell migration/invasion images.

The app is designed for images where cells are purple/blue stained and membrane pores appear as small hollow rings. It outputs the cell count together with an annotated image, mask, stain-score image, and a CSV table of detected cell coordinates.

## Features

- Upload TIFF, PNG, JPG, JPEG, or BMP images directly in the browser.
- Tune detection settings interactively.
- Reduce false positives from hollow membrane pores using stain-center and hollow-ratio filters.
- Split touching cells with watershed segmentation.
- Download annotated proof images and per-cell CSV data.
- Run as a public web app or locally from source.

## Try Online

The public app is available here:

https://xushaojie-transwell-cell-counter.hf.space/

Users can open the URL directly, upload an image, inspect the annotated result, and download output images. No installation is required.

Deploy this repository with one of these free web-app hosts:

- Streamlit Community Cloud: connect your GitHub repository and set `app.py` as the app entry point.
- Hugging Face Spaces: create a Docker Space and push this repository. The included `Dockerfile` starts the Streamlit app with Python 3.12.

After deployment, users only need to open the web URL and upload images. No Windows installation is required.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

## Detection Logic

The app does not simply threshold the whole image like a basic ImageJ workflow. It tries to separate solid stained cells from hollow membrane pores:

1. It builds a stain score from purple/blue color, saturation, darkness, and local background correction.
2. It creates candidate stained regions with an adaptive threshold.
3. It separates touching cells using distance transform and watershed segmentation.
4. It rejects likely pores by checking object area, solidity, hollow ratio, and whether the object center is actually stained.
5. It draws circles on accepted cells so users can visually audit the count.

## Sample Result

The local sample `I40_1_1.tif` was counted with the default parameters:

- Detected cells: `2941`
- Annotated image: `sample_result/I40_1_1_annotated.png`
- Mask: `sample_result/I40_1_1_mask.png`
- Stain score: `sample_result/I40_1_1_score.png`
- Cell table: `sample_result/I40_1_1_cells.csv`

The original microscopy TIFF is not included in this repository because raw experimental data should remain private unless you intentionally publish it.

## Notes

This is an image-analysis aid, not a ground-truth biological measurement. Always inspect the annotated image and tune parameters for each imaging/staining condition before reporting final counts.

## License

MIT License. See `LICENSE`.
