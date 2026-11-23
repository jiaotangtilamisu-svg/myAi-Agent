from types import SimpleNamespace
from unittest.mock import Mock

from app.services import model_usage as mod


def test_logs_only_provider_usage_not_private_output(monkeypatch):
    log=Mock();monkeypatch.setattr(mod,'logger',log)
    mod.ModelUsageCallback().on_llm_end(SimpleNamespace(llm_output={'model_name':'test-model','token_usage':{'prompt_tokens':4,'completion_tokens':2,'total_tokens':6},'private':'MUST_NOT_LOG'},generations=[]))
    assert log.info.call_args.kwargs == {'model':'test-model','prompt_tokens':4,'completion_tokens':2,'total_tokens':6,'usage_provided':True}


def test_missing_usage_is_explicit_and_errors_do_not_leak(monkeypatch):
    log=Mock();monkeypatch.setattr(mod,'logger',log)
    cb=mod.ModelUsageCallback();cb.on_llm_end(SimpleNamespace(llm_output=None,generations=[]))
    assert log.info.call_args.kwargs['usage_provided'] is False
    cb.on_llm_error(RuntimeError('MUST_NOT_LOG'))
    assert log.warning.call_args.kwargs == {'error_type':'RuntimeError'}
