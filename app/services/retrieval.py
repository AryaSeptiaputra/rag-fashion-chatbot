"""Retrieval semantik dokumen FAQ dari ChromaDB."""

from chromadb.api import ClientAPI
from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import NodeWithScore
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.config import settings
from app.models.chat import Citation
from app.utils.errors import COLLECTION_MISSING_ERRORS
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Panjang cuplikan yang ditampilkan di panel kutipan UI. Cukup untuk mengenali
# paragrafnya, tidak cukup untuk menggantikan jawaban.
_PANJANG_CUPLIKAN = 180


def to_citations(
    nodes: list[NodeWithScore], max_citations: int = 4
) -> list[Citation]:
    """Ubah hasil retrieval jadi kutipan yang bisa ditampilkan ke pembeli.

    Dipisah dari format_for_llm() karena keduanya melayani pembaca berbeda:
    yang satu menyusun teks untuk model, yang ini menyusun metadata untuk
    layar. Yang diterima model tidak berubah sama sekali.

    Skor dari ChromaDB adalah exp(-jarak), jadi selalu berada di (0, 1] dan
    aman dipersenkan apa adanya. Nilainya dilabeli "kemiripan", bukan
    "akurasi": dengan embedding e5, kecocokan bagus jatuh di 55-82% dan yang
    lemah di 20-37%.

    Args:
        nodes: Hasil dari FAQRetriever.retrieve().
        max_citations: Jumlah kutipan terbanyak yang dikembalikan.

    Returns:
        Kutipan unik per (nama berkas, halaman), terurut dari paling mirip.
    """
    terbaik: dict[tuple[str, str | None], Citation] = {}

    for node in nodes:
        metadata = getattr(node, "metadata", None)
        if not isinstance(metadata, dict):
            # Node tanpa metadata bisa muncul kalau tipe node berubah antar
            # versi LlamaIndex. Lewati, jangan gagalkan seluruh jawaban.
            continue

        file_name = str(metadata.get("file_name") or "Dokumen FAQ")
        page = metadata.get("page_label")
        page = str(page) if page is not None else None
        score = getattr(node, "score", None)

        kutipan = Citation(
            file_name=file_name,
            page=page,
            score=score,
            match_percent=_persen(score),
            snippet=_cuplikan(node),
        )

        kunci = (file_name, page)
        sebelumnya = terbaik.get(kunci)
        if sebelumnya is None or (score or 0.0) > (sebelumnya.score or 0.0):
            terbaik[kunci] = kutipan

    terurut = sorted(terbaik.values(), key=lambda c: c.score or 0.0, reverse=True)
    return terurut[:max_citations]


def _persen(score: float | None) -> int | None:
    """Ubah skor kemiripan jadi persentase bulat.

    Args:
        score: Skor dari vector store, atau None.

    Returns:
        Persentase 0-100, atau None kalau skor tidak tersedia.
    """
    if score is None:
        return None
    return round(min(max(score, 0.0), 1.0) * 100)


def _cuplikan(node: NodeWithScore) -> str:
    """Ambil awal isi chunk sebagai cuplikan satu baris.

    Args:
        node: Node hasil retrieval.

    Returns:
        Teks yang spasinya sudah dirapikan dan dipotong, atau string kosong.
    """
    ambil_isi = getattr(node, "get_content", None)
    if not callable(ambil_isi):
        return ""

    isi = " ".join(str(ambil_isi()).split())
    if len(isi) <= _PANJANG_CUPLIKAN:
        return isi
    return isi[:_PANJANG_CUPLIKAN].rstrip() + "..."


class FAQRetriever:
    """Mencari potongan FAQ yang paling relevan dengan pertanyaan pembeli."""

    def __init__(
        self,
        chroma_client: ClientAPI,
        embed_model: BaseEmbedding,
        collection_name: str | None = None,
        top_k: int | None = None,
    ) -> None:
        self.chroma_client = chroma_client
        self.embed_model = embed_model
        self.collection_name = collection_name or settings.chroma_collection
        self.top_k = top_k or settings.retrieval_top_k
        self._index: VectorStoreIndex | None = None

    def retrieve(self, query: str, top_k: int | None = None) -> list[NodeWithScore]:
        """Ambil chunk FAQ paling relevan.

        Args:
            query: Pertanyaan pembeli.
            top_k: Jumlah chunk yang diambil; default dari setting.

        Returns:
            List node beserta skor kemiripan, terurut dari paling relevan.

        Raises:
            RuntimeError: Kalau koleksi FAQ belum pernah di-index.
        """
        retriever = self._get_index().as_retriever(
            similarity_top_k=top_k or self.top_k
        )
        nodes = retriever.retrieve(query)
        logger.info(f"Retrieval FAQ mengembalikan {len(nodes)} chunk untuk: {query!r}")
        return nodes

    def format_for_llm(self, nodes: list[NodeWithScore]) -> str:
        """Ubah hasil retrieval jadi teks siap dibaca LLM.

        Args:
            nodes: Hasil dari retrieve().

        Returns:
            Teks berisi kutipan FAQ beserta sumbernya, atau pesan eksplisit
            kalau tidak ada yang cocok.
        """
        if not nodes:
            return (
                "Tidak ditemukan informasi terkait di dokumen FAQ. "
                "Jangan mengarang jawaban."
            )

        blocks: list[str] = []
        for position, node in enumerate(nodes, start=1):
            source = node.metadata.get("file_name", "FAQ")
            page = node.metadata.get("page_label")
            location = f"{source} hal. {page}" if page else source
            blocks.append(
                f"[Kutipan {position} - sumber: {location}]\n{node.get_content().strip()}"
            )

        return "\n\n".join(blocks)

    def collection_size(self) -> int:
        """Hitung jumlah chunk yang tersimpan di koleksi FAQ.

        Returns:
            Jumlah chunk; 0 kalau koleksi belum dibuat.
        """
        try:
            collection = self.chroma_client.get_collection(self.collection_name)
        except COLLECTION_MISSING_ERRORS as exc:
            logger.warning(f"Koleksi '{self.collection_name}' belum tersedia: {exc}")
            return 0
        return collection.count()

    def _get_index(self) -> VectorStoreIndex:
        if self._index is not None:
            return self._index

        if self.collection_size() == 0:
            raise RuntimeError(
                f"Koleksi FAQ '{self.collection_name}' kosong. "
                "Jalankan 'python scripts/ingest_faq.py' lebih dulu."
            )

        collection = self.chroma_client.get_collection(self.collection_name)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        self._index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.embed_model,
        )
        return self._index
