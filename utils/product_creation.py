"""Validated product creation, independent of financial configuration.

Related writes are staged under an OS lock and compensated on request failure.
This protects normal failures/retries; it is not a crash-recovery journal.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import tempfile

from utils.file_lock import interprocess_file_lock
from utils.product_catalog import RESERVED_FACTORY_NAMESPACES


class CreationConflict(ValueError):
    pass


def business_name(value, *, product=False):
    if not isinstance(value, str):
        raise ValueError("نام واردشده معتبر نیست.")
    value = value.strip()
    device = value.split('.')[0].rstrip().upper()
    if (not value or len(value.encode('utf-8')) > 200
            or value.startswith(('.', '__')) or value.endswith(('.', ' '))
            or any(ord(c) < 32 or ord(c) == 127 or c in '/\\<>:"|?*' for c in value)
            or value.casefold() in RESERVED_FACTORY_NAMESPACES
            or device in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
            or device in {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in '123456789¹²³'}
            or (product and value.casefold().endswith('_meta'))):
        raise ValueError("نام واردشده برای ایجاد پوشه یا محصول مجاز نیست.")
    return value


def creation_path(data_root, factory, *parts):
    """Reject symlink parents and keep writes in exactly the selected factory."""
    data_root = Path(data_root).resolve()
    root = data_root / 'Factories'
    path = root / business_name(factory)
    for part in parts:
        path /= business_name(part)
    current = path
    while current != data_root:
        if current.is_symlink():
            raise ValueError("مسیر انتخاب‌شده مجاز نیست.")
        current = current.parent
    if root.resolve() not in path.resolve().parents:
        raise ValueError("مسیر انتخاب‌شده مجاز نیست.")
    return path


def _parent(path):
    if not path.is_dir():
        raise ValueError("پوشه والد انتخاب‌شده وجود ندارد.")


def _new(path):
    # lexists semantics, including dangling links and case aliases on Windows.
    if path.exists() or path.is_symlink():
        raise CreationConflict("این نام از قبل وجود دارد؛ داده موجود حفظ شد.")
    # Apply Windows case-insensitive identity rules on Ubuntu as well.
    if any(child.name.casefold() == path.name.casefold() for child in path.parent.iterdir()):
        raise CreationConflict("این نام از قبل وجود دارد؛ داده موجود حفظ شد.")


def capacity_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("ظرفیت باید یک عدد صحیح مثبت باشد.")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("ظرفیت باید یک عدد صحیح مثبت باشد.") from None
    if not number.is_finite() or number < 1 or number != number.to_integral_value():
        raise ValueError("ظرفیت باید یک عدد صحیح مثبت باشد.")
    return int(number)


def stage_bytes(path, content):
    """A unique same-filesystem temporary file, closed before Windows rename."""
    with tempfile.NamedTemporaryFile(prefix='.product-create-', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            temporary.unlink()
            raise
    return temporary


def atomic_bytes(path, content):
    temporary = stage_bytes(path, content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create(data_root, factory, kind, names, *, capacity=None, refresh):
    """Preflight, stage, publish, refresh hierarchy; undo only our new writes."""
    root = creation_path(data_root, factory)
    _parent(root)
    target = creation_path(data_root, factory, *names)
    if kind == 'product':
        name = business_name(names[-1], product=True)
        target = target.with_name(f'{name}.json')
        metadata = target.with_name(f'{name}_meta.json')
        capacity = capacity_value(capacity)
        template = Path(data_root) / 'Overall' / 'sample_product.json'
        content = template.read_bytes()
        try:
            document = json.loads(content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError('invalid product template') from exc
        if not isinstance(document, dict) or not isinstance(document.get('data'), dict) or not isinstance(document.get('_order'), list):
            raise RuntimeError('invalid product template columns')
        writes = [(metadata, json.dumps({'capacity': capacity}, ensure_ascii=False).encode('utf-8')),
                  (target, content)]  # Publish BOM last, after capacity is ready.
    else:
        writes = []
    _parent(target.parent)
    for path in [target, *[path for path, _ in writes]]:
        _new(path)
    # Shared hierarchy metadata is refreshed under the same cross-factory lock.
    with interprocess_file_lock(root.parent / '.product-creation.lock'):
        creation_path(data_root, factory, *names)  # Recheck after acquiring lock.
        _parent(target.parent)
        for path in [target, *[path for path, _ in writes]]:
            _new(path)
        staged, published = [], []
        directory_created = False
        try:
            for path, value in writes:
                staged.append((path, stage_bytes(path, value)))
            if kind != 'product':
                target.mkdir()
                directory_created = True
            for path, temporary in staged:
                _new(path)
                os.replace(temporary, path)
                published.append(path)
            refresh()
        except BaseException:
            for path in reversed(published):
                path.unlink()
            if directory_created:
                target.rmdir()
            raise
        finally:
            for _, temporary in staged:
                temporary.unlink(missing_ok=True)
