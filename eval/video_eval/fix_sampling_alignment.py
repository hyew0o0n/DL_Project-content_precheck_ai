"""Fix W8 dataset sample-time labels to match FFmpeg fps=1:round=near.

Run once from ~/project: python eval/video_eval/fix_sampling_alignment.py
Does not regenerate or change any MP4, caption image, background, or model.
Retains existing provenance URLs and other dataset fields.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'eval/data/video_eval'
TOOLS = ROOT / 'eval/video_eval'


def adjusted(text: str, old: str, new: str, name: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f'{name}: expected source expression not found; no files changed')


def main() -> None:
    label_file = DATA / 'labels.json'
    source_file = TOOLS / 'make_video_set.py'
    validator_file = TOOLS / 'validate_video_set.py'
    ocr_file = TOOLS / 'evaluate_video_ocr.py'

    paths = [source_file, validator_file, ocr_file]
    contents = {path: path.read_text(encoding='utf-8') for path in paths}

    contents[source_file] = adjusted(
        contents[source_file],
        'sample_hits = [t for t in range(int(VIDEO_SECONDS)) if start <= t < end]',
        'sample_hits = [t for t in range(int(VIDEO_SECONDS)) if start <= t + 0.5 < end]',
        'make_video_set.py',
    )
    contents[validator_file] = adjusted(
        contents[validator_file],
        'expect = [t for t in range(10) if start <= t < end]',
        'expect = [t for t in range(10) if start <= t + 0.5 < end]',
        'validate_video_set.py',
    )
    contents[ocr_file] = adjusted(
        contents[ocr_file],
        'targets = expected or {2, 3}  # V01: test the surrounding integer seconds',
        'targets = expected or {max(0, min(9, int(item["caption_start_sec"]))), max(0, min(9, int(item["caption_end_sec"])))}',
        'evaluate_video_ocr.py',
    )

    labels = json.loads(label_file.read_text(encoding='utf-8'))
    items = labels.get('items', [])
    if len(items) != 10:
        raise RuntimeError(f'Unexpected item count {len(items)}; no files changed')

    for item in items:
        start, end = float(item['caption_start_sec']), float(item['caption_end_sec'])
        hits = [t for t in range(10) if start <= t + 0.5 < end]
        item['ideal_1fps_sample_times_sec'] = hits
        item['ideal_1fps_sampling_visible'] = bool(hits)
        print(f"{item['id']}: corrected 1fps samples {hits}")

    labels['sampling_assumption'] = (
        'video/frames.py FFmpeg fps=fps=1:start_time=0:round=near: '
        'sample index t represents content near t+0.5s (actual frame timing is approximate).'
    )
    labels['sampling_alignment_note'] = (
        'Original labels assumed sample content at integer t and were corrected; '
        'V01 has sampled caption, V02 is missed at 1fps. No MP4 was modified.'
    )

    # Validate all code transformations before writing anything.
    for path, code in contents.items():
        compile(code, str(path), 'exec')
    rendered_labels = json.dumps(labels, indent=2, ensure_ascii=False) + '\n'
    json.loads(rendered_labels)

    # No existing provenance, labels, or additional fields are removed.
    for path, code in contents.items():
        if path.read_text(encoding='utf-8') != code:
            path.write_text(code, encoding='utf-8')
    if label_file.read_text(encoding='utf-8') != rendered_labels:
        label_file.write_text(rendered_labels, encoding='utf-8')
    print('✅ Dataset labels, generator, validator, OCR evaluator aligned')
    print('✅ Videos/caption images untouched; provenance retained')


if __name__ == '__main__':
    main()
