"""MCP 2026-07-28: domínio mínimo e MRTR protegido pelo SDK oficial."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from mcp import types
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.request_state import RequestStateSecurity
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel
from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TIME = timezone(timedelta(hours=-3))
VERSION = "2026-07-28"
QUESTION = "escolha_de_sala"


def secret_bytes():
    value = os.getenv("REQUEST_STATE_SECRET", "")
    try:
        key = bytes.fromhex(value)
    except ValueError:
        raise ValueError(
            "REQUEST_STATE_SECRET deve ser hexadecimal gerado com secrets.token_hex(32)."
        ) from None
    if len(key) < 32:
        raise ValueError(
            "REQUEST_STATE_SECRET precisa representar pelo menos 32 bytes aleatórios."
        )
    return key


class Sala(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaSalas(BaseModel):
    salas: list[Sala]


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[dict]


class Reserva(BaseModel):
    reserva: str | None = None
    reservado: bool = True
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


def create_server():
    salas = json.loads((ROOT / "dados/salas.json").read_text())
    reservas = json.loads((ROOT / "dados/reservas.json").read_text())
    politica = (ROOT / "dados/politica-de-uso.md").read_text()
    versao = politica.splitlines()[0].split(":", 1)[1].strip()
    server = MCPServer(
        "central-de-salas",
        version="1.0.0",
        request_state_security=RequestStateSecurity(keys=[secret_bytes()], ttl=600),
    )

    def validate(sala, inicio, fim):
        room = next((s for s in salas if s["id"] == sala), None)
        if room is None:
            raise ToolError(f"Sala inexistente: {sala}")
        try:
            start, end = datetime.fromisoformat(inicio), datetime.fromisoformat(fim)
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError()
            start, end = start.astimezone(LOCAL_TIME), end.astimezone(LOCAL_TIME)
        except ValueError:
            raise ToolError("Data invalida: informe ISO8601 com fuso horario") from None
        if end <= start:
            raise ToolError("Intervalo invalido: fim deve ser posterior a inicio")
        opening = start.replace(hour=8, minute=0, second=0, microsecond=0)
        closing = start.replace(hour=20, minute=0, second=0, microsecond=0)
        if start < opening or end > closing:
            raise ToolError(
                "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
            )
        if end - start > timedelta(hours=2):
            raise ToolError(
                "Duracao acima do limite: a politica permite no maximo 2 horas"
            )
        return room, start, end

    def conflicts(sala, start, end):
        return [
            r
            for r in reservas
            if r["sala"] == sala
            and start < datetime.fromisoformat(r["fim"])
            and end > datetime.fromisoformat(r["inicio"])
        ]

    def create(args):
        validate(args["sala"], args["inicio"], args["fim"])
        reservation = {"id": f"res-{len(reservas) + 1:04d}", **args}
        reservas.append(reservation)
        return Reserva(reserva=reservation["id"], **args, politica=versao)

    @server.tool()
    def listar_salas() -> ListaSalas:
        """Lista todas as salas com capacidade e recursos."""
        return ListaSalas(salas=salas)

    @server.tool()
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        """Consulta disponibilidade aplicando a política de uso."""
        _, start, end = validate(sala, inicio, fim)
        found = conflicts(sala, start, end)
        return Disponibilidade(sala=sala, livre=not found, conflitos=found)

    @server.tool()
    def reservar_sala(
        sala: str, inicio: str, fim: str, responsavel: str, ctx: Context
    ) -> Reserva | types.InputRequiredResult:
        """Reserva sala ou pede escolha de alternativa por MRTR."""
        args = {"sala": sala, "inicio": inicio, "fim": fim, "responsavel": responsavel}
        room, start, end = validate(sala, inicio, fim)
        if not responsavel.strip():
            raise ToolError("Responsavel deve ser informado")
        if ctx.request_state is not None:
            state = json.loads(
                ctx.request_state
            )  # SDK já verificou AEAD, expiração e binding.
            response = (ctx.input_responses or {}).get(QUESTION)
            if not isinstance(response, types.ElicitResult):
                raise MCPError(-32602, "Resposta de elicitation ausente ou invalida")
            if response.action in ("decline", "cancel"):
                return Reserva(reservado=False, motivo="recusado")
            chosen = (response.content or {}).get("sala")
            if chosen not in state["alternatives"]:
                raise MCPError(-32602, "Escolha fora das alternativas oferecidas")
            args = state["arguments"]
            args["sala"] = chosen
            _, start, end = validate(chosen, args["inicio"], args["fim"])
            if conflicts(chosen, start, end):
                raise ToolError(
                    "Alternativa indisponivel no intervalo; inicie nova reserva"
                )
            return create(args)
        if not conflicts(sala, start, end):
            return create(args)
        alternatives = [
            s["id"]
            for s in sorted(salas, key=lambda s: (s["capacidade"], s["id"]))
            if s["capacidade"] >= room["capacidade"]
            and not conflicts(s["id"], start, end)
        ][:3]
        if not alternatives:
            raise ToolError("Sem alternativas disponiveis no intervalo")
        capabilities = ctx.client_capabilities
        if (
            capabilities is None
            or capabilities.elicitation is None
            or capabilities.elicitation.form is None
        ):
            raise MCPError(
                -32021,
                "Cliente deve declarar elicitation em form mode",
                {"requiredCapabilities": {"elicitation": {"form": {}}}},
            )
        request = types.ElicitRequest(
            params=types.ElicitRequestFormParams(
                mode="form",
                message="A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.",
                requestedSchema={
                    "type": "object",
                    "properties": {"sala": {"type": "string", "enum": alternatives}},
                    "required": ["sala"],
                },
            )
        )
        return types.InputRequiredResult(
            input_requests={QUESTION: request},
            request_state=json.dumps({"arguments": args, "alternatives": alternatives}),
        )

    @server.resource("politica://uso", mime_type="text/markdown")
    def politica_de_uso() -> str:
        return politica

    return server


class RequestGuard:
    """Audita a entrada e exige metadados; o SDK mantém transporte/protocolo."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/mcp"
        ):
            return await self.app(scope, receive, send)
        messages = []
        body = b""
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if len(body) > 4 * 1024 * 1024:
                return await JSONResponse(
                    {"error": "Corpo excede limite"}, status_code=413
                )(scope, receive, send)
            if not message.get("more_body"):
                break
        try:
            request = json.loads(body)
        except (ValueError, UnicodeError):
            request = {}
        if isinstance(request, dict):
            params = request.get("params")
            meta = params.get("_meta", {}) if isinstance(params, dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            print(
                json.dumps(
                    {
                        "method": request.get("method"),
                        "id": request.get("id"),
                        "traceparent": meta.get("traceparent"),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            required = (
                "io.modelcontextprotocol/protocolVersion",
                "io.modelcontextprotocol/clientCapabilities",
            )
            if request.get("method") and any(k not in meta for k in required):
                result = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32602,
                        "message": "_meta protocolVersion e clientCapabilities obrigatorios",
                    },
                }
                return await JSONResponse(result, status_code=400)(scope, receive, send)

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay, send)


if __name__ == "__main__":
    try:
        server = create_server()
        app = RequestGuard(
            server.streamable_http_app(stateless_http=True, json_response=True)
        )
        uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("MCP_PORT", "7301")))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
