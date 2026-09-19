# Validação da fase308

Em2026-09-19, Python3.11.16, MCP2.2.0; uv.lock fixado.

- Validador oficial: **36/36PASS** em dois subprocessos novos por HTTP.
- `uv run pytest -q`: **9passed**. Inclui próprio validador e casos extras.
- Retry de estado original após parar/reiniciar exclusivamente o MCP: reserva concluída.
- Estado adulterado: -32602; estado autenticamente selado mas expirado: -32602.
- TTL do estado observado:600s. Troca de argumentos: -32602; escolha fora do enum: -32602.
- Decline/cancel: complete/reservadofalse sem isError.
- Headers divergentes: -32020HTTP400. Metadados ausentes: -32602HTTP400.
- Logs: descoberta anterior às tools, trace-id preservado, ids diferentes no retry.
- Regras adicionais: timezone equivalenteUTC, intervalos adjacentes, janela atravessando dias.
- Inicialização sem chave/hexinválido/menos32bytes falha antes de abrir servidor.
- SHA256 dos diretórios congelados preservados, testes de integridade passam.

Processos dos testes usam portas livres e são encerrados por PIDpróprio. Segredos sintéticos em memória, não salvos. MCPInspector não foi aberto; os testes exercitam o wire real equivalente e todas as36verificações. Main/entrega acadêmica aguardam integração coordenada, não foram realizadas.
