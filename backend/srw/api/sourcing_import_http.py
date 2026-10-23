from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError
from srw.modules.recruitment_intelligence.importer import preview_csv, csv_digest
from srw.modules.recruitment_intelligence.service import record_observation


async def _body(request: Request) -> dict:
    try: value = await request.json()
    except Exception as exc: raise V1InvariantError('request body must be valid JSON') from exc
    if not isinstance(value, dict): raise V1InvariantError('request body must be an object')
    return value


def _text(body: dict, key: str, default: str='') -> str:
    value = body.get(key, default)
    if value is None: return ''
    if not isinstance(value, str): raise V1InvariantError(f'{key} must be a string')
    return value


def install_sourcing_import_http_routes(app, factory):
    async def import_preview(request: Request):
        body = await _body(request)
        return JSONResponse(preview_csv(_text(body, 'content')))

    async def import_commit(request: Request):
        body = await _body(request)
        content = _text(body, 'content')
        expected = _text(body, 'expected_digest').strip()
        actual = csv_digest(content)
        if not expected or expected != actual:
            raise V1InvariantError('CSV digest mismatch; preview the exact file again before commit')
        preview = preview_csv(content)
        if not preview['can_commit']:
            raise V1InvariantError('CSV contains validation errors and cannot be committed')
        project_id = request.path_params['project_id']
        filename = _text(body, 'filename', 'sourcing-observations.csv').strip() or 'sourcing-observations.csv'
        override_confirmed = body.get('human_confirmed') is True
        actor = _text(body, 'actor', 'human').strip() or 'human'
        ids=[]
        with factory.begin() as session:
            for row in preview['rows']:
                item = record_observation(
                    session, project_id,
                    channel=row['channel'], period=row['period'], sourced=row['sourced'], contacted=row['contacted'],
                    screened=row['screened'], interviewed=row['interviewed'], offered=row['offered'], hired=row['hired'],
                    spend_cny=row['spend_cny'], human_confirmed=(override_confirmed or row['human_confirmed']),
                    provenance=f'csv_import:{filename};actor={actor};sha256={actual}', notes=row['notes'],
                )
                ids.append(item.id)
        return JSONResponse({
            'status':'committed','digest':actual,'imported_count':len(ids),'observation_ids':ids,
            'human_confirmation_override':override_confirmed,
            'semantics':{'candidate_ranking_unchanged':True,'market_signal_is_not_candidate_score':True},
        })

    app.routes.extend([
        Route('/api/v1/projects/{project_id:str}/sourcing-observations/import-preview', import_preview, methods=['POST']),
        Route('/api/v1/projects/{project_id:str}/sourcing-observations/import-commit', import_commit, methods=['POST']),
    ])
