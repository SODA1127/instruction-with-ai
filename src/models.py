from __future__ import annotations
import json
import requests
import streamlit as st
from src.config import P, DEFAULT_SAMPLING, LMSTUDIO_PREFERRED, OPENAI_COMPAT_ENDPOINTS

def build_openai_messages(
    system_prompt: str,
    user_content: str,
    images_b64: list[str] | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

    if images_b64:
        parts = []
        for b64 in images_b64:
            parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        parts.append({"type": "text", "text": user_content})
        messages.append({"role": "user", "content": parts})
    else:
        messages.append({"role": "user", "content": user_content})
    return messages


def build_claude_payload(
    system_prompt: str,
    user_content: str,
    model: str,
    images_b64: list[str] | None = None,
    history: list[dict] | None = None,
    stream: bool = False,
) -> dict:
    messages = []
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

    if images_b64:
        content = []
        for b64 in images_b64:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
        content.append({"type": "text", "text": user_content})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_content})

    return {
        "model": model,
        "system": system_prompt,
        "messages": messages,
        "max_tokens": 4096,
        "stream": stream,
        **DEFAULT_SAMPLING,
    }


def _extract_error(resp: requests.Response) -> str:
    try:
        body = resp.json()
        if "error" in body:
            err = body["error"]
            return err.get("message", str(err)) if isinstance(err, dict) else str(err)
    except Exception:
        pass
    return resp.text[:300]


def call_openai_compat(
    endpoint: str,
    api_key: str,
    messages: list[dict],
    model: str,
    stream: bool = False,
) -> str | requests.Response:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        **DEFAULT_SAMPLING,
    }

    resp = requests.post(endpoint, headers=headers, json=payload, stream=stream, timeout=180)
    if not resp.ok:
        raise RuntimeError(f"[{resp.status_code}] {_extract_error(resp)}")

    if stream:
        return resp

    data = resp.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content", "").strip()
    reasoning = msg.get("reasoning_content", "").strip()

    if reasoning and content:
        content = f"<think>\n{reasoning}\n</think>\n{content}"
    elif reasoning:
        content = reasoning

    return content


def call_claude(
    api_key: str,
    payload: dict,
    stream: bool = False,
) -> str | requests.Response:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        stream=stream,
        timeout=180,
    )
    if not resp.ok:
        raise RuntimeError(f"[{resp.status_code}] {_extract_error(resp)}")

    if stream:
        return resp

    data = resp.json()
    parts = data.get("content", [])
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return text.strip()


def call_ai(
    system_prompt: str,
    user_content: str,
    provider: str,
    model: str,
    api_key: str = "",
    images_b64: list[str] | None = None,
    history: list[dict] | None = None,
    stream: bool = False,
) -> str | requests.Response:
    try:
        if provider == P.CLAUDE:
            payload = build_claude_payload(system_prompt, user_content, model, images_b64, history, stream)
            return call_claude(api_key, payload, stream)
        elif provider == P.WEBLLM:
            raise NotImplementedError("WebLLM은 현재 준비 중입니다. 일반 브라우저 환경에서 직접 실행을 권장합니다.")
        elif provider in OPENAI_COMPAT_ENDPOINTS:
            endpoint = OPENAI_COMPAT_ENDPOINTS[provider]
            messages = build_openai_messages(system_prompt, user_content, images_b64, history)
            return call_openai_compat(endpoint, api_key, messages, model, stream)
        else:
            raise ValueError(f"지원되지 않는 프로바이더입니다: {provider}")

    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"{provider} 서버에 연결할 수 없습니다. 서비스가 실행 중인지 확인하세요.")
    except requests.exceptions.Timeout:
        raise TimeoutError("응답 시간이 초과되었습니다. 다시 시도해주세요.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"API 호출 오류: {e}")


def stream_openai_compat(resp: requests.Response) -> str:
    placeholder = st.empty()
    full_text = ""
    reasoning_text = ""

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
            delta = chunk["choices"][0].get("delta", {})
            token = delta.get("content", "")
            reasoning_token = delta.get("reasoning_content", "")
            if reasoning_token:
                reasoning_text += reasoning_token
            if token:
                full_text += token
                placeholder.markdown(full_text + "▌")
        except (json.JSONDecodeError, KeyError):
            continue

    placeholder.markdown(full_text)

    if reasoning_text.strip():
        return f"<think>\n{reasoning_text.strip()}\n</think>\n{full_text}"
    return full_text


def stream_claude(resp: requests.Response) -> str:
    placeholder = st.empty()
    full_text = ""

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data_str = line[6:]
            try:
                chunk = json.loads(data_str)
                if chunk.get("type") == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        token = delta.get("text", "")
                        full_text += token
                        placeholder.markdown(full_text + "▌")
            except json.JSONDecodeError:
                continue

    placeholder.markdown(full_text)
    return full_text


def stream_ai(resp: requests.Response, provider: str) -> str:
    if provider == P.CLAUDE:
        return stream_claude(resp)
    return stream_openai_compat(resp)


# ────────────────────────────────────────────────────────────
# 로컬 서비스(Ollama, LM Studio) 연결 체크
# ────────────────────────────────────────────────────────────

def check_ollama_connection() -> tuple[bool, str, list[str]]:
    """Ollama 연결 확인 및 로컬 모델 목록 반환."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code != 200:
            return False, "", []
        
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        if not models:
            return False, "", []
        
        return True, models[0], models
    except Exception:
        return False, "", []


def check_lmstudio_connection() -> tuple[bool, str, list[str]]:
    try:
        resp = requests.get("http://localhost:1234/v1/models", timeout=3)
        if resp.status_code != 200:
            return False, "", []

        all_ids = [m["id"] for m in resp.json().get("data", [])]
        chat_ids = [m for m in all_ids if "embed" not in m.lower()]

        candidates = [m for m in LMSTUDIO_PREFERRED if m in chat_ids] + \
                     [m for m in chat_ids if m not in LMSTUDIO_PREFERRED]

        for model_id in candidates:
            try:
                ping = requests.post(
                    "http://localhost:1234/v1/chat/completions",
                    json={"model": model_id, "messages": [{"role": "user", "content": "hi"}], "stream": False, "max_tokens": 1},
                    timeout=10,
                )
                if ping.status_code == 200:
                    return True, model_id, candidates
            except Exception:
                continue

        return False, "", candidates
    except Exception:
        return False, "", []
