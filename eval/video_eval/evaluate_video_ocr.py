"""W8 synthetic video dataset: 1fps PaddleOCR caption recognition check.

Use from the repository root:
    python eval/video_eval/evaluate_video_ocr.py --ids V01 V02 V04
    python eval/video_eval/evaluate_video_ocr.py
    python eval/video_eval/evaluate_video_ocr.py --all-frames

Only invokes frame extraction and vision.ocr.run_ocr. It does NOT call
classification, RAG, LLM, or VLM.
"""

import argparse
import csv
import json
import tempfile
import unicodedata
import sys
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from video.frames import extract_frames
from vision.ocr import run_ocr

DATA_ROOT = PROJECT_ROOT / 'eval/data/video_eval'


def normalize(text):
    value = unicodedata.normalize('NFKC', str(text)).casefold()
    return ''.join(ch for ch in value if ch.isalnum())


def closest_similarity(target, texts):
    """Diagnostic similarity, not a pass/fail threshold."""
    goal = normalize(target)
    if not goal:
        return 0.0
    candidates = [normalize(x) for x in texts if normalize(x)]
    candidates.append(normalize('\n'.join(texts)))
    best = 0.0
    length = len(goal)
    for candidate in candidates:
        if not candidate:
            continue
        if goal in candidate:
            return 1.0
        if len(candidate) <= length + 4:
            windows = [candidate]
        else:
            windows = []
            for size in (max(1, length - 2), length, length + 2):
                for start in range(max(1, len(candidate) - size + 1)):
                    windows.append(candidate[start:start + size])
        for window in windows:
            best = max(best, SequenceMatcher(None, goal, window).ratio())
    return round(best, 3)


def evaluate(item, all_frames):
    video = DATA_ROOT / item['video']
    expected = set(map(int, item['ideal_1fps_sample_times_sec']))
    if all_frames:
        targets = set(range(10))
    else:
        targets = expected or {max(0, min(9, int(item["caption_start_sec"]))), max(0, min(9, int(item["caption_end_sec"])))}

    rows = []
    with tempfile.TemporaryDirectory(prefix='w8_ocr_eval_') as temp_dir:
        frames = extract_frames(str(video), output_dir=temp_dir)
        available = {int(frame['t']): frame['path'] for frame in frames}
        for t in sorted(targets):
            if t not in available:
                raise RuntimeError(f"{item['id']}: {t}s frame missing")
            boxes = run_ocr(available[t])
            if not isinstance(boxes, list):
                raise TypeError(f"{item['id']} t={t}: OCR must return list")
            texts = [str(box.get('text', '')).strip() for box in boxes]
            texts = [x for x in texts if x]
            combined = '\n'.join(texts)
            caption_exact = normalize(item['caption']) in normalize(combined)
            similarity = closest_similarity(item['caption'], texts)
            row = {
                'id': item['id'],
                'label': item['label'],
                'issue_type': item['issue_type'] or '',
                't': t,
                'caption_expected_at_sample': t in expected,
                'caption_exact_in_ocr': caption_exact,
                'caption_similarity_diagnostic': similarity,
                'caption': item['caption'],
                'ocr_text': combined.replace('\n', ' | '),
                'ocr_box_count': len(boxes),
            }
            rows.append(row)
            print(
                f"{item['id']} {t:>2}s | expected={'Y' if t in expected else 'N'} "
                f"| exact={'Y' if caption_exact else 'N'} | sim={similarity:.3f} "
                f"| OCR: {row['ocr_text'][:170] or '(none)'}",
                flush=True,
            )
    return rows


def main():
    parser = argparse.ArgumentParser(description='W8 1fps real OCR evaluation')
    parser.add_argument('--ids', nargs='+', metavar='VXX', help='V01 V02 ...; default all')
    parser.add_argument('--all-frames', action='store_true', help='Evaluate all 10 sampled seconds per video')
    args = parser.parse_args()

    labels = json.loads((DATA_ROOT / 'labels.json').read_text(encoding='utf-8'))
    items = labels['items']
    if args.ids:
        selected = set(args.ids)
        available = {item['id'] for item in items}
        unknown = selected - available
        if unknown:
            parser.error(f'Unknown video ID(s): {sorted(unknown)}')
        items = [item for item in items if item['id'] in selected]

    rows = []
    for item in items:
        rows.extend(evaluate(item, args.all_frames))

    suffix = 'all' if not args.ids else '_'.join(item['id'] for item in items)
    if args.all_frames:
        suffix += '_allframes'
    output_csv = DATA_ROOT / f'ocr_eval_{suffix}.csv'
    output_json = DATA_ROOT / f'ocr_eval_{suffix}_summary.json'
    with output_csv.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    expected_rows = [row for row in rows if row['caption_expected_at_sample']]
    exact_hits = sum(row['caption_exact_in_ocr'] for row in expected_rows)
    false_matches = sum(row['caption_exact_in_ocr'] for row in rows if not row['caption_expected_at_sample'])
    summary = {
        'video_count': len(items),
        'evaluated_frames': len(rows),
        'expected_caption_frames': len(expected_rows),
        'exact_caption_matches': exact_hits,
        'exact_match_recall': round(exact_hits / len(expected_rows), 3) if expected_rows else None,
        'unexpected_caption_matches_on_noncaption_frames': false_matches,
        'mode': 'all_frames' if args.all_frames else 'caption_window_only',
        'note': 'Exact string match is strict; similarity is diagnostic only. Not a policy classification accuracy metric.',
        'csv_path': str(output_csv),
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('\n===== W8 OCR 평가 요약 =====')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'✅ 결과 CSV: {output_csv}')
    print(f'✅ 요약 JSON: {output_json}')


if __name__ == '__main__':
    main()
