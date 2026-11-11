"""Build an isolated GitHub Pages artifact. Never include storefront or backend."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def build():
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    allowed = {'index.html', 'demo.js', 'style.css', '.nojekyll'}
    unexpected = [p.name for p in output.iterdir() if p.name not in allowed]
    if unexpected:
        raise RuntimeError(f'Refusing to publish unexpected files: {unexpected}')
    for name in ('index.html', 'demo.js'):
        shutil.copyfile(ROOT / 'pages' / name, output / name)
    shutil.copyfile(ROOT / 'web/style.css', output / 'style.css')
    (output / '.nojekyll').touch()
    print(f'Pages demo: {output} (4 public files, no buyer inputs/API)')


if __name__ == '__main__':
    build()
