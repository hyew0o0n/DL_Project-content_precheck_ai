"""W8 합성 영상 평가셋 10개 검증 (모델/Gemini 호출 없음).

프로젝트 루트에서:
  python eval/video_eval/validate_video_set.py
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / 'eval/data/video_eval'


def inspect_video(path: Path):
    p = subprocess.run([
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate',
        '-of', 'json', str(path)
    ], check=True, capture_output=True, text=True)
    return json.loads(p.stdout)


def main():
    labels = json.loads((DATA_ROOT / 'labels.json').read_text(encoding='utf-8'))
    items = labels['items']
    assert len(items) == 10, f'영상 수가 10이 아님: {len(items)}'
    counts = Counter(x['label'] for x in items)
    assert counts == {'issue': 8, 'normal': 2}, counts
    durations = Counter(x['caption_duration_sec'] for x in items if x['label'] == 'issue')
    assert durations == {0.5: 2, 1.0: 2, 2.0: 2, 3.0: 2}, durations
    ids = [x['id'] for x in items]
    assert len(set(ids)) == 10

    for item in items:
        path = DATA_ROOT / item['video']
        assert path.is_file(), f'영상 없음: {path}'
        assert (DATA_ROOT / 'captions' / f"{item['id']}.png").is_file(), f"자막 없음: {item['id']}"
        probed = inspect_video(path)
        length = float(probed['format']['duration'])
        assert abs(length - 10.0) < 0.15, f'{item["id"]} 길이 오류: {length}'
        video = [s for s in probed['streams'] if s['codec_type'] == 'video']
        audio = [s for s in probed['streams'] if s['codec_type'] == 'audio']
        assert len(video) == 1 and not audio, f'{item["id"]} 영상/오디오 스트림 오류'
        assert (video[0]['width'], video[0]['height']) == (720, 1280), f'{item["id"]} 크기 오류'
        assert video[0]['codec_name'] == 'h264', f'{item["id"]} 코덱 오류'
        start, end = item['caption_start_sec'], item['caption_end_sec']
        assert 0 <= start < end <= length
        assert abs((end-start) - item['caption_duration_sec']) < 1e-6
        expect = [t for t in range(10) if start <= t + 0.5 < end]
        assert item['ideal_1fps_sample_times_sec'] == expect
        print(f"✅ {item['id']}: {item['label']}, {item['caption_duration_sec']}초, 1fps 샘플 {expect}")

    print('✅ 영상 10개, 문제 8/정상 2, 노출 시간 분포, 해상도·길이·코덱·무음 검증 완료')
    print('참고: 자막의 실제 OCR 탐지 성능과 정책 판정 정확도는 별도 평가 대상')


if __name__ == '__main__':
    main()
