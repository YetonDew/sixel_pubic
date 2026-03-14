from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from google.cloud import storage
from google.cloud import vision


# ========= CONFIG =========
GCS_BUCKET = "sixel-ocr"
GCS_INPUT_PREFIX = "input"
GCS_OUTPUT_PREFIX = "output"
OCR_TIMEOUT_SECONDS = 300  # 5 minutos


def _storage_client() -> storage.Client:
    return storage.Client()


def _vision_client() -> vision.ImageAnnotatorClient:
    return vision.ImageAnnotatorClient()


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> str:
    """
    Sube un archivo local a GCS y devuelve su URI gs://...
    """
    client = _storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    return f"gs://{bucket_name}/{blob_name}"


def download_json_objects(bucket_name: str, prefix: str) -> List[dict]:
    """
    Descarga todos los JSON generados por Vision dentro de un prefix.
    """
    client = _storage_client()
    bucket = client.bucket(bucket_name)

    objs: List[dict] = []
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.endswith(".json"):
            raw = blob.download_as_bytes()
            objs.append(json.loads(raw))
    return objs


def cleanup_prefix(bucket_name: str, prefix: str) -> None:
    """
    Borra todos los objetos bajo un prefix (para limpiar input/output).
    """
    client = _storage_client()
    bucket = client.bucket(bucket_name)

    blobs = list(bucket.list_blobs(prefix=prefix))
    for b in blobs:
        b.delete()


def ocr_pdf_google_vision(
    pdf_path: str | Path,
    bucket_name: str = GCS_BUCKET,
    input_prefix: str = GCS_INPUT_PREFIX,
    output_prefix: str = GCS_OUTPUT_PREFIX,
    pages: Optional[List[int]] = None,
    cleanup: bool = False,
) -> Tuple[str, Dict]:
    """
    OCR de PDF con Google Vision usando async_batch_annotate_files.
    Requiere bucket GCS y credenciales (GOOGLE_APPLICATION_CREDENTIALS).

    Retorna:
      full_text: texto completo concatenado por páginas
      debug: información sobre URIs y cantidad de resultados
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe: {pdf_path}")

    ts = int(time.time())

    # GCS paths
    input_blob_name = f"{input_prefix}/{ts}_{pdf_path.name}"
    output_prefix_name = f"{output_prefix}/{ts}_{pdf_path.stem}/"

    gcs_source_uri = upload_to_gcs(pdf_path, bucket_name, input_blob_name)
    gcs_destination_uri = f"gs://{bucket_name}/{output_prefix_name}"

    client = _vision_client()

    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    gcs_source = vision.GcsSource(uri=gcs_source_uri)
    input_config = vision.InputConfig(
        gcs_source=gcs_source,
        mime_type="application/pdf",
    )

    gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
    output_config = vision.OutputConfig(
        gcs_destination=gcs_destination,
        batch_size=20,
    )

    request = vision.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
    )

    operation = client.async_batch_annotate_files(requests=[request])
    operation.result(timeout=OCR_TIMEOUT_SECONDS)

    # Descargar resultados (JSON)
    json_objs = download_json_objects(bucket_name, output_prefix_name)

    page_texts: List[str] = []
    for obj in json_objs:
        # obj: {"responses":[{fullTextAnnotation:{text:...}}, ...]}
        for resp in obj.get("responses", []):
            doc = resp.get("fullTextAnnotation") or {}
            text = doc.get("text") or ""
            if text.strip():
                page_texts.append(text)

    full_text = "\n\n".join(page_texts).strip()

    debug = {
        "bucket": bucket_name,
        "gcs_source_uri": gcs_source_uri,
        "gcs_output_prefix": output_prefix_name,
        "json_files": len(json_objs),
        "pages_detected": len(page_texts),
    }

    if cleanup:
        # Borra el PDF subido + JSONs generados
        cleanup_prefix(bucket_name, input_blob_name)
        cleanup_prefix(bucket_name, output_prefix_name)

    return full_text, debug
