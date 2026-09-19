# Implementation Plan: Ponte A2A MCP
**Branch**: feature/sdd-fase-308 | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

## Summary
Dois processos Python: MCPServer oficial e aplicação A2A ASGI. RequestStateSecurity nativo sela JSON com args/enum/chave; agente faz HTTP cru para receber input_required sem auto-resolução.
## Technical Context
Python3.11; mcp2.2.0, Starlette1.6.0, Uvicorn0.53.0, httpx2 2.13.0, pytest8.3.4. Versões exatas pyproject/uv.lock. JSON congelado lido apenas pelo servidor. Sem LLM/banco.
## Constitution Check
PASS pré/pós design: dois processos, SDKoficial, AEAD nativo, fronteira domínio/agente, diretórios congelados, testes antes de publicação. Sem hooks configurados.
## Project Structure
- servidor-mcp/server.py: dados, validações, tools/resource, MRTR e wrapperASGI de metadados/logs. MCPServer processa protocolo.
- agente/server.py: MCP HTTP client, descoberta por tools/list, leituraresource, TaskStore/lock, parser formato fixo, card e JSON-RPC1.0.
- tests/: integrações com portas livres/processos próprios, validador oficial subprocess, restart/expiry/tamper/headers/logs.
- docs/: integridade, resultados, fontes e decisões.
- specs/001-ponte-a2a-mcp/: spec/plan/research/data-model/contracts/quickstart/tasks.
## Complexity Tracking
Sem exceção. Middleware de entrada apenas verifica metadados obrigatórios e registra logs, sem substituir transporte SDK. Cliente usa HTTP JSON explícito para preservar pausa, permitido pelo contrato de host MCP.
