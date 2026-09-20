"""Agente determinístico: host MCP por HTTP e servidor A2A1.0 por fora."""

import asyncio
import copy
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx2 as httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

VERSION = "2026-07-28"
TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED"}


def identifier(prefix):
    return f"{prefix}-{uuid4().hex}"


class RpcError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message


class MCPHost:
    def __init__(self, client, url):
        self.client = client
        self.url = url

    async def request(self, method, params, traceparent):
        meta = {
            "io.modelcontextprotocol/protocolVersion": VERSION,
            "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
            "io.modelcontextprotocol/clientInfo": {
                "name": "agente-central-de-salas",
                "version": "1.0.0",
            },
        }
        if traceparent:
            meta["traceparent"] = traceparent
        params = {**params, "_meta": meta}
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": VERSION,
            "Mcp-Method": method,
        }
        if method == "tools/call":
            headers["Mcp-Name"] = params["name"]
        if method == "resources/read":
            headers["Mcp-Name"] = params["uri"]
        response = await self.client.post(
            self.url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": identifier("mcp"),
                "method": method,
                "params": params,
            },
        )
        body = response.json()
        if "error" in body:
            raise RpcError(body["error"]["code"], body["error"]["message"])
        response.raise_for_status()
        return body["result"]


@dataclass
class TaskRecord:
    public: dict
    traceparent: str | None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    arguments: dict = field(default_factory=dict)
    tool: str = ""
    policy: str = ""
    request_state: str | None = None
    input_key: str | None = None
    alternatives: list[str] = field(default_factory=list)


class Bridge:
    def __init__(self, host):
        self.host = host
        self.tasks = {}

    def state(self, record, state, text=None):
        record.public["status"] = {"state": state}
        if text is not None:
            message = {
                "messageId": identifier("msg"),
                "role": "ROLE_AGENT",
                "parts": [{"text": text}],
                "taskId": record.public["id"],
                "contextId": record.public["contextId"],
            }
            record.public["status"]["message"] = message
            record.public["history"].append(message)

    def pause(self, record):
        self.state(
            record,
            "TASK_STATE_INPUT_REQUIRED",
            "alternativas: " + ", ".join(record.alternatives),
        )

    async def apply(self, record, result):
        if result.get("resultType") == "input_required":
            requests = result.get("inputRequests", {})
            if len(requests) != 1 or not result.get("requestState"):
                raise RpcError(-32603, "Servidor MCP retornou pausa incompatível")
            key, question = next(iter(requests.items()))
            params = question.get("params", {})
            if (
                question.get("method") != "elicitation/create"
                or params.get("mode") != "form"
            ):
                raise RpcError(-32603, "Somente elicitation form é suportada")
            choice = params["requestedSchema"]["properties"]["sala"]
            alternatives = choice.get("enum") or [choice["const"]]
            record.request_state = result["requestState"]
            record.input_key = key
            record.alternatives = alternatives
            self.pause(record)
            return
        if result.get("isError"):
            text = "\n".join(x.get("text", "") for x in result.get("content", []))
            self.state(record, "TASK_STATE_FAILED", text)
            return
        data = result.get("structuredContent")
        if not isinstance(data, dict) or "reservado" not in data:
            raise RpcError(-32603, "Resultado MCP sem contrato de reserva")
        if data["reservado"] is False:
            self.state(record, "TASK_STATE_CANCELED", data.get("motivo", "recusado"))
            return
        artifact = {**data, "politica": record.policy}
        record.public["artifacts"] = [
            {
                "artifactId": identifier("art"),
                "name": "reserva",
                "parts": [{"text": json.dumps(artifact, ensure_ascii=False)}],
            }
        ]
        self.state(
            record,
            "TASK_STATE_COMPLETED",
            f"Reserva {data['reserva']} confirmada na {data['sala']}.",
        )
        record.request_state = None
        record.alternatives = []
        record.input_key = None

    async def send(self, message, traceparent):
        if (
            not isinstance(message, dict)
            or message.get("role") != "ROLE_USER"
            or not isinstance(message.get("messageId"), str)
        ):
            raise RpcError(-32602, "messageId e ROLE_USER obrigatórios")
        parts = message.get("parts")
        if (
            not isinstance(parts, list)
            or len(parts) != 1
            or not isinstance(parts[0], dict)
            or not isinstance(parts[0].get("text"), str)
        ):
            raise RpcError(-32602, "Envie uma única parte text")
        text = parts[0]["text"]
        task_id = message.get("taskId")
        if task_id:
            record = self.tasks.get(task_id)
            if record is None:
                raise RpcError(-32001, "Task não encontrada")
        else:
            task_id = identifier("task")
            record = TaskRecord(
                {
                    "id": task_id,
                    "contextId": identifier("ctx"),
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "history": [],
                    "artifacts": [],
                },
                traceparent,
            )
            self.tasks[task_id] = record
        async with record.lock:
            state = record.public["status"]["state"]
            if state in TERMINAL:
                raise RpcError(-32002, "Task em estado terminal")
            record.public["history"].append(copy.deepcopy(message))
            try:
                if record.request_state is not None:
                    match = re.fullmatch(r"escolha=([^\s]+)", text)
                    choice = match[1] if match else None
                    if choice != "recusar" and choice not in record.alternatives:
                        self.pause(record)
                        return copy.deepcopy(record.public)
                    self.state(record, "TASK_STATE_WORKING")
                    answer = (
                        {"action": "decline"}
                        if choice == "recusar"
                        else {"action": "accept", "content": {"sala": choice}}
                    )
                    result = await self.host.request(
                        "tools/call",
                        {
                            "name": record.tool,
                            "arguments": record.arguments,
                            "inputResponses": {record.input_key: answer},
                            "requestState": record.request_state,
                        },
                        record.traceparent,
                    )
                else:
                    self.state(record, "TASK_STATE_WORKING")
                    match = re.fullmatch(
                        r"reservar sala=(\S+) inicio=(\S+) fim=(\S+) responsavel=(.+)",
                        text,
                    )
                    if not match:
                        raise RpcError(
                            -32602,
                            "Formato: reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>",
                        )
                    record.arguments = dict(
                        zip(("sala", "inicio", "fim", "responsavel"), match.groups())
                    )
                    tools = await self.host.request(
                        "tools/list", {}, record.traceparent
                    )
                    discovered = {tool["name"]: tool for tool in tools["tools"]}
                    # Seleciona a capacidade necessária entre ferramentas descobertas em runtime.
                    tool = discovered.get("reservar_sala")
                    if (
                        tool is None
                        or tool.get("inputSchema", {}).get("type") != "object"
                    ):
                        raise RpcError(
                            -32603, "Servidor MCP não oferece reserva compatível"
                        )
                    record.tool = tool["name"]
                    policy = await self.host.request(
                        "resources/read", {"uri": "politica://uso"}, record.traceparent
                    )
                    policy_text = policy["contents"][0]["text"]
                    first = policy_text.splitlines()[0]
                    if not first.startswith("versao:"):
                        raise RpcError(-32603, "Resource sem versão de política")
                    record.policy = first.split(":", 1)[1].strip()
                    result = await self.host.request(
                        "tools/call",
                        {"name": record.tool, "arguments": record.arguments},
                        record.traceparent,
                    )
                await self.apply(record, result)
            except RpcError as error:
                self.state(record, "TASK_STATE_FAILED", error.message)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                self.state(
                    record,
                    "TASK_STATE_FAILED",
                    "Falha de comunicação ou contrato com servidor MCP",
                )
            return copy.deepcopy(record.public)


def make_app():
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=15) as client:
            app.state.bridge = Bridge(
                MCPHost(client, os.getenv("MCP_URL", "http://127.0.0.1:7301/mcp"))
            )
            yield

    async def card(request):
        url = os.getenv(
            "AGENT_URL", f"http://127.0.0.1:{os.getenv('AGENT_PORT', '7300')}"
        )
        return JSONResponse(
            {
                "name": "Central de Salas",
                "description": "Reserva salas da Hill Valley Tech.",
                "version": "1.0.0",
                "supportedInterfaces": [
                    {
                        "url": url + "/a2a",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "capabilities": {
                    "streaming": False,
                    "pushNotifications": False,
                    "extendedAgentCard": False,
                },
                "defaultInputModes": ["text/plain"],
                "defaultOutputModes": ["text/plain"],
                "skills": [
                    {
                        "id": "reservar-sala",
                        "name": "Reservar sala",
                        "description": "Reserva sala; em conflito pede alternativa.",
                        "tags": ["salas", "agenda"],
                        "inputModes": ["text/plain"],
                        "outputModes": ["text/plain"],
                    }
                ],
            }
        )

    async def rpc(request: Request):
        request_id = None
        try:
            body = await request.json()
            if (
                not isinstance(body, dict)
                or body.get("jsonrpc") != "2.0"
                or "id" not in body
            ):
                raise RpcError(-32600, "Request JSON-RPC inválido")
            request_id = body["id"]
            params = body.get("params", {})
            if not isinstance(params, dict):
                raise RpcError(-32602, "params deve ser objeto")
            bridge = request.app.state.bridge
            if body.get("method") == "SendMessage":
                task = await bridge.send(
                    params.get("message"), request.headers.get("traceparent")
                )
            elif body.get("method") == "GetTask":
                record = bridge.tasks.get(params.get("id"))
                if record is None:
                    raise RpcError(-32001, "Task não encontrada")
                task = copy.deepcopy(record.public)
            else:
                raise RpcError(-32601, "Método desconhecido")
            return JSONResponse(
                {"jsonrpc": "2.0", "id": request_id, "result": {"task": task}}
            )
        except (ValueError, TypeError):
            error = RpcError(-32700, "JSON inválido")
        except RpcError as error_value:
            error = error_value
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": error.code, "message": error.message},
            }
        )

    return Starlette(
        routes=[
            Route("/.well-known/agent-card.json", card),
            Route("/a2a", rpc, methods=["POST"]),
        ],
        lifespan=lifespan,
    )


if __name__ == "__main__":
    uvicorn.run(make_app(), host="127.0.0.1", port=int(os.getenv("AGENT_PORT", "7300")))
