"""
RAG 知识库 DAO — 操作 rag_kb_document + rag_kb_index_log 表（V3.0 新增，SQLAlchemy ORM）
记录 ChromaDB 文档元数据和索引构建日志
"""

from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import func, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import RagKbDocument, RagKbIndexLog, RagKbManagedDoc


def _doc_dict(r: RagKbDocument, with_timestamps: bool = True) -> Dict:
    result = {
        "id": r.id,
        "doc_id": r.doc_id,
        "kb_name": r.kb_name,
        "file_path": r.file_path,
        "title": r.title,
        "chunk_count": r.chunk_count,
        "char_count": r.char_count,
        "chroma_collection": r.chroma_collection,
        "status": r.status,
        "last_indexed_at": r.last_indexed_at,
        "indexed_by": r.indexed_by,
    }
    if with_timestamps:
        result["created_at"] = r.created_at
        result["updated_at"] = r.updated_at
    return result


class RAGDAO:
    """RAG 知识库数据访问（全局共享，无权限过滤）"""

    # V3.3：新增 company（集团概况）/ classes（开班计划）/ awards（荣誉资质）
    KB_NAMES = {
        "scripts", "sops", "faqs", "cases", "customer_profiles", "chat_messages",
        "company", "classes", "awards",
    }

    # ==================== 文档管理 ====================

    @staticmethod
    def get_document(doc_id: str) -> Optional[Dict]:
        """按文档 ID 查询"""
        with session_scope() as session:
            r = (
                session.query(RagKbDocument)
                .filter(RagKbDocument.doc_id == doc_id)
                .first()
            )
            return _doc_dict(r) if r else None

    @staticmethod
    def get_documents_by_kb(
        kb_name: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        """按知识库查询文档列表"""
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        with session_scope() as session:
            query = session.query(RagKbDocument).filter(RagKbDocument.kb_name == kb_name)
            if status:
                query = query.filter(RagKbDocument.status == status)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(RagKbDocument.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [_doc_dict(r) for r in rows]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_all_documents(status: Optional[str] = None) -> List[Dict]:
        """获取所有文档（用于全量同步）"""
        with session_scope() as session:
            query = session.query(RagKbDocument)
            if status:
                query = query.filter(RagKbDocument.status == status)
            rows = (
                query.order_by(RagKbDocument.kb_name, RagKbDocument.doc_id)
                .all()
            )
            return [_doc_dict(r, with_timestamps=False) for r in rows]

    @staticmethod
    def get_documents_by_status(status: str) -> List[Dict]:
        """按状态查询文档（用于索引任务）"""
        return RAGDAO.get_all_documents(status)

    @staticmethod
    def upsert_document(
        doc_id: str,
        kb_name: str,
        file_path: str,
        title: Optional[str] = None,
        chunk_count: int = 0,
        char_count: int = 0,
        chroma_collection: Optional[str] = None,
        indexed_by: Optional[str] = None,
    ) -> bool:
        """
        插入或更新文档元数据
        """
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        if chroma_collection is None:
            chroma_collection = f"k12_{kb_name}"

        with session_scope(commit=True) as session:
            row = (
                session.query(RagKbDocument)
                .filter(RagKbDocument.doc_id == doc_id)
                .first()
            )
            now = datetime.now()
            if row:
                row.kb_name = kb_name
                row.file_path = file_path
                row.title = title
                row.chunk_count = chunk_count
                row.char_count = char_count
                row.chroma_collection = chroma_collection
                row.status = "active"
                row.last_indexed_at = now
                row.indexed_by = indexed_by
            else:
                session.add(
                    RagKbDocument(
                        doc_id=doc_id,
                        kb_name=kb_name,
                        file_path=file_path,
                        title=title,
                        chunk_count=chunk_count,
                        char_count=char_count,
                        chroma_collection=chroma_collection,
                        status="active",
                        last_indexed_at=now,
                        indexed_by=indexed_by,
                    )
                )
            return True

    @staticmethod
    def update_document_status(doc_id: str, status: str) -> bool:
        """更新文档索引状态"""
        if status not in {"active", "pending_reindex", "deleted"}:
            raise ValueError(f"无效的 status: {status}，允许值: active / pending_reindex / deleted")

        with session_scope(commit=True) as session:
            result = session.execute(
                update(RagKbDocument)
                .where(RagKbDocument.doc_id == doc_id)
                .values(status=status)
            )
            return result.rowcount > 0

    @staticmethod
    def update_document_stats(doc_id: str, chunk_count: int, char_count: int) -> bool:
        """更新文档统计信息"""
        with session_scope(commit=True) as session:
            result = session.execute(
                update(RagKbDocument)
                .where(RagKbDocument.doc_id == doc_id)
                .values(
                    chunk_count=chunk_count,
                    char_count=char_count,
                    last_indexed_at=datetime.now(),
                )
            )
            return result.rowcount > 0

    @staticmethod
    def delete_document(doc_id: str) -> bool:
        """物理删除文档元数据"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(RagKbDocument).where(RagKbDocument.doc_id == doc_id)
            )
            return result.rowcount > 0

    @staticmethod
    def delete_documents_by_kb(kb_name: str) -> int:
        """删除某知识库的所有文档元数据"""
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        with session_scope(commit=True) as session:
            result = session.execute(
                delete(RagKbDocument).where(RagKbDocument.kb_name == kb_name)
            )
            return result.rowcount

    @staticmethod
    def get_kb_stats(kb_name: str) -> Dict:
        """获取知识库统计信息"""
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        with session_scope() as session:
            r = (
                session.query(
                    func.count(RagKbDocument.id).label("doc_count"),
                    func.sum(RagKbDocument.chunk_count).label("total_chunks"),
                    func.sum(RagKbDocument.char_count).label("total_chars"),
                    func.max(RagKbDocument.last_indexed_at).label("last_indexed_at"),
                )
                .filter(
                    RagKbDocument.kb_name == kb_name,
                    RagKbDocument.status == "active",
                )
                .first()
            )
            if not r or not r.doc_count:
                return {"doc_count": 0, "total_chunks": 0, "total_chars": 0, "last_indexed_at": None}
            return {
                "doc_count": int(r.doc_count),
                "total_chunks": int(r.total_chunks or 0),
                "total_chars": int(r.total_chars or 0),
                "last_indexed_at": r.last_indexed_at,
            }

    @staticmethod
    def doc_exists(doc_id: str) -> bool:
        """检查文档是否存在"""
        with session_scope() as session:
            return (
                session.query(RagKbDocument)
                .filter(RagKbDocument.doc_id == doc_id)
                .first()
                is not None
            )

    # ==================== 索引日志管理 ====================

    @staticmethod
    def log_index_build(
        kb_name: str,
        doc_count: int,
        chunk_count: int,
        elapsed_ms: int,
        status: str,
        triggered_by: str,
        error_message: Optional[str] = None,
    ) -> Optional[int]:
        """记录索引构建日志"""
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        with session_scope(commit=True) as session:
            obj = RagKbIndexLog(
                kb_name=kb_name,
                doc_count=doc_count,
                chunk_count=chunk_count,
                elapsed_ms=elapsed_ms,
                status=status,
                error_message=error_message,
                triggered_by=triggered_by,
            )
            session.add(obj)
            session.flush()
            return obj.id

    @staticmethod
    def get_index_logs(
        kb_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """查询索引构建日志"""
        with session_scope() as session:
            query = session.query(RagKbIndexLog)
            if kb_name:
                if kb_name not in RAGDAO.KB_NAMES:
                    raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")
                query = query.filter(RagKbIndexLog.kb_name == kb_name)
            if status:
                query = query.filter(RagKbIndexLog.status == status)
            rows = (
                query.order_by(RagKbIndexLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "kb_name": r.kb_name,
                    "doc_count": r.doc_count,
                    "chunk_count": r.chunk_count,
                    "elapsed_ms": r.elapsed_ms,
                    "status": r.status,
                    "error_message": r.error_message,
                    "triggered_by": r.triggered_by,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @staticmethod
    def get_last_index_log(kb_name: str) -> Optional[Dict]:
        """获取某知识库最近一次索引构建日志"""
        if kb_name not in RAGDAO.KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.KB_NAMES}")

        with session_scope() as session:
            r = (
                session.query(RagKbIndexLog)
                .filter(RagKbIndexLog.kb_name == kb_name)
                .order_by(RagKbIndexLog.created_at.desc())
                .limit(1)
                .first()
            )
            if not r:
                return None
            return {
                "id": r.id,
                "kb_name": r.kb_name,
                "doc_count": r.doc_count,
                "chunk_count": r.chunk_count,
                "elapsed_ms": r.elapsed_ms,
                "status": r.status,
                "error_message": r.error_message,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at,
            }

    # ==================== 资料库托管文档管理（V3.3 二期） ====================
    # 运营在管理后台上传/替换/审核/发布文档，发布后由索引器重建向量。

    MANAGED_KB_NAMES = {"company", "classes", "awards", "faqs", "sops", "scripts", "cases"}
    DOC_STATUSES = {"draft", "reviewing", "published", "archived"}

    @staticmethod
    def _managed_doc_dict(r: RagKbManagedDoc) -> Dict:
        return {
            "id": r.id,
            "doc_key": r.doc_key,
            "kb_name": r.kb_name,
            "title": r.title,
            "content": r.content,
            "doc_status": r.doc_status,
            "version": r.version,
            "created_by": r.created_by,
            "reviewed_by": r.reviewed_by,
            "review_comment": r.review_comment,
            "reviewed_at": r.reviewed_at,
            "published_at": r.published_at,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }

    @staticmethod
    def get_managed_doc(doc_key: str) -> Optional[Dict]:
        """按 doc_key 查询托管文档"""
        with session_scope() as session:
            r = (
                session.query(RagKbManagedDoc)
                .filter(RagKbManagedDoc.doc_key == doc_key)
                .first()
            )
            return RAGDAO._managed_doc_dict(r) if r else None

    @staticmethod
    def get_managed_doc_by_id(doc_id: int) -> Optional[Dict]:
        """按数字 id 查询托管文档（V3.3.1：doc_key 含 / 不适合放 URL 路径，统一用 id）"""
        with session_scope() as session:
            r = (
                session.query(RagKbManagedDoc)
                .filter(RagKbManagedDoc.id == doc_id)
                .first()
            )
            return RAGDAO._managed_doc_dict(r) if r else None

    @staticmethod
    def list_managed_docs(
        kb_name: Optional[str] = None,
        doc_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        """查询托管文档列表"""
        with session_scope() as session:
            query = session.query(RagKbManagedDoc)
            if kb_name:
                query = query.filter(RagKbManagedDoc.kb_name == kb_name)
            if doc_status:
                query = query.filter(RagKbManagedDoc.doc_status == doc_status)

            total = session.query(func.count()).select_from(query.subquery()).scalar()
            rows = (
                query.order_by(RagKbManagedDoc.kb_name, RagKbManagedDoc.doc_key)
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            items = [RAGDAO._managed_doc_dict(r) for r in rows]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_published_managed_docs(kb_name: Optional[str] = None) -> List[Dict]:
        """获取已发布托管文档（索引器读取用）"""
        with session_scope() as session:
            query = (
                session.query(RagKbManagedDoc)
                .filter(RagKbManagedDoc.doc_status == "published")
            )
            if kb_name:
                query = query.filter(RagKbManagedDoc.kb_name == kb_name)
            rows = query.order_by(RagKbManagedDoc.doc_key).all()
            return [RAGDAO._managed_doc_dict(r) for r in rows]

    @staticmethod
    def upsert_managed_doc(
        doc_key: str,
        kb_name: str,
        title: str,
        content: str,
        doc_status: str = "draft",
        created_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        review_comment: Optional[str] = None,
    ) -> Dict:
        """新增或替换托管文档（替换时版本 +1 并回退为草稿等待重新审核）"""
        if kb_name not in RAGDAO.MANAGED_KB_NAMES:
            raise ValueError(f"无效的 kb_name: {kb_name}，允许值: {RAGDAO.MANAGED_KB_NAMES}")
        if doc_status not in RAGDAO.DOC_STATUSES:
            raise ValueError(f"无效的 doc_status: {doc_status}，允许值: {RAGDAO.DOC_STATUSES}")

        with session_scope(commit=True) as session:
            row = (
                session.query(RagKbManagedDoc)
                .filter(RagKbManagedDoc.doc_key == doc_key)
                .first()
            )
            now = datetime.now()
            if row:
                row.title = title
                row.content = content
                row.kb_name = kb_name
                row.version = row.version + 1
                row.doc_status = doc_status
                row.reviewed_by = reviewed_by
                row.review_comment = review_comment
                row.reviewed_at = now if doc_status == "published" else None
                row.published_at = now if doc_status == "published" else None
                row.created_by = created_by or row.created_by
            else:
                row = RagKbManagedDoc(
                    doc_key=doc_key,
                    kb_name=kb_name,
                    title=title,
                    content=content,
                    doc_status=doc_status,
                    version=1,
                    created_by=created_by,
                    reviewed_by=reviewed_by,
                    review_comment=review_comment,
                    reviewed_at=now if doc_status == "published" else None,
                    published_at=now if doc_status == "published" else None,
                )
                session.add(row)
            session.flush()
            return RAGDAO._managed_doc_dict(row)

    @staticmethod
    def update_managed_doc_status(
        doc_key: str,
        doc_status: str,
        reviewed_by: Optional[str] = None,
        review_comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """更新托管文档状态（审核通过 / 发布 / 归档）"""
        if doc_status not in RAGDAO.DOC_STATUSES:
            raise ValueError(f"无效的 doc_status: {doc_status}，允许值: {RAGDAO.DOC_STATUSES}")

        with session_scope(commit=True) as session:
            row = (
                session.query(RagKbManagedDoc)
                .filter(RagKbManagedDoc.doc_key == doc_key)
                .first()
            )
            if not row:
                return None
            now = datetime.now()
            row.doc_status = doc_status
            if doc_status == "published":
                row.reviewed_by = reviewed_by or row.reviewed_by
                row.review_comment = review_comment or row.review_comment
                row.reviewed_at = now
                row.published_at = now
            elif doc_status == "reviewing":
                row.review_comment = None
            return RAGDAO._managed_doc_dict(row)

    @staticmethod
    def delete_managed_doc(doc_key: str) -> bool:
        """删除托管文档"""
        with session_scope(commit=True) as session:
            result = session.execute(
                delete(RagKbManagedDoc).where(RagKbManagedDoc.doc_key == doc_key)
            )
            return result.rowcount > 0
