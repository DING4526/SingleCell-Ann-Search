"""Three-scope knowledge ingestion and permission-aware hybrid retrieval."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import pathlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
from flask import current_app
from sklearn.feature_extraction.text import TfidfVectorizer
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    AiModelConfig,
    AiProviderCall,
    KnowledgeChunk,
    KnowledgeDocument,
    User,
)
from app.services.access_service import can_edit_dataset, can_view_dataset, is_admin


ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
CHUNK_MIN = 800
CHUNK_MAX = 1200
CHUNK_OVERLAP = 150
MAX_CONTEXT_CHUNKS = 8
MAX_CONTEXT_CHARS = 12_000
MAX_CHUNKS_PER_DOCUMENT = 4

_KNOWLEDGE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ai-knowledge")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean_text(value: str) -> str:
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def can_view_document(document: KnowledgeDocument, user: User) -> bool:
    if not document or not user or not getattr(user, "is_authenticated", True):
        return False
    if document.scope == "platform":
        return True
    if document.scope == "personal":
        return document.owner_id == user.id
    return bool(document.dataset and can_view_dataset(document.dataset, user))


def can_manage_document(document: KnowledgeDocument, user: User) -> bool:
    if not document or not user:
        return False
    if document.source_type == "builtin":
        return is_admin(user)
    if document.scope == "platform":
        return is_admin(user)
    if document.scope == "personal":
        return document.owner_id == user.id
    return bool(document.dataset and can_edit_dataset(document.dataset, user))


def visible_documents(user: User, *, include_failed: bool = True) -> list[KnowledgeDocument]:
    query = KnowledgeDocument.query.order_by(KnowledgeDocument.updated_at.desc())
    if not include_failed:
        query = query.filter(KnowledgeDocument.status.in_(["ready", "degraded"]))
    return [row for row in query.all() if can_view_document(row, user)]


def document_to_dict(document: KnowledgeDocument, user: User | None = None) -> dict:
    return {
        "id": document.id,
        "scope": document.scope,
        "owner_id": document.owner_id,
        "dataset_id": document.dataset_id,
        "dataset_name": document.dataset.name if document.dataset else None,
        "title": document.title,
        "description": document.description or "",
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "size_bytes": int(document.size_bytes or 0),
        "source_type": document.source_type,
        "source_key": document.source_key,
        "version": document.version,
        "status": document.status,
        "semantic_status": document.semantic_status,
        "page_count": document.page_count,
        "chunk_count": int(document.chunk_count or 0),
        "error_message": document.error_message,
        "can_manage": can_manage_document(document, user) if user else False,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本文件必须使用 UTF-8、UTF-16 或 GB18030 编码。")


def _extract_sections(document: KnowledgeDocument) -> tuple[list[dict], int | None]:
    if not document.stored_path:
        raise ValueError("知识文档文件不存在。")
    path = pathlib.Path(document.stored_path)
    if not path.is_file():
        raise ValueError("知识文档文件不存在。")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("缺少 pypdf，无法解析 PDF。") from exc
        reader = PdfReader(str(path))
        max_pages = int(current_app.config.get("AI_KNOWLEDGE_MAX_PDF_PAGES", 500))
        if len(reader.pages) > max_pages:
            raise ValueError(f"PDF 页数不能超过 {max_pages} 页。")
        sections = []
        for page_number, page in enumerate(reader.pages, 1):
            text = _clean_text(page.extract_text() or "")
            if text:
                sections.append({"text": text, "page_number": page_number, "heading": None})
        if not sections:
            raise ValueError("PDF 没有可提取文本；本阶段暂不支持扫描件 OCR。")
        return sections, len(reader.pages)

    text = _clean_text(_decode_text(path.read_bytes()))
    if not text:
        raise ValueError("文档没有可用于检索的文本。")
    return [{"text": text, "page_number": None, "heading": None}], None


def _paragraphs(section: dict) -> list[dict]:
    heading = section.get("heading")
    result = []
    for block in re.split(r"\n\s*\n", section.get("text") or ""):
        block = _clean_text(block)
        if not block:
            continue
        first_line, _, rest = block.partition("\n")
        match = re.match(r"^#{1,6}\s+(.+)$", first_line.strip())
        if match:
            heading = match.group(1).strip()[:500]
            block = _clean_text(rest)
            if not block:
                continue
        result.append({
            "text": block,
            "heading": heading,
            "page_number": section.get("page_number"),
        })
    return result


def chunk_sections(sections: list[dict]) -> list[dict]:
    """Paragraph-aware chunks with a bounded overlap for follow-on context."""
    chunks: list[dict] = []
    buffer = ""
    heading = None
    page_number = None

    def emit() -> None:
        nonlocal buffer
        text = _clean_text(buffer)
        if text:
            chunks.append({"content": text, "heading": heading, "page_number": page_number})
        buffer = text[-CHUNK_OVERLAP:] if len(text) > CHUNK_OVERLAP else ""

    for section in sections:
        for paragraph in _paragraphs(section):
            text = paragraph["text"]
            if buffer and len(buffer) + 2 + len(text) > CHUNK_MAX and len(buffer) >= CHUNK_MIN:
                emit()
            if len(text) > CHUNK_MAX:
                for start in range(0, len(text), CHUNK_MAX - CHUNK_OVERLAP):
                    part = text[start:start + CHUNK_MAX]
                    if buffer:
                        part = buffer + "\n\n" + part
                        buffer = ""
                    chunks.append({
                        "content": _clean_text(part),
                        "heading": paragraph.get("heading"),
                        "page_number": paragraph.get("page_number"),
                    })
                continue
            if not buffer:
                heading = paragraph.get("heading")
                page_number = paragraph.get("page_number")
            buffer = f"{buffer}\n\n{text}" if buffer else text
    if buffer:
        text = _clean_text(buffer)
        if text and (not chunks or text != chunks[-1]["content"]):
            chunks.append({"content": text, "heading": heading, "page_number": page_number})

    deduped = []
    seen = set()
    for chunk in chunks:
        digest = _sha256(chunk["content"].encode("utf-8"))
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append({**chunk, "content_hash": digest})
    return deduped


def _default_embedding_model() -> AiModelConfig | None:
    return (
        AiModelConfig.query
        .filter_by(capability="embedding", enabled=True, is_default=True, last_test_status="success")
        .first()
        or AiModelConfig.query.filter_by(
            capability="embedding", enabled=True, last_test_status="success"
        ).order_by(AiModelConfig.id.asc()).first()
    )


def _record_provider_call(
    *, model: AiModelConfig, operation: str, usage, status: str,
    user_id: int | None = None, document_id: int | None = None, run_id: int | None = None,
    error_code: str | None = None,
) -> None:
    db.session.add(AiProviderCall(
        user_id=user_id,
        run_id=run_id,
        document_id=document_id,
        model_config_id=model.id,
        operation=operation,
        status=status,
        request_count=int(getattr(usage, "requests", 1) or 1),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        latency_ms=float(getattr(usage, "latency_ms", 0.0) or 0.0),
        error_code=error_code,
    ))


def _embed_document(document: KnowledgeDocument, chunks: list[KnowledgeChunk]) -> bool:
    model = _default_embedding_model()
    if not model:
        document.semantic_status = "not_configured"
        return False
    from app.ai.service import configured_provider

    provider = configured_provider(model)
    try:
        for start in range(0, len(chunks), 10):
            batch = chunks[start:start + 10]
            completion = provider.embed_texts(
                model=model.model_id,
                texts=[item.content for item in batch],
            )
            _record_provider_call(
                model=model, operation="knowledge_embedding", usage=completion.usage,
                status="success", user_id=document.owner_id, document_id=document.id,
            )
            for row, vector in zip(batch, completion.vectors):
                array = np.asarray(vector, dtype=np.float32)
                row.embedding_blob = array.tobytes()
                row.embedding_dimensions = int(array.shape[0])
                row.embedding_model_config_id = model.id
        document.semantic_status = "ready"
        return True
    except Exception as exc:
        usage = getattr(exc, "usage", None)
        _record_provider_call(
            model=model, operation="knowledge_embedding", usage=usage or object(),
            status="error", user_id=document.owner_id, document_id=document.id,
            error_code=exc.__class__.__name__,
        )
        document.semantic_status = "error"
        return False


def process_document(document_id: int, *, embed: bool = True) -> None:
    document = db.session.get(KnowledgeDocument, document_id)
    if not document:
        return
    if document.status in {"extracting", "indexing"}:
        return
    try:
        document.status = "extracting"
        document.error_message = None
        db.session.commit()
        sections, page_count = _extract_sections(document)
        pieces = chunk_sections(sections)
        if not pieces:
            raise ValueError("文档无法生成有效知识片段。")
        document.status = "indexing"
        document.page_count = page_count
        document.chunks.clear()
        db.session.flush()
        chunks = []
        for index, piece in enumerate(pieces):
            row = KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                heading=piece.get("heading"),
                page_number=piece.get("page_number"),
                content=piece["content"],
                content_hash=piece["content_hash"],
            )
            db.session.add(row)
            chunks.append(row)
        db.session.flush()
        document.chunk_count = len(chunks)
        semantic_ready = _embed_document(document, chunks) if embed else False
        if not embed:
            document.semantic_status = "pending" if _default_embedding_model() else "not_configured"
        document.status = "ready" if semantic_ready or document.semantic_status == "not_configured" else "degraded"
        document.updated_at = datetime.utcnow()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        document = db.session.get(KnowledgeDocument, document_id)
        if document:
            document.status = "error"
            document.error_message = str(exc)[:500]
            document.updated_at = datetime.utcnow()
            db.session.commit()


def _process_with_app(app, document_id: int) -> None:
    with app.app_context():
        process_document(document_id)


def submit_document_processing(app, document_id: int) -> None:
    _KNOWLEDGE_EXECUTOR.submit(_process_with_app, app, document_id)


def create_uploaded_document(*, file_storage, scope: str, title: str, description: str,
                             user: User, dataset=None) -> KnowledgeDocument:
    suffix = pathlib.Path(file_storage.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 PDF、Markdown 和 TXT 文档。")
    if scope not in {"platform", "dataset", "personal"}:
        raise ValueError("知识空间类型无效。")
    if scope == "platform" and not is_admin(user):
        raise PermissionError("只有管理员可以维护平台知识。")
    if scope == "personal" and dataset is not None:
        raise ValueError("个人知识不能关联数据集。")
    if scope == "dataset":
        if not dataset or not can_edit_dataset(dataset, user):
            raise PermissionError("需要数据集 Editor 权限才能上传资料。")

    data = file_storage.read()
    from app.ai.service import get_ai_settings
    limit_mb = int(get_ai_settings().max_knowledge_file_mb or current_app.config.get("AI_KNOWLEDGE_MAX_FILE_MB", 25))
    if not data:
        raise ValueError("上传文件为空。")
    if len(data) > limit_mb * 1024 * 1024:
        raise ValueError(f"知识文件不能超过 {limit_mb} MB。")
    safe_name = secure_filename(file_storage.filename or f"document{suffix}") or f"document{suffix}"
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = pathlib.Path(current_app.config["KNOWLEDGE_DIR"]) / stored_name
    path.write_bytes(data)
    document = KnowledgeDocument(
        scope=scope,
        owner_id=user.id,
        dataset_id=dataset.id if dataset else None,
        title=(title or pathlib.Path(safe_name).stem)[:300],
        description=(description or "")[:2000],
        original_filename=safe_name,
        stored_path=str(path),
        mime_type=file_storage.mimetype or mimetypes.guess_type(safe_name)[0],
        size_bytes=len(data),
        checksum=_sha256(data),
        source_type="upload",
        status="pending",
    )
    db.session.add(document)
    db.session.commit()
    return document


def delete_document(document: KnowledgeDocument) -> None:
    path = pathlib.Path(document.stored_path) if document.stored_path else None
    db.session.delete(document)
    db.session.commit()
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def ensure_builtin_knowledge() -> None:
    """Idempotently load concise, checked-in documentation without external calls."""
    root = pathlib.Path(current_app.root_path).parent / "docs" / "ai-knowledge"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*.md")):
        data = path.read_bytes()
        checksum = _sha256(data)
        source_key = path.name
        first_heading = next((
            line.lstrip("#").strip() for line in _decode_text(data).splitlines()
            if line.strip().startswith("#")
        ), path.stem.replace("-", " "))
        document = KnowledgeDocument.query.filter_by(source_type="builtin", source_key=source_key).first()
        if document and document.checksum == checksum and document.status in {"ready", "degraded"}:
            continue
        if not document:
            document = KnowledgeDocument(
                scope="platform", title=first_heading, source_type="builtin",
                source_key=source_key, checksum=checksum, original_filename=path.name,
            )
            db.session.add(document)
        document.title = first_heading[:300]
        document.stored_path = str(path)
        document.mime_type = "text/markdown"
        document.size_bytes = len(data)
        document.checksum = checksum
        document.status = "pending"
        document.error_message = None
        db.session.commit()
        process_document(document.id, embed=False)

    # Tool capabilities are generated from the executable registry rather than
    # copied into a second hand-maintained document.
    from app.ai.tools import tool_catalog
    catalog_lines = ["# AI 只读分析工具", ""]
    for item in tool_catalog():
        confirmation = "需要用户确认" if item["requires_confirmation"] else "无需单独确认"
        catalog_lines.extend([
            f"## {item['label']}", "", f"工具名：`{item['name']}`。{item['description']}",
            f"执行策略：{confirmation}。", "",
        ])
    data = "\n".join(catalog_lines).encode("utf-8")
    generated_path = pathlib.Path(current_app.config["KNOWLEDGE_DIR"]) / "builtin-tool-capabilities.md"
    generated_path.write_bytes(data)
    checksum = _sha256(data)
    source_key = "generated-tool-capabilities"
    document = KnowledgeDocument.query.filter_by(source_type="builtin", source_key=source_key).first()
    if not document:
        document = KnowledgeDocument(
            scope="platform", title="AI 只读分析工具", source_type="builtin",
            source_key=source_key, checksum=checksum, original_filename=generated_path.name,
        )
        db.session.add(document)
    if document.checksum != checksum or document.status not in {"ready", "degraded"}:
        document.title = "AI 只读分析工具"
        document.stored_path = str(generated_path)
        document.mime_type = "text/markdown"
        document.size_bytes = len(data)
        document.checksum = checksum
        document.status = "pending"
        document.error_message = None
        db.session.commit()
        process_document(document.id, embed=False)


def _semantic_scores(query: str, chunks: list[KnowledgeChunk], *, user_id: int | None,
                     run_id: int | None) -> dict[int, float]:
    model = _default_embedding_model()
    if not model:
        return {}
    candidates = [
        row for row in chunks
        if row.embedding_model_config_id == model.id and row.embedding_blob and row.embedding_dimensions
    ]
    if not candidates:
        return {}
    from app.ai.service import configured_provider
    try:
        completion = configured_provider(model).embed_texts(model=model.model_id, texts=[query])
        _record_provider_call(
            model=model, operation="rag_query_embedding", usage=completion.usage,
            status="success", user_id=user_id, run_id=run_id,
        )
    except Exception as exc:
        _record_provider_call(
            model=model, operation="rag_query_embedding", usage=getattr(exc, "usage", object()),
            status="error", user_id=user_id, run_id=run_id,
            error_code=exc.__class__.__name__,
        )
        return {}
    query_vector = np.asarray(completion.vectors[0], dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vector)) or 1.0
    scores = {}
    for row in candidates:
        vector = np.frombuffer(row.embedding_blob, dtype=np.float32)
        if vector.shape[0] != query_vector.shape[0]:
            continue
        denom = (float(np.linalg.norm(vector)) or 1.0) * query_norm
        scores[row.id] = float(np.dot(vector, query_vector) / denom)
    return scores


def retrieve_knowledge(query: str, *, user: User, scopes: list[str] | None = None,
                       dataset_ids: list[int] | None = None, limit: int = MAX_CONTEXT_CHUNKS,
                       run_id: int | None = None) -> list[dict]:
    query = _clean_text(query)
    if not query:
        return []
    allowed_scopes = set(["platform", "dataset", "personal"] if scopes is None else scopes)
    if not allowed_scopes:
        return []
    allowed_dataset_ids = set(dataset_ids or [])
    documents = []
    for document in visible_documents(user, include_failed=False):
        if document.scope not in allowed_scopes:
            continue
        if document.scope == "dataset" and allowed_dataset_ids and document.dataset_id not in allowed_dataset_ids:
            continue
        documents.append(document)
    chunks = [chunk for document in documents for chunk in document.chunks]
    if not chunks:
        return []

    lexical_scores: dict[int, float] = {}
    try:
        corpus = [row.content for row in chunks] + [query]
        matrix = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 4), min_df=1, max_features=50_000, norm="l2"
        ).fit_transform(corpus)
        values = (matrix[:-1] @ matrix[-1].T).toarray().ravel()
        lexical_scores = {row.id: float(score) for row, score in zip(chunks, values) if score > 0}
    except ValueError:
        lexical_scores = {}
    semantic_scores = _semantic_scores(query, chunks, user_id=user.id, run_id=run_id)

    def ranked(scores: dict[int, float]) -> list[int]:
        return [key for key, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:30]]

    fused: dict[int, float] = {}
    for ranking in (ranked(lexical_scores), ranked(semantic_scores)):
        for rank, chunk_id in enumerate(ranking, 1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank)
    if not fused:
        return []
    by_id = {row.id: row for row in chunks}
    selected = []
    per_document: dict[int, int] = {}
    total_chars = 0
    for chunk_id, score in sorted(fused.items(), key=lambda item: item[1], reverse=True):
        row = by_id[chunk_id]
        if per_document.get(row.document_id, 0) >= MAX_CHUNKS_PER_DOCUMENT:
            continue
        if total_chars + len(row.content) > MAX_CONTEXT_CHARS and selected:
            continue
        key = f"K:{row.document_id}:{row.chunk_index}"
        selected.append({
            "key": key,
            "chunk_id": row.id,
            "document_id": row.document_id,
            "title": row.document.title,
            "scope": row.document.scope,
            "dataset_id": row.document.dataset_id,
            "heading": row.heading,
            "page_number": row.page_number,
            "content": row.content,
            "excerpt": row.content[:300],
            "score": round(score, 8),
        })
        per_document[row.document_id] = per_document.get(row.document_id, 0) + 1
        total_chars += len(row.content)
        if len(selected) >= max(1, min(int(limit), MAX_CONTEXT_CHUNKS)):
            break
    return selected


def citation_snapshot(hit: dict) -> dict:
    return {
        "citation_key": hit["key"],
        "chunk_id": hit["chunk_id"],
        "source_title": hit["title"],
        "heading": hit.get("heading"),
        "page_number": hit.get("page_number"),
        "excerpt": (hit.get("excerpt") or "")[:300],
    }
