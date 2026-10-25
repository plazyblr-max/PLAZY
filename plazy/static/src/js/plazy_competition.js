/** @odoo-module **/

/* global owl */

owl.whenReady(() => {
    const input = document.querySelector('#pz-invite-email');
    if (!input) return;
    const output = document.createElement('div');
    output.setAttribute('aria-live', 'polite');
    output.id = 'pz-player-suggestions';
    input.setAttribute('aria-controls', output.id);
    input.after(output);
    let timer;
    let controller;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        controller?.abort();
        output.replaceChildren();
        const email = input.value.trim();
        if (email.length < 3) return;
        const completeEmail = input.checkValidity();
        timer = setTimeout(async () => {
            controller = new AbortController();
            output.textContent = 'Checking player...';
            try {
                const response = await fetch(completeEmail ? '/plazy/team/player-email-validation' : '/plazy/team/players/search', {
                    method: 'POST', signal: controller.signal,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {email}, id: Date.now()}),
                });
                const {result} = await response.json();
                if (input.value.trim() !== email) return;
                output.replaceChildren();
                if (!response.ok || !result || (completeEmail && !result.valid)) {
                    output.textContent = result?.message || 'Unable to check this player. Try again.';
                    return;
                }
                const players = completeEmail ? (result.player ? [result.player] : [null]) : (result.players || []);
                if (!players.length) output.textContent = result.message || 'No discoverable players found. Enter a complete email to invite someone.';
                for (const player of players) {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'pz-player-result';
                    button.textContent = player ? `${player.name} · ${player.email} · ${player.position || 'Player'} · Available` : 'Invite New Player';
                    button.addEventListener('click', () => {
                        if (player) {
                            input.value = player.email;
                            const name = input.form.elements.namedItem('player_name');
                            if (name) name.value = player.name;
                            const position = input.form.querySelector(`input[name="position"][value="${CSS.escape(player.position)}"]`);
                            if (position) position.checked = true;
                        }
                        output.textContent = player ? 'Existing player selected. They will receive an invitation to accept.' : 'Continue to invite a new player.';
                        input.focus();
                    });
                    output.append(button);
                }
            } catch (error) {
                if (error.name !== 'AbortError') output.textContent = 'Unable to check this player. Please try again.';
            }
        }, 450);
    });
    input.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' && output.querySelector('button')) {
            event.preventDefault();
            output.querySelector('button').focus();
        }
    });
    output.addEventListener('keydown', event => {
        const buttons = [...output.querySelectorAll('button')];
        const index = buttons.indexOf(document.activeElement);
        if (event.key === 'Escape') { output.replaceChildren(); input.focus(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
        }
    });
});
