# Deployment Guide

This project is ready for GitHub-based web deployment. If Streamlit Community Cloud blocks your account with a fair-use `403`, use the Hugging Face Spaces Docker option.

## Option A: Streamlit Community Cloud

1. Create a public GitHub repository.
2. Push this project to the repository.
3. Go to `https://share.streamlit.io`.
4. Click `Create app`.
5. Select the GitHub repository, branch, and entry file:

```text
app.py
```

6. In advanced settings, choose Python 3.12 if available.
7. Deploy.

Streamlit will install dependencies from `requirements.txt` and run the app from the repository root.

If deployment tries to use Python 3.14 and compiles scientific packages from source, set the Python version to 3.12 in advanced settings. This repository also includes `runtime.txt` with `python-3.12`.

## Option B: Hugging Face Spaces Docker

Use this option if Streamlit Community Cloud shows a fair-use `403` block.

1. Create a Hugging Face account.
2. Create a new Space at `https://huggingface.co/new-space`.
3. Choose:

```text
Space SDK: Docker
Visibility: Public
```

4. Push this repository to the Space repository, or import/sync the GitHub repository.
5. Hugging Face will build the included `Dockerfile`.

The Docker image uses Python 3.12 and starts:

```text
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Publishing Raw Images

Do not commit private microscopy TIFF files unless you intentionally want them public. Upload images through the web app at runtime instead.

## Useful Links

- Streamlit deployment docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Streamlit file organization docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization
- Streamlit dependency docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- Hugging Face Streamlit Spaces docs: https://huggingface.co/docs/hub/spaces-sdks-streamlit
