# Deployment Guide

This project is ready for GitHub-based web deployment. The simplest path is Streamlit Community Cloud.

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

## Option B: Hugging Face Spaces

Hugging Face Spaces can host Streamlit apps, but the built-in Streamlit SDK path has changed over time. For new Spaces, follow the current Hugging Face Streamlit template or Docker-based Streamlit instructions.

The app entry file is still:

```text
app.py
```

The dependency file is:

```text
requirements.txt
```

## Publishing Raw Images

Do not commit private microscopy TIFF files unless you intentionally want them public. Upload images through the web app at runtime instead.

## Useful Links

- Streamlit deployment docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Streamlit file organization docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization
- Streamlit dependency docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- Hugging Face Streamlit Spaces docs: https://huggingface.co/docs/hub/spaces-sdks-streamlit
