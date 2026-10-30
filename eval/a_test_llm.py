#llm 연결 작업 완료 확인

from typing import Literal
from pydantic import BaseModel
from llm.client import generate

class Judgment(BaseModel):
    verdict: Literal["위반", "검토 필요", "통과"]
    message: str

text = "다음 광고 문구를 검수해줘: '이 크림 하나면 부작용 없이 100% 주름 개선!'"
for i in range(3):
    out = generate(text, schema=Judgment)
    print(i, out)
    assert set(out) == {"verdict", "message"}
    assert out["verdict"] in ("위반", "검토 필요", "통과")
print("OK")