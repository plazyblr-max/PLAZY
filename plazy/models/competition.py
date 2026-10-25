from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


def require_admin(env):
    if not is_competition_admin(env):
        raise AccessError(_('Only a PLAZY administrator can manage competitions.'))


def is_competition_admin(env):
    return env.su or env.user.has_group('base.group_system') or env.user.has_group('plazy.competition_admin')


class Tournament(models.Model):
    _name = 'plazy.tournament'
    _description = 'Football Competition'
    _order = 'start_date desc, id desc'

    name = fields.Char(required=True)
    logo = fields.Image(max_width=512, max_height=512)
    description = fields.Text()
    rules = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    football_format = fields.Selection([('five_a_side', '5-a-side'), ('seven_a_side', '7-a-side')], required=True, default='seven_a_side')
    format = fields.Selection([('league', 'League'), ('knockout', 'Knockout'), ('hybrid', 'League + Knockout')], required=True, default='hybrid')
    location = fields.Char(required=True)
    registration_start = fields.Datetime(required=True)
    registration_end = fields.Datetime(required=True)
    start_date = fields.Datetime(required=True)
    end_date = fields.Datetime(required=True)
    min_teams = fields.Integer(default=4, required=True)
    max_teams = fields.Integer(default=16, required=True)
    group_count = fields.Integer(default=4, required=True)
    qualifiers = fields.Integer(default=2, required=True)
    double_round = fields.Boolean(string='Double round robin')
    duration = fields.Integer(default=40, required=True)
    rest_minutes = fields.Integer(default=20, required=True)
    venue_ids = fields.Many2many('plazy.tournament.venue', string='Scheduling grounds')
    max_matches_day = fields.Integer(default=8, required=True)
    win_points = fields.Integer(default=3)
    draw_points = fields.Integer(default=1)
    loss_points = fields.Integer(default=0)
    tie_breaker = fields.Selection([('gd', 'Points, goal difference, goals scored'), ('gf', 'Points, goals scored, goal difference')], default='gd', required=True)
    state = fields.Selection([(x, y) for x, y in [('draft', 'Draft'), ('open', 'Registration Open'), ('closed', 'Registration Closed'), ('scheduled', 'Scheduled'), ('live', 'In Progress'), ('completed', 'Completed'), ('postponed', 'Postponed'), ('cancelled', 'Cancelled')]], default='draft', required=True)
    previous_state = fields.Char(copy=False)
    change_reason = fields.Text(copy=False)
    published = fields.Boolean(default=False)
    registration_ids = fields.One2many('plazy.tournament.registration', 'tournament_id')
    group_ids = fields.One2many('plazy.tournament.group', 'tournament_id')
    match_ids = fields.One2many('plazy.tournament.match', 'tournament_id')
    champion_id = fields.Many2one('plazy.team', readonly=True, copy=False)
    approved_count = fields.Integer(compute='_counts')

    @api.depends('registration_ids.state')
    def _counts(self):
        for record in self:
            record.approved_count = len(record.registration_ids.filtered(lambda r: r.state == 'approved'))

    @api.constrains('registration_start', 'registration_end', 'start_date', 'end_date', 'min_teams', 'max_teams', 'group_count', 'qualifiers', 'duration', 'rest_minutes')
    def _validate(self):
        for t in self:
            if not t.registration_start <= t.registration_end <= t.start_date < t.end_date:
                raise ValidationError(_('Registration and tournament dates must be in chronological order.'))
            if not 2 <= t.min_teams <= t.max_teams <= 32 or t.group_count < 1 or t.qualifiers < 1 or t.duration < 1 or t.rest_minutes < 0:
                raise ValidationError(_('Check team capacity (2-32), groups, qualifiers, duration and rest period.'))

    def _lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM plazy_tournament WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def write(self, vals):
        require_admin(self.env)
        rules = {'football_format', 'format', 'group_count', 'qualifiers', 'double_round', 'win_points', 'draw_points', 'loss_points', 'tie_breaker'}
        if rules.intersection(vals) and any(self.mapped('match_ids')):
            raise ValidationError(_('Competition rules are locked once fixtures exist.'))
        return super().write(vals)

    def action_open(self):
        require_admin(self.env)
        for t in self:
            if t.state != 'draft':
                raise ValidationError(_('Only draft competitions can open registration.'))
            t.write({'state': 'open', 'published': True})

    def action_close(self):
        require_admin(self.env)
        for t in self:
            if t.state != 'open':
                raise ValidationError(_('Registration is not open.'))
            t.state = 'closed'

    def action_postpone(self):
        require_admin(self.env)
        for t in self:
            if not t.change_reason or t.state in ('completed', 'cancelled', 'postponed'):
                raise ValidationError(_('Enter a reason for postponing an active competition.'))
            t.write({'previous_state': t.state, 'state': 'postponed'})

    def action_resume(self):
        require_admin(self.env)
        for t in self:
            if t.state != 'postponed' or not t.previous_state:
                raise ValidationError(_('This competition is not postponed.'))
            t.state = t.previous_state

    def action_cancel(self):
        require_admin(self.env)
        for t in self:
            if not t.change_reason or t.state == 'completed':
                raise ValidationError(_('Enter a cancellation reason; completed competitions cannot be cancelled.'))
            t.state = 'cancelled'
            t.match_ids.filtered(lambda m: m.state not in ('completed', 'walkover', 'cancelled', 'bye')).write({'state': 'cancelled', 'correction_reason': t.change_reason})

    def _entrants(self):
        self.ensure_one()
        entrants = self.registration_ids.filtered(lambda r: r.state == 'approved').sorted(lambda r: (r.seed or 100000, r.id))
        if not self.min_teams <= len(entrants) <= self.max_teams:
            raise ValidationError(_('The approved team count is outside competition limits.'))
        for entry in entrants:
            entry._eligible()
        return entrants

    def action_generate_league(self):
        require_admin(self.env)
        self._lock()
        if self.match_ids:
            return True
        if self.state != 'closed' or self.format == 'knockout':
            raise ValidationError(_('Close registration before generating league fixtures.'))
        entrants = self._entrants()
        if len(entrants) < self.group_count * 2:
            raise ValidationError(_('Each group needs at least two teams.'))
        groups = self.group_ids
        if groups:
            if len(groups) != self.group_count or any(r.group_id not in groups for r in entrants):
                raise ValidationError(_('Assign every approved entrant to the configured number of groups.'))
            sizes = [len(g.registration_ids.filtered(lambda r: r.state == 'approved')) for g in groups]
            if min(sizes) < 2 or max(sizes) - min(sizes) > 1:
                raise ValidationError(_('Groups must be balanced and contain at least two approved teams.'))
        else:
            for number in range(self.group_count):
                group = self.env['plazy.tournament.group'].create({'name': 'Group %s' % chr(65 + number), 'tournament_id': self.id})
                members = entrants[number::self.group_count]
                members.write({'group_id': group.id})
        for group in self.group_ids:
            members = group.registration_ids.filtered(lambda r: r.state == 'approved')
            teams = members.mapped('team_id').ids
            if len(teams) % 2:
                teams.append(False)
            for round_index in range(len(teams) - 1):
                for i in range(len(teams) // 2):
                    home, away = teams[i], teams[-1-i]
                    if home and away:
                        for leg in range(2 if self.double_round else 1):
                            self.env['plazy.tournament.match'].create({'tournament_id': self.id, 'group_id': group.id, 'stage': 'league', 'round_number': round_index + 1 + leg * (len(teams)-1), 'home_id': away if leg else home, 'away_id': home if leg else away, 'fixture_key': 'L:%s:%s:%s:%s' % (group.id, home, away, leg)})
                teams = [teams[0], teams[-1], *teams[1:-1]]
        return True

    def standings(self, group=False):
        self.ensure_one()
        entries = self.registration_ids.filtered(lambda r: r.state == 'approved' and (not group or r.group_id == group))
        rows = {r.team_id.id: dict(team=r.team_id, p=0, w=0, d=0, l=0, gf=0, ga=0, gd=0, pts=0) for r in entries}
        for match in self.match_ids.filtered(lambda m: m.stage == 'league' and m.state in ('completed', 'walkover') and (not group or m.group_id == group)):
            for team, scored, conceded in [(match.home_id, match.home_score, match.away_score), (match.away_id, match.away_score, match.home_score)]:
                if team.id not in rows:
                    continue
                row = rows[team.id]
                outcome = 'w' if scored > conceded else 'l' if scored < conceded else 'd'
                row['p'] += 1
                row[outcome] += 1
                row['gf'] += scored
                row['ga'] += conceded
                row['gd'] = row['gf'] - row['ga']
                row['pts'] += {'w': self.win_points, 'd': self.draw_points, 'l': self.loss_points}[outcome]
        return self._rank_standings(list(rows.values()), group)

    def action_generate_knockout(self):
        require_admin(self.env)
        self._lock()
        if self.match_ids.filtered(lambda m: m.stage == 'knockout'):
            return True
        if self.format == 'league' or self.state not in ('closed', 'scheduled', 'live'):
            raise ValidationError(_('This competition is not ready for a knockout bracket.'))
        if self.format == 'hybrid':
            league = self.match_ids.filtered(lambda m: m.stage == 'league')
            if not league or any(m.state not in ('completed', 'walkover') for m in league):
                raise ValidationError(_('Finalize every league match before qualification.'))
            teams = []
            for group in self.group_ids.sorted('id'):
                table = self.standings(group)
                if self.qualifiers >= len(table):
                    raise ValidationError(_('Qualifiers per group must be fewer than group teams.'))
                if table[self.qualifiers-1]['rank_key'] == table[self.qualifiers]['rank_key']:
                    raise ValidationError(_('Qualification is tied. Resolve the sporting tie before generating a bracket.'))
                teams.extend(row['team'].id for row in table[:self.qualifiers])
            # Pair group winners against runners-up in adjacent groups.
            if self.qualifiers == 2 and len(self.group_ids) % 2 == 0:
                teams = [teams[i+j] for i in range(0, len(teams), 4) for j in (0, 3, 2, 1)]
        else:
            teams = self._entrants().mapped('team_id').ids
        if not 2 <= len(teams) <= 32:
            raise ValidationError(_('A knockout bracket requires between two and thirty-two teams.'))
        if self.third_place and len(teams) < 4:
            raise ValidationError(_('A third-place match requires at least four qualifiers.'))
        size = 1 << (len(teams) - 1).bit_length()
        if len(teams) != size:
            seed_order = [1, 2]
            while len(seed_order) < size:
                complement = len(seed_order) * 2 + 1
                seed_order = [value for seed in seed_order for value in (seed, complement - seed)]
            teams = [teams[seed-1] if seed <= len(teams) else False for seed in seed_order]
        round_number, previous, semifinal = 1, [], []
        byes = self.env['plazy.tournament.match']
        while len(teams) > 1:
            current = []
            for i in range(0, len(teams), 2):
                match = self.env['plazy.tournament.match'].create({'tournament_id': self.id, 'stage': 'knockout', 'round_number': round_number, 'home_id': teams[i], 'away_id': teams[i+1], 'fixture_key': 'K:%s:%s' % (round_number, i//2)})
                if round_number == 1 and bool(teams[i]) != bool(teams[i+1]):
                    match.is_bye = True
                    byes |= match
                if previous:
                    previous[i].write({'next_match_id': match.id, 'next_slot': 'home'})
                    previous[i+1].write({'next_match_id': match.id, 'next_slot': 'away'})
                current.append(match)
            if len(current) == 2:
                semifinal = current
            previous = current
            teams = [False] * len(current)
            round_number += 1
        if self.third_place:
            third = self.env['plazy.tournament.match'].create({'tournament_id': self.id, 'stage': 'knockout', 'round_number': round_number - 1, 'fixture_key': 'K:third-place', 'is_third_place': True})
            semifinal[0].write({'loser_match_id': third.id, 'loser_slot': 'home'})
            semifinal[1].write({'loser_match_id': third.id, 'loser_slot': 'away'})
        for bye in byes:
            bye._advance_bye()
        self._event('bracket_generated', 'Bracket size %s; byes %s; third-place %s' % (size, len(byes), self.third_place))
        return True

    def action_publish(self):
        require_admin(self.env)
        for t in self:
            if t.state not in ('closed', 'scheduled', 'live'):
                raise ValidationError(_('This competition cannot publish fixtures in its current state.'))
            if not t.match_ids or any(not m.kickoff or not m.venue_id for m in t.match_ids.filtered(lambda m: not m.is_bye)):
                raise ValidationError(_('Schedule all fixtures before publishing.'))
            t.match_ids._check_schedule()
            t.match_ids.filtered(lambda m: not m.published).write({'published': True})
            t.write({'published': True, 'state': 'live' if t.state == 'live' else 'scheduled'})

    def action_schedule(self):
        require_admin(self.env)
        self._lock()
        if self.state not in ('closed', 'scheduled', 'live'):
            raise ValidationError(_('Close registration before scheduling fixtures.'))
        if not self.venue_ids or self.max_matches_day < 1:
            raise ValidationError(_('Select scheduling grounds and a positive daily match limit.'))
        for match in self.match_ids.filtered(lambda m: not m.kickoff and not m.is_bye).sorted(lambda m: (m.round_number, not m.is_third_place, m.id)):
            assigned = False
            for slot in self.venue_ids.mapped('slot_ids').sorted('start'):
                candidate = max(slot.start, self.start_date)
                predecessors = self.match_ids.filtered(lambda m: (m.next_match_id == match or m.loser_match_id == match) and m.kickoff)
                if predecessors:
                    candidate = max(candidate, max(m.kickoff + timedelta(minutes=m.reserved_minutes + self.rest_minutes) for m in predecessors))
                while candidate + timedelta(minutes=match.reserved_minutes) <= min(slot.end, self.end_date):
                    daily = self.match_ids.filtered(lambda m: m.kickoff and m.state not in ('cancelled', 'postponed') and self._local_day(m.kickoff) == self._local_day(candidate))
                    if len(daily) < self.max_matches_day:
                        try:
                            with self.env.cr.savepoint():
                                match.write({'kickoff': candidate, 'venue_id': slot.venue_id.id})
                            assigned = True
                            break
                        except ValidationError:
                            pass
                    candidate += timedelta(minutes=self.kickoff_interval)
                if assigned:
                    break
            if not assigned:
                raise ValidationError(_('Insufficient ground availability. Add slots or adjust the daily limit. No partial schedule was saved.'))
        return True

    def action_complete(self):
        require_admin(self.env)
        for t in self:
            if t.state != 'live':
                raise ValidationError(_('Only an in-progress tournament can be completed.'))
            if not t.match_ids or any(m.state not in ('completed', 'walkover', 'bye') for m in t.match_ids):
                raise ValidationError(_('All matches must have official results.'))
            if t.format == 'league':
                if len(t.group_ids) != 1:
                    raise ValidationError(_('A league-only champion requires one group.'))
                table = t.standings()
                if len(table) > 1 and table[0]['rank_key'] == table[1]['rank_key']:
                    raise ValidationError(_('The championship is tied.'))
                t.champion_id = table[0]['team']
            elif not t.champion_id:
                raise ValidationError(_('Complete the knockout final first.'))
            t.state = 'completed'


class Registration(models.Model):
    _name = 'plazy.tournament.registration'
    _description = 'Competition Application'
    _rec_name = 'team_id'

    tournament_id = fields.Many2one('plazy.tournament', required=True, ondelete='cascade', index=True)
    team_id = fields.Many2one('plazy.team', required=True, ondelete='restrict', index=True)
    group_id = fields.Many2one('plazy.tournament.group', ondelete='restrict')
    state = fields.Selection([('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('waitlisted', 'Waitlisted'), ('withdrawn', 'Withdrawn')], default='pending', required=True)
    reason = fields.Text()
    roster_ids = fields.Many2many('plazy.player', string='Competition roster', copy=False)
    _unique_team = models.Constraint('unique(tournament_id, team_id)', 'This team already has an application for this competition.')

    @api.constrains('group_id', 'tournament_id')
    def _check_group_tournament(self):
        for entry in self:
            if entry.group_id and entry.group_id.tournament_id != entry.tournament_id:
                raise ValidationError(_('The assigned group must belong to this tournament.'))

    def _eligible(self):
        for r in self:
            team = r.team_id
            if team.company_id != r.tournament_id.company_id or team.registration_status != 'approved' or not team.required_player_count <= team.joined_player_count <= team.maximum_player_count or team.team_type != r.tournament_id.football_format:
                raise ValidationError(_('Only approved teams with an eligible roster and matching format may enter.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tournament = self.env['plazy.tournament'].browse(vals['tournament_id'])
            tournament._lock()
            if self.search_count([('tournament_id', '=', tournament.id), ('team_id', '=', vals['team_id'])]):
                raise ValidationError(_('This team already has an application for this competition.'))
        records = super().create(vals_list)
        records._eligible()
        for r in records:
            now = fields.Datetime.now()
            if r.tournament_id.state != 'open' or not r.tournament_id.registration_start <= now <= r.tournament_id.registration_end:
                raise ValidationError(_('Tournament registration is closed.'))
        return records

    def write(self, vals):
        require_admin(self.env)
        if {'team_id', 'tournament_id', 'group_id', 'roster_ids', 'state'}.intersection(vals):
            for r in self:
                if r.tournament_id.match_ids:
                    raise ValidationError(_('Applications and groups are locked once fixtures exist.'))
        result = super().write(vals)
        if vals.get('state') == 'approved':
            self._eligible()
            for r in self:
                r.tournament_id._lock()
                if r.tournament_id.approved_count > r.tournament_id.max_teams:
                    raise ValidationError(_('Tournament capacity is full.'))
        return result

    def action_approve(self):
        require_admin(self.env)
        for r in self:
            r.tournament_id._lock()
            r._eligible()
            if r.state not in ('pending', 'waitlisted') or r.tournament_id.match_ids:
                raise ValidationError(_('Only pending applications can be approved before fixtures exist.'))
            if r.tournament_id.approved_count >= r.tournament_id.max_teams:
                r.state = 'waitlisted'
            else:
                r.write({'state': 'approved', 'roster_ids': [(6, 0, r.team_id.player_ids.ids)]})

    def action_reject(self):
        require_admin(self.env)
        for r in self:
            if not r.reason or r.tournament_id.match_ids:
                raise ValidationError(_('Enter a reason. Registrations with fixtures cannot be removed.'))
            r.state = 'rejected'

    def action_withdraw(self):
        require_admin(self.env)
        for r in self:
            if r.state not in ('pending', 'approved', 'waitlisted') or r.tournament_id.match_ids:
                raise ValidationError(_('Applications can only be withdrawn before fixtures are created.'))
            r.state = 'withdrawn'


class Group(models.Model):
    _name = 'plazy.tournament.group'
    _description = 'League Group'
    name = fields.Char(required=True)
    tournament_id = fields.Many2one('plazy.tournament', required=True, ondelete='cascade')
    registration_ids = fields.One2many('plazy.tournament.registration', 'group_id')
    _unique_name = models.Constraint('unique(tournament_id, name)', 'Group names must be unique within a tournament.')


class Venue(models.Model):
    _name = 'plazy.tournament.venue'
    _description = 'Football Ground'
    name = fields.Char(required=True)
    location = fields.Char(required=True)
    slot_ids = fields.One2many('plazy.tournament.slot', 'venue_id')


class Slot(models.Model):
    _name = 'plazy.tournament.slot'
    _description = 'Ground Availability'
    venue_id = fields.Many2one('plazy.tournament.venue', required=True, ondelete='cascade')
    start = fields.Datetime(required=True)
    end = fields.Datetime(required=True)

    @api.constrains('start', 'end')
    def _check_dates(self):
        for slot in self:
            if slot.start >= slot.end:
                raise ValidationError(_('Availability must end after it starts.'))


class Match(models.Model):
    _name = 'plazy.tournament.match'
    _description = 'Football Match'
    _order = 'round_number, kickoff, id'
    _rec_name = 'fixture_key'

    tournament_id = fields.Many2one('plazy.tournament', required=True, ondelete='restrict', index=True)
    fixture_key = fields.Char(required=True, default=lambda s: 'manual:%s' % fields.Datetime.now().isoformat())
    stage = fields.Selection([('league', 'League'), ('knockout', 'Knockout')], default='league', required=True)
    group_id = fields.Many2one('plazy.tournament.group', ondelete='restrict')
    round_number = fields.Integer(default=1)
    home_id = fields.Many2one('plazy.team', ondelete='restrict')
    away_id = fields.Many2one('plazy.team', ondelete='restrict')
    kickoff = fields.Datetime(index=True)
    venue_id = fields.Many2one('plazy.tournament.venue', ondelete='restrict')
    referee = fields.Char()
    duration = fields.Integer(default=40, required=True)
    state = fields.Selection([(x, x.title()) for x in ('scheduled', 'live', 'completed', 'postponed', 'cancelled', 'abandoned', 'walkover', 'bye')], default='scheduled', required=True)
    published = fields.Boolean(default=False)
    home_score = fields.Integer()
    away_score = fields.Integer()
    extra_home = fields.Integer()
    extra_away = fields.Integer()
    penalties_home = fields.Integer()
    penalties_away = fields.Integer()
    result_entered = fields.Boolean(string='Scores entered')
    result_kind = fields.Selection([('completed', 'Played match'), ('walkover', 'Walkover')], default='completed', required=True)
    winner_id = fields.Many2one('plazy.team', readonly=True, copy=False)
    completed_at = fields.Datetime(readonly=True, copy=False)
    notes = fields.Text()
    correction_reason = fields.Text(copy=False)
    next_match_id = fields.Many2one('plazy.tournament.match', ondelete='restrict', copy=False)
    next_slot = fields.Selection([('home', 'Home'), ('away', 'Away')])
    loser_match_id = fields.Many2one('plazy.tournament.match', ondelete='restrict', copy=False)
    loser_slot = fields.Selection([('home', 'Home'), ('away', 'Away')])
    is_bye = fields.Boolean(readonly=True, copy=False)
    is_third_place = fields.Boolean(readonly=True, copy=False)
    reserved_minutes = fields.Integer(compute='_compute_reserved_minutes')
    round_label = fields.Char(compute='_compute_round_label')
    audit_ids = fields.One2many('plazy.match.result.audit', 'match_id')
    _fixture_unique = models.Constraint('unique(tournament_id, fixture_key)', 'This fixture already exists.')

    @api.depends('duration', 'stage', 'tournament_id.knockout_buffer')
    def _compute_reserved_minutes(self):
        for match in self:
            match.reserved_minutes = match.duration + (match.tournament_id.knockout_buffer if match.stage == 'knockout' else 0)

    @api.depends('stage', 'round_number', 'is_third_place', 'tournament_id.match_ids.round_number')
    def _compute_round_label(self):
        for match in self:
            final_round = max(match.tournament_id.match_ids.filtered(lambda m: m.stage == 'knockout').mapped('round_number'), default=match.round_number)
            size = 2 ** max(1, final_round - match.round_number + 1)
            match.round_label = 'Third place' if match.is_third_place else 'League round %s' % match.round_number if match.stage == 'league' else {2: 'Final', 4: 'Semifinal', 8: 'Quarterfinal', 16: 'Round of 16', 32: 'Round of 32'}.get(size, 'Knockout')

    def _advance_bye(self):
        self.ensure_one()
        if not self.is_bye or bool(self.home_id) == bool(self.away_id) or not self.next_match_id:
            raise ValidationError(_('A bye must have one participant and a following round.'))
        winner = self.home_id or self.away_id
        super(Match, self).write({'state': 'bye', 'winner_id': winner.id})
        self.next_match_id.write({self.next_slot + '_id': winner.id})

    @api.model_create_multi
    def create(self, vals_list):
        require_admin(self.env)
        for vals in vals_list:
            if vals.get('state', 'scheduled') not in ('scheduled', 'postponed'):
                raise ValidationError(_('Create a draft fixture before confirming results.'))
            if 'duration' not in vals:
                vals['duration'] = self.env['plazy.tournament'].browse(vals['tournament_id']).duration
        return super().create(vals_list)

    @api.constrains('home_id', 'away_id', 'tournament_id', 'group_id', 'stage', 'duration', 'home_score', 'away_score', 'extra_home', 'extra_away', 'penalties_home', 'penalties_away')
    def _validate_match(self):
        for m in self:
            if m.duration < 1 or any(m[f] < 0 for f in ('home_score', 'away_score', 'extra_home', 'extra_away', 'penalties_home', 'penalties_away')):
                raise ValidationError(_('Duration must be positive and scores cannot be negative.'))
            if m.home_id and m.home_id == m.away_id:
                raise ValidationError(_('A team cannot play itself.'))
            approved = m.tournament_id.registration_ids.filtered(lambda r: r.state == 'approved').mapped('team_id')
            if (m.home_id | m.away_id) - approved:
                raise ValidationError(_('Both teams must be approved competition entrants.'))
            if m.group_id and m.group_id.tournament_id != m.tournament_id:
                raise ValidationError(_('Group belongs to a different tournament.'))
            if m.stage == 'league':
                members = m.group_id.registration_ids.filtered(lambda r: r.state == 'approved').mapped('team_id')
                if not m.group_id or (m.home_id | m.away_id) - members:
                    raise ValidationError(_('League teams must be approved members of the selected group.'))
            elif m.group_id:
                raise ValidationError(_('Knockout fixtures cannot belong to a league group.'))

    @api.constrains('kickoff', 'venue_id', 'duration', 'home_id', 'away_id', 'state', 'referee')
    def _check_schedule(self):
        # Serialize scheduling globally so concurrent venue/team allocations cannot overlap.
        self.env.cr.execute('SELECT pg_advisory_xact_lock(72419021)')
        for m in self:
            if not m.kickoff or not m.venue_id or m.state in ('cancelled', 'postponed', 'bye'):
                continue
            end = m.kickoff + timedelta(minutes=m.reserved_minutes)
            predecessors = self.search([('kickoff', '!=', False), '|', ('next_match_id', '=', m.id), ('loser_match_id', '=', m.id)])
            if any(p.kickoff + timedelta(minutes=p.reserved_minutes + m.tournament_id.rest_minutes) > m.kickoff for p in predecessors):
                raise ValidationError(_('A knockout round must follow its feeder matches and rest period.'))
            if any(target.kickoff and end + timedelta(minutes=m.tournament_id.rest_minutes) > target.kickoff for target in (m.next_match_id | m.loser_match_id)):
                raise ValidationError(_('This fixture would overlap its next knockout round.'))
            if m.kickoff < m.tournament_id.start_date or end > m.tournament_id.end_date:
                raise ValidationError(_('Kickoff is outside the competition dates.'))
            if not m.venue_id.slot_ids.filtered(lambda s: s.start <= m.kickoff and s.end >= end):
                raise ValidationError(_('No ground availability covers this match.'))
            day = m.tournament_id._local_day(m.kickoff)
            same_day = m.tournament_id.match_ids.filtered(lambda match: match.kickoff and match.state not in ('cancelled', 'postponed', 'bye') and m.tournament_id._local_day(match.kickoff) == day)
            if len(same_day) > m.tournament_id.max_matches_day:
                raise ValidationError(_('The tournament daily match limit is exceeded.'))
            others = self.sudo().search([('id', '!=', m.id), ('kickoff', '!=', False), ('state', 'not in', ['cancelled', 'postponed', 'bye'])])
            for other in others:
                rest = max(m.tournament_id.rest_minutes, other.tournament_id.rest_minutes)
                same_team = bool((m.home_id | m.away_id) & (other.home_id | other.away_id))
                buffer = timedelta(minutes=rest if same_team else 0)
                same_referee = bool(m.referee and m.referee.strip().casefold() == (other.referee or '').strip().casefold())
                if (same_team or same_referee or m.venue_id == other.venue_id) and m.kickoff < other.kickoff + timedelta(minutes=other.reserved_minutes) + buffer and end + buffer > other.kickoff:
                    raise ValidationError(_('This time conflicts with another fixture, referee assignment or required team rest.'))

    def write(self, vals):
        require_admin(self.env)
        protected = {'state', 'result_kind', 'published', 'tournament_id', 'stage', 'group_id', 'next_match_id', 'next_slot', 'loser_match_id', 'loser_slot', 'is_bye', 'is_third_place', 'home_score', 'away_score', 'extra_home', 'extra_away', 'penalties_home', 'penalties_away', 'home_id', 'away_id', 'winner_id', 'completed_at'}
        if protected.intersection(vals) and any(m.state in ('completed', 'walkover') for m in self):
            raise ValidationError(_('Reopen the result with a correction reason before editing an official result.'))
        if (protected - {'published'}).intersection(vals) and any(m.state == 'bye' for m in self):
            raise ValidationError(_('A generated bye cannot be edited as a played match.'))
        if vals.get('state') in ('completed', 'walkover', 'bye'):
            raise ValidationError(_('Use Confirm Result to finalize official scores.'))
        changed = self.filtered('published') if {'kickoff', 'venue_id', 'duration', 'state'}.intersection(vals) else self.browse()
        if changed and not all(m.correction_reason or vals.get('correction_reason') for m in changed):
            raise ValidationError(_('Enter a change reason before changing a published fixture.'))
        result = super().write(vals)
        for match in changed:
            self.env['plazy.match.result.audit'].create({'match_id': match.id, 'description': 'Published fixture changed: %s. Reason: %s' % (', '.join(sorted(vals)), match.correction_reason)})
            recipients = (match.home_id | match.away_id).mapped('email')
            if recipients:
                self.env['mail.mail'].sudo().create({'subject': 'PLAZY fixture updated', 'body_html': '<p>A published fixture has changed. Please check your PLAZY match centre for the latest details.</p>', 'email_to': ','.join(recipients), 'email_from': self.env.company.email or self.env.user.email})
        return result

    def action_confirm(self):
        require_admin(self.env)
        for m in self:
            m.tournament_id._lock()
            m.invalidate_recordset()
            if m.state in ('completed', 'walkover', 'bye'):
                continue
            if m.state not in ('scheduled', 'live'):
                raise ValidationError(_('Reschedule a stopped or cancelled match before confirming a result.'))
            if not m.result_entered or not m.home_id or not m.away_id or not m.published or m.tournament_id.state not in ('scheduled', 'live'):
                raise ValidationError(_('Publish a scheduled match with both teams and enter its scores first.'))
            if m.result_kind == 'walkover' and (not m.notes or m.home_score == m.away_score or m.extra_home or m.extra_away or m.penalties_home or m.penalties_away):
                raise ValidationError(_('A walkover needs a reason and a decisive awarded regulation score.'))
            home, away = m.home_score + m.extra_home, m.away_score + m.extra_away
            if m.stage == 'league' and (m.extra_home or m.extra_away or m.penalties_home or m.penalties_away):
                raise ValidationError(_('League matches do not use extra time or penalties.'))
            if m.stage == 'knockout' and home == away:
                if m.penalties_home == m.penalties_away:
                    raise ValidationError(_('A tied knockout match needs a decisive penalty score.'))
                home, away = m.penalties_home, m.penalties_away
            elif m.penalties_home or m.penalties_away:
                raise ValidationError(_('Penalty shootouts are only valid after a tied knockout score.'))
            winner = m.home_id if home > away else m.away_id if away > home else self.env['plazy.team']
            if m.next_match_id:
                target = m.next_match_id
                if target.state != 'scheduled':
                    raise ValidationError(_('The next round has already started.'))
                if target[m.next_slot + '_id'] and target[m.next_slot + '_id'] != winner:
                    raise ValidationError(_('The next-round participant conflicts with this result.'))
                target.write({m.next_slot + '_id': winner.id})
            if m.loser_match_id:
                loser = (m.home_id | m.away_id) - winner
                target = m.loser_match_id
                if target.state != 'scheduled' or (target[m.loser_slot + '_id'] and target[m.loser_slot + '_id'] != loser):
                    raise ValidationError(_('The third-place fixture is already started or has a conflicting participant.'))
                target.write({m.loser_slot + '_id': loser.id})
            super(Match, m).write({'state': m.result_kind, 'winner_id': winner.id, 'completed_at': fields.Datetime.now()})
            self.env['plazy.match.result.audit'].create({'match_id': m.id, 'description': 'Confirmed: %s-%s; extra %s-%s; penalties %s-%s' % (m.home_score, m.away_score, m.extra_home, m.extra_away, m.penalties_home, m.penalties_away)})
            m.tournament_id.state = 'live'
            if m.stage == 'knockout' and not m.next_match_id and not m.is_third_place:
                m.tournament_id.champion_id = winner

    def action_live(self):
        require_admin(self.env)
        if any(m.state != 'scheduled' or not m.home_id or not m.away_id or not m.published for m in self):
            raise ValidationError(_('Only published scheduled matches with both teams can start.'))
        self.write({'state': 'live', 'correction_reason': 'Kickoff confirmed'})

    def action_postpone(self):
        self.write({'state': 'postponed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_abandon(self):
        self.write({'state': 'abandoned'})

    def action_reschedule(self):
        self.write({'state': 'scheduled'})

    def action_reopen(self):
        require_admin(self.env)
        for m in self:
            m.tournament_id._lock()
            if m.state not in ('completed', 'walkover') or not m.correction_reason:
                raise ValidationError(_('Enter a reason to reopen a finalized result.'))
            if any(target.published or target.state != 'scheduled' for target in (m.next_match_id | m.loser_match_id)):
                raise ValidationError(_('Published or started downstream fixtures block correction. Administrator adjudication is required.'))
            if m.stage == 'league' and m.tournament_id.match_ids.filtered(lambda x: x.stage == 'knockout'):
                raise ValidationError(_('A knockout bracket already depends on these standings.'))
            self.env['plazy.match.result.audit'].create({'match_id': m.id, 'description': 'Reopened %s-%s; extra %s-%s; penalties %s-%s. Reason: %s' % (m.home_score, m.away_score, m.extra_home, m.extra_away, m.penalties_home, m.penalties_away, m.correction_reason)})
            if m.next_match_id:
                m.next_match_id.write({m.next_slot + '_id': False})
            if m.loser_match_id:
                m.loser_match_id.write({m.loser_slot + '_id': False})
            if m.group_id and any(m.group_id.registration_ids.mapped('tie_order')):
                m.group_id.registration_ids._apply_tie_order(0)
                m.tournament_id._event('tie_invalidated', 'Result correction invalidated the tie decision in %s.' % m.group_id.name)
            super(Match, m).write({'state': 'scheduled', 'winner_id': False, 'completed_at': False})
            m.tournament_id.write({'champion_id': False, 'state': 'live'})

    def _dependent_matches(self):
        self.ensure_one()
        result = self.browse()
        pending = self.next_match_id | self.loser_match_id
        while pending:
            result |= pending
            pending = (pending.mapped('next_match_id') | pending.mapped('loser_match_id')) - result
        return result.sorted(lambda m: (m.round_number, m.id))

    def action_prepare_correction(self):
        require_admin(self.env)
        self.ensure_one()
        self.tournament_id._lock()
        if self.stage != 'knockout' or self.state not in ('completed', 'walkover') or not (self.correction_reason or '').strip():
            raise ValidationError(_('Choose a finalized knockout result and enter the correction reason.'))
        dependent = self._dependent_matches()
        if any(m.state != 'scheduled' for m in dependent):
            raise ValidationError(_('A dependent match has started or been resolved. Formal adjudication is required; no fixtures were changed.'))
        self.tournament_id._event('correction_review', 'Unpublishing dependent fixtures %s for match %s. Reason: %s' % (dependent.ids, self.fixture_key, self.correction_reason))
        dependent.write({'published': False})
        recipients = (dependent.mapped('home_id') | dependent.mapped('away_id')).mapped('email')
        if recipients:
            self.env['mail.mail'].sudo().create({'subject': 'PLAZY bracket under review', 'body_html': '<p>Dependent fixtures have been unpublished while an official result is corrected. Please wait for the revised schedule.</p>', 'email_to': ','.join(recipients), 'email_from': self.env.company.email or self.env.user.email})
        self.action_reopen()

    @api.constrains('next_match_id', 'next_slot', 'loser_match_id', 'loser_slot', 'round_number', 'tournament_id')
    def _check_progression(self):
        for match in self:
            for target, slot in [(match.next_match_id, match.next_slot), (match.loser_match_id, match.loser_slot)]:
                if not target:
                    continue
                if target.tournament_id != match.tournament_id or target.round_number <= match.round_number or not slot:
                    raise ValidationError(_('Progression must point to a later round in the same tournament.'))
                sources = self.search(['|', ('next_match_id', '=', target.id), ('loser_match_id', '=', target.id)])
                count = sum(int(s.next_match_id == target and s.next_slot == slot) + int(s.loser_match_id == target and s.loser_slot == slot) for s in sources)
                if count > 1:
                    raise ValidationError(_('Two fixtures cannot feed the same participant slot.'))

    def unlink(self):
        if any(m.published or m.audit_ids for m in self):
            raise ValidationError(_('Published or audited matches cannot be deleted.'))
        return super().unlink()


class ResultAudit(models.Model):
    _name = 'plazy.match.result.audit'
    _description = 'Official Result Audit'
    _order = 'create_date desc, id desc'
    match_id = fields.Many2one('plazy.tournament.match', required=True, ondelete='restrict')
    description = fields.Text(required=True)

    def write(self, vals):
        raise AccessError(_('Result audit entries cannot be edited.'))

    def unlink(self):
        raise AccessError(_('Result audit entries cannot be deleted.'))
