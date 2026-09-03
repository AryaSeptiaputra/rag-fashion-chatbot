"""Test permukaan tool agent: schema parameter, audit, dan penanganan error."""

from typing import Any

from app.repositories.catalog import CatalogRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.sales import SalesRepository
from app.repositories.sizing import SizingRepository
from app.services.catalog import CatalogService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.tools.registry import ToolCallRecorder, build_tools
from tests.conftest import FakeSupabaseClient

EXPECTED_TOOL_NAMES = {
    "search_faq",
    "search_products",
    "get_product_detail",
    "check_stock",
    "recommend_size",
    "track_order",
    "check_promotion",
    "escalate_to_human",
}


class StubRetriever:
    """FAQRetriever palsu yang mengembalikan teks tetap."""

    def __init__(self, output: str = "kutipan FAQ") -> None:
        self.output = output
        self.queries: list[str] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        """Catat query dan kembalikan node dummy."""
        self.queries.append(query)
        return ["node"]

    def format_for_llm(self, nodes: list[Any]) -> str:
        """Kembalikan teks tetap."""
        return self.output


def build_toolset(recorder: ToolCallRecorder) -> dict[str, Any]:
    """Rakit delapan tool di atas dependensi palsu."""
    client = FakeSupabaseClient(
        rpc_rows={
            "check_availability": [
                {
                    "variant_sku": "KAO-0001-L-HIT",
                    "product_sku": "KAO-0001",
                    "product_name": "Kaos Ashen",
                    "size": "L",
                    "color": "Hitam",
                    "price": 119000,
                    "available_quantity": 5,
                    "is_available": True,
                    "next_restock_date": None,
                }
            ]
        }
    )

    def escalate_handler(reason: str, contact: str | None = None) -> str:
        return f"diteruskan: {reason}"

    tools = build_tools(
        faq_retriever=StubRetriever(),  # type: ignore[arg-type]
        catalog_service=CatalogService(
            CatalogRepository(client),  # type: ignore[arg-type]
            SalesRepository(client),  # type: ignore[arg-type]
        ),
        inventory_service=InventoryService(
            InventoryRepository(client),  # type: ignore[arg-type]
            SizingRepository(client),  # type: ignore[arg-type]
        ),
        order_service=OrderService(SalesRepository(client)),  # type: ignore[arg-type]
        escalate_handler=escalate_handler,
        recorder=recorder,
    )
    return {tool.metadata.name: tool for tool in tools}


def test_registry_exposes_exactly_eight_tools() -> None:
    toolset = build_toolset(ToolCallRecorder())

    assert set(toolset) == EXPECTED_TOOL_NAMES


def test_tool_schema_preserves_parameters() -> None:
    # Wrapper audit memakai functools.wraps supaya LlamaIndex tetap bisa membaca
    # signature; tanpa itu schema akan kosong dan LLM tidak tahu argumennya.
    toolset = build_toolset(ToolCallRecorder())

    schema = toolset["check_stock"].metadata.get_parameters_dict()

    assert set(schema["properties"]) == {"sku", "size", "color"}
    assert "sku" in schema["required"]


def test_tool_descriptions_state_when_not_to_use() -> None:
    toolset = build_toolset(ToolCallRecorder())

    for name, tool in toolset.items():
        assert "JANGAN PAKAI" in tool.metadata.description, name


def test_recorder_captures_arguments_and_latency() -> None:
    recorder = ToolCallRecorder()
    toolset = build_toolset(recorder)

    toolset["check_stock"].call(sku="KAO-0001", size="L")

    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record.tool_name == "check_stock"
    assert record.arguments["sku"] == "KAO-0001"
    assert record.arguments["color"] is None
    assert record.is_error is False
    assert record.latency_ms is not None


def test_tool_failure_is_recorded_and_reported_to_llm() -> None:
    recorder = ToolCallRecorder()

    def failing_retrieve(query: str, top_k: int | None = None) -> list[str]:
        raise RuntimeError("Koleksi FAQ kosong")

    retriever = StubRetriever()
    retriever.retrieve = failing_retrieve  # type: ignore[method-assign]

    client = FakeSupabaseClient()
    tools = build_tools(
        faq_retriever=retriever,  # type: ignore[arg-type]
        catalog_service=CatalogService(
            CatalogRepository(client),  # type: ignore[arg-type]
            SalesRepository(client),  # type: ignore[arg-type]
        ),
        inventory_service=InventoryService(
            InventoryRepository(client),  # type: ignore[arg-type]
            SizingRepository(client),  # type: ignore[arg-type]
        ),
        order_service=OrderService(SalesRepository(client)),  # type: ignore[arg-type]
        escalate_handler=lambda reason, contact=None: "ok",
        recorder=recorder,
    )
    search_faq = next(tool for tool in tools if tool.metadata.name == "search_faq")

    output = str(search_faq.call(query="cara retur"))

    assert "gagal dijalankan" in output
    assert recorder.records[0].is_error is True
