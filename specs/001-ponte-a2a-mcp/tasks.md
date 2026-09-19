# Tasks: Ponte A2A MCP
## Phase1 Setup
- [X] T001 Ler wire/enunciado, confirmarSDK e registrar spec/plan/research.
- [X] T002 Fixar ambiente em pyproject.toml/uv.lock e integridade em docs/upstream-integrity.json.
## Phase2 Foundation
- [X] T003 Criar tests/test_integration.py com processos isolados, protocolo/errors e integridade.
## Phase3 US1 MCP
- [X] T004 [US1] Implementar servidor-mcp/server.py com domínio mínimo, tools/resource e metadados/logs.
## Phase4 US2 MRTR
- [X] T005 [US2] Implementar InputRequiredResult e RequestStateSecurity nativos em servidor-mcp/server.py; testar restart,expiry,tamper,args.
## Phase5 US3 A2A
- [X] T006 [US3] Implementar agente/server.py com discovery/resource/tracing e Taskstate.
- [X] T007 [US3] Ligar pausa/retomada/decline com estado privado e retry novoID em agente/server.py.
## Phase6 Polish
- [X] T008 Rodar validador36 e testes extra, registrar docs/validacao.md e logs.
- [X] T009 Redigir quatro seções obrigatóriasREADME, testar clone limpo seguindo comandos.
- [X] T010 Converge, revisar diff/integridade/segredos e publicar feature após testes.
## Dependencies
T001→T002→T003→T004→T005→T006→T007→T008→T009→T010. Arquivos isolados permitiriam MCP e agente paralelos após contrato; execução atual sequencial por agenteexclusivo.
## Strategy
MCPprimeiro, MRTRdepois, A2Apor último; validador oficial prova fio completo. Testes complementares cobrem critérios além das36checagens.
