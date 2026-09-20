# Ponte A2A MCP Constitution

## Core Principles
### I. Fronteira de protocolo
MUST executar dois processos e comunicar via HTTP. O agente não importa regras de negócio do servidor e não usa LLM.
### II. SDK oficial e contratos intactos
MUST usar MCP oficial v2 e A2A1.0; preservar dados/, exemplos/ e validador/ byte a byte. Não reescrever o MCP para contornar SDK.
### III. Estado explícito e protegido
MUST proteger requestState com codec nativo, chave ambiente de >=32bytes e TTL600s. O agente armazena estado por Task sem abrir ou expor. Retry ganha id novo.
### IV. Validação antes de publicação
MUST passar validador36, testes de reinício/adulteração/expiração/metadados e revisão de diff antes de commit. Nenhum segredo real no Git.
### V. SDD e evidência
MUST rastrear requisitos em spec/plan/tasks e documentar resultados reais. Main/submissão são coordenadas após revisão da feature.

## Restrições
Sem ORM, banco, container, autenticação, frontend, streaming ou LLM. Reservas em memória inicializadas dos JSON acadêmicos.

## Workflow
Constitution→specify→plan→tasks→implement→converge; revisão em cada etapa. Casos de teste cobrem contrato e comportamento adverso.

## Governance
Semver: major muda princípios, minor amplia e patch esclarece. Alterações exigem spec e teste compatíveis.
**Version**: 1.0.0 | **Ratified**: 2026-09-19 | **Last Amended**: 2026-09-19
