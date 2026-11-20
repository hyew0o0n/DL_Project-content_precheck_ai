"""[W7] 이미지 분기 구조 테스트 (가짜 OCR·얼굴·VLM·분류기·LLM·RAG)

B의 vision/ 모듈, GPU, Gemini 키 없이도 pipeline.run_image의 JSON 모양을 확인한다.
노션 W7 "형식 ①" 그대로의 가짜 결과를 넣음.

    python eval/a_test_image_pipeline.py          # 가짜 모듈로 구조만 확인 (어디서나)
    python eval/a_test_image_pipeline.py --real IMG.jpg   # 서버에서 실제 모듈로 1장 실행
"""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAKE_OCR = [
    {"bbox": [120, 80, 560, 140], "text": "지금 바로 구매", "conf": 0.88},
    {"bbox": [96, 1120, 984, 1236], "text": "먹기만 해도 -10kg! 부작용 없음", "conf": 0.93},
    {"bbox": [96, 1250, 700, 1300], "text": "문의 010-1234-5678", "conf": 0.90},
]
FAKE_FACES = [{"bbox": [410, 220, 690, 560], "conf": 0.91}]
FAKE_VLM = {"items": [
    {"type": "historical_symbol", "description": "배경에 붉은 원에서 뻗는 햇살 줄기 무늬", "confidence": 0.82},
    {"type": "ip", "description": "오른쪽 아래 스포츠 브랜드 로고", "confidence": 0.4},   # MIN_CONF 미만 → 버림
]}


def install_fakes():
    """무거운 모듈(torch 분류기, Gemini, Chroma)을 가짜로 바꿔 끼움."""
    m = types.ModuleType("models.predict")
    m.predict = lambda text, **kw: []
    sys.modules["models.predict"] = m

    c = types.ModuleType("llm.client")
    def generate(prompt, schema=None, image=None):
        if image is not None:
            return FAKE_VLM
        return {"used_doc_ids": [], "message": "가짜 설명이에요."}
    c.generate = generate
    sys.modules["llm.client"] = c

    r = types.ModuleType("rag.search")
    r.search = lambda q, k=3, violation_types=None, purpose=None, **kw: [
        {"doc_id": f"FAKE-{violation_types[0]}", "doc": "가짜 문서", "clause": "1조", "status": "시행"}]
    sys.modules["rag.search"] = r

    o = types.ModuleType("vision.ocr");  o.run_ocr = lambda p: FAKE_OCR
    f = types.ModuleType("vision.face"); f.detect_faces = lambda p: FAKE_FACES
    sys.modules["vision.ocr"], sys.modules["vision.face"] = o, f


def check(res):
    assert res["input"]["media_type"] == "image"
    assert res["input"]["width"] == 1080 and res["input"]["height"] == 1350
    subs = [f["subtype"] for f in res["findings"]]
    assert "exaggeration" in subs, subs
    assert "phone" in subs, subs
    assert "ai_virtual_human" in subs, subs            # 인물 안내
    assert "historical_symbol" in subs, subs
    assert "ip" not in subs, subs                       # 확신도 0.4 → 버림
    for f in res["findings"]:
        loc = f["location"]
        assert loc["modality"] == "image"
        assert "search_types" not in f and "rule_id" not in f
        if f["subtype"] == "phone":
            assert loc["bbox"] == FAKE_OCR[2]["bbox"]
            s, e = loc["span"]
            assert loc["ocr_text"][s:e] == "010-1234-5678"
        if f["source"] == "vlm":
            assert loc["bbox"] is None and f["verdict"] == "검토 필요"
            assert f["evidence"] == [] and f["explain_status"] == "vlm_notice_only"   # 상징은 근거 연결 안 함 (ip는 W8부터 연결)
            assert "감지됐어요" in f["message"]
        if f["source"] == "face":
            assert loc["bboxes"] == [FAKE_FACES[0]["bbox"]]
    assert res["meta"]["steps"] == {"ocr": "ok", "face": "ok", "vlm": "ok"}
    print("✅ 구조 테스트 통과:", res["summary"])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--real":
        import pipeline
        print(json.dumps(pipeline.run_file(sys.argv[2]), ensure_ascii=False, indent=1))
        sys.exit()

    install_fakes()
    from PIL import Image
    import tempfile
    import pipeline
    pipeline.explain_findings.__globals__["CALL_GAP_SEC"] = 0

    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "fake_ad.jpg"
        Image.new("RGB", (1080, 1350), "white").save(img)
        res = pipeline.run_file(str(img), purpose="none", post_date="2026-03-01")
        print(json.dumps(res, ensure_ascii=False, indent=1)[:3000])
        check(res)

        # 광고가 아닌 이미지 + 인물: FACE_NOTICE="always"라 그래도 안내함
        sys.modules["vision.ocr"].run_ocr = lambda p: [{"bbox": [0, 0, 10, 10], "text": "가족 여행", "conf": 0.9}]
        pipeline.run_ocr = sys.modules["vision.ocr"].run_ocr
        res2 = pipeline.run_image(str(img))
        assert any(f["source"] == "face" for f in res2["findings"]), res2["findings"]
        print("✅ 비광고 이미지에서도 인물 안내 확인")