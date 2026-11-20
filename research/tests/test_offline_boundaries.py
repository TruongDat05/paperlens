import json
from pathlib import Path
import httpx
import pytest
from backend.app.core.config import get_settings
from backend.app.core.db import get_connection
from research.evaluation.run_eval import evaluate_dataset
from research.evaluation.replay import ReplayAdapter, ReplayError

@pytest.mark.parametrize('pipeline',['B1','B2','B3','B4','A1','A2'])
@pytest.mark.parametrize('mode',['fixture','replay'])
def test_evaluation_offline_and_database_isolated(tmp_path,monkeypatch,pipeline,mode):
    attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append(True)
        raise AssertionError('Offline evaluation attempted network')
    monkeypatch.setattr(httpx.AsyncClient,'send',forbidden)
    product=Path(get_settings().db_path)
    get_connection().execute('CREATE TABLE sentinel (value TEXT)')
    get_connection().commit()
    before=product.read_bytes()
    record=tmp_path/'replay.json'
    record.write_text(json.dumps({'records':{'q':{'predicted_parents':['p'],'available_evidence_ids':['p']}}}))
    papers=[dict(paper_id='test',paragraphs=[dict(id='p',text='Self-attention replaces recurrence.')],questions=[dict(question_id='q',question='self-attention')])]
    evaluate_dataset(papers,pipeline,mode,output_dir=str(tmp_path/'out'),replay_adapter=ReplayAdapter(str(record)) if mode=='replay' else None)
    assert attempts == []
    assert product.read_bytes()==before
    assert get_connection().execute('SELECT count(*) FROM papers').fetchone()[0]==0

def test_missing_replay_fails_closed(tmp_path):
    with pytest.raises(ReplayError):
        evaluate_dataset([],mode='replay',output_dir=str(tmp_path))
