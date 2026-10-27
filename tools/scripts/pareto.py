"""Heretic optuna 체크포인트에서 전체 trial 과 Pareto front 를 표로 뽑는다.

사용: python pareto.py <checkpoint.jsonl> <out.tsv>
Pareto 순서는 Heretic 메뉴와 같게 (점수 오름차순) 정렬해 trial_index(0부터) 를 함께 기록한다.
"""
import sys

import optuna
from optuna.storages import JournalStorage
from optuna.storages.journal import JournalFileBackend, JournalFileOpenLock
from optuna.trial import TrialState

path, out = sys.argv[1], sys.argv[2]
storage = JournalStorage(JournalFileBackend(path, lock_obj=JournalFileOpenLock(path)))
study = optuna.load_study(study_name=storage.get_all_studies()[0].study_name, storage=storage)

done = [t for t in study.trials if t.state == TrialState.COMPLETE]
pareto = sorted(study.best_trials, key=lambda t: tuple(t.values))
pareto_ids = {t.number: i for i, t in enumerate(pareto)}

lines = ["trial\tpareto_index\trefusals\tkl\tparams"]
for t in sorted(done, key=lambda t: tuple(t.values)):
    p = t.user_attrs.get("parameters", t.params)
    lines.append(f"{t.user_attrs.get('index', t.number + 1)}\t{pareto_ids.get(t.number, '')}\t"
                 f"{t.values[0]:g}\t{t.values[1]:.4f}\t{p}")
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")

print(f"completed={len(done)} pareto={len(pareto)}")
print("pareto_index  trial  refusals  kl")
for i, t in enumerate(pareto):
    print(f"{i:>12}  {t.user_attrs.get('index', t.number + 1):>5}  {t.values[0]:>8g}  {t.values[1]:.4f}")
