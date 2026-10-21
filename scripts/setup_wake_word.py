"""Install the official local Chinese wake recognizer model; no audio upload."""
from pathlib import Path
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge.app.security import resolve_data_dir, anchor_path

URL = 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip'


def main():
    store, source = resolve_data_dir()
    anchor = anchor_path()
    if anchor.is_file():
        anchored = Path(anchor.read_text(encoding='utf-8').strip())
        if source == 'env' and store.resolve() != anchored.resolve():
            raise RuntimeError('Explicit model store differs from the Bridge anchor')
        store = anchored
    target = store / 'models/vosk-model-small-cn-0.22'
    if (target / 'am/final.mdl').is_file():
        print('Wake model already installed')
        return
    proxies = urllib.request.getproxies()
    # Windows can store one URI rather than a per-protocol proxy map.
    if 'http' in proxies and 'https' not in proxies:
        proxies['https'] = proxies['http']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='wake-download-') as tmp:
        root = Path(tmp)
        archive = root / 'model.zip'
        with opener.open(URL, timeout=30) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
        with zipfile.ZipFile(archive) as model:
            for name in model.namelist():
                if not (root / name).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Unsafe model archive path')
            model.extractall(root)
        extracted = root / target.name
        if not (extracted / 'am/final.mdl').is_file():
            raise ValueError('Expected Chinese model not found')
        if target.exists():
            raise FileExistsError('Incomplete model directory exists; inspect before replacing it')
        extracted.rename(target)
        print('Official wake model installed; archive SHA256:', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
