import os
import secrets
import time

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
MATERIAL_EXTS = {".pdf", ".doc", ".docx", ".odt", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods", ".zip", ".jpg", ".png"}


def upload_path(subdir, filename=""):
    path = os.path.join(UPLOAD_DIR, subdir) if subdir else UPLOAD_DIR
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, filename) if filename else path


def new_filename(ext):
    return f"{int(time.time() * 1000)}-{secrets.token_hex(4)}{ext}"


def save_image(file, subdir):
    """儲存 JPG/PNG 圖片，回傳檔名；格式不符回傳 None。"""
    ext = IMAGE_TYPES.get(file.mimetype)
    if not ext:
        return None
    filename = new_filename(ext)
    file.save(upload_path(subdir, filename))
    return filename


def save_material(file):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in MATERIAL_EXTS:
        return None
    filename = new_filename(ext)
    file.save(upload_path("materials", filename))
    return filename


def remove_file(subdir, filename):
    if not filename:
        return
    try:
        os.remove(upload_path(subdir, filename))
    except FileNotFoundError:
        pass
