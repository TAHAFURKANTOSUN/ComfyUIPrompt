"""Sahte ComfyUI sunucusu — testler için.

Gerçek ComfyUI API yüzeyinin kullanılan kısmını taklit eder:
  - GET  /object_info/CheckpointLoaderSimple, /object_info/LoraLoader
  - POST /prompt  (workflow'u doğrular; bilinmeyen checkpoint/LoRA -> 400 node_errors)
  - GET  /_last   (yalnızca test: son kabul edilen workflow)
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

CHECKPOINTS = ["sdxl_base.safetensors", "flux1-dev-fp8.safetensors"]
LORAS = ["characters/miku_v2.safetensors", "styles/watercolor_xl.safetensors"]
LAST = {}


def _info(node: str, field: str, values: list) -> dict:
    return {node: {"input": {"required": {field: [values]}}}}


@app.get("/object_info/CheckpointLoaderSimple")
async def ckpts():
    return _info("CheckpointLoaderSimple", "ckpt_name", CHECKPOINTS)


@app.get("/object_info/LoraLoader")
async def loras():
    return _info("LoraLoader", "lora_name", LORAS)


@app.post("/prompt")
async def prompt(request: Request):
    body = await request.json()
    wf = body.get("prompt", {})
    errors = {}
    for nid, node in wf.items():
        inputs = node.get("inputs", {})
        if node.get("class_type") == "CheckpointLoaderSimple" and inputs.get("ckpt_name") not in CHECKPOINTS:
            errors[nid] = "Value not in list: ckpt_name"
        if node.get("class_type") == "LoraLoader" and inputs.get("lora_name") not in LORAS:
            errors[nid] = "Value not in list: lora_name"
        # bağlantı bütünlüğü: referans verilen her düğüm mevcut olmalı
        for val in inputs.values():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str) and val[0] not in wf:
                errors[nid] = f"missing node {val[0]}"
    if errors:
        return JSONResponse(status_code=400, content={"error": "invalid prompt", "node_errors": errors})
    LAST.clear()
    LAST.update(wf)
    return {"prompt_id": "mock-prompt-id", "number": 1}


@app.get("/_last")
async def last():
    return LAST
