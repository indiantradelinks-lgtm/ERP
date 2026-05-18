"""File upload / list / download / soft-delete."""
import io
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query
import jwt as pyjwt

from core import db, get_current_user, now_iso, new_id, JWT_SECRET, JWT_ALGORITHM, logger
from storage import put_object, get_object, MAX_BYTES

router = APIRouter(tags=["files"])


@router.post("/uploads")
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Form("documents"),
    parent_type: str = Form(""),
    parent_id: str = Form(""),
    title: str = Form(""),
    user: dict = Depends(get_current_user),
):
    if folder not in ("documents", "safety"):
        raise HTTPException(status_code=400, detail="folder must be 'documents' or 'safety'")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    try:
        result = put_object(folder=folder, filename=file.filename or "file.bin", data=data, content_type=file.content_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    record = {
        "id": new_id(),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": result.get("content_type") or file.content_type,
        "size": result.get("size") or len(data),
        "title": title or file.filename,
        "folder": folder,
        "parent_type": parent_type or None,
        "parent_id": parent_id or None,
        "uploaded_by": user.get("name") or user.get("email"),
        "uploaded_by_id": user["id"],
        "is_deleted": False,
        "created_at": now_iso(),
    }
    await db.files.insert_one(record)
    record.pop("_id", None)
    return record


@router.get("/files")
async def list_files(parent_type: str = "", parent_id: str = "", folder: str = "", user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {"is_deleted": False}
    if parent_type:
        q["parent_type"] = parent_type
    if parent_id:
        q["parent_id"] = parent_id
    if folder:
        q["folder"] = folder
    rows = await db.files.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/files/{file_id}/download")
async def download_file(file_id: str, request: Request, auth: str = Query(None)):
    # Auth via cookie OR ?auth=<access_token> query param (for inline <img src>)
    if auth:
        try:
            payload = pyjwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                raise HTTPException(status_code=401, detail="Invalid token")
        except pyjwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        await get_current_user(request)

    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, ct = get_object(record["storage_path"])
    except Exception as e:
        logger.exception(f"download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")
    headers = {"Content-Disposition": f'inline; filename="{record.get("original_filename", "file")}"'}
    return Response(content=data, media_type=record.get("content_type") or ct, headers=headers)


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, user: dict = Depends(get_current_user)):
    result = await db.files.update_one(
        {"id": file_id},
        {"$set": {"is_deleted": True, "deleted_at": now_iso(), "deleted_by": user["id"]}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
