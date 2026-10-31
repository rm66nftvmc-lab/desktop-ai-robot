"""Conservative, offline transcript cleanup. Never infer missing intent."""

from dataclasses import dataclass
import re
import time


@dataclass(frozen=True)
class CleanupResult:
    original: str
    simplified: str
    text: str
    changes: tuple[str, ...]
    elapsed_ms: float
    warning: str | None = None


# Preserve quoted literals, code, URLs and explicit filesystem paths verbatim.
_LITERAL = re.compile(r'```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|'
                      r"'[^'\n]*'|https?://[^\s，。！？；]+|[A-Za-z]:[\\/][^\s，。！？；]+")
_STARTER = re.compile(r'(^|[，,。！？!?；;])(?P<p>请帮我|帮我|我想问一下|我想要|我想|麻烦你|请问)'
                      r'(?:[，,\s]*(?P=p))+(?=\S)')
_NUMBER = r'(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)'
_REPAIR = r'\s*[，,]\s*(?:不对|说错了)[，,\s]*(?:应该是|改成|是)?\s*'
_DAY = r'(?:大后天|后天|明天|今天|昨天|前天|下(?:周|星期)[一二三四五六日天]|(?:周|星期)[一二三四五六日天])'
_DAY_REPAIR = re.compile(r'(?P<old>' + _DAY + ')' + _REPAIR + r'(?P<new>' + _DAY + ')')
_QUANTITY_REPAIR = re.compile(r'(?<![A-Za-z0-9零〇一二两三四五六七八九十百千万.+−负-])(?P<old>' + _NUMBER + r')(?P<unit>小时|分钟|秒钟|厘米|毫米|公斤|千克|毫升|点|分|秒|个|次|元|块|岁|年|月|天|米|克|升|度|%|％)'
                              + _REPAIR + r'(?P<new>' + _NUMBER + r')(?P=unit)(?![\d钟米克升])')
_NEGATION = re.compile(r'不|没|别|勿|禁止|拒绝')


def _repair(match, text):
    # Negation and questions can change the scope of an apparent correction.
    left = re.split(r'[。！？!?；;]', text[:match.start()])[-1]
    right = re.split(r'[。！!；;]', text[match.end():])[0]
    if _NEGATION.search(left) or re.search(r'吗|么|呢|对不对|是不是|还是|[？?]', right):
        return match.group(0)
    if 'unit' in match.re.groupindex:
        return match['new'] + match['unit']
    return match['new']


def light_cleanup(text):
    text = _STARTER.sub(lambda m: m[1] + m['p'], text)
    for pattern in (_DAY_REPAIR, _QUANTITY_REPAIR):
        for _ in range(3):  # Bounded chained corrections, never free-form rewriting.
            updated = pattern.sub(lambda m: _repair(m, text), text)
            if updated == text:
                break
            text = updated
    return text


class SpeechCleanup:
    def __init__(self):
        self._converter = None

    def prepare(self):
        if self._converter is None:
            from opencc import OpenCC
            self._converter = OpenCC('t2s')

    def process(self, original, mode='light'):
        if mode not in ('light', 'simplified'):
            raise ValueError('Invalid cleanup mode')
        started = time.perf_counter()
        try:
            self.prepare()
        except Exception:
            return CleanupResult(original, original.strip(), original.strip(), (),
                                 round((time.perf_counter() - started) * 1000, 3),
                                 '语音优化不可用，已保留原文；请检查本地 OpenCC 安装')
        pieces, literals = [], []
        previous = 0
        for match in _LITERAL.finditer(original):
            pieces.append(self._converter.convert(original[previous:match.start()]))
            literals.append(match.group(0))
            previous = match.end()
        pieces.append(self._converter.convert(original[previous:]))
        simplified = ''.join(part + (literals[i] if i < len(literals) else '') for i, part in enumerate(pieces)).strip()
        changes = ['simplified'] if simplified != original.strip() else []
        warning = None
        cleaned = pieces
        # Literal-containing utterances are simplified only: never infer the
        # scope of corrections around a quoted command, path or code sample.
        if mode == 'light' and not literals:
            try:
                cleaned = [light_cleanup(part) for part in pieces]
            except Exception:
                cleaned = pieces
                warning = '轻度优化暂不可用，已使用简体原文'
        text = ''.join(part + (literals[i] if i < len(literals) else '') for i, part in enumerate(cleaned)).strip()
        if text != simplified:
            changes.append('light')
        if not text and simplified:  # Never turn a nonempty utterance into silence.
            text = simplified
        return CleanupResult(original, simplified, text, tuple(changes),
                             round((time.perf_counter() - started) * 1000, 3), warning)
