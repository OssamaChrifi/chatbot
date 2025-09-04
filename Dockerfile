# Stage 1: Pre-install unstructured PDF dependencies
FROM python:3.12-slim AS base
WORKDIR /app

# Install system packages for PDF parsing
RUN apt-get update && apt-get install -y \
    libmagic-dev \
    poppler-utils \
    tesseract-ocr \
    qpdf \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements including unstructured for PDFs
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim AS runtime
WORKDIR /usr/src/app

# Install curl (for debugging) and OpenCV GL dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
  && rm -rf /var/lib/apt/lists/*

# Copy system tools from base
COPY --from=base /usr/bin/tesseract /usr/bin/tesseract
COPY --from=base /usr/bin/pdfinfo /usr/bin/pdfinfo
COPY --from=base /usr/bin/pdftotext /usr/bin/pdftotext
COPY --from=base /usr/bin/pdftoppm /usr/bin/pdftoppm
COPY --from=base /usr/bin/qpdf /usr/bin/qpdf
COPY --from=base /usr/lib/libmagic* /usr/lib/libmagic*
COPY --from=base /usr/share/fontconfig /usr/share/fontconfig

# Copy installed Python packages
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Expose Flask port
EXPOSE 5000
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]