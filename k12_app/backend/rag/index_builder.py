"""
RAG 离线索引构建
加载 knowledge_base/ 下 Markdown 文档 → LlamaIndex 切片 + Embedding → ChromaDB

知识库 Collection（4 个）：k12_scripts / k12_sops / k12_faqs / k12_cases
画像向量 Collection（V3.1 新增）：k12_customer_profiles（由画像确认流程异步触发）
"""
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import chromadb
from llama_index.core.node_parser import SentenceSplitter

from k12_app.backend.rag.embeddings import embed_texts, get_embed_dimensions
from k12_app.backend.dao.rag_dao import RAGDAO
from k12_app.backend.dao.profile_dao import ProfileDAO
from k12_app.backend.dao.task_log_dao import TaskLogDAO
from k12_app.backend.dao.message_dao import MessageDAO
from k12_app.backend.dao.wework_account_dao import WeWorkAccountDAO

logger = logging.getLogger(__name__)

# ChromaDB 持久化路径（k12_app/chroma_data，与 knowledge_base 同处 k12_app 根目录）
CHROMA_PATH = Path(__file__).parent.parent.parent / "chroma_data"

# 知识库目录（k12_app/knowledge_base，backend 的上一级）
KB_DIR = Path(__file__).parent.parent.parent / "knowledge_base"

# Collection 映射
# V3.3 二期新增：company（集团概况）/ classes（开班计划）/ awards（荣誉资质）
KB_COLLECTION_MAP = {
    "scripts": "k12_scripts",
    "sops": "k12_sops",
    "faqs": "k12_faqs",
    "cases": "k12_cases",
    "customer_profiles": "k12_customer_profiles",
    "chat_messages": "k12_chat_messages",
    "company": "k12_company",
    "classes": "k12_classes",
    "awards": "k12_awards",
}

# 切片参数
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


def _get_chroma_client() -> chromadb.PersistentClient:
    """获取 ChromaDB 持久化客户端"""
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def _load_markdown_files(kb_name: str) -> List[Dict[str, Any]]:
    """
    加载知识库目录下的所有 .md 文件，并与已发布的托管文档（rag_kb_managed_doc）合并。

    托管文档优先级更高：同一 doc_key 时以托管文档内容为准（运营后台替换后版本递增）。

    Returns:
        [{doc_id, kb_name, file_path, title, content}, ...]
    """
    kb_path = KB_DIR / kb_name
    docs = []
    seen_keys = set()

    if kb_path.exists():
        for md_file in sorted(kb_path.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                # 提取标题（第一个 # 行）
                title = md_file.stem
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

                doc_id = f"{kb_name}/{md_file.stem}"
                seen_keys.add(doc_id)
                docs.append({
                    "doc_id": doc_id,
                    "kb_name": kb_name,
                    "file_path": str(md_file.relative_to(KB_DIR.parent)),
                    "title": title,
                    "content": content,
                })
            except Exception as e:
                logger.error(f"读取文件失败: {md_file} — {e}")

    # V3.3：合并已发布的托管文档（运营后台维护，优先于文件版本）
    try:
        from k12_app.backend.dao.rag_dao import RAGDAO
        managed = RAGDAO.get_published_managed_docs(kb_name)
        for m in managed:
            doc_key = m["doc_key"]
            # 替换同名文件版本
            docs = [d for d in docs if d["doc_id"] != doc_key]
            docs.append({
                "doc_id": doc_key,
                "kb_name": kb_name,
                "file_path": f"managed/{doc_key}",
                "title": m["title"],
                "content": m["content"],
            })
            seen_keys.add(doc_key)
    except Exception as e:
        logger.warning(f"加载托管文档失败 kb_name={kb_name}: {e}")

    # 保证顺序稳定（先文件后托管，按 doc_id 排序）
    docs.sort(key=lambda d: d["doc_id"])
    return docs


def reindex_kb(
    kb_name: str,
    triggered_by: str = "manual",
    force: bool = False,
) -> Dict[str, Any]:
    """
    重建指定知识库的向量索引。

    Args:
        kb_name: 知识库名称（scripts / sops / faqs / cases / customer_profiles）
        triggered_by: 触发者标识
        force: 是否强制全量重建（默认增量）

    Returns:
        {
            kb_name: str,
            status: "success" | "error",
            doc_count: int,
            chunk_count: int,
            elapsed_ms: int,
            error_message: str | None,
        }
    """
    if kb_name not in KB_COLLECTION_MAP:
        raise ValueError(f"无效的知识库名称: {kb_name}，允许值: {list(KB_COLLECTION_MAP.keys())}")

    collection_name = KB_COLLECTION_MAP[kb_name]
    start_time = time.time()

    try:
        # 1. 加载文档
        docs = _load_markdown_files(kb_name)
        if not docs:
            return {
                "kb_name": kb_name,
                "status": "success",
                "doc_count": 0,
                "chunk_count": 0,
                "elapsed_ms": 0,
                "error_message": None,
            }

        # 2. 分块
        splitter = SentenceSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        dim = get_embed_dimensions()

        # 3. 获取/创建 ChromaDB Collection
        client = _get_chroma_client()
        if force:
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"已删除旧 Collection: {collection_name}")
            except Exception:
                pass  # Collection 不存在则忽略

        try:
            collection = client.get_collection(name=collection_name)
            logger.info(f"使用已有 Collection: {collection_name} (count={collection.count()})")
        except Exception:
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"创建新 Collection: {collection_name}")

        # 4. 逐文档处理
        total_chunks = 0
        total_chars = 0
        all_ids = []
        all_embeddings = []
        all_metadatas = []
        all_documents = []

        for doc in docs:
            # 切片
            chunks = splitter.split_text(doc["content"])

            if not chunks:
                logger.warning(f"文档无有效内容: {doc['doc_id']}")
                continue

            # 逐 chunk 生成 Embedding
            chunk_ids = []
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{doc['doc_id']}_chunk_{i}"
                chunk_ids.append(chunk_id)
                all_ids.append(chunk_id)
                all_documents.append(chunk_text)
                all_metadatas.append({
                    "doc_id": doc["doc_id"],
                    "kb_name": kb_name,
                    "title": doc["title"],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                })

            # 批量生成 Embedding
            embeddings = embed_texts(chunks)
            all_embeddings.extend(embeddings)

            chunk_count = len(chunks)
            total_chunks += chunk_count
            total_chars += len(doc["content"])

            # 记录到 MySQL
            RAGDAO.upsert_document(
                doc_id=doc["doc_id"],
                kb_name=kb_name,
                file_path=doc["file_path"],
                title=doc["title"],
                chunk_count=chunk_count,
                char_count=len(doc["content"]),
                chroma_collection=collection_name,
                indexed_by=triggered_by,
            )

            logger.info(f"已索引: {doc['doc_id']} ({chunk_count} chunks, {len(doc['content'])} chars)")

        # 5. 写入 ChromaDB
        if all_ids:
            collection.upsert(
                ids=all_ids,
                embeddings=all_embeddings,
                metadatas=all_metadatas,
                documents=all_documents,
            )
            logger.info(f"ChromaDB 写入完成: {collection_name} ({len(all_ids)} vectors)")

        # 5.4 清理失效向量：删除不再存在于源文档中的旧 chunk（撤稿/删除文档后不残留旧内容）
        try:
            if collection and all_ids:
                current_doc_ids = {d["doc_id"] for d in docs}
                existing = collection.get(where={"kb_name": kb_name}, include=[])
                stale_ids = [
                    cid for cid in (existing.get("ids") or [])
                    if cid.rsplit("_chunk_", 1)[0] not in current_doc_ids
                ]
                if stale_ids:
                    # 分批删除，避免一次删除过多
                    for i in range(0, len(stale_ids), 500):
                        collection.delete(ids=stale_ids[i:i + 500])
                    logger.info(f"已清理 {len(stale_ids)} 条失效向量: {collection_name}")
        except Exception as e:
            logger.warning(f"清理失效向量失败: {e}")

        # 5.5 V3.3：失效检索缓存，保证"一键发布"立即生效（无需重启）
        try:
            from k12_app.backend.rag.retriever import invalidate_collection_cache
            invalidate_collection_cache(kb_name)
        except Exception as e:
            logger.warning(f"失效检索缓存失败: {e}")

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 6. 记录索引日志
        RAGDAO.log_index_build(
            kb_name=kb_name,
            doc_count=len(docs),
            chunk_count=total_chunks,
            elapsed_ms=elapsed_ms,
            status="success",
            triggered_by=triggered_by,
        )

        return {
            "kb_name": kb_name,
            "status": "success",
            "doc_count": len(docs),
            "chunk_count": total_chunks,
            "elapsed_ms": elapsed_ms,
            "error_message": None,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        logger.error(f"索引构建失败: {kb_name} — {error_msg}", exc_info=True)

        RAGDAO.log_index_build(
            kb_name=kb_name,
            doc_count=0,
            chunk_count=0,
            elapsed_ms=elapsed_ms,
            status="error",
            triggered_by=triggered_by,
            error_message=error_msg,
        )

        return {
            "kb_name": kb_name,
            "status": "error",
            "doc_count": 0,
            "chunk_count": 0,
            "elapsed_ms": elapsed_ms,
            "error_message": error_msg,
        }


def reindex_all(triggered_by: str = "manual", force: bool = False) -> Dict[str, Any]:
    """重建全部 7 个知识库的索引（V3.3：含 company/classes/awards）"""
    results = {}
    for kb_name in ["scripts", "sops", "faqs", "cases", "company", "classes", "awards"]:
        results[kb_name] = reindex_kb(kb_name, triggered_by=triggered_by, force=force)
    return results


def ensure_indexes_initialized() -> Dict[str, Any]:
    """
    启动时自动补建缺失的向量索引（问题 3 修复）。

    遍历所有 Collection，仅当集合不存在或为空 且 存在可索引的源数据时补建：
    - chat_messages：全量窗口 days=90（覆盖种子数据所在时间窗），不删旧集合
    - customer_profiles：由已确认画像构建
    - 其余知识库：从 markdown 文件 / 已发布托管文档构建

    全程 best-effort：任一集合失败仅告警，绝不影响服务启动。
    已非空的集合跳过（后续增量由 flush_chat_conversation / 手动 reindex 维护）。

    Returns:
        {kb_name: reindex 结果}，被跳过的集合不在结果中
    """
    results: Dict[str, Any] = {}
    client = _get_chroma_client()
    for kb_name, collection_name in KB_COLLECTION_MAP.items():
        try:
            collection = client.get_collection(name=collection_name)
            if collection.count() > 0:
                continue  # 已有索引，交给增量同步
        except Exception:
            pass  # 集合不存在 → 需要补建

        try:
            if kb_name == "chat_messages":
                results[kb_name] = reindex_chat_messages(
                    days=90, limit=5000, triggered_by="startup", incremental=False,
                )
            elif kb_name == "customer_profiles":
                results[kb_name] = reindex_profiles(triggered_by="startup")
            else:
                results[kb_name] = reindex_kb(kb_name, triggered_by="startup")
            logger.info(f"启动自动补建索引 {kb_name}: {results[kb_name].get('status')}, "
                        f"doc_count={results[kb_name].get('doc_count')}")
        except Exception as e:
            logger.warning(f"启动自动补建索引 {kb_name} 失败（不影响服务）: {e}")
            results[kb_name] = {"kb_name": kb_name, "status": "error", "error_message": str(e)}
    return results


def _build_profile_text(profile_id: int) -> Optional[str]:
    """将画像字段项拼接为用于向量化的文本"""
    items = ProfileDAO.get_items(profile_id)
    if not items:
        return None
    text_parts = []
    for item in items:
        name = (item.get("item_name") or "").strip()
        value = (item.get("item_value") or "").strip()
        if name and value:
            text_parts.append(f"{name}: {value}")
    return "\n".join(text_parts) if text_parts else None


def reindex_profiles(triggered_by: str = "manual", force: bool = False) -> Dict[str, Any]:
    """
    重建画像向量索引（V3.1）。
    从 ai_customer_profile 表中读取已确认的画像（embedding_status=pending/stale），
    提取 profile_item 文本拼接为画像摘要，生成 1024 维向量写入 k12_customer_profiles Collection。
    索引完成后将 embedding_status 更新为 indexed。
    """
    kb_name = "customer_profiles"
    collection_name = KB_COLLECTION_MAP[kb_name]
    start_time = time.time()

    try:
        # 1. 查询待索引的已确认画像（ORM：ProfileDAO）
        profiles = ProfileDAO.get_indexable_profiles()

        if not profiles:
            return {
                "kb_name": kb_name,
                "status": "success",
                "doc_count": 0,
                "chunk_count": 0,
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "error_message": None,
            }

        # 2. 获取 / 重建 ChromaDB Collection
        client = _get_chroma_client()
        if force:
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"已删除旧 Collection: {collection_name}")
            except Exception:
                pass

        try:
            collection = client.get_collection(name=collection_name)
            logger.info(f"使用已有 Collection: {collection_name} (count={collection.count()})")
        except Exception:
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"创建新 Collection: {collection_name}")

        # 3. 逐画像处理
        all_ids = []
        all_embeddings = []
        all_metadatas = []
        all_documents = []
        indexed_ids = []
        error_count = 0

        for profile in profiles:
            profile_id = profile["id"]
            external_id = profile["external_id"]

            try:
                profile_text = _build_profile_text(profile_id)
                if not profile_text:
                    logger.warning(f"画像无有效字段项，跳过: profile_id={profile_id}")
                    continue

                embeddings = embed_texts([profile_text])
                if not embeddings:
                    continue

                chunk_id = f"profile/{profile_id}"

                all_ids.append(chunk_id)
                all_embeddings.extend(embeddings)
                all_metadatas.append({
                    "external_id": external_id,
                    "profile_id": profile_id,
                    "follow_user_id": profile["follow_user_id"] or "",
                    "wework_account_id": profile["wework_account_id"] or "",
                })
                all_documents.append(profile_text)
                indexed_ids.append(profile_id)

            except Exception as e:
                error_count += 1
                logger.error(f"画像索引失败 profile_id={profile_id}: {e}")

        # 4. 写入 ChromaDB
        total_chunks = len(all_ids)
        if all_ids:
            collection.upsert(
                ids=all_ids,
                embeddings=all_embeddings,
                metadatas=all_metadatas,
                documents=all_documents,
            )
            logger.info(f"ChromaDB 写入完成: {collection_name} ({total_chunks} vectors)")

        # 4.5 V3.3：失效检索缓存（画像重建后立即生效）
        try:
            from k12_app.backend.rag.retriever import invalidate_collection_cache
            invalidate_collection_cache(kb_name)
        except Exception as e:
            logger.warning(f"失效检索缓存失败: {e}")

        # 5. 更新 embedding_status 为 indexed
        if indexed_ids:
            updated = ProfileDAO.batch_update_embedding_status(indexed_ids, "indexed")
            logger.info(f"embedding_status 更新: {updated}/{len(indexed_ids)} 条 → indexed")

        elapsed_ms = int((time.time() - start_time) * 1000)
        status = "success" if error_count == 0 else "partial"

        # 6. 记录索引日志
        RAGDAO.log_index_build(
            kb_name=kb_name,
            doc_count=len(profiles),
            chunk_count=total_chunks,
            elapsed_ms=elapsed_ms,
            status=status,
            triggered_by=triggered_by,
            error_message=f"{error_count} 条失败" if error_count > 0 else None,
        )

        return {
            "kb_name": kb_name,
            "status": status,
            "doc_count": len(profiles),
            "chunk_count": total_chunks,
            "elapsed_ms": elapsed_ms,
            "error_message": f"{error_count} 条画像索引失败" if error_count > 0 else None,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        logger.error(f"画像索引构建失败: {error_msg}", exc_info=True)

        try:
            RAGDAO.log_index_build(
                kb_name=kb_name,
                doc_count=0,
                chunk_count=0,
                elapsed_ms=elapsed_ms,
                status="error",
                triggered_by=triggered_by,
                error_message=error_msg,
            )
        except Exception:
            pass

        return {
            "kb_name": kb_name,
            "status": "error",
            "doc_count": 0,
            "chunk_count": 0,
            "elapsed_ms": elapsed_ms,
            "error_message": error_msg,
        }


def reindex_chat_messages(
    days: int = 7,
    limit: int = 1000,
    triggered_by: str = "manual",
    force: bool = False,
    adopted_only: bool = False,
    incremental: bool = True,
) -> Dict[str, Any]:
    """
    重建聊天记录向量索引。

    从 msg_wxqy_chat 表中读取文本消息，逐条生成 1024 维向量，
    写入 k12_chat_messages Collection。

    支持三种模式：
    - 全量模式 (force=True)：删除旧 Collection 后全量索引
    - 增量模式 (incremental=True，默认)：仅索引上次同步之后的新消息
    - 采纳模式 (adopted_only=True)：仅索引被 AI 采纳过的回复对应的会话消息

    Args:
        days: 索引最近 N 天的聊天记录（全量模式时生效）
        limit: 单次最大索引条数
        triggered_by: 触发者标识
        force: 是否强制全量重建
        adopted_only: 仅索引被采纳的会话消息
        incremental: 增量模式（仅索引上次同步后的新消息）

    Returns:
        {kb_name, status, doc_count, chunk_count, elapsed_ms, error_message, mode}
    """
    kb_name = "chat_messages"
    collection_name = KB_COLLECTION_MAP[kb_name]
    start_time = time.time()
    mode = "full" if force else ("adopted_incr" if adopted_only else "incr" if incremental else "batch")

    try:
        # === 增量模式：获取上次同步时间 ===
        last_sync_time = None
        if incremental and not force:
            last_log = RAGDAO.get_last_index_log(kb_name)
            if last_log and last_log.get("status") == "success" and last_log.get("created_at"):
                last_sync_time = last_log["created_at"]
                logger.info(f"增量同步，上次同步时间: {last_sync_time}")

        # === 采纳模式：获取被采纳会话的 external_id 列表 ===
        adopted_external_ids = None
        if adopted_only:
            adopted_external_ids = TaskLogDAO.get_adopted_external_ids(
                after_time=last_sync_time,
                limit=200,
            )

            if not adopted_external_ids:
                return {
                    "kb_name": kb_name,
                    "status": "success",
                    "doc_count": 0,
                    "chunk_count": 0,
                    "elapsed_ms": int((time.time() - start_time) * 1000),
                    "error_message": "无新的被采纳会话",
                    "mode": mode,
                }
            logger.info(f"采纳模式: {len(adopted_external_ids)} 个被采纳客户")

        # === 1. 查询待索引的文本消息（ORM：MessageDAO） ===
        messages = []
        if adopted_only and adopted_external_ids:
            # 采纳模式：只查被采纳客户的聊天记录
            messages = MessageDAO.get_messages_for_reindex(
                external_ids=adopted_external_ids,
                after_time=last_sync_time,
                limit=limit,
            )
        else:
            # 全量 / 普通增量模式
            end_date = datetime.now().date()
            if incremental and last_sync_time and not force:
                start_date = last_sync_time.date()
            else:
                start_date = end_date - timedelta(days=days)

            # 单窗口消息可能超过单次 limit（如单日 >1000 条），分页取全，
            # 避免更早消息被挤出且游标仍前进导致永不被索引
            page_size = limit or 1000
            offset = 0
            while True:
                page = MessageDAO.get_messages_for_reindex(
                    start_date=start_date,
                    end_date=end_date,
                    limit=page_size,
                    offset=offset,
                )
                if not page:
                    break
                messages.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size

        if not messages:
            return {
                "kb_name": kb_name,
                "status": "success",
                "doc_count": 0,
                "chunk_count": 0,
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "error_message": "无新消息需要索引",
                "mode": mode,
            }

        # 2. 获取 / 重建 ChromaDB Collection
        client = _get_chroma_client()
        if force:
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"已删除旧 Collection: {collection_name}")
            except Exception:
                pass

        try:
            collection = client.get_collection(name=collection_name)
            logger.info(f"使用已有 Collection: {collection_name} (count={collection.count()})")
        except Exception:
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"创建新 Collection: {collection_name}")

        # 3. 逐条消息生成 Embedding
        all_ids = []
        all_embeddings = []
        all_metadatas = []
        all_documents = []
        indexed_count = 0
        skipped_count = 0
        dup_count = 0
        seen_ids = set()

        # 批量收集文本后统一调用 embed_texts（每批 20 条）
        batch_texts = []
        batch_msgs = []

        for msg in messages:
            msg_id = msg["msg_id"]
            chunk_id = f"chat/{msg_id}"

            # 跳过重复 msg_id（同一消息可能出现在不同分区）
            if chunk_id in seen_ids:
                dup_count += 1
                continue
            seen_ids.add(chunk_id)

            content = (msg["content"] or "").strip()
            if len(content) < 2:
                skipped_count += 1
                continue

            batch_texts.append(content)
            batch_msgs.append(msg)

            if len(batch_texts) >= 20:
                _flush_chat_batch(
                    batch_texts, batch_msgs,
                    all_ids, all_embeddings, all_metadatas, all_documents,
                )
                indexed_count += len(batch_texts)
                batch_texts = []
                batch_msgs = []

        # 处理最后一批
        if batch_texts:
            _flush_chat_batch(
                batch_texts, batch_msgs,
                all_ids, all_embeddings, all_metadatas, all_documents,
            )
            indexed_count += len(batch_texts)

        # 4. 写入 ChromaDB
        total_chunks = len(all_ids)
        if all_ids:
            collection.upsert(
                ids=all_ids,
                embeddings=all_embeddings,
                metadatas=all_metadatas,
                documents=all_documents,
            )
            logger.info(f"ChromaDB 写入完成: {collection_name} ({total_chunks} vectors)")

        # 4.5 V3.3：失效检索缓存（聊天记录重建后立即生效）
        try:
            from k12_app.backend.rag.retriever import invalidate_collection_cache
            invalidate_collection_cache(kb_name)
        except Exception as e:
            logger.warning(f"失效检索缓存失败: {e}")

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 5. 记录索引日志
        skip_info_parts = []
        if dup_count > 0:
            skip_info_parts.append(f"去重 {dup_count} 条")
        if skipped_count > 0:
            skip_info_parts.append(f"跳过 {skipped_count} 条过短消息")
        skip_info = "; ".join(skip_info_parts) if skip_info_parts else None

        RAGDAO.log_index_build(
            kb_name=kb_name,
            doc_count=len(messages),
            chunk_count=total_chunks,
            elapsed_ms=elapsed_ms,
            status="success",
            triggered_by=triggered_by,
            error_message=skip_info,
        )

        return {
            "kb_name": kb_name,
            "status": "success",
            "doc_count": len(messages),
            "chunk_count": total_chunks,
            "elapsed_ms": elapsed_ms,
            "error_message": skip_info,
            "mode": mode,
            "adopted_customers": len(adopted_external_ids) if adopted_external_ids else None,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        logger.error(f"聊天记录索引构建失败: {error_msg}", exc_info=True)

        try:
            RAGDAO.log_index_build(
                kb_name=kb_name,
                doc_count=0,
                chunk_count=0,
                elapsed_ms=elapsed_ms,
                status="error",
                triggered_by=triggered_by,
                error_message=error_msg,
            )
        except Exception:
            pass

        return {
            "kb_name": kb_name,
            "status": "error",
            "doc_count": 0,
            "chunk_count": 0,
            "elapsed_ms": elapsed_ms,
            "error_message": error_msg,
        }


def _flush_chat_batch(
    texts: List[str],
    msgs: List[Dict[str, Any]],
    all_ids: List[str],
    all_embeddings: List[List[float]],
    all_metadatas: List[Dict[str, Any]],
    all_documents: List[str],
) -> None:
    """批量生成 Embedding 并追加到结果列表"""
    if not texts:
        return
    embeddings = embed_texts(texts)
    for i, msg in enumerate(msgs):
        chunk_id = f"chat/{msg['msg_id']}"
        all_ids.append(chunk_id)
        if i < len(embeddings):
            all_embeddings.append(embeddings[i])
        all_metadatas.append({
            "msg_id": msg["msg_id"],
            "external_id": msg["external_id"],
            "user_id": msg["user_id"],
            "wework_account_id": msg["wework_account_id"],
            "sender_name": msg.get("sender_name") or "",
            "msg_type": msg["msg_type"],
            "send_time": msg["send_time"].isoformat() if hasattr(msg["send_time"], "isoformat") else str(msg["send_time"]),
            "msg_date": msg["msg_date"].isoformat() if hasattr(msg["msg_date"], "isoformat") else str(msg["msg_date"]),
        })
        all_documents.append(texts[i])


def flush_chat_conversation(
    user_id: str,
    external_id: str,
    keep_recent: int = 10,
) -> Dict[str, Any]:
    """
    将单个会话（顾问 + 客户）的聊天记录转存到向量库，然后删除 MySQL 中更早的记录。

    用于聊天缓冲区的自动归档：当某会话累积到阈值后调用，
    避免 msg_wxqy_chat 无限增长，同时保留向量化历史供 AI 检索。
    归档时保留最近 keep_recent 条在 MySQL，避免清空近期对话上下文。
    """
    from k12_app.backend.dao.message_dao import MessageDAO

    collection_name = KB_COLLECTION_MAP["chat_messages"]
    start_time = time.time()

    messages = MessageDAO.get_chat_messages_for_flush(user_id, external_id)
    if not messages:
        return {
            "kb_name": "chat_messages",
            "status": "empty",
            "chunk_count": 0,
            "deleted": 0,
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    # 保留最近 keep_recent 条在 MySQL，只归档更早的消息
    if len(messages) <= keep_recent:
        return {
            "kb_name": "chat_messages",
            "status": "below_keep",
            "chunk_count": 0,
            "deleted": 0,
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    to_archive = messages[:-keep_recent]
    archive_ids = [m["msg_id"] for m in to_archive]

    client = _get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        collection = client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    all_ids: List[str] = []
    all_embeddings: List[List[float]] = []
    all_metadatas: List[Dict[str, Any]] = []
    all_documents: List[str] = []
    batch_texts: List[str] = []
    batch_msgs: List[Dict[str, Any]] = []
    seen_ids = set()

    for msg in to_archive:
        chunk_id = f"chat/{msg['msg_id']}"
        if chunk_id in seen_ids:
            continue
        content = (msg["content"] or "").strip()
        if len(content) < 2:
            continue
        seen_ids.add(chunk_id)
        batch_texts.append(content)
        batch_msgs.append(msg)
        if len(batch_texts) >= 20:
            _flush_chat_batch(
                batch_texts, batch_msgs,
                all_ids, all_embeddings, all_metadatas, all_documents,
            )
            batch_texts = []
            batch_msgs = []

    if batch_texts:
        _flush_chat_batch(
            batch_texts, batch_msgs,
            all_ids, all_embeddings, all_metadatas, all_documents,
        )

    if all_ids:
        collection.upsert(
            ids=all_ids,
            embeddings=all_embeddings,
            metadatas=all_metadatas,
            documents=all_documents,
        )

    # V3.3：失效检索缓存（会话归档后立即生效）
    try:
        from k12_app.backend.rag.retriever import invalidate_collection_cache
        invalidate_collection_cache("chat_messages")
    except Exception as e:
        logger.warning(f"失效检索缓存失败: {e}")

    deleted = MessageDAO.delete_chat_messages_by_msg_ids(archive_ids)

    logger.info(
        f"会话归档完成: user={user_id}, external_id={external_id}, "
        f"vectors={len(all_ids)}, deleted={deleted}, kept={min(keep_recent, len(messages))}"
    )
    return {
        "kb_name": "chat_messages",
        "status": "success",
        "chunk_count": len(all_ids),
        "deleted": deleted,
        "kept": min(keep_recent, len(messages)),
        "elapsed_ms": int((time.time() - start_time) * 1000),
    }


def _get_region_account_ids(wework_account_id: Optional[str]) -> List[str]:
    """查询与给定企微账户同区域的全部账户 ID（用于向量库 region 范围删除）"""
    if not wework_account_id:
        return []
    try:
        return WeWorkAccountDAO.get_same_region_account_ids(wework_account_id)
    except Exception as e:
        logger.warning(f"查询同区域账户失败: {e}")
        return []


def delete_chat_vectors(
    external_id: str,
    user_id: Optional[str] = None,
    wework_account_id: Optional[str] = None,
    data_scope: str = "self",
) -> int:
    """删除向量库中该客户的聊天记录向量，范围与 MySQL 删除保持一致。

    清空会话时不仅清 MySQL 表，还要清 ChromaDB 里已归档的历史向量，
    否则 AI（自由对话 / 回复建议 / 模拟家长）仍能从向量库检索到旧记忆。
    """
    collection_name = KB_COLLECTION_MAP["chat_messages"]
    client = _get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return 0

    where: Dict[str, Any] = {"external_id": external_id}
    if data_scope == "self":
        # V3.3.2：与 MySQL 删除一致——按客户归属删除，不再限定消息的 user_id，
        # 否则其它操作人（如超管）代发/模拟家长的消息向量删不掉，清空后 AI 仍"记得"
        if not wework_account_id:
            return 0
        where = {
            "$and": [
                {"external_id": external_id},
                {"wework_account_id": wework_account_id},
            ]
        }
    elif data_scope == "region":
        region_account_ids = _get_region_account_ids(wework_account_id)
        if not region_account_ids:
            return 0
        where = {
            "$and": [
                {"external_id": external_id},
                {"wework_account_id": {"$in": region_account_ids}},
            ]
        }
    # data_scope == "all": 仅按 external_id 过滤

    try:
        collection.delete(where=where)
        logger.info(f"向量库聊天记录已删除: external_id={external_id}, scope={data_scope}")
        return 1
    except Exception as e:
        logger.warning(f"删除向量库聊天记录失败: external_id={external_id}, err={e}")
        return 0


def delete_profile_vectors(external_id: str) -> int:
    """删除向量库中该客户的画像向量（V3.3.2：「清空重置」彻底清除 AI 记忆用）。

    k12_customer_profiles 集合按 external_id 过滤删除，
    否则相似客户检索仍能命中已删除画像的客户。
    """
    collection_name = KB_COLLECTION_MAP["customer_profiles"]
    client = _get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return 0
    try:
        collection.delete(where={"external_id": external_id})
        logger.info(f"向量库画像已删除: external_id={external_id}")
        try:
            from k12_app.backend.rag.retriever import invalidate_collection_cache
            invalidate_collection_cache("customer_profiles")
        except Exception as e:
            logger.warning(f"失效检索缓存失败: {e}")
        return 1
    except Exception as e:
        logger.warning(f"删除向量库画像失败: external_id={external_id}, err={e}")
        return 0


def get_reindex_status() -> Dict[str, Any]:
    """
    获取所有知识库的索引状态。

    以 ChromaDB 实际 Collection 内容为准（doc_count/total_chars），
    last_indexed_at 取最近一次成功索引日志时间；无日志时回退到文档表时间。
    修复：原实现读 rag_kb_document 表，与 ChromaDB 实际数据不一致（如 chat_messages 仅由
    flush_chat_conversation 写入但未登记文档表），导致管理后台显示全部为 0。
    """
    client = _get_chroma_client()
    result: Dict[str, Any] = {}

    for kb_name, collection_name in KB_COLLECTION_MAP.items():
        # 1. ChromaDB 实际计数
        doc_count = 0
        total_chars = 0
        try:
            collection = client.get_collection(name=collection_name)
            doc_count = collection.count()
            if doc_count > 0:
                # 采样统计字符数（最多取 200 条，避免大集合全量加载）
                sample = collection.get(limit=min(doc_count, 200))
                docs = sample.get("documents") or []
                total_chars = sum(len(d or "") for d in docs)
        except Exception:
            doc_count = 0

        # 2. 最近一次成功索引时间（优先日志表，回退文档表）
        last_indexed_at = None
        try:
            last_log = RAGDAO.get_last_index_log(kb_name)
            if last_log and last_log.get("created_at"):
                last_indexed_at = last_log["created_at"]
        except Exception:
            last_log = None

        if last_indexed_at is None:
            try:
                stats = RAGDAO.get_kb_stats(kb_name)
                last_indexed_at = stats.get("last_indexed_at")
            except Exception:
                last_indexed_at = None

        result[kb_name] = {
            "doc_count": doc_count,
            "total_chunks": doc_count,
            "total_chars": total_chars,
            "last_indexed_at": last_indexed_at,
        }
        # 问题 3 修复：空集合给出明确提示（前端可展示，字段新增不破坏既有响应）
        if doc_count == 0:
            result[kb_name]["hint"] = (
                "集合为空，未构建索引；可手动触发重建，或重启服务自动补建"
            )

    return result
