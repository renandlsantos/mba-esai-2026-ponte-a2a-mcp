# Quickstart
`uv sync --frozen`; exportar REQUEST_STATE_SECRET gerado por secrets.token_hex(32); `uv run python servidor-mcp/server.py` e `uv run python agente/server.py` em terminais distintos. `uv run python validador/validar.py`. Cada rodada exige servidor novo para restaurar JSONinicial. Testes `uv run pytest -q` gerenciam exclusivamente subprocessos próprios em portas livres.
