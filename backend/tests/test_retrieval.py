import json

from app.core.config import Settings
from app.schemas.dream import DreamSymbols
from app.services.aliyun import EmbeddingBatch, RerankBatch, RerankItem
from app.services.knowledge_index import KnowledgeIndex, KnowledgeChunk
from app.services.retrieval import DreamRetrievalService, RetrievalExpansion


class FakeModels:
    def __init__(self):
        self.chat_user = None
        self.rerank_documents = None

    def chat_json(self, _model, _system, user, schema):
        self.chat_user = json.loads(user)
        return schema(english_queries=["deer in a forest"], english_keywords=["deer", "forest"])

    def embed_texts(self, texts):
        assert texts == ["deer in a forest"]
        return EmbeddingBatch(vectors=[[1.0] + [0.0] * 63],
                                      model="text-embedding-v4", total_tokens=4)

    def rerank_texts(self, query, documents, top_n):
        assert query == "deer in a forest"
        self.rerank_documents = documents
        assert top_n == 1
        return RerankBatch(results=[RerankItem(index=0, relevance_score=0.88)],
                           model="qwen3-rerank", total_tokens=10)


def test_retrieval_uses_confirmed_symbols_and_preserves_source(tmp_path):
    settings = Settings(
        _env_file=None, DREAMCARD_MODEL_MODE="aliyun", DASHSCOPE_API_KEY="test",
        DREAMCARD_EMBEDDING_DIMENSIONS=64, DREAMCARD_KNOWLEDGE_INDEX_PATH=tmp_path / "index.sqlite3",
    )
    chunk = KnowledgeChunk(
        source_id="miller:deer", book="Book", author="Author", translator=None,
        chapter="Deer", language="en", original_text="A deer crossed the forest.",
        source_line_start=10, source_line_end=12, source_file_sha256="a" * 64,
        source_url="https://example.com", rights_status="candidate", verified=False,
        quality_flags=(),
    )
    with KnowledgeIndex(settings.knowledge_index_path, settings.embedding_model, 64) as index:
        index.add_batch([chunk], [[1.0] + [0.0] * 63], 1)

    models = FakeModels()
    service = DreamRetrievalService(settings, models=models)
    result = service.retrieve(
        DreamSymbols(
            scenes=["森林"],
            characters=["鹿"],
            emotions=["平静"],
            reality_context=["最近工作上要向领导汇报项目"],
        ),
        candidate_limit=1, final_limit=1,
    )
    assert models.chat_user["confirmed_symbols"]["characters"] == ["鹿"]
    assert "reality_context" not in models.chat_user["confirmed_symbols"]
    assert "dream_text" not in models.chat_user
    assert result.passages[0].source_id == "miller:deer"
    assert result.passages[0].source_line_start == 10
    assert result.passages[0].rerank_score == 0.88
    assert result.embedding_tokens == 4 and result.rerank_tokens == 10


def test_expansion_deduplicates_case_insensitively():
    expansion = RetrievalExpansion(
        english_queries=[" Deer ", "deer"],
        english_keywords=["Forest", " forest "],
    )
    assert expansion.english_queries == ["Deer"]
    assert expansion.english_keywords == ["Forest"]
