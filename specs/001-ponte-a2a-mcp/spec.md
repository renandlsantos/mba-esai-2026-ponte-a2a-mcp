# Feature Specification: Ponte A2A MCP
**Feature Branch**: feature/sdd-fase-308
**Created**: 2026-09-19
**Status**: Revisada
**Input**: Fase308 do MBA: reservas determinísticas ligando MRTR MCP a Tasks A2A.

## User Scenarios & Testing
### User Story 1 - Descobrir e reservar (Priority: P1)
Cliente consulta tools/resource e reserva sala livre.
**Independent Test**: Validador1–12,20 e24–26.
**Acceptance Scenarios**: Given dados iniciais, When reserva válida, Then resultado estruturado e texto equivalentes; Given política violada, Then erro exato de execução.
### User Story 2 - Resolver conflito (Priority: P1)
Cliente recebe alternativas, retoma ou recusa.
**Independent Test**: MRTR direto, reinício servidor e duas Tasks independentes.
**Acceptance Scenarios**: Given conflito, When pedido, Then input_required com enum ordenado; Given estado assinado, When retry novoID após reinício, Then reservar escolha; Given alteração/expiração, Then -32602; Given recusa, Then resultado reservado=false.
### User Story 3 - Integrar A2A (Priority: P1)
Cliente descobre card, abre Task e acompanha pausa e conclusão.
**Independent Test**: Validador21–36 e logs.
**Acceptance Scenarios**: Given Task pausada, When escolha inválida, Then manter pausa; Given terminal, When continuação, Then erro; Given traceparent, When MCP, Then mesmo trace-id nos logs.
### Edge Cases
Sala inexistente, datas inválidas/sem fuso, intervalo vazio/invertido, fora da janela, >2h, nenhuma alternativa, requestState adulterado/expirado, argumentos adulterados, capability ausente, headers divergentes, Task desconhecida e chamadas concorrentes na mesma Task.

## Requirements
### Functional Requirements
- FR-001: MCP StreamableHTTP7301/mcp com listar_salas, consultar_disponibilidade, reservar_sala; schemas e JSONtext+structuredContent; politica://uso.
- FR-002: Validar sala, horário08–20(-03), duração<=2h e sobreposição, com mensagens exatas do contrato; alternativas capacidade>=original, ordem capacidade/id, máximo3.
- FR-003: Metadados protocolVersion/clientCapabilities obrigatórios por request, -32602HTTP400; sem elicitation.form em conflito -32021HTTP400; headers divergentes -32020; resource desconhecido -32602.
- FR-004: MRTR com uma elicitation.form, inputRequests/map, requestState AEAD600s, sobrevivência restart, argumentos selados, recusa normal, novoIDretry.
- FR-005: Agente descobre tools antes de chamar, lê resource, inclui metadados/headers e propaga traceparent em todo request.
- FR-006: A2A1.0 card7300, SendMessage/GetTask, estados SUBMITTED/WORKING/INPUT_REQUIRED/COMPLETED/CANCELED/FAILED; terminais definitivos; artifact reserva inclui política lida.
- FR-007: Estado por Task, opaco e privado; alternativas exatamente formatadas; escolha inválida repete pausa; duas Tasks não misturam estado.
- FR-008: README com Como rodar/Onde a ponte acontece/Decisões técnicas/Saída do validador, verificado em clone limpo.
### Key Entities
Sala e Reserva usam JSON fornecido. Task pública contém id/contextId/status/history/artifacts. Continuação privada contém argumentos originais, requestState, chave inputRequest, enum e traceparent.

## Success Criteria
- SC-001:36/36 verificações oficiais passam em processos novos.
- SC-002: Retry sobrevive restart com mesma chave; adulteração/expiração e troca de args rejeitadas.
- SC-003: Logs mostram descoberta anterior à chamada, traceparent e ids diferentes no retry.
- SC-004: Zero alterações nos diretórios congelados e zero segredo commitado; execução reproduzível.

## Assumptions
Python3.11, mcp2.2.0 disponível no PyPI; reserva persiste somente no processo. Tasks também em memória, conforme escopo. SDK gerencia protocolo/AEAD, A2A binding implementado em pequena aplicação ASGI.
