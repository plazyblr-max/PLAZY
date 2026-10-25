/** @odoo-module **/

/* global owl */

const {Component, mount, onWillStart, proxy, t, useProps, xml} = owl;

class PlazyAdminPortal extends Component {
    props = useProps({
        csrfToken: t.string(),
        adminName: t.string(),
    });

    setup() {
        this.state = proxy({
            view: 'overview', summary: {}, records: [], detail: null,
            query: '', status: '', sort: 'recent', page: 1, pages: 1,
            loading: true, message: '', error: '',
        });
        this.csrfToken = this.props.csrfToken;
        onWillStart(() => this.loadSummary());
    }

    async rpc(route, params = {}) {
        const response = await fetch(route, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params, id: Date.now()}),
        });
        const payload = await response.json();
        if (!response.ok || payload.error) throw new Error(payload.error?.data?.message || 'The request could not be completed.');
        return payload.result;
    }

    async loadSummary() {
        this.state.loading = true;
        try {
            this.state.summary = await this.rpc('/plazy/admin/portal/summary');
        } catch (error) {
            this.state.error = error.message;
        } finally {
            this.state.loading = false;
        }
    }

    async loadRecords() {
        this.state.loading = true;
        this.state.error = '';
        try {
            const result = await this.rpc('/plazy/admin/portal/records', {
                entity: this.state.view, query: this.state.query, status: this.state.status,
                sort: this.state.sort, page: this.state.page,
            });
            this.state.records = result.records;
            this.state.page = result.page;
            this.state.pages = result.pages;
        } catch (error) {
            this.state.error = error.message;
        } finally {
            this.state.loading = false;
        }
    }

    async selectView(view) {
        this.state.view = view;
        this.state.detail = null;
        this.state.query = '';
        this.state.status = '';
        this.state.sort = 'recent';
        this.state.page = 1;
        this.state.message = '';
        if (view === 'overview') return this.loadSummary();
        return this.loadRecords();
    }

    async openDetail(record) {
        try {
            this.state.detail = await this.rpc('/plazy/admin/portal/detail', {
                entity: this.state.view, record_id: record.id,
            });
        } catch (error) {
            this.state.error = error.message;
        }
    }

    async updateTeam(action) {
        const team = this.state.detail;
        const reason = action === 'reject' ? window.prompt('Why is this team being rejected?') : '';
        if (action === 'reject' && !reason?.trim()) return;
        await this.runAction('/plazy/admin/portal/team-action', {team_id: team.id, action, reason});
    }

    async updateTournament(action) {
        const tournament = this.state.detail;
        const reason = ['postpone', 'cancel'].includes(action) ? window.prompt(`Reason to ${action} this tournament:`) : '';
        if (['postpone', 'cancel'].includes(action) && !reason?.trim()) return;
        await this.runAction('/plazy/admin/portal/tournament-action', {tournament_id: tournament.id, action, reason});
    }

    async runAction(route, params) {
        this.state.error = '';
        try {
            const result = await this.rpc(route, params);
            if (!result.ok) {
                this.state.error = result.message;
                return;
            }
            this.state.message = result.message;
            this.state.detail = null;
            await this.loadSummary();
            if (this.state.view !== 'overview') await this.loadRecords();
        } catch (error) {
            this.state.error = error.message;
        }
    }

    async search() {
        this.state.page = 1;
        await this.loadRecords();
    }

    async setFilter(field, event) {
        this.state[field] = event.target.value;
        await this.search();
    }

    async changePage(delta) {
        const page = this.state.page + delta;
        if (page < 1 || page > this.state.pages) return;
        this.state.page = page;
        await this.loadRecords();
    }

    recordTitle(record) {
        return record.name || `${record.home} vs ${record.away}`;
    }

    recordMeta(record) {
        if (this.state.view === 'players') return `${record.position || 'Player'} · ${record.teams.length ? record.teams.map(team => team.name).join(', ') : 'Available'}`;
        if (this.state.view === 'fixtures') return `${record.tournament} · ${record.kickoff || 'Kickoff pending'}`;
        if (this.state.view === 'tournaments') return `${record.location} · ${record.approved_count}/${record.max_teams} teams`;
        return `${record.manager_name || 'Manager not set'} · ${record.joined_players}/${record.required_players} players`;
    }

    recordStatus(record) {
        return record.status || record.state || (record.active ? 'active' : 'pending');
    }

    icon() {
        return {players: 'fa-user', teams: 'fa-users', approvals: 'fa-check-circle', tournaments: 'fa-trophy', fixtures: 'fa-calendar'}[this.state.view] || 'fa-th-large';
    }

    statusChoices() {
        if (['teams', 'approvals'].includes(this.state.view)) return [['', 'All statuses'], ['waiting', 'Waiting'], ['approved', 'Approved'], ['rejected', 'Rejected']];
        if (['tournaments', 'fixtures'].includes(this.state.view)) return [['', 'All statuses'], ['draft', 'Draft'], ['open', 'Open'], ['scheduled', 'Scheduled'], ['live', 'Live'], ['completed', 'Completed'], ['cancelled', 'Cancelled']];
        return [['', 'All players']];
    }

    tournamentActions() {
        const state = this.state.detail?.state;
        return {
            draft: [['open', 'Open registration'], ['cancel', 'Cancel']],
            open: [['close', 'Close registration'], ['cancel', 'Cancel']],
            closed: [['league', 'Generate league'], ['knockout', 'Generate knockout'], ['schedule', 'Auto schedule'], ['publish', 'Publish fixtures'], ['cancel', 'Cancel']],
            scheduled: [['schedule', 'Auto schedule'], ['publish', 'Publish fixtures'], ['complete', 'Complete'], ['postpone', 'Postpone'], ['cancel', 'Cancel']],
            live: [['complete', 'Complete'], ['postpone', 'Postpone'], ['cancel', 'Cancel']],
            postponed: [['resume', 'Resume'], ['cancel', 'Cancel']],
        }[state] || [];
    }

    hasItems(key) {
        return Boolean(this.state.detail && this.state.detail[key] && this.state.detail[key].length);
    }

    static template = xml`
        <div class="pz-admin-shell">
            <t t-set="state" t-value="this.state"/>
            <t t-set="selectView" t-value="this.selectView.bind(this)"/>
            <t t-set="openDetail" t-value="this.openDetail.bind(this)"/>
            <t t-set="updateTeam" t-value="this.updateTeam.bind(this)"/>
            <t t-set="updateTournament" t-value="this.updateTournament.bind(this)"/>
            <t t-set="search" t-value="this.search.bind(this)"/>
            <t t-set="setFilter" t-value="this.setFilter.bind(this)"/>
            <t t-set="changePage" t-value="this.changePage.bind(this)"/>
            <t t-set="recordTitle" t-value="this.recordTitle.bind(this)"/>
            <t t-set="recordMeta" t-value="this.recordMeta.bind(this)"/>
            <t t-set="recordStatus" t-value="this.recordStatus.bind(this)"/>
            <t t-set="icon" t-value="this.icon.bind(this)"/>
            <t t-set="statusChoices" t-value="this.statusChoices.bind(this)"/>
            <t t-set="tournamentActions" t-value="this.tournamentActions.bind(this)"/>
            <t t-set="hasItems" t-value="this.hasItems.bind(this)"/>
            <header class="pz-admin-topbar">
                <div><p class="pz-admin-kicker">PLAZY COMMAND CENTRE</p><h1>Hi, <t t-esc="this.props.adminName"/>.</h1><p>Monitor your community, teams, competitions, and match activity.</p></div>
                <a class="pz-admin-back" href="/plazy/admin/choose"><i class="fa fa-arrow-left"/> Admin menu</a>
            </header>
            <nav class="pz-admin-nav" aria-label="Admin portal sections">
                <button t-foreach="[['overview', 'Overview'], ['players', 'Players'], ['teams', 'Teams'], ['approvals', 'Approvals'], ['tournaments', 'Tournaments'], ['fixtures', 'Fixtures']]" t-as="tab" t-key="tab[0]" t-att-class="state.view === tab[0] ? 'is-active' : ''" t-on-click="() => selectView(tab[0])" t-esc="tab[1]"/>
            </nav>
            <p t-if="state.message" role="status" class="pz-admin-glass pz-admin-section" t-esc="state.message"/>
            <p t-if="state.error" role="alert" class="pz-admin-error" t-esc="state.error"/>
            <t t-if="state.view === 'overview'">
                <section class="pz-admin-stat-grid" t-if="!state.loading">
                    <button class="pz-admin-stat" t-on-click="() => selectView('players')"><i class="fa fa-user"/><strong t-esc="state.summary.players || 0"/><span>Registered players</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('teams')"><i class="fa fa-users"/><strong t-esc="state.summary.teams || 0"/><span>Registered teams</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('approvals')"><i class="fa fa-check-circle"/><strong t-esc="state.summary.pending_approvals || 0"/><span>Pending approvals</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('teams')"><i class="fa fa-shield"/><strong t-esc="state.summary.approved_teams || 0"/><span>Approved teams</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('teams')"><i class="fa fa-times-circle"/><strong t-esc="state.summary.rejected_teams || 0"/><span>Rejected teams</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('tournaments')"><i class="fa fa-trophy"/><strong t-esc="state.summary.tournaments || 0"/><span>Total tournaments</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('tournaments')"><i class="fa fa-play-circle"/><strong t-esc="state.summary.active_tournaments || 0"/><span>Active tournaments</span></button>
                    <button class="pz-admin-stat" t-on-click="() => selectView('fixtures')"><i class="fa fa-calendar"/><strong t-esc="state.summary.fixtures || 0"/><span>Fixtures · <t t-esc="state.summary.live_fixtures || 0"/> live</span></button>
                </section>
                <section class="pz-admin-glass pz-admin-section"><div class="pz-admin-section-head"><h2>Recent fixtures</h2><button class="pz-admin-action" t-on-click="() => selectView('fixtures')">View all fixtures</button></div><div class="pz-admin-fixtures"><div t-foreach="state.summary.recent_fixtures || []" t-as="fixture" t-key="fixture.id" class="pz-admin-fixture"><strong t-esc="fixture.home"/><span class="pz-admin-score" t-esc="fixture.score"/><strong t-esc="fixture.away"/><span t-attf-class="pz-admin-badge is-#{fixture.state}" t-esc="fixture.state"/></div><p t-if="!(state.summary.recent_fixtures || []).length" class="pz-admin-empty">No fixtures have been created yet.</p></div></section>
            </t>
            <section t-else="" class="pz-admin-glass pz-admin-section">
                <div class="pz-admin-section-head"><h2><t t-esc="state.view.charAt(0).toUpperCase() + state.view.slice(1)"/></h2><div class="pz-admin-controls"><input t-att-value="state.query" t-on-input="(event) => setFilter('query', event)" type="search" placeholder="Search records"/><select t-att-value="state.status" t-on-change="(event) => setFilter('status', event)"><option t-foreach="statusChoices()" t-as="choice" t-key="choice[0]" t-att-value="choice[0]" t-esc="choice[1]"/></select><select t-att-value="state.sort" t-on-change="(event) => setFilter('sort', event)"><option value="recent">Most recent</option><option value="name">Name A–Z</option></select></div></div>
                <p t-if="state.loading" class="pz-admin-empty">Loading records…</p>
                <div t-else="" class="pz-admin-record-grid"><button t-foreach="state.records" t-as="record" t-key="record.id" class="pz-admin-record" t-on-click="() => openDetail(record)"><span class="pz-admin-icon"><i t-attf-class="fa #{icon()}"/></span><h3 t-esc="recordTitle(record)"/><p t-esc="recordMeta(record)"/><small><span t-attf-class="pz-admin-badge is-#{recordStatus(record)}" t-esc="recordStatus(record)"/></small></button></div>
                <p t-if="!state.loading &amp;&amp; !state.records.length" class="pz-admin-empty">No matching records.</p>
                <div class="pz-admin-pagination"><button t-att-disabled="state.page &lt;= 1" t-on-click="() => changePage(-1)">Previous</button><span>Page <t t-esc="state.page"/> of <t t-esc="state.pages"/></span><button t-att-disabled="state.page >= state.pages" t-on-click="() => changePage(1)">Next</button></div>
            </section>
            <div t-if="state.detail" class="pz-admin-modal" t-on-click="() => state.detail = null"><article class="pz-admin-modal-card" t-on-click.stop=""><header class="pz-admin-modal-head"><div><span t-attf-class="pz-admin-badge is-#{recordStatus(state.detail)}" t-esc="recordStatus(state.detail)"/><h2 t-esc="recordTitle(state.detail)"/></div><button class="pz-admin-close" aria-label="Close details" t-on-click="() => state.detail = null">×</button></header><div class="pz-admin-detail-grid"><div t-if="state.detail.email"><small>Email</small><span t-esc="state.detail.email"/></div><div t-if="state.detail.mobile"><small>Mobile</small><span t-esc="state.detail.mobile"/></div><div t-if="state.detail.location"><small>Location</small><span t-esc="state.detail.location"/></div><div t-if="state.detail.kickoff"><small>Kickoff</small><span t-esc="state.detail.kickoff"/></div><div t-if="state.detail.start_date"><small>Dates</small><span><t t-esc="state.detail.start_date"/> – <t t-esc="state.detail.end_date"/></span></div><div t-if="state.detail.score"><small>Score</small><span t-esc="state.detail.score"/></div></div><div t-if="hasItems('players')"><h3>Players</h3><p t-foreach="state.detail.players" t-as="player" t-key="player.id"><t t-esc="player.name"/> · <t t-esc="player.position || 'Player'"/></p></div><div t-if="hasItems('registrations')"><h3>Applications</h3><p t-foreach="state.detail.registrations" t-as="registration" t-key="registration.team"><t t-esc="registration.team"/> · <t t-esc="registration.state"/></p></div><div t-if="hasItems('fixtures')"><h3>Fixtures</h3><p t-foreach="state.detail.fixtures" t-as="fixture" t-key="fixture.id"><t t-esc="fixture.home"/> <t t-esc="fixture.score"/> <t t-esc="fixture.away"/></p></div><div class="pz-admin-actions" t-if="state.view === 'approvals' || state.view === 'teams'"><button t-if="state.detail.status === 'waiting'" class="pz-admin-action is-primary" t-on-click="() => updateTeam('approve')">Approve team</button><button t-if="state.detail.status === 'waiting'" class="pz-admin-action" t-on-click="() => updateTeam('reject')">Reject team</button></div><div class="pz-admin-actions" t-if="state.view === 'tournaments'"><button t-foreach="tournamentActions()" t-as="action" t-key="action[0]" t-att-class="action[0] === 'open' ? 'pz-admin-action is-primary' : 'pz-admin-action'" t-on-click="() => updateTournament(action[0])" t-esc="action[1]"/></div></article></div>
        </div>`;
}

owl.whenReady(() => {
    const target = document.getElementById('plazy-admin-portal');
    if (target) mount(PlazyAdminPortal, target, {props: {csrfToken: target.dataset.csrfToken, adminName: target.dataset.adminName}});
});
