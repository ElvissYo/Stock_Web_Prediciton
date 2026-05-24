# Free Public Deployment

Recommended target: Hugging Face Spaces with Docker.

This gives a public link without buying a domain:

```text
https://huggingface.co/spaces/YOUR_USERNAME/ihsg-forecasting-dashboard
https://YOUR_USERNAME-ihsg-forecasting-dashboard.hf.space
```

Hugging Face Spaces supports Docker apps and exposes the app port configured in the Space README.
The free CPU Basic hardware is enough for this dashboard's Python API, LightGBM artifact, and
Parquet files.

## Files Required In The Space

Upload the repo code plus these runtime artifacts:

```text
data/prices_full_top100.parquet
data/news_raw.parquet
data/nlp_features.parquet
data/final_dataset.parquet
data/processed/price_features.parquet
data/processed/global_model_predictions.parquet
data/processed/company_profiles.json
data/seeds/idx_stock_universe.csv
models/global_model_with_nlp.joblib
reports/metrics.json
reports/feature_importance.png
```

The artifacts are intentionally tracked with Git LFS rules in `.gitattributes`.

## Deploy Steps

1. Create a Hugging Face account.
2. Create a new Space.
3. Choose `Docker` as the SDK.
4. Name it `ihsg-forecasting-dashboard`.
5. Keep hardware as the free `CPU Basic`.
6. Copy `README.HF.md` content into the Space `README.md`.
7. Push this repo's files to the Space repository.
8. Make sure Git LFS is enabled before pushing Parquet/model artifacts:

```powershell
git lfs install
git lfs track "*.parquet" "*.joblib" "*.pkl" "*.png" "models/*.txt"
git add .gitattributes
```

9. Add the runtime artifacts. They are ignored in normal app development, so use `-f` only for
   the Hugging Face Space deployment branch/repository:

```powershell
git add -f data/prices_full_top100.parquet
git add -f data/news_raw.parquet
git add -f data/nlp_features.parquet
git add -f data/final_dataset.parquet
git add -f data/processed/price_features.parquet
git add -f data/processed/global_model_predictions.parquet
git add -f data/processed/company_profiles.json
git add -f models/global_model_with_nlp.joblib
git add -f reports/metrics.json reports/feature_importance.png
git add -f README.HF.md Dockerfile .dockerignore DEPLOYMENT.md
```

10. Push to the Space repo:

```powershell
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/ihsg-forecasting-dashboard
git push hf main
```

Hugging Face will build the Docker image and publish the app at the Space URL.

## Local Docker Check

Before pushing, test the same container locally:

```powershell
docker build -t ihsg-dashboard .
docker run --rm -p 7860:7860 ihsg-dashboard
```

Open:

```text
http://127.0.0.1:7860
```

## Notes

- No custom domain is needed. Use the free Hugging Face URL.
- Free Spaces can sleep or rebuild, so the first request can be slower.
- If you retrain the model locally, regenerate and push the updated artifacts.
