"""Resolusi kelas exception pihak ketiga yang nama/lokasinya berubah antar versi."""

# ChromaDB memindahkan kelas exception "koleksi tidak ada" antar versi minor,
# jadi di-resolve sekali saat import dengan fallback yang aman.
try:
    from chromadb.errors import NotFoundError as _ChromaNotFoundError

    COLLECTION_MISSING_ERRORS: tuple[type[Exception], ...] = (
        _ChromaNotFoundError,
        ValueError,
        KeyError,
    )
except ImportError:  # pragma: no cover - hanya untuk versi ChromaDB lama
    COLLECTION_MISSING_ERRORS = (ValueError, KeyError)
