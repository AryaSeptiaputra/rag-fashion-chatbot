"""Fondasi akses data Supabase: eksekusi query + normalisasi error."""

from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class RepositoryError(RuntimeError):
    """Kegagalan akses data yang sudah diberi konteks nama operasi."""


class BaseRepository:
    """Pembungkus tipis client Supabase.

    Semua subclass mengakses database hanya lewat dua method di sini, sehingga
    penanganan error dan logging seragam di seluruh repository.
    """

    def __init__(self, client: Client) -> None:
        self.client = client

    def call_rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Panggil RPC Postgres dan kembalikan barisnya.

        Args:
            function_name: Nama fungsi di database (mis. "search_products").
            params: Argumen fungsi, memakai prefix p_ sesuai definisi SQL.

        Returns:
            List baris hasil; list kosong kalau tidak ada yang cocok.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        try:
            response = self.client.rpc(function_name, params).execute()
        except APIError as exc:
            logger.error(
                f"RPC {function_name} gagal: {exc.message}", exc_info=True
            )
            raise RepositoryError(f"Query {function_name} gagal dijalankan") from exc

        return self._as_rows(response.data)

    def select_view(
        self,
        view_name: str,
        filters: dict[str, Any] | None = None,
        columns: str = "*",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Baca baris dari view dengan filter kesamaan sederhana.

        Args:
            view_name: Nama view (mis. "v_product_catalog").
            filters: Pasangan kolom-nilai untuk klausa eq.
            columns: Daftar kolom yang diambil.
            limit: Batas jumlah baris.

        Returns:
            List baris hasil; list kosong kalau tidak ada yang cocok.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        try:
            query = self.client.table(view_name).select(columns)
            for column, value in (filters or {}).items():
                query = query.eq(column, value)
            if limit is not None:
                query = query.limit(limit)
            response = query.execute()
        except APIError as exc:
            logger.error(f"Select {view_name} gagal: {exc.message}", exc_info=True)
            raise RepositoryError(f"Query {view_name} gagal dijalankan") from exc

        return self._as_rows(response.data)

    @staticmethod
    def _as_rows(data: Any) -> list[dict[str, Any]]:
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return list(data)
