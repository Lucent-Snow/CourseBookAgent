"""Selectively package one completed book and its input; never export credentials."""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from coursebook_agent.product.service import ProductService


def export(job_id: str, source: Path, target: Path):
    history = json.loads((source / 'jobs' / f'{job_id}.json').read_text())
    state = history['state']
    if state['status'] != 'completed' or not state.get('book'):
        raise ValueError('Only a completed Job can be a preset')
    snapshot_id = state['request']['snapshot_id']
    original = ProductService(source / 'product')
    snapshot = original.get_snapshot(snapshot_id)
    target.mkdir(parents=True, exist_ok=True)
    destination = ProductService(target / 'product')
    with original._connect() as src, destination._connect() as dst:
        dataset = dict(src.execute('SELECT * FROM datasets WHERE dataset_id=?', (snapshot.dataset_id,)).fetchone())
        dataset['description'] = '完成预设：可直接阅读已有教辅，也可选择资料重新生成。'
        def insert(table, record):
            columns = ','.join(record)
            dst.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in record)})", tuple(record.values()))
        insert('datasets', dataset)
        for revision_id in snapshot.resource_revision_ids:
            revision = dict(src.execute('SELECT * FROM revisions WHERE revision_id=?', (revision_id,)).fetchone())
            resource = dict(src.execute('SELECT * FROM resources WHERE resource_id=?', (revision['resource_id'],)).fetchone())
            insert('resources', resource)
            # Allowlisted provenance only: do not ship captured sessions or arbitrary metadata.
            metadata = json.loads(revision['metadata_json'])
            revision['metadata_json'] = json.dumps({k: metadata[k] for k in ('course_id','course_name','lecture_id','lecture_index','duration','teacher','term') if k in metadata}, ensure_ascii=False)
            for field, folder in [('blob_path', 'blobs'), ('text_path', 'text')]:
                if revision[field]:
                    path = original._stored_path(revision[field])
                    dest = destination.root / folder / path.name
                    shutil.copyfile(path, dest)
                    revision[field] = f'{folder}/{path.name}'
            insert('revisions', revision)
        record = dict(src.execute('SELECT * FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone())
        insert('snapshots', record)
    state['message'] = '已有完成预设；本次未重新调用模型'
    state['request'] = {k: state['request'][k] for k in ('snapshot_id','course_id','dataset_id','dataset_name','regenerate','review','concurrency','chapter_indices') if k in state['request']}
    state['request']['completed_preset'] = True
    state['metrics'] = {}
    state['events'] = []
    (target / 'jobs').mkdir(exist_ok=True)
    (target / 'jobs' / f'{job_id}.json').write_text(json.dumps({'state':state,'events':[]}, ensure_ascii=False))
    (target / 'preset-imported.json').write_text(json.dumps({'job_id':job_id,'dataset_id':snapshot.dataset_id}))
    print('Preset exported:', len(snapshot.resource_revision_ids), 'resources,', len(state['book']['chapters']), 'chapters')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--source', type=Path, default=Path('data'))
    parser.add_argument('--target', type=Path, default=Path('data/deployment-preset'))
    args = parser.parse_args()
    export(args.job, args.source, args.target)
