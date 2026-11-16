#!/bin/bash
# v5 후속 실험 4개를 순서대로 실행 (총 약 45분)
#   v6     : 제곱근 가중치 + 3 epoch  → v5와 비교해 "epoch 효과" 분리 (약 6분)
#   v7     : 제곱근 가중치 + 8 epoch  → 더 오르는지 (약 16분)
#   v5_s7  : v5 설정 그대로, seed 7   → 결과가 운이었는지 확인 (약 10분)
#   v5_s123: v5 설정 그대로, seed 123 (약 10분)
#
# 실행 (서버, screen 안에서):
#   screen -S train
#   cd ~/project && source .venv/bin/activate
#   bash notebooks/a_run_v6_v7_seeds.sh
#   Ctrl+A → D 로 빠져나오기 / screen -r train 으로 다시 확인
#
# 끝나면: results/a_v5_followup_summary.txt 에 노션용 한 줄씩 모여 있음
# 하나가 실패해도 나머지는 계속 돎. 실패한 건 results/a_train_{버전}.log 확인

cd ~/project
SUMMARY=results/a_v5_followup_summary.txt
echo "===== $(date '+%m/%d %H:%M') v5 후속 실험 =====" >> "$SUMMARY"

run() {
  local ver=$1; shift
  echo ""
  echo "########## $ver 시작 ($(date '+%H:%M')) ##########"
  python notebooks/a_train_v5.py --version "$ver" "$@" 2>&1 | tee -a "results/a_train_${ver}.log"
  # 노션 기록용 한 줄만 요약 파일에 모으기
  grep -A1 "\[노션 모델 기록용\]" "results/a_train_${ver}.log" | tail -1 >> "$SUMMARY" \
    || echo "$ver | 실패 → results/a_train_${ver}.log 확인" >> "$SUMMARY"
}

run v6      --epochs 3
run v7      --epochs 8
run v5_s7   --seed 7
run v5_s123 --seed 123

echo ""
echo "########## 전부 끝 ($(date '+%H:%M')) ##########"
cat "$SUMMARY"
nvidia-smi --query-gpu=memory.used --format=csv