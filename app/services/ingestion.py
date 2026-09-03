"""Pipeline ingestion dokumen FAQ: PDF menjadi vector index di ChromaDB."""

from pathlib import Path

from chromadb.api import ClientAPI
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import BaseNode, Document
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.config import settings
from app.utils.errors import COLLECTION_MISSING_ERRORS
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class FAQIngestionService:
    """Membaca dokumen FAQ, memecahnya jadi chunk, lalu menyimpan ke ChromaDB."""

    def __init__(
        self,
        chroma_client: ClientAPI,
        embed_model: BaseEmbedding,
        collection_name: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chroma_client = chroma_client
        self.embed_model = embed_model
        self.collection_name = collection_name or settings.chroma_collection
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size or settings.chunk_size,
            chunk_overlap=chunk_overlap or settings.chunk_overlap,
        )
        self.markdown_splitter = MarkdownNodeParser()

    def load_documents(self, source_dir: Path) -> list[Document]:
        """Baca semua dokumen FAQ dari direktori sumber.

        Args:
            source_dir: Direktori berisi PDF/teks FAQ.

        Returns:
            List dokumen LlamaIndex dengan metadata nama file.

        Raises:
            FileNotFoundError: Kalau direktori tidak ada atau tidak berisi dokumen.
        """
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Direktori FAQ tidak ditemukan: {source_dir}")

        reader = SimpleDirectoryReader(
            input_dir=str(source_dir),
            required_exts=[".pdf", ".txt", ".md"],
            recursive=True,
            filename_as_id=True,
        )
        documents = reader.load_data()

        if not documents:
            raise FileNotFoundError(
                f"Tidak ada dokumen FAQ (.pdf/.txt/.md) di {source_dir}"
            )

        logger.info(f"Membaca {len(documents)} halaman dokumen dari {source_dir}")
        return documents

    def build_index(self, documents: list[Document], reset: bool = True) -> int:
        """Bangun vector index dari dokumen dan simpan ke ChromaDB.

        Args:
            documents: Dokumen hasil load_documents.
            reset: Kalau True, koleksi lama dihapus lebih dulu supaya tidak ada
                chunk duplikat dari ingestion sebelumnya.

        Returns:
            Jumlah chunk yang di-index.
        """
        if reset:
            self._drop_collection()

        collection = self.chroma_client.get_or_create_collection(self.collection_name)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        nodes = self._split_documents(documents)
        logger.info(f"Memecah dokumen menjadi {len(nodes)} chunk")

        VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=False,
        )

        logger.info(
            f"Index selesai: {len(nodes)} chunk tersimpan di koleksi "
            f"'{self.collection_name}'"
        )
        return len(nodes)

    def run(self, source_dir: Path | None = None, reset: bool = True) -> int:
        """Jalankan pipeline ingestion end-to-end.

        Args:
            source_dir: Direktori sumber; default dari setting FAQ_SOURCE_DIR.
            reset: Hapus koleksi lama sebelum index ulang.

        Returns:
            Jumlah chunk yang di-index.
        """
        documents = self.load_documents(source_dir or settings.faq_path)
        return self.build_index(documents, reset=reset)

    def _split_documents(self, documents: list[Document]) -> list[BaseNode]:
        """Pecah dokumen jadi chunk, menghormati batas topik kalau ada.

        Dokumen Markdown dipecah per heading lebih dulu supaya satu chunk tidak
        mencampur beberapa topik FAQ; hasil potongan yang masih terlalu panjang
        dipecah lagi per kalimat. Format lain (PDF, teks) langsung dipecah per
        kalimat karena tidak punya penanda struktur.

        Args:
            documents: Dokumen hasil load_documents.

        Returns:
            List node siap di-embed.
        """
        markdown_docs = [
            doc
            for doc in documents
            if str(doc.metadata.get("file_name", "")).lower().endswith((".md", ".markdown"))
        ]
        other_docs = [doc for doc in documents if doc not in markdown_docs]

        nodes: list[BaseNode] = []

        if markdown_docs:
            sections = self.markdown_splitter.get_nodes_from_documents(markdown_docs)
            nodes.extend(self.splitter.get_nodes_from_documents(sections))
            logger.info(
                f"{len(markdown_docs)} dokumen Markdown dipecah per heading "
                f"menjadi {len(sections)} bagian"
            )

        if other_docs:
            nodes.extend(self.splitter.get_nodes_from_documents(other_docs))

        return nodes

    def _drop_collection(self) -> None:
        try:
            self.chroma_client.delete_collection(self.collection_name)
            logger.info(f"Koleksi lama '{self.collection_name}' dihapus")
        except COLLECTION_MISSING_ERRORS:
            logger.info(f"Koleksi '{self.collection_name}' belum ada, lanjut buat baru")
