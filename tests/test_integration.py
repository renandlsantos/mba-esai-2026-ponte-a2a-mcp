"""Integração real com processos próprios e portas reservadas para cada fixture."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026-07-28"
TRACE = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def post(url, body, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


class Stack:
    def __init__(self, tmp):
        self.tmp = tmp
        self.mcp_port = port()
        self.agent_port = port()
        self.env = {
            **os.environ,
            "REQUEST_STATE_SECRET": secrets.token_hex(32),
            "MCP_PORT": str(self.mcp_port),
            "AGENT_PORT": str(self.agent_port),
            "MCP_URL": f"http://127.0.0.1:{self.mcp_port}/mcp",
        }
        self.processes = []
        self.handles = []

    def start(self, script, probe):
        handle = open(self.tmp / (Path(script).parent.name + ".log"), "a")
        self.handles.append(handle)
        process = subprocess.Popen(
            [sys.executable, str(ROOT / script)],
            cwd=ROOT,
            env=self.env,
            stdout=handle,
            stderr=handle,
        )
        self.processes.append(process)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(
                    (self.tmp / (Path(script).parent.name + ".log")).read_text()
                )
            try:
                urllib.request.urlopen(probe, timeout=0.2).close()
                return process
            except urllib.error.HTTPError:
                return process
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("startup timeout")

    def start_mcp(self):
        self.server = self.start(
            "servidor-mcp/server.py", f"http://127.0.0.1:{self.mcp_port}/mcp"
        )

    def start_agent(self):
        self.agent = self.start(
            "agente/server.py",
            f"http://127.0.0.1:{self.agent_port}/.well-known/agent-card.json",
        )

    def stop(self):
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        for h in self.handles:
            h.close()

    def mcp(self, method, params, meta=None, headers=None):
        params = {
            **params,
            "_meta": meta
            if meta is not None
            else {
                "io.modelcontextprotocol/protocolVersion": VERSION,
                "io.modelcontextprotocol/clientCapabilities": {
                    "elicitation": {"form": {}}
                },
                "traceparent": TRACE,
            },
        }
        body = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": method,
            "params": params,
        }
        hdr = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": VERSION,
            "Mcp-Method": method,
        }
        if method == "tools/call":
            hdr["Mcp-Name"] = params["name"]
        if method == "resources/read":
            hdr["Mcp-Name"] = params["uri"]
        hdr.update(headers or {})
        return post(f"http://127.0.0.1:{self.mcp_port}/mcp", body, hdr)

    def reserve(self, args, **extra):
        return self.mcp(
            "tools/call", {"name": "reservar_sala", "arguments": args, **extra}
        )

    def a2a(self, text, task=None):
        message = {
            "messageId": uuid.uuid4().hex,
            "role": "ROLE_USER",
            "parts": [{"text": text}],
        }
        if task:
            message["taskId"] = task
        return post(
            f"http://127.0.0.1:{self.agent_port}/a2a",
            {
                "jsonrpc": "2.0",
                "id": uuid.uuid4().hex,
                "method": "SendMessage",
                "params": {"message": message},
            },
            {"traceparent": TRACE},
        )[1]


@pytest.fixture
def stack(tmp_path):
    app = Stack(tmp_path)
    try:
        app.start_mcp()
        app.start_agent()
        yield app
    finally:
        app.stop()


@pytest.fixture
def conflict():
    return {
        "sala": "sala-garagem",
        "inicio": "2026-11-03T14:00:00-03:00",
        "fim": "2026-11-03T15:00:00-03:00",
        "responsavel": "Marty",
    }


def test_original_validator_36(stack, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "validador/validar.py",
            "--agente",
            f"http://127.0.0.1:{stack.agent_port}",
            "--mcp",
            f"http://127.0.0.1:{stack.mcp_port}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "36 passaram, 0 falharam" in result.stdout
    (tmp_path / "validator.txt").write_text(result.stdout)


def test_retry_survives_restart_and_rejects_tamper(stack, conflict):
    _, response = stack.reserve(conflict)
    pending = response["result"]
    key = next(iter(pending["inputRequests"]))
    state = pending["requestState"]
    _, bad = stack.reserve(
        conflict,
        requestState=state[:-6] + "AAAAAA",
        inputResponses={key: {"action": "decline"}},
    )
    assert bad["error"]["code"] == -32602
    stack.server.terminate()
    stack.server.wait(timeout=5)
    stack.start_mcp()
    _, result = stack.reserve(
        conflict,
        requestState=state,
        inputResponses={key: {"action": "accept", "content": {"sala": "sala-fusca"}}},
    )
    assert result["result"]["structuredContent"]["sala"] == "sala-fusca"


def test_missing_meta_and_mismatched_header(stack):
    status, res = stack.mcp("tools/list", {}, meta={})
    assert status == 400 and res["error"]["code"] == -32602
    status, res = stack.mcp("tools/list", {}, headers={"Mcp-Method": "tools/call"})
    assert status == 400 and res["error"]["code"] == -32020


def test_task_private_state_and_distinct_retry_id(stack, conflict):
    text = "reservar " + " ".join(f"{k}={v}" for k, v in conflict.items())
    paused = stack.a2a(text)["result"]["task"]
    assert paused["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert "requestState" not in json.dumps(paused)
    invalid = stack.a2a("escolha=sala-aquario", paused["id"])["result"]["task"]
    assert invalid["status"]["message"]["parts"] == paused["status"]["message"]["parts"]
    done = stack.a2a("escolha=recusar", paused["id"])["result"]["task"]
    assert done["status"]["state"] == "TASK_STATE_CANCELED"
    logs = (stack.tmp / "servidor-mcp.log").read_text().splitlines()
    rows = [json.loads(line) for line in logs if line.startswith('{"method"')]
    assert rows[0]["method"] == "tools/list"
    assert all(x["traceparent"] == TRACE for x in rows)
    calls = [x for x in rows if x["method"] == "tools/call"]
    assert len(calls) == 2 and calls[0]["id"] != calls[1]["id"]


def test_frozen_starter():
    for path, digest in json.loads(
        (ROOT / "docs/upstream-integrity.json").read_text()
    ).items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path


def test_expired_state_rejected(stack, conflict):
    from mcp.server.request_state import AESGCMRequestStateCodec

    _, response = stack.reserve(conflict)
    pending = response["result"]
    key = next(iter(pending["inputRequests"]))
    codec = AESGCMRequestStateCodec([bytes.fromhex(stack.env["REQUEST_STATE_SECRET"])])
    claims = json.loads(codec.unseal(pending["requestState"]))
    assert 599 <= claims["exp"] - claims["iat"] <= 601
    claims["iat"] = time.time() - 700
    claims["exp"] = time.time() - 100
    expired = codec.seal(json.dumps(claims).encode())
    _, result = stack.reserve(
        conflict, requestState=expired, inputResponses={key: {"action": "decline"}}
    )
    assert result["error"]["code"] == -32602


def test_retry_arguments_and_choice_are_untrusted(stack, conflict):
    _, response = stack.reserve(conflict)
    pending = response["result"]
    key = next(iter(pending["inputRequests"]))
    state = pending["requestState"]
    _, bad = stack.reserve(
        {**conflict, "responsavel": "Attacker"},
        requestState=state,
        inputResponses={key: {"action": "accept", "content": {"sala": "sala-fusca"}}},
    )
    assert bad["error"]["code"] == -32602
    _, bad = stack.reserve(
        conflict,
        requestState=state,
        inputResponses={key: {"action": "accept", "content": {"sala": "sala-aquario"}}},
    )
    assert bad["error"]["code"] == -32602
    _, ok = stack.reserve(
        conflict, requestState=state, inputResponses={key: {"action": "cancel"}}
    )
    assert ok["result"]["structuredContent"]["reservado"] is False
    assert not ok["result"].get("isError")


def test_policy_timezone_and_adjacent_intervals(stack):
    args = {
        "sala": "sala-aquario",
        "inicio": "2026-11-03T11:00:00+00:00",
        "fim": "2026-11-03T12:00:00+00:00",
        "responsavel": "Doc",
    }
    _, response = stack.reserve(args)
    assert response["result"]["structuredContent"]["reservado"] is True
    args.update(inicio="2026-11-03T09:00:00-03:00", fim="2026-11-03T10:00:00-03:00")
    _, response = stack.reserve(args)
    assert response["result"]["structuredContent"]["reservado"] is True
    args.update(inicio="2026-11-03T19:00:00-03:00", fim="2026-11-04T08:00:00-03:00")
    _, response = stack.reserve(args)
    assert response["result"]["isError"] is True


def test_server_rejects_missing_or_short_secret(tmp_path):
    for secret in ("", "abc", "aabb"):
        result = subprocess.run(
            [sys.executable, str(ROOT / "servidor-mcp/server.py")],
            cwd=ROOT,
            env={**os.environ, "REQUEST_STATE_SECRET": secret},
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 1
        assert "REQUEST_STATE_SECRET" in result.stderr
