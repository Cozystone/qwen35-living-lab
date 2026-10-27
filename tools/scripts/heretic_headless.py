"""콘솔 없이 Heretic 을 실행한다.

1) Heretic 은 ask_if_unset(value, questionary.select(...)) 처럼 질문 객체를 값 확인 전에 먼저 만든다.
   Windows 에서 콘솔이 없으면 그 생성 단계에서 NoConsoleScreenBufferError 가 난다.
   여기서는 questionary 생성자를 스텁으로 바꾼다. 설정에 없는 질문이 실제로 필요해지면 즉시 오류를 낸다.
2) 환경변수 HERETIC_TRIAL=<trial 번호> 가 있으면 trial 선택 메뉴에서 Pareto 순번(trial_index) 대신
   해당 번호의 trial 을 정확히 고른다. (trial_index 지정이 의도와 다른 trial 을 복원한 사례가 있어 추가)
   메뉴에 보인 후보 전체를 로그에 출력한다.

사용: (config.toml 이 있는 폴더에서) [HERETIC_TRIAL=55] python heretic_headless.py
"""
import os

import questionary


class _Unanswerable:
    def __init__(self, kind, message=None, *args, **kwargs):
        self.kind, self.message, self.choices = kind, message, kwargs.get("choices")

    def ask(self, *args, **kwargs):
        raise RuntimeError(f"headless run needs an answer for {self.kind}: {self.message!r} — set it in config.toml")

    unsafe_ask = ask


for _name in ("select", "text", "path", "password", "confirm", "checkbox"):
    setattr(questionary, _name, lambda *a, _n=_name, **k: _Unanswerable(_n, *a, **k))

from heretic import main as heretic_main  # noqa: E402  (패치 후 import 해야 함)
from heretic.utils import ask_if_unset as _orig_ask_if_unset  # noqa: E402

_wanted = os.environ.get("HERETIC_TRIAL")


def _ask_if_unset(value, question, unsafe=False):
    choices = getattr(question, "choices", None)
    if _wanted and choices and "trial" in str(question.message).lower():
        print("[headless] trial menu:")
        for c in choices:
            v = getattr(c, "value", None)
            idx = v.user_attrs.get("index") if hasattr(v, "user_attrs") else v
            print(f"[headless]   index={idx} title={getattr(c, 'title', '')!s}")
        for c in choices:
            v = getattr(c, "value", None)
            if hasattr(v, "user_attrs") and str(v.user_attrs.get("index")) == _wanted:
                print(f"[headless] selecting trial {_wanted} (Heretic proposed index {value.user_attrs.get('index') if hasattr(value, 'user_attrs') else value})")
                return v
        raise RuntimeError(f"trial {_wanted} not in Pareto menu")
    return _orig_ask_if_unset(value, question, unsafe)


heretic_main.questionary = questionary
heretic_main.ask_if_unset = _ask_if_unset
heretic_main.main()
