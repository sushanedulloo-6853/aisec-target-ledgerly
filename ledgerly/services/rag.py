"""LlamaIndex vector index over ingested invoices, receipts and contracts."""

import threading
from pathlib import Path

from llama_index.core import Document, PromptTemplate, StorageContext, VectorStoreIndex, load_index_from_storage
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from ledgerly import llm
from ledgerly.config import settings
from ledgerly.db import connect

_index: VectorStoreIndex | None = None
_lock = threading.RLock()

QA_PROMPT = PromptTemplate(
    "You are Ledgerly's document assistant for {business_name}. Use the documents below to answer.\n"
    "---------------------\n{context_str}\n---------------------\n"
    "Question: {query_str}\nAnswer:"
)


def _to_document(row) -> Document:
    return Document(
        doc_id=f"doc-{row['id']}",
        text=row["text_content"] or "",
        metadata={
            "document_id": row["id"],
            "business_id": row["business_id"],
            "filename": row["filename"] or "",
            "doc_type": row["doc_type"] or "",
            "vendor_name": row["vendor_name"] or "",
        },
    )


def _build_from_db() -> VectorStoreIndex:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM documents WHERE text_content IS NOT NULL").fetchall()
        index = VectorStoreIndex.from_documents([_to_document(r) for r in rows], embed_model=llm.get_embed_model())
        conn.execute("UPDATE documents SET indexed = 1 WHERE text_content IS NOT NULL")
        conn.commit()
    finally:
        conn.close()
    return index


def get_index() -> VectorStoreIndex:
    global _index
    with _lock:
        if _index is None:
            persist_dir = Path(settings.INDEX_DIR)
            if (persist_dir / "docstore.json").exists():
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                _index = load_index_from_storage(storage, embed_model=llm.get_embed_model())
            else:
                _index = _build_from_db()
                _persist()
        return _index


def _persist() -> None:
    Path(settings.INDEX_DIR).mkdir(parents=True, exist_ok=True)
    _index.storage_context.persist(persist_dir=settings.INDEX_DIR)


def reset_index() -> None:
    global _index
    with _lock:
        _index = None


def add_document(row) -> None:
    with _lock:
        index = get_index()
        index.insert(_to_document(row))
        _persist()


def _tenant_filter(business_id: int) -> MetadataFilters:
    return MetadataFilters(filters=[ExactMatchFilter(key="business_id", value=business_id)])


def search(business_id: int, query: str, top_k: int = 4) -> list[dict]:
    retriever = get_index().as_retriever(similarity_top_k=top_k, filters=_tenant_filter(business_id))
    return [
        {"document_id": n.metadata.get("document_id"), "filename": n.metadata.get("filename"), "text": n.get_content()}
        for n in retriever.retrieve(query)
    ]


def ask(business_id: int, business_name: str, question: str) -> dict:
    engine = get_index().as_query_engine(
        llm=llm.get_llama_llm(),
        similarity_top_k=4,
        filters=_tenant_filter(business_id),
        text_qa_template=QA_PROMPT.partial_format(business_name=business_name),
    )
    result = engine.query(question)
    return {
        "answer": str(result),
        "sources": [
            {
                "document_id": n.metadata.get("document_id"),
                "filename": n.metadata.get("filename"),
                "snippet": n.get_content()[:300],
                "score": n.score,
            }
            for n in result.source_nodes
        ],
    }
