"""Read-only closing-date counts for the Opportunity create/edit form."""
from collections import Counter
import json

from . import opportunities as op, tenders
from .opportunity_retention import active_sql


def deadline_load(store, params, user):
    """Count other registered projects, without applying the current view filters.

    One Opportunity is one project even when it has several builders. Retired
    and deleted records are excluded, while every visible workflow status is
    included. Team combinations keep each project in one group so their counts
    add up to the total. The check never changes a deadline or assignment.
    """
    op.initialize(store)
    teams, users = op.directory()
    op._actor(user, users)
    team_names = {team['id']: team['name'] for team in teams}
    due = tenders.date_value(params.get('due'), required=True)
    exclude = tenders.text(params.get('excludeId'), 'Opportunity ID', limit=100)
    # Forms display the JSON deadline. Some historical migrations intentionally
    # preserve different SQL values, so prefer that displayed date. Only an
    # absent JSON key falls back to SQL; a cleared blank/null date stays empty.
    displayed_due = """CASE WHEN json_type(o.body,'$.due') IS NULL THEN o.due
                            ELSE json_extract(o.body,'$.due') END"""
    with store.connect() as db:
        rows = db.execute(
            'SELECT o.body FROM opportunities o WHERE o.deleted_at IS NULL '
            'AND o.id!=? AND ' + active_sql('opportunity', 'o.id') +
            ' AND (' + displayed_due + ')=?', (exclude, due))
        groups = Counter()
        for row in rows:
            assigned = json.loads(row['body']).get('assignedTeamIds')
            assigned = assigned if isinstance(assigned, list) else []
            names = {team_names.get(identifier, 'Former team')
                     for identifier in assigned if type(identifier) is int}
            # People-only assignments do not imply a team assignment. Missing
            # teams retain the same label as the Opportunity's assigned names.
            key = tuple(sorted(names, key=lambda name: (name.casefold(), name)))
            groups[key] += 1
    ordered = sorted(groups, key=lambda names: (
        not bool(names), tuple((name.casefold(), name) for name in names)))
    return {'due': due, 'count': sum(groups.values()), 'teamGroups': [
        {'teamNames': list(names), 'count': groups[names]} for names in ordered]}
