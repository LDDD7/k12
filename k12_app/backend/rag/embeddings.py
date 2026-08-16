"""
Embedding 模型配置
模型：阿里云 DashScope text-embedding-v3（1024 维）
使用 OpenAI 兼容接口直接调用（绕过 llama-index 模型名校验）
"""
from typing import List

from openai import OpenAI

from k12_app.backend.config import settings

DASHSCOPE_API_KEY = settings.DASHSCOPE_API_KEY
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBED_MODEL_NAME = "text-embedding-v3"
EMBED_DIMENSIONS = 1024

if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY 未配置，请检查 .env 文件")

# 全局复用客户端
_embed_client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
)


def get_embed_dimensions() -> int:
    """返回向量维度"""
    return EMBED_DIMENSIONS


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量生成文本 Embedding（每批 10 条，DashScope text-embedding-v3 API 限制 batch ≤ 10）"""
    if not texts:
        return []
    batch_size = 10
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = _embed_client.embeddings.create(
            model=EMBED_MODEL_NAME,
            input=batch,
            dimensions=EMBED_DIMENSIONS,
            encoding_format="float",
        )
        all_embeddings.extend([d.embedding for d in resp.data])
    return all_embeddings


def embed_query(text: str) -> List[float]:
    """单条查询 Embedding"""
    resp = _embed_client.embeddings.create(
        model=EMBED_MODEL_NAME,
        input=[text],
        dimensions=EMBED_DIMENSIONS,
        encoding_format="float",
    )
    return resp.data[0].embedding
