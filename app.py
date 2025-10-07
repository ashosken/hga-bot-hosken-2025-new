# app.py — HGA Bot • Twilio WhatsApp ↔ OpenAI • Vercel-ready
# Rotas: "/", /health, /diag/openai, /whatsapp, /status (opcional)
# Observações:
# - Twilio envia application/x-www-form-urlencoded → usamos request.form()
# - Resposta ao webhook deve ser TwiML (XML) e precisa de escape (&, <, >)
# - Crie a env var OPENAI_API_KEY na Vercel (formato sk-...)

import os, html, sys, traceback
from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI(title="HGA Bot")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# ---- Rota raiz (evita 404 ao abrir o domínio) ----
@app.get("/")
def index():
    return {
        "ok": True,
        "message": "HGA Bot online",
        "routes": ["/health", "/diag/openai", "/whatsapp", "/status"]
    }

# ---- Vida ----
@app.get("/health")
def health():
    return {"ok": True}

# ---- Diagnóstico da OpenAI ----
@app.get("/diag/openai")
async def diag_openai():
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY ausente no ambiente da Vercel"}
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role":"user","content":"Responda apenas: ok"}],
            "temperature": 0.1
        }
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            return {"ok": True, "text": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---- Chamada à OpenAI (uso interno) ----
async def call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY ausente")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role":"system","content":(
                "Você é um assistente informativo do escritório Hosken & Geraldino. "
                "Responda de modo breve e claro, sem aconselhamento jurídico individual "
                "e sem promessas de resultado. Em urgência, oriente contato humano."
            )},
            {"role":"user","content": prompt}
        ],
        "temperature": 0.3
    }
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

# ---- Webhook do WhatsApp (Twilio) ----
@app.post("/whatsapp")
async def whatsapp(request: Request):
    # Twilio envia application/x-www-form-urlencoded
    try:
        form = dict((await request.form()).items())
    except Exception:
        return Response(status_code=415, content="Unsupported Media Type (esperado form-urlencoded)")

    user_text = (form.get("Body") or "").strip()

    # Chamada à OpenAI com timeout/fallback
    try:
        reply = await call_openai(user_text or "Diga olá em uma frase.")
    except Exception as e:
        print("OPENAI_ERROR:", str(e), file=sys.stderr)
        traceback.print_exc()
        reply = "Recebi sua mensagem e vou encaminhar à nossa equipe. Retornaremos em breve."

    # Rodapé com aviso (OAB/LGPD) + número do Sandbox Twilio
    disclaimer = "[Aviso] Resposta informativa. Não substitui consulta com advogado(a). Contato: (21) 2018-4200 • WhatsApp: +1 415 523 8886"
    final_text = f"{reply}\n\n{disclaimer}"

    # Escape de XML para &, <, >
    final_xml = html.escape(final_text)

    # TwiML
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{final_xml}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")

# ---- (Opcional) Callback de status da Twilio ----
@app.post("/status")
async def status_callback(request: Request):
    try:
        data = dict((await request.form()).items())
    except Exception:
        data = {"error": "esperado form-urlencoded"}
    # Aqui você pode salvar em log/DB: MessageSid, MessageStatus, ErrorCode, etc.
    return {"ok": True, "received": data.get("MessageStatus", "unknown")}
