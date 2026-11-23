"""One authoritative effective-mode decision; user identity is not part of routing."""
from app.supervisor.routing import signals

def effective_mode(text, requested):
    if requested not in {'support','shopping','supervisor'}:raise ValueError('未知 Agent 类型')
    after,shopping=signals(text)
    if requested=='supervisor' or after and shopping:return 'supervisor'
    if after:return 'support'
    if shopping:return 'shopping'
    return requested
