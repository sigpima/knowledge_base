def test_main_calls_mcp_run_with_streamable_http_transport(monkeypatch):
    import main_mcp

    calls = []
    monkeypatch.setattr(main_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    main_mcp.main()

    assert calls == [{
        "transport": "streamable-http",
        "host": main_mcp.settings.mcp_server_host,
        "port": main_mcp.settings.mcp_server_port,
        "max_request_body_size": 16 * 1024 * 1024,
    }]


def test_search_policies_is_registered_and_documents_how_to_use_it():
    import asyncio

    import main_mcp

    tools = {tool.name: tool for tool in asyncio.run(main_mcp.mcp.list_tools())}

    description = tools["search_policies"].description
    for phrase in ("quy trình", "định mức", "bảo hành", "nghiệm thu", "[slug › section]", "passages", "rỗng"):
        assert phrase in description, phrase
    assert set(tools["search_policies"].input_schema["properties"]) == {"query", "top_k", "doc_type"}


def test_policy_service_builds_a_read_only_store_lazily(monkeypatch):
    import main_mcp
    from app.domains.policy.infrastructure.embedding import gemini
    from app.domains.policy.infrastructure.vectorstore import milvus_store
    from tests.policy_fakes import HashingEmbedder

    class StubStore:
        def search(self, vector, model, top_k, doc_type):
            return []

    store_calls = []

    def fake_build_store(*args, **kwargs):
        store_calls.append((args, kwargs))
        return StubStore()

    monkeypatch.setattr(milvus_store, "build_milvus_store", fake_build_store)
    monkeypatch.setattr(gemini, "build_embedder", lambda *args, **kwargs: HashingEmbedder())
    service = main_mcp._new_policy_search_service()
    assert store_calls == []  # dựng lười: chưa có lần gọi nào thì chưa chạm Milvus

    monkeypatch.setattr(main_mcp, "policy_search_service", service)
    result = main_mcp.search_policies("bảo hành bao lâu", top_k=3)

    assert result == {"passages": [], "row_count": 0}
    ((args, kwargs),) = store_calls
    assert kwargs.get("read_only") is True
    assert args == (main_mcp.settings.milvus_uri, main_mcp.settings.milvus_token, main_mcp.settings.milvus_collection)


def test_search_policies_without_gemini_key_returns_an_error_instead_of_raising(monkeypatch):
    import main_mcp

    monkeypatch.setattr(main_mcp.settings, "gemini_api_key", "")
    monkeypatch.setattr(main_mcp, "policy_search_service", main_mcp._new_policy_search_service())

    result = main_mcp.search_policies("bảo hành bao lâu")

    assert set(result) == {"error"} and "khoá Gemini" in result["error"]
