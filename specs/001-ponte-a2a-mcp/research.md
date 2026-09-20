# Pesquisa
- Decisão: MCP oficial Python2.2.0 confirmado no PyPI e SDK instalado. Fonte https://github.com/modelcontextprotocol/python-sdk e https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server/ (2026-09-19).
- Decisão: InputRequiredResult nativo com Context.input_responses/request_state. Não usar callback de elicitation, que resolveria a pergunta sem pausa A2A.
- Decisão: RequestStateSecurity(keys=[secret],ttl=600), AES256GCM/HKDF nativo, binding automático a método/argumentos/audience. Sem criptografia própria e sem chave efêmera.
- Decisão: HTTP direto do agente com headers/metadados explicitamente por request, IDsUUID novos; SDK v2 permite isso e mantém input_required visível.
- Decisão: A2A1.0 JSONRPC com TaskStore em memória, sem SDK adicional. Fonte https://a2a-protocol.org/latest/specification/ e 11exemplos wire completos do starter.
- Materiais privados consultados como índice: Protocolos de Comunicação, aulas18588,18600–18602,18621,18624. Não copiar transcrições para Git público.
- Revisão Endor dependency-reviewer/package-risk indisponível no ambiente (confirmado coordenador); sem alegação de auditoria de dependências. SDK oficial confirmado; dependências isoladas e travadas.

Leitura dos resumos privados18588/18624 concluída: capacidadesMCP separadas do cicloTaskA2A; opacidade permite agente determinístico semLLM. Apenas síntese aplicada publicada.
