from fastapi.testclient import TestClient
from app.main import app
from app.core import analyze, Request
client=TestClient(app)

def test_real_dag_out_of_order():
    req=Request(nodes=[{'id':'mean','op':'aggregate','depends_on':['filtered'],'params':{'field':'x','operation':'mean'}},{'id':'filtered','op':'filter','depends_on':['data'],'params':{'field':'x','comparison':'gt','value':1}},{'id':'data','op':'source','params':{'rows':[{'x':1},{'x':3},{'x':5}]}}])
    result=analyze(req)
    assert result['execution_order']==['data','filtered','mean']
    assert result['outputs']['mean']==[{'mean':4}]

def test_select_concat_count():
    nodes=[{'id':'a','op':'source','params':{'rows':[{'x':2,'y':4}]}},{'id':'b','op':'select','depends_on':['a'],'params':{'fields':['x']}},{'id':'c','op':'concat','depends_on':['a','b']},{'id':'d','op':'aggregate','depends_on':['c'],'params':{'operation':'count'}}]
    r=client.post('/analyze',json={'nodes':nodes})
    assert r.status_code==200
    assert r.json()['outputs']['d']==[{'count':2}]

def test_cycles_and_unknown_dependencies():
    for nodes in [[{'id':'a','op':'select','depends_on':['a']}],[{'id':'a','op':'select','depends_on':['b']}],[{'id':'a','op':'source'},{'id':'a','op':'source'}]]:
        assert client.post('/analyze',json={'nodes':nodes}).status_code==422

def test_no_arbitrary_execution_and_bad_inputs():
    assert client.post('/analyze',json={'nodes':[{'id':'a','op':'exec','params':{'code':'print(1)'}}]}).status_code==422
    nodes=[{'id':'a','op':'source','params':{'rows':[{'x':'text'}]}},{'id':'b','op':'aggregate','depends_on':['a'],'params':{'field':'x'}}]
    assert client.post('/analyze',json={'nodes':nodes}).status_code==422
    assert client.get('/health').status_code==200
    assert client.get('/').status_code==200

def test_reject_malformed_fields_unknown_params_and_empty_mean():
    base=[{'id':'a','op':'source','params':{'rows':[]}}]
    for node in [
        {'id':'b','op':'filter','depends_on':['a'],'params':{'field':[]}},
        {'id':'b','op':'aggregate','depends_on':['a'],'params':{'field':'x','operation':'mean'}},
        {'id':'b','op':'select','depends_on':['a'],'params':{'fields':['x'],'url':'http://example.com'}},
    ]:
        assert client.post('/analyze',json={'nodes':base+[node]}).status_code==422

def test_reject_row_limit():
    assert client.post('/analyze',json={'nodes':[{'id':'a','op':'source','params':{'rows':[{}]*10001}}]}).status_code==422
