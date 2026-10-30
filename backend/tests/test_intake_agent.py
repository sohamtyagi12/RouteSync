import pytest

import app.agents.base as agent_base
from app.agents.intake_agent import build_draft, find_location, run_intake_agent


# ---- scripted stand-in for the AI client (same idea as test_dispatch_agent.py) ----
class Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def tool_call(call_id, name, **inp):
    return Block(type='tool_use', id=call_id, name=name, input=inp)


def reply(*blocks):
    return Block(content=list(blocks), stop_reason='tool_use')


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.messages = self
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.script.pop(0)


@pytest.fixture(autouse=True)
def claude_shaped_fake(monkeypatch):
    monkeypatch.setenv('AGENT_PROVIDER', 'anthropic')


def use_fake(monkeypatch, script):
    fake = FakeClient(script)
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    return fake


# ---- the agent loop ----
def test_intake_returns_a_draft_with_looked_up_coordinates(monkeypatch):
    use_fake(monkeypatch, [
        reply(tool_call('t1', 'lookup_place', query='Powai'),
              tool_call('t2', 'lookup_place', query='Thane')),
        reply(tool_call('t3', 'submit_draft', pickup_place='Powai', dropoff_place='Thane',
                        package_description='Documents', priority='urgent',
                        assumptions='Weight not given, assumed 1 kg')),
    ])
    out = run_intake_agent('Pick up documents from Powai and deliver to Thane, urgent')
    d = out['draft']
    assert d['pickup_address'] == 'Powai, Mumbai'
    assert (d['pickup_latitude'], d['pickup_longitude']) == (19.1176, 72.9060)
    assert d['dropoff_address'] == 'Thane West'
    assert d['priority'] == 'urgent'
    assert d['package_weight'] == 1.0
    assert [t['tool'] for t in out['trace']] == ['lookup_place', 'lookup_place', 'submit_draft']


def test_intake_can_ask_a_clarifying_question(monkeypatch):
    use_fake(monkeypatch, [
        reply(tool_call('t1', 'ask_clarification', question='Where should it be delivered?')),
    ])
    out = run_intake_agent('Send my parcel from Powai')
    assert out['clarification'] == 'Where should it be delivered?'
    assert 'draft' not in out


def test_unknown_place_is_rejected_and_the_agent_can_recover(monkeypatch):
    fake = use_fake(monkeypatch, [
        reply(tool_call('t1', 'submit_draft', pickup_place='Atlantis', dropoff_place='Thane',
                        package_description='Documents')),
        reply(tool_call('t2', 'submit_draft', pickup_place='Powai', dropoff_place='Thane',
                        package_description='Documents')),
    ])
    out = run_intake_agent('Documents from Atlantis to Thane')
    assert out['draft']['pickup_address'] == 'Powai, Mumbai'
    assert len(fake.requests) == 2  # the first attempt was bounced back to the model


# ---- guards that run before the AI is ever called ----
def test_empty_and_overlong_requests_are_rejected():
    with pytest.raises(ValueError):
        run_intake_agent('   ')
    with pytest.raises(ValueError):
        run_intake_agent('x' * 501)


# ---- build_draft: the code that checks the model's output ----
def test_find_location_matches_loosely_and_never_guesses():
    assert find_location('POWAI')[0] == 'Powai, Mumbai'
    assert find_location('near thane west station')[0] == 'Thane West'
    assert find_location('Atlantis') is None
    assert find_location('') is None


@pytest.mark.parametrize('bad', [
    {'pickup_place': 'Powai', 'dropoff_place': 'Powai', 'package_description': 'x'},
    {'pickup_place': 'Powai', 'dropoff_place': 'Thane', 'package_description': 'x', 'priority': 'asap'},
    {'pickup_place': 'Powai', 'dropoff_place': 'Thane', 'package_description': 'x', 'package_weight': 500},
    {'pickup_place': 'Powai', 'dropoff_place': 'Thane', 'package_description': 'x', 'package_weight': 'heavy'},
    {'pickup_place': 'Powai', 'dropoff_place': 'Thane', 'package_description': '  '},
])
def test_build_draft_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        build_draft(bad)