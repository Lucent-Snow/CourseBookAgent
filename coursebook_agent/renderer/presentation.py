"""Student-facing book projection; internal evidence stays on stored models."""
import re

_INTERNAL_KEYS = {'warnings', 'quality_notes', 'continuity_notes', 'source_index', 'source_ranges', 'source_ref', 'source_labels', 'source_revision_ids', 'source_chunk_ids', 'time_links', 'transcript_links', 'context_fingerprint', 'quality_metrics', 'evidence_from_class'}
_UNRESOLVED = re.compile(r'待核(?:查|实|对)?|须核对|需核对|(?:须|需|需要|应)[^。！？\n]{0,16}(?:原课件|原资料)[^。！？\n]{0,8}核对|出自原资料|无法确认|不能确认|不确定[:：]|原课件此处有图')
_META = re.compile(r'[（(](?:来源|出自原资料|据口述重写)[^）)]*[）)]|\[(?:来源|据口述重写)[^\]]*\]')


def reader_text(text: str) -> str:
    text = _META.sub('', text)
    text = re.sub(r'据口述(?:重写|重建)?|来源与核对状态', '', text)
    text = re.sub(r'[、，]([）)])', r'\1', text)
    text = text.replace('编写上我们坚持三条原则', '编写上注重术语统一与完整验算')
    text = re.sub(r'(?:来源|出自)\s*rev_[a-z0-9]+[^。\n]*', '', text)
    # Omit the unresolved claim, not just its label; keep clear neighboring claims.
    return ''.join(part for part in re.findall(r'[^。！？\n]+[。！？\n]*|[。！？\n]+', text) if not _UNRESOLVED.search(part)).strip()


def reader_projection(value):
    if isinstance(value, str):
        return reader_text(value)
    if isinstance(value, list):
        return [item for original in value if (item := reader_projection(original)) not in ('', None)]
    if isinstance(value, dict):
        return {key: reader_projection(item) for key, item in value.items() if key not in _INTERNAL_KEYS and not re.search(r"来源|核对状态|^source_|^evidence_", key)}
    return value
