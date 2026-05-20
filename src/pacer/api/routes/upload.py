from __future__ import annotations
import base64
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pacer.api.deps import current_student_id
from pacer.tools.vision_tool import VisionUnderstandImageTool
from pacer.config import get_settings

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/image")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    student_id: int = Depends(current_student_id),
):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="unsupported image type")
    settings = get_settings()
    max_bytes = settings.upload_max_bytes
    # Read in chunks so we can reject oversize uploads without loading them all.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"image exceeds {max_bytes} bytes")
        chunks.append(chunk)
    content = b"".join(chunks)
    b64 = base64.b64encode(content).decode("ascii")
    tool = VisionUnderstandImageTool(llm=request.app.state.llm, model=settings.main_model)
    result = await tool.execute(image_base64=b64, hint=None)
    return {
        "ocr_result": result,
        "auto_routed_to_subject": result.get("subject", ""),
        "auto_filled_stem": result.get("stem", ""),
    }
