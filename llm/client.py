# 제미나이 호출 코드 generate()함수 하나로 감싸기.

import os, json
from pathlib import Path
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent      # /workspace/project
load_dotenv(ROOT / ".env")
with open(ROOT / "config.yaml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)["llm"]

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def generate(prompt, schema=None, image=None):
    """prompt: str / schema: pydantic 클래스 / image: PIL.Image (W7에서 사용)"""
    contents = [prompt] if image is None else [image, prompt]
    config = types.GenerateContentConfig(temperature=CFG["temperature"])
    if schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = schema
    resp = _client.models.generate_content(
        model=CFG["model"], contents=contents, config=config
    )
    return json.loads(resp.text) if schema is not None else resp.text