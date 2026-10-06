"""Portable archives and content manifests. Local receipts are not upload receipts."""
import hashlib
import json
import pathlib
import tarfile


def manifest(root):
    root = pathlib.Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'archive input contains a symlink: {path}')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def archive(root, target):
    root, target = pathlib.Path(root).resolve(), pathlib.Path(target).resolve()
    if target.is_relative_to(root):
        raise ValueError('archive must be outside its input directory')
    manifest(root)  # Reject links rather than copying bytes from outside the tree.
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        with tarfile.open(fileobj=output, mode='w:gz') as tar:
            tar.add(root, arcname=root.name)
    return hashlib.sha256(target.read_bytes()).hexdigest()
