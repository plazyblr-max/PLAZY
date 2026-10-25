from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .competition import require_admin


class TournamentAdvanced(models.Model):
    _inherit = 'plazy.tournament'

    third_place = fields.Boolean(string='Third-place match')
    timezone = fields.Char(required=True, default='Asia/Kolkata')
    kickoff_interval = fields.Integer(default=15, required=True, string='Kickoff grid (minutes)')
    knockout_buffer = fields.Integer(default=20, required=True, string='Knockout extra-time allowance')
    tie_breaker = fields.Selection(selection_add=[('h2h', 'Points, head-to-head mini-table, goal difference, goals scored')], ondelete={'h2h': 'set default'})
    event_ids = fields.One2many('plazy.competition.event', 'tournament_id')

    @api.constrains('timezone', 'kickoff_interval', 'knockout_buffer', 'max_matches_day')
    def _validate_scheduling_policy(self):
        for tournament in self:
            try:
                ZoneInfo(tournament.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValidationError(_('Enter a valid IANA timezone, for example Asia/Kolkata.'))
            if tournament.kickoff_interval < 1 or tournament.knockout_buffer < 0 or tournament.max_matches_day < 1:
                raise ValidationError(_('Kickoff intervals must be positive and extra-time allowance cannot be negative.'))

    def _local_day(self, kickoff):
        self.ensure_one()
        return kickoff.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(self.timezone)).date()

    def _event(self, action, details):
        self.ensure_one()
        return self.env['plazy.competition.event'].sudo().create({
            'tournament_id': self.id, 'action': action, 'details': details,
        })

    def write(self, vals):
        if {'third_place', 'timezone', 'kickoff_interval', 'knockout_buffer'}.intersection(vals) and self.mapped('match_ids'):
            raise ValidationError(_('Scheduling and bracket policies are locked once fixtures exist.'))
        snapshots = {t.id: {key: str(t[key]) for key in vals if key in t._fields and key != 'event_ids'} for t in self}
        result = super().write(vals)
        for tournament in self:
            if snapshots[tournament.id]:
                tournament._event('configuration', '%s -> %s' % (snapshots[tournament.id], {k: str(tournament[k]) for k in snapshots[tournament.id]}))
        return result

    def _rank_standings(self, rows, group=False):
        self.ensure_one()
        point_groups = defaultdict(list)
        for row in rows:
            point_groups[row['pts']].append(row)
        entries = self.registration_ids.filtered(lambda r: r.state == 'approved')
        orders = {r.team_id.id: r.tie_order for r in entries}
        for tied in point_groups.values():
            ids = {r['team'].id for r in tied}
            mini = {team: [0, 0, 0] for team in ids}
            relevant = self.match_ids.filtered(lambda m: m.stage == 'league' and (not group or m.group_id == group) and m.home_id.id in ids and m.away_id.id in ids)
            expected = len(ids) * (len(ids) - 1) // 2 * (2 if self.double_round else 1)
            complete = len(relevant) == expected and all(m.state in ('completed', 'walkover') for m in relevant)
            if complete:
                for match in relevant:
                    for team, scored, conceded in [(match.home_id.id, match.home_score, match.away_score), (match.away_id.id, match.away_score, match.home_score)]:
                        mini[team][0] += self.win_points if scored > conceded else self.loss_points if scored < conceded else self.draw_points
                        mini[team][1] += scored - conceded
                        mini[team][2] += scored
            for row in tied:
                base = (row['pts'], row['gd'], row['gf']) if self.tie_breaker != 'gf' else (row['pts'], row['gf'], row['gd'])
                if self.tie_breaker == 'h2h':
                    base = (row['pts'], *mini[row['team'].id], row['gd'], row['gf'])
                row['sporting_key'] = base
                row['rank_key'] = (*base, -(orders[row['team'].id] or 100000))
                row['h2h_complete'] = complete
        return sorted(rows, key=lambda r: r['rank_key'], reverse=True)


class RegistrationAdvanced(models.Model):
    _inherit = 'plazy.tournament.registration'

    seed = fields.Integer(string='Bracket seed', default=0)
    tie_order = fields.Integer(readonly=True, copy=False)
    team_reference = fields.Integer(related='team_id.id', string='Team ID')

    def write(self, vals):
        if 'tie_order' in vals:
            raise AccessError(_('Use the audited tie decision action.'))
        if 'seed' in vals and self.mapped('tournament_id.match_ids'):
            raise ValidationError(_('Seeds are locked once fixtures exist.'))
        result = super().write(vals)
        if {'state', 'seed', 'group_id'}.intersection(vals):
            for entry in self:
                entry.tournament_id._event('application', '%s: %s' % (entry.team_id.name, vals))
        return result

    @api.constrains('seed')
    def _check_seed(self):
        for entry in self:
            if entry.seed < 0 or (entry.seed and self.search_count([('id', '!=', entry.id), ('tournament_id', '=', entry.tournament_id.id), ('seed', '=', entry.seed)])):
                raise ValidationError(_('Seeds must be positive and unique within a tournament, or zero for automatic ordering.'))

    def _apply_tie_order(self, number):
        return super().write({'tie_order': number})


class GroupAdvanced(models.Model):
    _inherit = 'plazy.tournament.group'

    decision_reason = fields.Text(string='Tie decision reason')
    decision_order = fields.Char(string='Team IDs in decided order', help='Comma-separated team IDs for the entire unresolved tie, best ranked first.')

    def write(self, vals):
        require_admin(self.env)
        if 'tournament_id' in vals and any(group.registration_ids or group.tournament_id.match_ids for group in self):
            raise ValidationError(_('A group with entrants or fixtures cannot move to another tournament.'))
        return super().write(vals)

    def action_resolve_tie(self):
        require_admin(self.env)
        self.ensure_one()
        self.tournament_id._lock()
        tournament = self.tournament_id
        if not (self.decision_reason or '').strip() or tournament.match_ids.filtered(lambda m: m.stage == 'knockout'):
            raise ValidationError(_('Enter a decision reason before the knockout bracket is created.'))
        league = tournament.match_ids.filtered(lambda m: m.group_id == self)
        if not league or any(m.state not in ('completed', 'walkover') for m in league):
            raise ValidationError(_('Complete all group matches before adjudicating a tie.'))
        try:
            ids = [int(value.strip()) for value in (self.decision_order or '').split(',')]
        except ValueError:
            raise ValidationError(_('Enter comma-separated team IDs.'))
        rows = tournament.standings(self)
        chosen = [r for r in rows if r['team'].id in ids]
        if len(ids) < 2 or len(set(ids)) != len(ids) or len(chosen) != len(ids) or len({r['sporting_key'] for r in chosen}) != 1:
            raise ValidationError(_('The decision must contain distinct teams tied under the configured sporting rules.'))
        tied = {r['team'].id for r in rows if r['sporting_key'] == chosen[0]['sporting_key']}
        if tied != set(ids):
            raise ValidationError(_('Include every team in the unresolved tie.'))
        for order, team_id in enumerate(ids, 1):
            self.registration_ids.filtered(lambda r: r.team_id.id == team_id)._apply_tie_order(order)
        tournament._event('tie_decision', '%s: %s. Reason: %s' % (self.name, ids, self.decision_reason))


class CompetitionEvent(models.Model):
    _name = 'plazy.competition.event'
    _description = 'Competition Event History'
    _order = 'create_date desc, id desc'

    tournament_id = fields.Many2one('plazy.tournament', required=True, ondelete='restrict', index=True)
    action = fields.Char(required=True)
    details = fields.Text(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Competition events are recorded by workflow actions.'))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('Competition history is immutable.'))

    def unlink(self):
        raise AccessError(_('Competition history cannot be deleted.'))
