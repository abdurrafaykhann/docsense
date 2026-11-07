FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./
# INSTALL_ML=1 (default): docTR OCR, sentence-transformers, YOLO. These are the real models the demo uses.
# INSTALL_ML=0: small image; set OCR_ENGINE=fake EMBEDDER=hash RERANKER=overlap for a models-free demo.
ARG INSTALL_ML=1
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_ML" = "1" ]; then \
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
   && pip install -r requirements-ml.txt; \
    fi

# Bake the pretrained weights into the image and run offline afterwards. Otherwise every model load
# makes dozens of Hugging Face hub requests, and flaky Docker DNS turns the first question into minutes.
RUN if [ "$INSTALL_ML" = "1" ]; then       python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); from doctr.models import ocr_predictor; ocr_predictor(det_arch='db_mobilenet_v3_large', reco_arch='crnn_mobilenet_v3_small', pretrained=True)"    && echo 'models baked';     fi
ENV HF_HUB_OFFLINE=1

COPY . .
RUN chmod +x docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
