"""Explicit, permission-checked assistant actions.

The model never executes SQL or supplies tool names. A small deterministic
intent parser offers a preview; a separate user gesture confirms the operation.
"""
import re
from datetime import date
import time
import uuid

from .accounts import AccessError
from . import workspace, project_notes

_ACTION_EXPIRY_SECONDS = 300
_STATUSES = {
    'not started': 'draft', 'draft': 'draft',
    'in progress': 'in_progress', 'in review': 'in_review',
    'submitted': 'submitted', 'closed': 'closed',
}


def parse_intent(text):
    text = str(text or '').strip()
    note = re.match(r'^(?:please\s+)?(?:add|create|record)\s+(?:a\s+)?(?:project\s+)?note(?:\s+(?:to|on|for)\s+(?:(?:this|the|current)\s+)?(?:project|estimate))?\s*[:\-]\s*(.+)$', text, flags=re.I | re.S)
    if note:
        body=note[1].strip()
        if not 1 <= len(body) <= 1000:
            raise ValueError('Write a note of 1 to 1,000 characters after the colon.')
        return {'kind':'add_note','body':body}
    status = re.match(r'^(?:please\s+)?(?:set|change|update|mark)\s+(?:(?:this|the|current)\s+)?(?:project|estimate)(?:\s+(?:progress|status))?\s+(?:to|as)\s+(not started|draft|in progress|in review|submitted|closed)(?:\s+(?:until|on|by)\s+(\d{4}-\d{2}-\d{2}))?\s*[.!]?$', text, re.I)
    if status:
        chosen=_STATUSES[status[1].casefold()]
        deadline=status[2]
        if chosen=='in_review' and not deadline:
            raise ValueError('In review requires a review deadline. For example: Set this project status to in review until 2026-12-01.')
        if deadline and chosen!='in_review':
            raise ValueError('Only In review accepts a review deadline here.')
        if deadline:
            try:date.fromisoformat(deadline)
            except ValueError:raise ValueError('Enter a valid review date (YYYY-MM-DD).') from None
        return {'kind':'set_status','status':chosen,**({'review_deadline':deadline} if deadline else {})}
    deadline = re.match(r'^(?:please\s+)?(?:set|change|update)\s+(?:(?:this|the|current)\s+)?(?:project|estimate)(?:\s+submission)?\s+deadline\s+(?:to|as)\s+(\d{4}-\d{2}-\d{2})\s*[.!]?$', text, re.I)
    if deadline:
        try:date.fromisoformat(deadline[1])
        except ValueError:raise ValueError('Enter a valid submission date (YYYY-MM-DD).') from None
        return {'kind':'set_deadline','submission_deadline':deadline[1]}
    outcome = re.match(r'^(?:please\s+)?(?:mark|set|change)\s+(?:(?:this|the|current)\s+)?(?:project|estimate)\s+(?:(?:result|outcome)\s+(?:to|as)\s+|as\s+)(won|lost)\s*[.!]?$', text, re.I)
    if outcome:
        return {'kind':'set_outcome','award_status':outcome[1].casefold()}
    rename = re.match(r'^(?:please\s+)?rename\s+(?:(?:this|the|current)\s+)?(?:project|estimate)\s+to\s+(.+)$', text, re.I | re.S)
    if rename:
        name=rename[1].strip()
        if not 1<=len(name)<=500:raise ValueError('Enter a project name of 1–500 characters.')
        return {'kind':'rename','name':name}
    return None


def prepare(conn, user, question, project_id):
    intent=parse_intent(question)
    if not intent:
        return None
    if type(project_id) is not int or project_id < 1:
        raise ValueError('Open the estimate you want to change, then ask again.')
    project=workspace.require_project(conn, project_id, user, 'edit')
    if intent['kind'] in ('set_deadline','rename') and not workspace.permissions(conn,project,user)['can_manage']:
        raise AccessError(403,'Only the project owner or an administrator may change its name or submission deadline.')
    match={'set_status': ('status','status'), 'set_deadline':('submission_deadline','submission_deadline'),
        'set_outcome':('award_status','award_status'), 'rename':('name','name')}
    if intent['kind'] in match:
        project_field,intent_field=match[intent['kind']]
        if project[project_field]==intent[intent_field]:
            return {'answer':'This estimate already has that value. No change was made.','mode':'No action required'}
        intent['expected_revision']=project['revision']
    if intent['kind']=='set_status':
        readable=intent['status'].replace('_',' ').title()
        description=f'Change progress for “{project["name"]}” to {readable}.'
        if intent.get('review_deadline'):
            description+=f' Review until {intent["review_deadline"]}.'
    elif intent['kind']=='set_deadline':
        description=f'Change submission deadline for “{project["name"]}” to {intent["submission_deadline"]}.'
    elif intent['kind']=='set_outcome':
        description=f'Mark the tender result for “{project["name"]}” as {intent["award_status"].upper()}.'
    elif intent['kind']=='rename':
        description=f'Rename “{project["name"]}” to “{intent["name"]}”.'
    else:
        description=f'Add this note to “{project["name"]}”:\n\n{intent["body"]}'
    return {
        'intent': intent,
        'project_id': project_id,
        'project_name': project['name'],
        'description': description,
        'token': uuid.uuid4().hex,
        'expires_at': time.time()+_ACTION_EXPIRY_SECONDS,
    }


def confirmed(conn, user, pending, token):
    if not isinstance(pending,dict) or pending.get('token')!=token:
        raise AccessError(409,'This action is no longer pending. Ask the assistant again to create a new preview.')
    if time.time() > pending.get('expires_at',0):
        raise AccessError(409,'The action preview expired. Ask again and review a new preview.')
    pid=pending['project_id']
    intent=pending['intent']
    workspace.require_project(conn,pid,user,'edit')  # LIVE authorization on every confirmation
    if intent['kind']=='add_note':
        project_notes.add_note(conn,pid,user,{'body':intent['body']})
        return {'answer':f'Note added to {pending["project_name"]}.','sources':[{'label':'Open estimate','url':f'#/estimate/{pid}'}]}
    if intent['kind'] in ('set_status','set_deadline','set_outcome','rename'):
        fields={'set_status':('status','review_deadline'),'set_deadline':('submission_deadline',),
            'set_outcome':('award_status',),'rename':('name',)}[intent['kind']]
        payload={field:intent[field] for field in fields if field in intent}
        payload['expected_revision']=intent['expected_revision']
        workspace.update_workflow(conn,pid,payload,user)
        return {'answer':'Confirmed: '+pending['description'].split('\n')[0],
            'sources':[{'label':'Open estimate','url':f'#/estimate/{pid}'}]}
    raise ValueError('Unsupported assistant action.')
