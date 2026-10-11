"""Install a fresh personal copy of the explicitly bundled completed preset."""
import os
import shutil
from pathlib import Path


def install_preset(root: Path):
    source = Path(os.getenv('COURSEBOOK_PRESET_DIR', 'bundled-preset'))
    if (root / 'preset-imported.json').exists() or not (source / 'preset-imported.json').exists():
        return
    if (root / 'product/product.sqlite3').exists():
        return  # Never replace an existing visitor's library.
    for path in source.rglob('*'):
        if path.is_file() and not path.is_symlink():
            target = root / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
