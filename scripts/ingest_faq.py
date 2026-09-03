"""Bangun vector index FAQ dari dokumen di data/raw/faq/.

Jalankan: python scripts/ingest_faq.py
"""

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.dependencies import get_chroma_client, get_embedding_model
from app.services.ingestion import FAQIngestionService
from app.utils.console import configure_console_encoding
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Baca argumen command line.

    Returns:
        Namespace berisi source_dir dan flag append.
    """
    parser = argparse.ArgumentParser(description="Ingest dokumen FAQ ke ChromaDB")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Direktori dokumen FAQ (default dari FAQ_SOURCE_DIR di .env)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Tambahkan ke koleksi yang ada, jangan hapus index lama",
    )
    return parser.parse_args()


def main() -> int:
    """Jalankan pipeline ingestion FAQ.

    Returns:
        0 kalau berhasil, 1 kalau gagal.
    """
    configure_console_encoding()
    args = parse_args()
    source_dir = args.source_dir or settings.faq_path

    service = FAQIngestionService(
        chroma_client=get_chroma_client(),
        embed_model=get_embedding_model(),
    )

    try:
        chunk_count = service.run(source_dir=source_dir, reset=not args.append)
    except FileNotFoundError as exc:
        logger.error(f"{exc}")
        logger.error(
            "Taruh minimal satu file PDF/TXT/MD berisi FAQ di direktori tersebut, "
            "lalu jalankan ulang."
        )
        return 1

    print(
        f"Indexed {chunk_count} chunks ke koleksi '{settings.chroma_collection}' "
        f"di {settings.chroma_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
