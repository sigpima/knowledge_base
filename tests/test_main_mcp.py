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
