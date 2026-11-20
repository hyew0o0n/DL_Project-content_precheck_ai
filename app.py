"""
beFore · AI 콘텐츠 사전 검수 데모 UI

- 화면 1(업로드) → 화면 2(검수 결과) 두 화면을 한 페이지에서 전환
- pipeline.py가 돌려주는 JSON만 읽어서 그림 (UI에 판정 로직 없음)
- 실행: python app.py → VS Code "포트" 탭 7860 → 노트북 브라우저 localhost:7860
- share=True 금지 (학과 정책). 다 쓰면 Ctrl+C로 종료.
"""
import base64
import html
import io
import json
from datetime import date
from pathlib import Path

import gradio as gr

import pipeline

# pipeline 진입 함수: fn(text: str, purpose: str) -> dict (v0.2 JSON). 이름이 다르면 여기만 수정
RUN = getattr(pipeline, "run", None) or getattr(pipeline, "analyze", None)
if RUN is None:
    raise ImportError("pipeline.py에서 run(text, purpose) 함수를 찾지 못했어요. app.py의 RUN을 맞춰주세요.")
RUN_FILE = getattr(pipeline, "run_file", None)   # [W7] 이미지: fn(path, purpose, input_id, post_date) -> dict
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# ---------------------------------------------------------------
# 디자인 토큰
# ---------------------------------------------------------------
BRAND = "#F5FAC4"
COLORS = {"위반": "#CE3B45", "검토 필요": "#F2A639", "통과": "#4CA75A"}
HL = {"위반": "rgba(206,59,69,0.30)", "검토 필요": "rgba(242,166,57,0.30)"}   # 하이라이트 30%
SEVERITY = {"위반": 2, "검토 필요": 1}  # 구간이 겹칠 때 어떤 색을 보일지만 정함 (판정 X)

PURPOSES = [("광고 · 홍보", "ad"), ("정보 제공", "info"), ("개인 일상", "daily"),
            ("재미 · 유머", "fun"), ("기타", "etc"), ("선택 안 함", "none")]
PURPOSE_LABEL = {v: k for k, v in PURPOSES}

STATUS_LABEL = {"시행": "시행 중", "예정": "시행 예정", "행정예고": "행정예고", "상시": "상시 적용"}

CSS = f"""
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
:root {{ --brand:{BRAND}; --ink:#111; --sub:#6b6b6b; --line:#d9d9d9; }}
.gradio-container, .gradio-container * {{ font-family:'Pretendard',-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif !important; }}
.gradio-container {{ max-width:1280px !important; margin:0 auto !important; padding:0 48px !important; background:#fff; }}
footer {{ display:none !important; }}
.gradio-container {{ width:100% !important; }}
.gradio-container .main, .gradio-container .wrap, .gradio-container .contain, .gradio-container .contain > .column {{ width:100% !important; max-width:none !important; }}
#upload-card {{ width:100% !important; }}

/* 헤더 */
#hdr-wrap {{ position:fixed !important; top:0; left:0; right:0; z-index:100; background:#fff; padding:0 48px !important; margin:0 !important; border-bottom:1px solid #e5e5e5; }}
.gradio-container {{ padding-top:56px !important; }}
#hdr-wrap .html-container, #hdr-wrap .prose {{ padding:0 !important; margin:0 !important; }}
#hdr {{ max-width:1096px; margin:0 auto; background:#fff; display:flex; align-items:center; justify-content:space-between; padding:14px 0; }}
#hdr .logo {{ font-size:24px; font-weight:800; letter-spacing:-0.5px; color:var(--ink);
             background:linear-gradient(transparent 58%, var(--brand) 58%); padding:0 4px; }}
#hdr nav {{ display:flex; align-items:center; gap:28px; font-size:14px; color:var(--sub); }}
#hdr .avatar {{ width:34px; height:34px; border-radius:50%; background:var(--brand); display:flex; align-items:center; justify-content:center; }}

/* 화면 1 */
#hero {{ text-align:center; padding:20px 0 18px; }}
#hero .eyebrow {{ display:inline-block; font-size:13px; font-weight:600; color:#4d5a00; background:var(--brand); padding:5px 12px; border-radius:999px; margin-bottom:14px; }}
#hero h1 {{ font-size:32px; font-weight:700; letter-spacing:-0.8px; line-height:1.4; margin:0; color:var(--ink); }}
#hero p {{ font-size:16px; color:var(--sub); margin:10px 0 0; }}
#hero p b {{ color:var(--ink); font-weight:600; background:linear-gradient(transparent 60%, var(--brand) 60%); }}

#upload-card {{ max-width:880px; margin:0 auto !important; border:1.5px solid var(--ink) !important; border-radius:18px !important;
               background:#fff !important; padding:0 !important; overflow:hidden; box-shadow:0 6px 24px rgba(0,0,0,0.05); gap:0 !important; }}
#upload-card > * {{ border:none !important; box-shadow:none !important; background:transparent !important; }}
#in-text textarea {{ border:none !important; box-shadow:none !important; font-size:17px !important; line-height:1.7 !important;
                     padding:18px 32px 4px !important; resize:none; background:transparent !important; }}
#in-text textarea::placeholder {{ color:#9a9a9a; }}
#purpose-hint {{ padding:4px 20px 0; font-size:14px; color:var(--sub); }}
#purpose-hint b {{ color:var(--ink); font-weight:600; margin-right:6px; }}
#in-purpose {{ padding:10px 32px 20px !important; }}
#in-purpose .wrap {{ gap:10px !important; }}
#in-purpose label {{ border:1.2px solid var(--ink) !important; border-radius:999px !important; padding:9px 0 !important; width:116px !important; justify-content:center !important;
                     background:#fff !important; font-size:15px !important; cursor:pointer; box-shadow:none !important; }}
#in-purpose label input {{ display:none !important; }}
#in-purpose label span {{ margin:0 !important; text-align:center; }}
#in-purpose label.selected, #in-purpose label:has(input:checked) {{ background:var(--brand) !important; font-weight:600; }}
#card-foot {{ border-top:1px solid #ececec !important; padding:14px 22px 14px 32px !important; align-items:center !important; }}
#btn-file {{ background:none !important; border:none !important; box-shadow:none !important; color:var(--ink) !important;
             font-size:15px !important; font-weight:500 !important; padding:0 !important; min-width:0 !important; max-width:110px; justify-content:flex-start !important; }}
#file-note {{ font-size:13px; color:#9a9a9a; }}
#file-note .ok {{ color:var(--ink); }}
#btn-go {{ width:52px !important; height:52px !important; min-width:52px !important; max-width:52px; border-radius:50% !important;
           background:var(--ink) !important; color:#fff !important; font-size:22px !important; padding:0 !important; margin-left:auto; }}
#btn-go:hover {{ background:#333 !important; }}
#features {{ display:flex; justify-content:center; gap:36px; padding:0 0 32px; margin-top:-6px; font-size:14px; color:var(--sub); }}
#features span::before {{ content:''; display:inline-block; width:8px; height:8px; border-radius:50%; background:#c9d66b; margin-right:8px; vertical-align:middle; }}

/* 화면 2 */
#result-wrap {{ padding:32px 0 80px; gap:56px !important; align-items:flex-start !important; }}
#left {{ position:sticky; top:104px; }}
.r-title {{ font-size:30px; font-weight:700; letter-spacing:-0.6px; margin:0; }}
.r-sub {{ font-size:15px; color:var(--sub); margin:8px 0 28px; }}
.overall .badge {{ white-space:nowrap; flex-shrink:0; }}
.overall {{ display:flex; align-items:center; gap:14px; padding:18px 22px; border-radius:14px; background:#fafafa; margin-bottom:16px; }}
.overall .score {{ margin-left:auto; text-align:right; }}
.overall .score b {{ font-size:30px; font-weight:800; line-height:1; }}
.overall .score small {{ display:block; font-size:12px; color:var(--sub); margin-bottom:2px; }}
.overall .sum {{ font-size:15px; font-weight:500; }}
.src-card {{ border:1.5px solid #909090; border-radius:18px; padding:26px 26px 24px; }}
.src-text {{ font-size:17px; line-height:1.9; white-space:pre-wrap; word-break:keep-all; }}
.src-text mark {{ border-radius:3px; padding:1px 2px; color:inherit; }}
.legend {{ display:flex; gap:14px; font-size:12px; color:var(--sub); margin-top:14px; }}
.legend i {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }}
.p-title {{ font-size:14px; font-weight:600; margin:24px 0 10px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; }}
.chip {{ border:1.2px solid var(--ink); border-radius:999px; padding:6px 0; width:86px; text-align:center; font-size:13px; }}
.no-purpose {{ width:100%; font-size:13px; color:var(--sub); margin-top:4px; }}
.chip.on {{ background:var(--brand); font-weight:600; }}
.ad-note {{ margin-top:2px; font-size:13px; color:var(--sub); }}
#btn-back {{ margin-top:16px; border:1.2px solid var(--ink) !important; background:#fff !important; border-radius:999px !important;
             box-shadow:none !important; font-weight:600 !important; }}

.f-head {{ font-size:15px; color:var(--sub); margin-bottom:6px; }}
.f-head b {{ color:var(--ink); }}
.finding {{ padding:28px 0; border-bottom:1px solid #ececec; }}
.finding:last-child {{ border-bottom:none; }}
.f-top {{ display:flex; align-items:center; gap:12px; }}
.badge {{ color:#fff; font-weight:700; font-size:14px; padding:5px 16px; border-radius:999px; }}
.f-label {{ font-size:19px; font-weight:700; letter-spacing:-0.3px; }}
.f-risk {{ margin-left:auto; font-size:13px; font-weight:600; }}
.f-risk b {{ font-size:22px; font-weight:800; margin-left:4px; }}
.f-quote {{ margin-top:14px; font-size:14px; color:var(--sub); }}
.f-quote span {{ color:var(--ink); padding:1px 4px; border-radius:3px; }}
.f-msg {{ margin-top:10px; font-size:16px; line-height:1.7; }}
.f-q {{ margin-top:14px; padding:14px 16px; border-radius:10px; background:rgba(242,166,57,0.12); font-size:15px; line-height:1.6; }}
.f-q b {{ display:block; font-size:13px; color:#a86a0e; margin-bottom:3px; }}
.f-sug {{ margin-top:12px; padding:14px 16px; border-radius:10px; background:rgba(76,167,90,0.10); font-size:15px; }}
.ev-title {{ font-size:15px; font-weight:700; margin:22px 0 10px; }}
.ev {{ margin-bottom:14px; }}
.ev-name {{ font-size:15px; font-weight:500; }}
.ev-name::before {{ content:'•'; margin-right:8px; }}
.ev-box {{ margin-top:10px; border:1.2px solid #909090; border-radius:12px; padding:16px 18px 12px; }}
.ev-ex {{ font-size:15px; line-height:1.75; color:#222; }}
.ev-meta {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:12px; font-size:13px; color:var(--sub); }}
.ev-meta .tag {{ background:var(--brand); color:#3d4700; font-weight:600; padding:3px 10px; border-radius:999px; }}
.ev-meta .st {{ border:1px solid var(--line); padding:2px 9px; border-radius:999px; }}
.ev-meta a {{ margin-left:auto; color:var(--ink); font-weight:600; text-decoration:none; }}
.ev-meta a:hover {{ text-decoration:underline; }}
.empty {{ padding:40px 0; font-size:17px; }}

/* [W7] 이미지 결과 · 특별한 날 · 게시 예정일 */
.img-wrap {{ position:relative; width:100%; line-height:0; border-radius:10px; overflow:hidden; }}
.img-wrap img {{ width:100%; height:auto; display:block; }}
.img-box {{ position:absolute; border:2px solid; border-radius:3px; box-sizing:border-box; }}
.img-box span {{ position:absolute; top:-2px; left:-2px; color:#fff; font-size:11px; font-weight:700; line-height:1; padding:3px 5px; border-radius:3px 0 3px 0; }}
.img-whole {{ margin-top:12px; font-size:13px; color:var(--sub); line-height:1.6; }}
.ocr-lines {{ margin-top:14px; font-size:13px; color:var(--sub); line-height:1.7; }}
.ocr-body {{ white-space:pre-wrap; }}
.ocr-lines summary {{ cursor:pointer; color:var(--ink); font-weight:600; list-style:none; }}
.ocr-lines summary::-webkit-details-marker {{ display:none; }}
.ocr-lines summary::after {{ content:" ▾"; }}
.ocr-lines[open] summary::after {{ content:" ▴"; }}
.ocr-body {{ margin-top:6px; padding:10px 12px; background:#fafafa; border-radius:8px; }}
.f-no {{ display:inline-flex; align-items:center; justify-content:center; min-width:22px; height:22px; border-radius:6px; font-size:12px; font-weight:700; color:#fff; }}
.day-banner {{ display:flex; gap:10px; align-items:flex-start; padding:14px 18px; margin-bottom:18px; border-radius:12px; background:var(--brand); font-size:15px; line-height:1.6; }}
#date-row {{ padding:0 32px 14px 20px !important; }}
#date-pick {{ display:flex; align-items:center; gap:10px; font-size:14px; color:var(--sub); white-space:nowrap; }}
#date-pick > b {{ color:var(--ink); font-weight:600; }}
#date-pick .date-anchor {{ position:relative; display:inline-block; }}
#date-pick .date-btn {{ border:1.2px solid var(--ink); border-radius:999px; background:#fff; padding:5px 14px; font-size:13px; font-weight:600; cursor:pointer; }}
#date-pick .date-btn:hover {{ background:var(--brand); }}
#date-pick input[type=date] {{ position:absolute; left:0; top:100%; width:1px; height:1px; opacity:0; border:0; padding:0; pointer-events:none; }}
#date-pick .date-btn.picked {{ background:var(--brand); }}
.hidden-box {{ display:none !important; }}

/* 분석 중 */
#loading {{ text-align:center; padding:96px 0 120px; }}
#loading .spinner {{ display:block; margin:0 auto 28px; animation:spin 0.9s linear infinite; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}
#loading h2 {{ font-size:26px; font-weight:700; margin:0; }}
#loading p {{ font-size:15px; color:var(--sub); margin:8px 0 32px; }}
#loading .steps {{ display:inline-flex; align-items:stretch; gap:16px; padding:0; margin:0; list-style:none; counter-reset:s; }}
/* [final] 세 상자 크기 같게(높이·너비 고정), 작은 설명은 한 줄로 (줄바꿈 X) */
#loading .steps li {{ counter-increment:s; border:1.2px solid #909090; border-radius:14px; text-align:left;
                     font-size:15px; font-weight:600; width:280px; height:86px; box-sizing:border-box; padding:20px 22px !important;
                     white-space:nowrap; animation:pulse 2.4s ease-in-out infinite; }}
#loading .steps li:nth-child(2) {{ animation-delay:0.8s; }}
#loading .steps li:nth-child(3) {{ animation-delay:1.6s; }}
#loading .steps li::before {{ content:counter(s); display:inline-block; width:22px; height:22px; line-height:22px; text-align:center;
                             border-radius:50%; background:var(--brand); font-size:12px; margin-right:8px; }}
#loading .steps small {{ display:block; font-size:12px; font-weight:400; color:var(--sub); margin:6px 0 0 30px;
                         white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
@keyframes pulse {{ 0%,100% {{ background:#fff; }} 30% {{ background:#fbfde8; }} }}
"""

HEADER = """
<div id="hdr">
  <span class="logo">beFore</span>
  <nav><span>최근 검수한 콘텐츠</span><span>로그아웃</span>
    <span class="avatar"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111" stroke-width="2">
      <circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg></span></nav>
</div>"""

HERO = """
<div id="hero">
  <span class="eyebrow">콘텐츠 사전 검수 AI</span>
  <h1>콘텐츠를 올리기 전에,<br>문제 될 표현을 정책 근거와 함께 알려드려요</h1>
  <p>복잡한 법령·정책을 일일이 찾지 않아도, 개인 게시물부터 광고·마케팅까지 <b>어디가, 왜 문제인지</b> 짚어드려요.</p>
</div>"""

LOADING = """
<div id="loading">
  <svg class="spinner" width="56" height="56" viewBox="0 0 56 56">
    <circle cx="28" cy="28" r="24" fill="none" stroke="#F5FAC4" stroke-width="6"/>
    <circle cx="28" cy="28" r="24" fill="none" stroke="#111" stroke-width="6" stroke-linecap="round" stroke-dasharray="38 113"/>
  </svg>
  <h2>분석 중이에요</h2>
  <p>보통 10~20초 정도 걸려요.</p>
  <ol class="steps">
    <li>표현 감지 <small>개인정보 · 혐오 · 욕설 · 광고 패턴</small></li>
    <li>정책 근거 검색 <small>법령 · 공정위 지침 · 플랫폼 정책</small></li>
    <li>안내 문장 작성 <small>어디가, 왜 문제인지</small></li>
  </ol>
</div>"""

FEATURES = """<div id="features"><span>검수 시간 단축</span><span>법령·정책 조항 근거</span><span>확실하지 않은 건 '검토 필요'로 안내</span></div>"""


# ---------------------------------------------------------------
# JSON → HTML
# ---------------------------------------------------------------
esc = html.escape


def badge(verdict):
    return f'<span class="badge" style="background:{COLORS.get(verdict, "#999")}">{esc(verdict)}</span>'


def highlighted(text, findings):
    spans = []
    for f in findings:
        loc = f.get("location") or {}
        if loc.get("modality") == "text" and loc.get("span"):
            s, e = loc["span"]
            spans.append((s, e, f["verdict"]))
    spans.sort(key=lambda x: (x[0], -SEVERITY.get(x[2], 0)))
    out, cur = [], 0
    for s, e, v in spans:
        s = max(s, cur)
        if s >= e:
            continue
        out.append(esc(text[cur:s]))
        out.append(f'<mark style="background:{HL.get(v, "transparent")}">{esc(text[s:e])}</mark>')
        cur = e
    out.append(esc(text[cur:]))
    return "".join(out)


def _thumb_b64(path, max_w=900):
    """결과 화면용으로 줄인 이미지 → data URI (원본 좌표는 퍼센트로 맞추므로 크기가 달라도 됨)."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _boxed_image(img_path, findings, W, H):
    """이미지 위에 finding 상자(bbox)를 그린 HTML + 상자 없는 finding 목록."""
    by_box, whole = {}, []   # 같은 상자(같은 OCR 줄)에 걸린 finding은 상자 하나로 묶음 → 번호 "2·3·4"
    for f in findings:
        loc = f.get("location") or {}
        v, no = f["verdict"], f.get("id", "").lstrip("f")
        bbs = loc.get("bboxes") or ([loc["bbox"]] if loc.get("bbox") else [])
        if not bbs:
            whole.append(f'<span style="color:{COLORS.get(v)};font-weight:700">{esc(no)}</span> {esc(f.get("label", ""))}')
        for bb in bbs:
            nos, worst = by_box.get(tuple(bb), ([], v))
            by_box[tuple(bb)] = (nos + [no], v if SEVERITY.get(v, 0) > SEVERITY.get(worst, 0) else worst)
    boxes = []
    for (x1, y1, x2, y2), (nos, v) in by_box.items():
        style = (f"left:{100*x1/W:.2f}%;top:{100*y1/H:.2f}%;width:{100*(x2-x1)/W:.2f}%;height:{100*(y2-y1)/H:.2f}%;"
                 f"border-color:{COLORS.get(v)};background:{HL.get(v, 'transparent')}")
        boxes.append(f'<div class="img-box" style="{style}"><span style="background:{COLORS.get(v)}">{esc("·".join(nos))}</span></div>')
    return f'<div class="img-wrap"><img src="{_thumb_b64(img_path)}">{"".join(boxes)}</div>', whole


def image_view(img_path, res):
    """[W7] 이미지 + 문제 상자(bbox). 위반 빨강 / 검토 필요 주황, 30% 투명. 번호 = 오른쪽 카드 번호."""
    inp = res.get("input", {})
    out, whole = _boxed_image(img_path, res.get("findings", []), inp.get("width") or 1, inp.get("height") or 1)
    if whole:
        out += f'<div class="img-whole">이미지 전체 관련 · {" · ".join(whole)}</div>'
    ocr_text = (res.get("meta") or {}).get("ocr_text", "")
    if ocr_text:   # [W8] 접이식: 기본은 닫힘
        n = len([l for l in ocr_text.splitlines() if l.strip()])
        out += (f'<details class="ocr-lines"><summary>추출된 텍스트 보기 ({n}줄)</summary>'
                f'<div class="ocr-body">{esc(ocr_text)}</div></details>')
    return out


def left_panel(text, purpose, res, img_path=None):
    v = res.get("verdict", "통과")
    chips = "".join(f'<span class="chip{" on" if val == purpose else ""}">{esc(lbl)}</span>' for lbl, val in PURPOSES[:-1])
    if purpose == "none":
        chips += '<div class="no-purpose">목적을 고르지 않아 모든 정책 기준으로 검수했어요.</div>'
    ad = res.get("ad_signal", {})
    ad_note = ""
    if ad.get("detected") and purpose != "ad":
        ad_note = '<div class="ad-note">홍보성 표현이 감지돼 광고 규정도 함께 확인했어요.</div>'
    return f"""
    <h2 class="r-title">검수 결과</h2>
    <p class="r-sub">정책에 어긋나거나 확인이 필요한 부분을 정리했어요.</p>
    <div class="overall">{badge(v)}<span class="sum">{esc(res.get("summary", ""))}</span>
      <span class="score"><small>위험도</small><b style="color:{COLORS.get(v)}">{res.get("risk_score", 0)}</b></span></div>
    <div class="src-card">
      {image_view(img_path, res) if img_path else f'<div class="src-text">{highlighted(text, res.get("findings", []))}</div>'}
      <div class="legend"><span><i style="background:{HL['위반']}"></i>위반</span><span><i style="background:{HL['검토 필요']}"></i>검토 필요</span></div>
      <div class="p-title">콘텐츠 게시 목적</div>
      <div class="chips">{chips}</div>
      {ad_note}
    </div>"""


def evidence_html(e):
    name = f'{esc(e.get("doc", ""))} — {esc(e.get("clause", ""))}'
    excerpt = (e.get("excerpt") or "").strip()      # 조항 원문 중 해당 부분 (v0.3)
    if len(excerpt) > 240:
        excerpt = excerpt[:240].rstrip() + "…"
    applies = e.get("applies_to")                   # 적용 대상 (v0.3), 리스트 또는 문자열
    if isinstance(applies, list):
        applies = ", ".join(applies)
    status = STATUS_LABEL.get(e.get("status", ""), e.get("status", ""))
    meta = []
    if applies:
        meta.append(f'<span class="tag">적용 대상 · {esc(applies)}</span>')
    if status:
        meta.append(f'<span class="st">{esc(status)}</span>')
    meta.append(f'<span>{esc(e.get("doc_id", ""))}</span>')
    if e.get("url"):
        meta.append(f'<a href="{esc(e["url"], quote=True)}" target="_blank">원문 보기 ↗</a>')
    box = f'<div class="ev-ex">“{esc(excerpt)}”</div>' if excerpt else ""
    return f'<div class="ev"><div class="ev-name">{name}</div><div class="ev-box">{box}<div class="ev-meta">{"".join(meta)}</div></div></div>'


def finding_html(f):
    v = f["verdict"]
    loc = f.get("location") or {}
    quote = loc.get("text") or loc.get("ocr_text") or loc.get("description")
    is_img = loc.get("modality") == "image"
    no = f'<span class="f-no" style="background:{COLORS.get(v)}">{esc(f.get("id", "").lstrip("f"))}</span>' if is_img else ""
    parts = [f'<div class="finding"><div class="f-top">{no}{badge(v)}<span class="f-label">{esc(f.get("label", ""))}</span>'
             f'<span class="f-risk" style="color:{COLORS.get(v)}">위험도<b style="color:{COLORS.get(v)}">{f.get("risk", 0)}</b></span></div>']
    if quote:
        parts.append(f'<div class="f-quote">{"해당 부분" if is_img else "해당 표현"} <span style="background:{HL.get(v)}">{esc(quote)}</span></div>')
        if is_img and loc.get("ocr_text") and loc.get("ocr_text") != quote:
            parts.append(f'<div class="f-quote">이미지 속 문구 · {esc(loc["ocr_text"])}</div>')
    # [final] 인물 감지는 '해당 부분 · 인물 n명' 바로 밑에 확인 질문 (설명 문장은 같은 말 반복이라 생략)
    if f.get("message") and f.get("source") != "face":
        parts.append(f'<div class="f-msg">{esc(f["message"])}</div>')
    if f.get("review_question"):
        parts.append(f'<div class="f-q"><b>확인해주세요</b>{esc(f["review_question"])}</div>')
    if f.get("suggestion"):
        parts.append(f'<div class="f-sug">✏️ 이렇게 바꿔보세요 · {esc(f["suggestion"])}</div>')
    ev = f.get("evidence") or []
    if ev:   # [W8] 근거가 있을 때만 표시 (VLM 로고·캐릭터 포함). 못 찾았을 때는 언급하지 않음
        parts.append('<div class="ev-title">근거 조항</div>')
        parts.append("".join(evidence_html(e) for e in ev))
    parts.append("</div>")
    return "".join(parts)


def day_banner(res):
    """[W7] 특별한 날이면 결과 화면 맨 위 배너 (utils/dates.py가 만든 message 그대로)."""
    sd = res.get("special_day")
    return f'<div class="day-banner"><span>📅</span><span>{esc(sd["message"])}</span></div>' if sd and sd.get("message") else ""


def right_panel(res):
    fs = res.get("findings", [])
    if not fs:
        return (day_banner(res) + f'<div class="empty">{badge("통과")}<p style="margin-top:16px">발견된 문제가 없어요. 그대로 게시해도 좋아요.</p></div>')
    n_v = sum(f["verdict"] == "위반" for f in fs)
    n_r = sum(f["verdict"] == "검토 필요" for f in fs)
    head = f'<div class="f-head">발견 항목 <b>{len(fs)}건</b> · 위반 {n_v} · 검토 필요 {n_r}</div>'
    return day_banner(res) + head + "".join(finding_html(f) for f in fs)


# ---------------------------------------------------------------
# 이벤트
# ---------------------------------------------------------------
def on_file(file):
    """.txt면 글자를 입력창에 채움. [W7] 이미지는 경로를 기억해 두고 이미지 검수로 보냄."""
    if file is None:
        return gr.update(), "", None
    p = Path(file if isinstance(file, str) else file.name)
    ext = p.suffix.lower()
    if ext == ".txt":
        return p.read_text(encoding="utf-8", errors="ignore"), f'<span class="ok">📎 {esc(p.name)}</span>', None
    if ext in IMAGE_EXT and RUN_FILE is not None:
        return gr.update(), f'<span class="ok">🖼️ {esc(p.name)} · 이미지를 검수해요</span>', str(p)
    return gr.update(), f'📎 {esc(p.name)} · 지원하지 않는 형식이에요', None


def on_start(text, img_path):
    """글이나 이미지가 있으면 '분석 중' 화면으로 전환. 둘 다 없으면 에러 → 다음 단계 실행 안 됨."""
    if not (text or "").strip() and not img_path:
        raise gr.Error("검수할 글을 입력하거나 이미지를 올려주세요.")
    return gr.Column(visible=False), gr.Column(visible=True)


# [W7] 게시 예정일: "선택하기" → 브라우저 기본 달력(작은 팝업). 고른 날짜는 숨긴 Textbox(#in-date)로 전달
DATE_JS = """
<script>
(() => {
  const fmt = v => { const [y, m, d] = v.split('-').map(Number); return `${y}년 ${m}월 ${d}일`; };
  const today = () => { const t = new Date(); t.setMinutes(t.getMinutes() - t.getTimezoneOffset()); return t.toISOString().slice(0, 10); };
  document.addEventListener('click', e => {
    if (!e.target.closest('#date-pick .date-btn')) return;
    const inp = document.getElementById('date-native');
    if (!inp) return;
    try { inp.showPicker(); } catch (_) { inp.style.pointerEvents = 'auto'; inp.focus(); inp.click(); }
  });
  document.addEventListener('change', e => {
    if (e.target.id !== 'date-native' || !e.target.value) return;
    const v = e.target.value;
    const btn = document.querySelector('#date-pick .date-btn');
    btn.textContent = fmt(v) + (v === today() ? ' (오늘)' : '');   // 고른 날짜는 버튼 글자로 보여줌
    btn.classList.add('picked');
    const box = document.querySelector('#in-date textarea, #in-date input');
    if (box) { box.value = v; box.dispatchEvent(new Event('input', { bubbles: true })); }
  });
})();
</script>
"""


def date_picker_html(value=None):
    """게시 예정일 · 안내 · [선택하기] 가로 한 줄. 안 고르면 오늘 기준. 고르면 버튼 글자가 날짜로 바뀜."""
    v = value or date.today().isoformat()
    return ('<div id="date-pick"><b>게시 예정일</b>'
            '<span>특별한 날·시행 예정 규정을 이 날짜 기준으로 확인해요</span>'
            '<span class="date-anchor"><button type="button" class="date-btn">선택하기</button>'
            f'<input type="date" id="date-native" value="{v}"></span></div>')


def _post_date(value):
    """날짜 입력 → 'YYYY-MM-DD' 또는 None (DateTime·Textbox 둘 다 대응)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        from datetime import datetime
        return datetime.fromtimestamp(value).date().isoformat()
    return str(value).strip()[:10] or None


def on_submit(text, purpose, img_path=None, post_date=None):
    text = (text or "").strip()
    purpose = purpose or "none"
    post_date = _post_date(post_date)
    try:
        if img_path:
            res = RUN_FILE(img_path, purpose, None, post_date)
        else:
            res = RUN(text, purpose, post_date=post_date)
        if isinstance(res, str):
            res = json.loads(res)
    except Exception as e:  # 분석 실패 → 업로드 화면으로 되돌림
        gr.Warning(f"분석 중 오류가 났어요: {type(e).__name__}")
        print("[app] pipeline 오류:", repr(e))
        return (gr.Column(visible=True), gr.Column(visible=False), gr.Row(visible=False),
                gr.update(), gr.update())
    left, right = left_panel(text, purpose, res, img_path), right_panel(res)
    return (gr.Column(visible=False), gr.Column(visible=False), gr.Row(visible=True), left, right)


def on_back():
    """다른 콘텐츠 검수: 올린 이미지도 비움."""
    return gr.Column(visible=True), gr.Row(visible=False), None, '<span id="file-note">txt · jpg · png</span>'


# ---------------------------------------------------------------
# 레이아웃
# ---------------------------------------------------------------
_major = int(gr.__version__.split(".")[0])
_blocks_kw = {} if _major >= 6 else {"css": CSS, "head": DATE_JS}
_launch_kw = {"css": CSS, "head": DATE_JS} if _major >= 6 else {}

with gr.Blocks(title="beFore · 콘텐츠 사전 검수", **_blocks_kw) as demo:
    gr.HTML(HEADER, elem_id="hdr-wrap")

    # 화면 1. 업로드
    with gr.Column(visible=True) as screen1:
        gr.HTML(HERO)
        with gr.Column(elem_id="upload-card"):
            in_text = gr.Textbox(show_label=False, lines=2, max_lines=12, elem_id="in-text", container=False,
                                 placeholder="검수할 글을 붙여넣거나, 아래에서 파일을 올려주세요.")
            gr.HTML('<div id="purpose-hint"><b>게시 목적</b>선택하면 목적에 맞는 정책만 골라 근거로 연결해요 (선택)</div>')
            in_purpose = gr.Radio(PURPOSES[:-1], value=None, show_label=False, elem_id="in-purpose", container=False)
            with gr.Column(elem_id="date-row"):   # [W7] 게시 예정일 (기본값 오늘, "선택하기" → 달력 팝업)
                date_html = gr.HTML(date_picker_html())
                in_date = gr.Textbox(value=date.today().isoformat(), elem_id="in-date",
                                     elem_classes="hidden-box", show_label=False, container=False)
            with gr.Row(elem_id="card-foot", equal_height=True):
                btn_file = gr.UploadButton("+ 파일 추가", file_types=[".txt", ".jpg", ".jpeg", ".png"],
                                           elem_id="btn-file", size="sm")
                file_note = gr.HTML('<span id="file-note">txt · jpg · png</span>')
                btn_go = gr.Button("→", elem_id="btn-go")
        gr.HTML(FEATURES)

    # 화면 1.5 분석 중
    with gr.Column(visible=False) as screen_loading:
        gr.HTML(LOADING)

    # 화면 2. 검수 결과
    with gr.Row(visible=False, elem_id="result-wrap") as screen2:
        with gr.Column(scale=5, elem_id="left"):
            out_left = gr.HTML()
            btn_back = gr.Button("← 다른 콘텐츠 검수하기", elem_id="btn-back")
        with gr.Column(scale=7):
            out_right = gr.HTML()

    img_state = gr.State(None)   # [W7] 올린 이미지 경로

    btn_file.upload(on_file, btn_file, [in_text, file_note, img_state])
    (btn_go.click(on_start, [in_text, img_state], [screen1, screen_loading], show_progress="hidden")
           .success(on_submit, [in_text, in_purpose, img_state, in_date],
                    [screen1, screen_loading, screen2, out_left, out_right],
                    show_progress="hidden"))
    btn_back.click(on_back, None, [screen1, screen2, img_state, file_note])


if __name__ == "__main__":
    # 127.0.0.1 → VS Code 포트 포워딩으로만 접속. share=True 금지
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, **_launch_kw)