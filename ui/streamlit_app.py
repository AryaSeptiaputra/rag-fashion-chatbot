"""Demo UI chat sederhana yang mengonsumsi REST API.

UI ini sengaja memanggil REST API alih-alih mengimpor ChatbotService langsung,
supaya yang didemokan ke klien adalah jalur yang sama dengan integrasi
produksi nantinya.

Jalankan: streamlit run ui/streamlit_app.py
"""

import uuid

import httpx
import streamlit as st

from app.config import settings

REQUEST_TIMEOUT_SECONDS = 120.0


def init_state() -> None:
    """Siapkan state sesi Streamlit kalau belum ada."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"demo-{uuid.uuid4().hex[:12]}"
    if "messages" not in st.session_state:
        st.session_state.messages = []


def call_chat_api(base_url: str, session_id: str, message: str) -> dict[str, object]:
    """Kirim pesan ke endpoint chat.

    Args:
        base_url: Base URL API.
        session_id: Identifier sesi percakapan.
        message: Pesan dari pengguna.

    Returns:
        Body respons API, atau dict berisi kunci "error" kalau gagal.
    """
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/v1/chat",
            json={"session_id": session_id, "message": message, "channel": "web"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return {"error": f"Tidak bisa menghubungi API di {base_url}: {exc}"}

    if response.status_code != 200:
        return {"error": f"API mengembalikan {response.status_code}: {response.text}"}

    return response.json()


def render_sidebar() -> str:
    """Gambar sidebar konfigurasi dan status.

    Returns:
        Base URL API yang dipilih pengguna.
    """
    with st.sidebar:
        st.subheader("Konfigurasi")
        base_url = st.text_input("Base URL API", value=settings.api_base_url)
        st.caption(f"Session ID: `{st.session_state.session_id}`")

        if st.button("Mulai percakapan baru", use_container_width=True):
            st.session_state.session_id = f"demo-{uuid.uuid4().hex[:12]}"
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.subheader("Status layanan")
        try:
            health = httpx.get(f"{base_url.rstrip('/')}/api/v1/health", timeout=10.0)
            payload = health.json()
            st.metric("Chunk FAQ ter-index", payload.get("faq_chunks", 0))
            st.write(f"Model: `{payload.get('llm_model', '-')}`")
            llm_ready = bool(payload.get("llm_ready"))
            st.write("LLM lokal: " + ("siap" if llm_ready else "belum siap"))
            if not llm_ready:
                st.warning(payload.get("llm_detail", "Ollama belum siap."))
            st.write(
                "Supabase: "
                + ("terhubung" if payload.get("supabase_connected") else "belum siap")
            )
        except (httpx.HTTPError, ValueError):
            st.warning("API belum bisa dihubungi. Jalankan uvicorn lebih dulu.")

    return base_url


def render_history() -> None:
    """Gambar ulang seluruh riwayat percakapan."""
    for entry in st.session_state.messages:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry.get("tool_calls"):
                names = ", ".join(call["tool_name"] for call in entry["tool_calls"])
                with st.expander(f"Tool yang dipakai: {names}"):
                    st.json(entry["tool_calls"])


def main() -> None:
    """Jalankan aplikasi Streamlit."""
    st.set_page_config(page_title="Fashion Brand CS Chatbot", page_icon="👕")
    init_state()

    st.title("Customer Service Chatbot")
    st.caption(
        "Demo RAG chatbot: FAQ dari dokumen PDF, stok dan pesanan dari database live."
    )

    base_url = render_sidebar()
    render_history()

    prompt = st.chat_input("Tanya soal produk, stok, ukuran, atau pesanan...")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Mengecek data..."):
            payload = call_chat_api(base_url, st.session_state.session_id, prompt)

        if "error" in payload:
            st.error(payload["error"])
            st.session_state.messages.append(
                {"role": "assistant", "content": f"Error: {payload['error']}"}
            )
            return

        answer = str(payload.get("answer", ""))
        tool_calls = payload.get("tool_calls", [])
        st.markdown(answer)

        if tool_calls:
            names = ", ".join(call["tool_name"] for call in tool_calls)
            with st.expander(f"Tool yang dipakai: {names}"):
                st.json(tool_calls)

        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "tool_calls": tool_calls}
        )


if __name__ == "__main__":
    main()
