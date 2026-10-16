from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, asdict

from srw.kernel.errors import V1InvariantError

_HEADER_ALIASES = {
    'channel': {'channel','source','source_channel','渠道','来源渠道','招聘渠道'},
    'period': {'period','month','quarter','期间','周期','月份','季度'},
    'sourced': {'sourced','source_count','candidates','候选人数','来源数','入库数'},
    'contacted': {'contacted','contact_count','已联系','联系数'},
    'screened': {'screened','screen_count','已筛选','筛选数','初筛数'},
    'interviewed': {'interviewed','interview_count','已面试','面试数'},
    'offered': {'offered','offer_count','已offer','offer数','发放offer数'},
    'hired': {'hired','hire_count','已录用','录用数','入职数'},
    'spend_cny': {'spend_cny','cost_cny','spend','cost','成本','花费','渠道成本'},
    'human_confirmed': {'human_confirmed','confirmed','人工确认','已确认'},
    'notes': {'notes','note','备注','说明'},
}
_REQUIRED = ('channel','sourced','contacted','screened','interviewed','offered','hired')


def _canon(value: str) -> str:
    return value.strip().lower().replace(' ', '_')


def _mapping(headers: list[str]) -> dict[str, str]:
    reverse = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            reverse[_canon(alias)] = canonical
    out = {}
    for h in headers:
        key = reverse.get(_canon(h))
        if key and key not in out:
            out[key] = h
    missing = [x for x in _REQUIRED if x not in out]
    if missing:
        raise V1InvariantError('CSV missing required columns: ' + ', '.join(missing))
    return out


def _integer(raw: str, field: str, row_no: int) -> int:
    text = (raw or '').strip()
    if text == '': return 0
    try:
        if any(c in text for c in '.eE'):
            value = float(text)
            if not value.is_integer(): raise ValueError
            return int(value)
        return int(text)
    except Exception as exc:
        raise ValueError(f'row {row_no}: {field} must be an integer') from exc


def _number(raw: str, field: str, row_no: int) -> float:
    text = (raw or '').strip()
    if text == '': return 0.0
    try: return float(text.replace(',',''))
    except Exception as exc: raise ValueError(f'row {row_no}: {field} must be numeric') from exc


def _boolean(raw: str) -> bool:
    return (raw or '').strip().lower() in {'1','true','yes','y','是','已确认','confirmed'}


def csv_digest(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def preview_csv(content: str) -> dict:
    if not isinstance(content, str) or not content.strip():
        raise V1InvariantError('CSV content is empty')
    if len(content.encode('utf-8')) > 5 * 1024 * 1024:
        raise V1InvariantError('CSV import is limited to 5 MiB')
    # UTF-8 BOM is common for Excel-exported CSV files.
    normalized = content.lstrip('\ufeff')
    sample = normalized[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(normalized), dialect=dialect)
    if not reader.fieldnames:
        raise V1InvariantError('CSV has no header row')
    mapping = _mapping([str(x) for x in reader.fieldnames])
    rows, errors = [], []
    for idx, raw in enumerate(reader, start=2):
        if not any((v or '').strip() for v in raw.values()):
            continue
        try:
            row = {
                'row_number': idx,
                'channel': (raw.get(mapping['channel']) or '').strip(),
                'period': (raw.get(mapping.get('period','')) or '').strip() if mapping.get('period') else '',
                'sourced': _integer(raw.get(mapping['sourced']) or '', 'sourced', idx),
                'contacted': _integer(raw.get(mapping['contacted']) or '', 'contacted', idx),
                'screened': _integer(raw.get(mapping['screened']) or '', 'screened', idx),
                'interviewed': _integer(raw.get(mapping['interviewed']) or '', 'interviewed', idx),
                'offered': _integer(raw.get(mapping['offered']) or '', 'offered', idx),
                'hired': _integer(raw.get(mapping['hired']) or '', 'hired', idx),
                'spend_cny': _number(raw.get(mapping.get('spend_cny','')) or '', 'spend_cny', idx) if mapping.get('spend_cny') else 0.0,
                'human_confirmed': _boolean(raw.get(mapping.get('human_confirmed','')) or '') if mapping.get('human_confirmed') else False,
                'notes': (raw.get(mapping.get('notes','')) or '').strip() if mapping.get('notes') else '',
            }
            if not row['channel']:
                raise ValueError(f'row {idx}: channel is required')
            counts=[row[x] for x in ('sourced','contacted','screened','interviewed','offered','hired')]
            if any(v < 0 for v in counts):
                raise ValueError(f'row {idx}: funnel counts must be non-negative')
            if not all(a >= b for a,b in zip(counts,counts[1:])):
                raise ValueError(f'row {idx}: funnel must satisfy sourced >= contacted >= screened >= interviewed >= offered >= hired')
            if row['spend_cny'] < 0:
                raise ValueError(f'row {idx}: spend_cny must be non-negative')
            rows.append(row)
        except ValueError as exc:
            errors.append({'row_number': idx, 'error': str(exc)})
    return {
        'schema': 'srw.sourcing-observation-import-preview.v1',
        'digest': csv_digest(content),
        'detected_delimiter': getattr(dialect,'delimiter',','),
        'mapped_columns': mapping,
        'rows': rows,
        'errors': errors,
        'row_count': len(rows),
        'error_count': len(errors),
        'can_commit': bool(rows) and not errors,
        'semantics': {
            'import_does_not_rank_candidates': True,
            'unconfirmed_data_is_advisory_only': True,
            'commit_requires_exact_preview_digest': True,
        },
    }
