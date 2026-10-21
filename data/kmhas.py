
"""K-MHaS 데이터 로더 + 라벨 정의. 학습·평가·데모 코드가 모두 이 파일을 import해서 씀."""
from datasets import load_dataset

# 라벨 순서 = 데이터셋 label 번호 (0~8). 데이터셋 카드에서 확인함
LABEL_NAMES = ["origin", "physical", "politics", "profanity",
               "age", "gender", "race", "religion", "not_hate"]
LABEL_KO = ["출신", "외모", "정치", "욕설", "연령", "성별", "인종", "종교", "해당없음"]

# K-MHaS 라벨 → 출력 JSON (category, subtype, hate_target)
LABEL_MAP = {
    "origin":    ("harmful", "hate", "origin"),
    "physical":  ("harmful", "hate", "physical"),
    "age":       ("harmful", "hate", "age"),
    "gender":    ("harmful", "hate", "gender"),
    "religion":  ("harmful", "hate", "religion"),
    "race":      ("harmful", "hate", "race"),
    "profanity": ("harmful", "profanity", None),
    "politics":  ("sensitive", "political", None),  # 검토 필요
    "not_hate":  None,                              # finding 안 만듦
}


def to_multi_hot(label_ids, n=9):
    """[2, 3] → [0,0,1,1,0,0,0,0,0]"""
    vec = [0] * n
    for i in label_ids:
        vec[i] = 1
    return vec


def load_kmhas():
    """(train, val, test) DataFrame 반환. 컬럼: text, labels(길이 9 리스트)"""
    ds = load_dataset("jeanlee/kmhas_korean_hate_speech")
    dfs = {}
    for split in ["train", "validation", "test"]:
        df = ds[split].to_pandas()
        df["text"] = df["text"].str.strip()
        df["labels"] = df["label"].apply(to_multi_hot)
        dfs[split] = df[["text", "labels"]]

    train = dfs["train"]
    n0 = len(train)
    train = train[train["text"] != ""]                         # 빈 문장
    n1 = len(train)
    train = train.drop_duplicates(subset="text")               # 중복
    n2 = len(train)
    train = train[~train["text"].isin(dfs["test"]["text"])]    # test와 겹침 (누수 방지)
    n3 = len(train)
    print(f"[train] 빈 문장 -{n0-n1}, 중복 -{n1-n2}, test와 겹침 -{n2-n3} → {n3}건")
    print(f"[최종] train {n3} / val {len(dfs['validation'])} / test {len(dfs['test'])}")
    return train.reset_index(drop=True), dfs["validation"], dfs["test"]
