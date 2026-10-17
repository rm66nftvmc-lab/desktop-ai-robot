"""Idempotent compatibility fixes for the pinned optional GPT-SoVITS checkout."""

import os
from pathlib import Path


def main():
    repo = Path(os.environ['LOCALAPPDATA']) / 'DesktopAiRobot/tts-paimon/repo'
    # jieba_fast has no Windows CPython 3.12 wheel; jieba exposes the same API.
    for name in ('chinese.py', 'chinese2.py', 'tone_sandhi.py'):
        path = repo / 'GPT_SoVITS/text' / name
        source = path.read_text(encoding='utf-8')
        updated = source.replace('import jieba_fast.posseg as psg', 'import jieba.posseg as psg')
        updated = updated.replace('import jieba_fast as jieba', 'import jieba')
        updated = updated.replace('import jieba_fast', 'import jieba as jieba_fast')
        if updated != source:
            path.write_text(updated, encoding='utf-8')
    # Match the upstream SoVITS loader's explicit legacy-checkpoint behavior.
    path = repo / 'api.py'
    source = path.read_text(encoding='utf-8')
    updated = source.replace('torch.load(gpt_path, map_location="cpu")',
                             'torch.load(gpt_path, map_location="cpu", weights_only=False)')
    updated = updated.replace('librosa.load(filename, int(hps.data.sampling_rate))',
                              'librosa.load(filename, sr=int(hps.data.sampling_rate))')
    # Explicit Chinese/English needs no probabilistic language classifier or
    # network download. Preserve the upstream splitter for other language modes.
    updated = updated.replace(
        'for tmp in LangSegmenter.getTexts(text):\n                if tmp["lang"] == "en":',
        'for tmp in (_bridge_zh_en_segments(text) if language == "zh" else LangSegmenter.getTexts(text)):\n                if tmp["lang"] == "en":')
    if 'def _bridge_zh_en_segments(' not in updated:
        helper = '''def _bridge_zh_en_segments(text):
    for match in re.finditer(r"[A-Za-z]+(?:[ \\'’-]+[A-Za-z]+)*|[^A-Za-z]+", text):
        part = match.group(0)
        yield {"lang": "en" if re.search(r"[A-Za-z]", part) else "zh", "text": part}


'''
        updated = updated.replace('def get_phones_and_bert(', helper + 'def get_phones_and_bert(', 1)
    if updated != source:
        path.write_text(updated, encoding='utf-8')
    # The checkout already includes its expanded CMU dictionaries and g2p_en's
    # OOV neural checkpoint. Avoid implicit NLTK downloads during speech.
    path = repo.parent / '.venv/Lib/site-packages/g2p_en/g2p.py'
    if path.is_file():
        source = path.read_text(encoding='utf-8')
        updated = source.replace("nltk.download('averaged_perceptron_tagger')", 'pass  # Offline: optional POS data')
        updated = updated.replace("nltk.download('cmudict')", 'pass  # Offline: use the checkout CMU dictionary')
        updated = updated.replace('self.cmu = cmudict.dict()', 'self.cmu = {}  # Replaced by en_G2p.get_dict()')
        if updated != source:
            path.write_text(updated, encoding='utf-8')
    path = repo / 'GPT_SoVITS/text/english.py'
    source = path.read_text(encoding='utf-8')
    updated = source.replace('tokens = pos_tag(words)  # tuples of (word, tag)',
        'try:\n            tokens = pos_tag(words)\n        except LookupError:\n'
        '            # Offline fallback: dictionary/OOV pronunciation; ambiguous homographs use noun defaults.\n'
        '            tokens = [(word, "NN") for word in words]')
    if updated != source:
        path.write_text(updated, encoding='utf-8')
    print('Pinned GPT-SoVITS compatibility fixes applied.')


if __name__ == '__main__':
    main()
