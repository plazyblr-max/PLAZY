/** @odoo-module **/

/* global owl */

class PlazyOnboarding {
    constructor(form) {
        this.form = form;
        this.mode = form.dataset.onboarding;
        this.steps = [...form.querySelectorAll('[data-step]')];
        this.index = 0;
        this.busy = false;
        this.dirty = false;
        this.logoURL = null;
        this.logoCheck = Promise.resolve();
        this.next = form.querySelector('[data-step-next]');
        this.back = form.querySelector('[data-step-back]');
        this.submit = form.querySelector('[data-step-submit]');
        this.error = form.querySelector('[data-onboarding-error]');
        this.progress = form.querySelector('progress');
        this.progressLabel = form.querySelector('[data-progress-label]');
        this.storageKey = 'plazy:onboarding:v1:' + this.mode;
        this.restoreDraft();
        form.noValidate = true;
        form.classList.add('is-guided');
        form.querySelector('.pz-progress-header').hidden = false;
        this.progress.hidden = false;
        this.next.addEventListener('click', () => this.advance());
        this.back.addEventListener('click', () => this.show(this.index - 1));
        form.addEventListener('submit', event => {
            event.preventDefault();
            if (this.index < this.steps.length - 1) this.advance();
            else this.send();
        });
        form.addEventListener('keydown', event => {
            if (event.key === 'Enter' && event.target.matches('input:not([type="file"]):not([type="radio"])') && !event.isComposing) {
                if (event.target.hasAttribute('list')) return;
                event.preventDefault();
                this.index === this.steps.length - 1 ? this.send() : this.advance();
            }
        });
        form.addEventListener('input', event => {
            if (event.target.matches('input')) event.target.setCustomValidity('');
            this.dirty = true;
            this.saveDraft();
            this.syncPreview();
        });
        form.addEventListener('change', () => {
            this.dirty = true;
            this.saveDraft();
        });
        form.querySelectorAll('[data-onboarding-toggle]').forEach(button => {
            button.addEventListener('click', () => {
                const input = form.querySelector('#' + button.dataset.onboardingToggle);
                const visible = input.type === 'password';
                input.type = visible ? 'text' : 'password';
                button.setAttribute('aria-pressed', String(visible));
                button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
                button.title = visible ? 'Hide password' : 'Show password';
            });
        });
        const file = form.elements.namedItem('logo');
        file?.addEventListener('change', () => { this.logoCheck = this.previewLogo(file); });
        form.querySelector('[data-remove-logo]')?.addEventListener('click', () => {
            file.value = '';
            file.setCustomValidity('');
            this.clearLogo();
        });
        this.beforeUnload = event => {
            if (this.dirty && !this.busy) {
                event.preventDefault();
                event.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', this.beforeUnload);
        window.addEventListener('pageshow', () => {
            this.busy = false;
            form.removeAttribute('aria-busy');
            this.controls();
        });
        this.syncPreview();
        this.show(form.querySelector('.pz-server-error') ? this.steps.length - 1 : this.index, false);
    }

    restoreDraft() {
        // Persist only non-sensitive registration fields. Invitations stay in memory.
        if (!['team', 'player'].includes(this.mode) || this.form.querySelector('.pz-server-error')) return;
        try {
            const draft = JSON.parse(sessionStorage.getItem(this.storageKey) || 'null');
            if (!draft || Date.now() - draft.saved > 86400000) return;
            for (const input of this.form.querySelectorAll('[data-review-label]')) {
                if (!(input.name in draft.values)) continue;
                if (input.type === 'radio') input.checked = input.value === draft.values[input.name];
                else input.value = draft.values[input.name];
            }
            this.index = Math.min(Math.max(Number(draft.step) || 0, 0), this.steps.length - 1);
            this.dirty = true;
            const notice = document.createElement('p');
            notice.className = 'pz-draft-note';
            notice.textContent = 'Your draft is back. Please re-enter your password' + (draft.hadLogo ? ' and choose your logo again.' : ' before creating your account.');
            this.form.querySelector('.pz-progress').after(notice);
        } catch { /* Browser storage is optional. */ }
    }

    saveDraft() {
        if (!['team', 'player'].includes(this.mode)) return;
        const values = {};
        for (const input of this.form.querySelectorAll('[data-review-label]')) {
            if (input.type !== 'radio' || input.checked) values[input.name] = input.value;
        }
        try {
            sessionStorage.setItem(this.storageKey, JSON.stringify({values, step: this.index, saved: Date.now(), hadLogo: Boolean(this.form.elements.namedItem('logo')?.files.length)}));
        } catch { /* Optional recovery must not block registration. */ }
    }

    controls() {
        const last = this.index === this.steps.length - 1;
        this.back.hidden = this.index === 0;
        this.next.hidden = last;
        this.submit.hidden = !last;
        for (const button of this.form.querySelectorAll('button')) button.disabled = this.busy || button.classList.contains('pz-ai-option');
        this.next.replaceChildren(document.createTextNode(this.index === 0 && this.steps[0].dataset.step === 'welcome'
            ? ({team: "Let's Build Your Team", player: "Let's Get Started", invite: 'Add a Player', accept: 'View My Invitation'}[this.mode] || 'Continue')
            : 'Continue'));
        const icon = document.createElement('i');
        icon.className = 'fa fa-arrow-right';
        icon.setAttribute('aria-hidden', 'true');
        this.next.append(icon);
    }

    show(index, focus = true) {
        if (this.busy) return;
        this.index = Math.max(0, Math.min(index, this.steps.length - 1));
        this.steps.forEach((step, stepIndex) => { step.hidden = stepIndex !== this.index; });
        this.error.hidden = true;
        this.progress.max = this.steps.length;
        this.progress.value = this.index + 1;
        this.progressLabel.textContent = 'Step ' + (this.index + 1) + ' of ' + this.steps.length;
        this.controls();
        if (this.steps[this.index].dataset.step === 'review') this.review();
        if (focus) {
            this.steps[this.index].querySelector('h1, h2')?.focus({preventScroll: true});
            this.form.scrollIntoView({block: 'start', behavior: 'instant'});
        }
        if (this.dirty) this.saveDraft();
    }

    syncPreview() {
        const fullName = this.form.elements.namedItem('full_name');
        if (fullName) this.form.elements.namedItem('name').value = fullName.value.trim();
        const preview = this.form.querySelector('[data-team-name-preview]');
        if (preview) preview.textContent = this.form.elements.namedItem('name').value.trim() || 'Your team';
    }

    fail(message, field) {
        this.error.textContent = message;
        this.error.hidden = false;
        if (field && !field.closest('[hidden]')) {
            field.setAttribute('aria-invalid', 'true');
            field.focus();
        } else this.error.focus();
    }

    async validate(step) {
        await this.logoCheck;
        const password = this.form.elements.namedItem('password');
        const confirmation = this.form.elements.namedItem('confirm_password');
        if (confirmation) confirmation.setCustomValidity(confirmation.value && confirmation.value !== password.value ? 'Your passwords do not match.' : '');
        for (const input of step.querySelectorAll('input')) {
            input.removeAttribute('aria-invalid');
            if (input.required && ['text', 'email', 'tel'].includes(input.type) && !input.value.trim()) input.setCustomValidity('Please enter a value to continue.');
            if (!input.checkValidity()) {
                this.fail(input.validationMessage, input);
                return false;
            }
        }
        if (this.mode === 'invite' && step.dataset.step === 'email') {
            const checkedEmail = this.form.elements.namedItem('email').value.trim();
            this.busy = true;
            this.controls();
            try {
                const response = await fetch('/plazy/team/player-email-validation', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {email: checkedEmail}, id: Date.now()}),
                });
                const data = await response.json();
                if (checkedEmail !== this.form.elements.namedItem('email').value.trim()) {
                    this.fail('Your email changed. Continue again to check the new address.');
                    return false;
                }
                if (!response.ok || !data.result?.valid) {
                    this.fail(data.result?.message || 'We could not check this email. Please try again.');
                    return false;
                }
                const mobile = this.form.elements.namedItem('mobile');
                if (mobile) {
                    mobile.required = !data.result.player;
                    mobile.disabled = Boolean(data.result.player);
                    if (data.result.player) mobile.value = '';
                }
                this.steps = [...this.form.querySelectorAll('[data-step]')].filter(section => !(data.result.player && section.dataset.step === 'mobile'));
                if (data.result.player) {
                    this.form.elements.namedItem('player_name').value = data.result.player.name;
                    const position = this.form.querySelector(`input[name="position"][value="${CSS.escape(data.result.player.position)}"]`);
                    if (position) position.checked = true;
                }
            } catch {
                this.fail('We could not check this email. Check your connection and try again.');
                return false;
            } finally {
                this.busy = false;
                this.controls();
            }
        }
        return true;
    }

    async advance() {
        if (this.busy || this.navigating) return;
        this.navigating = true;
        try {
            if (await this.validate(this.steps[this.index])) this.show(this.index + 1);
        } finally { this.navigating = false; }
    }

    clearLogo() {
        if (this.logoURL) URL.revokeObjectURL(this.logoURL);
        this.logoURL = null;
        const icon = document.createElement('i');
        icon.className = 'fa fa-futbol-o';
        icon.setAttribute('aria-hidden', 'true');
        this.form.querySelector('[data-upload-preview]').replaceChildren(icon);
        this.form.querySelector('[data-remove-logo]').hidden = true;
    }

    async previewLogo(input) {
        this.clearLogo();
        input.setCustomValidity('');
        const file = input.files[0];
        if (!file) return;
        if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
            input.setCustomValidity('Choose a PNG, JPG or WebP image smaller than 5 MB.');
            this.fail(input.validationMessage, input);
            return;
        }
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.src = url;
        try {
            await img.decode();
            if (input.files[0] !== file) { URL.revokeObjectURL(url); return; }
            this.logoURL = url;
            img.alt = 'Your team logo preview';
            this.form.querySelector('[data-upload-preview]').replaceChildren(img);
            this.form.querySelector('[data-remove-logo]').hidden = false;
            this.error.hidden = true;
        } catch {
            URL.revokeObjectURL(url);
            input.setCustomValidity('This image could not be opened. Please choose another image.');
            this.fail(input.validationMessage, input);
        }
    }

    review() {
        const details = this.form.querySelector('[data-review-details]');
        if (!details) return;
        details.replaceChildren();
        for (const field of this.form.querySelectorAll('[data-review-label]')) {
            if (field.type === 'radio' && !field.checked) continue;
            const row = document.createElement('div');
            const term = document.createElement('dt');
            term.textContent = field.dataset.reviewLabel;
            const value = document.createElement('dd');
            value.textContent = {five_a_side: '5-a-side Football', seven_a_side: '7-a-side Football'}[field.value] || field.value;
            const edit = document.createElement('button');
            edit.type = 'button';
            edit.className = 'pz-edit';
            edit.textContent = 'Edit';
            edit.setAttribute('aria-label', 'Edit ' + field.dataset.reviewLabel.toLowerCase());
            edit.addEventListener('click', () => this.show(this.steps.indexOf(field.closest('[data-step]'))));
            row.append(term, value, edit);
            details.append(row);
        }
        for (const [stepName, label, value] of [
            ['security', 'Security', this.form.elements.namedItem('password')?.value ? 'Password entered' : 'Password needed'],
            ['logo', 'Team logo', this.logoURL ? 'Logo uploaded' : 'No logo selected'],
        ]) {
            const stepIndex = this.steps.findIndex(step => step.dataset.step === stepName);
            if (stepIndex < 0) continue;
            const row = document.createElement('div');
            const term = document.createElement('dt');
            term.textContent = label;
            const description = document.createElement('dd');
            description.textContent = value;
            const edit = document.createElement('button');
            edit.type = 'button';
            edit.className = 'pz-edit';
            edit.textContent = 'Edit';
            edit.setAttribute('aria-label', 'Edit ' + label.toLowerCase());
            edit.addEventListener('click', () => this.show(stepIndex));
            row.append(term, description, edit);
            details.append(row);
        }
        const name = this.form.querySelector('[data-review-name]');
        if (name) name.textContent = this.form.elements.namedItem(this.mode === 'team' ? 'name' : 'full_name').value.trim() || 'Your football story';
        const subtitle = this.form.querySelector('[data-review-subtitle]');
        if (subtitle) subtitle.textContent = this.form.elements.namedItem('locality').value.trim() + ' / Bangalore';
        const logo = this.form.querySelector('[data-review-logo]');
        if (logo) {
            logo.replaceChildren();
            if (this.logoURL) {
                const img = document.createElement('img');
                img.src = this.logoURL;
                img.alt = 'Your team logo';
                logo.append(img);
            } else {
                const icon = document.createElement('i');
                icon.className = 'fa fa-futbol-o';
                icon.setAttribute('aria-hidden', 'true');
                logo.append(icon);
            }
        }
    }

    completed(destination) {
        this.form.replaceChildren();
        const section = document.createElement('section');
        section.className = 'pz-step pz-confirmed';
        const mark = document.createElement('span');
        mark.className = 'pz-success-mark';
        mark.textContent = '+';
        mark.setAttribute('aria-hidden', 'true');
        const heading = document.createElement('h2');
        heading.tabIndex = -1;
        heading.textContent = this.mode === 'invite' ? 'One more teammate. Invitation sent.' : "You're part of the team.";
        const copy = document.createElement('p');
        copy.className = 'pz-step-copy';
        copy.textContent = this.mode === 'invite' ? "They'll receive a link to accept your invitation. Follow their progress in your squad." : 'Your registration is complete. Welcome to your football home.';
        const link = document.createElement('a');
        link.href = destination;
        link.className = 'pz-next';
        link.textContent = this.mode === 'invite' ? 'Back to My Squad' : 'Continue to My Profile';
        section.append(mark, heading, copy, link);
        this.form.append(section);
        heading.focus();
    }

    async send() {
        if (this.busy || this.sending) return;
        this.sending = true;
        this.syncPreview();
        for (let i = 0; i < this.steps.length; i++) {
            if (!await this.validate(this.steps[i])) {
                const message = this.error.textContent;
                this.show(i);
                this.fail(message, this.steps[i].querySelector(':invalid'));
                this.sending = false;
                return;
            }
        }
        const body = new FormData(this.form);
        this.busy = true;
        this.form.setAttribute('aria-busy', 'true');
        this.controls();
        const originalLabel = this.submit.textContent;
        this.submit.textContent = 'One moment...';
        this.error.hidden = true;
        this.form.querySelector('.pz-server-error')?.remove();
        try {
            const response = await fetch(this.form.action, {method: 'POST', body});
            const markup = await response.text();
            const result = new DOMParser().parseFromString(markup, 'text/html');
            const serverError = result.querySelector('.pz-server-error, .plazy-form-error, .alert-danger');
            if (!response.ok || serverError) {
                this.fail(serverError?.textContent.trim() || 'We could not complete this step. Your details are still here. Please try again.');
                return;
            }
            const destination = new URL(response.url);
            if (!response.redirected) {
                this.fail('Your session may have expired. Refresh to continue. Passwords and uploads will need to be entered again.');
                return;
            }
            this.dirty = false;
            if (['team', 'player'].includes(this.mode)) {
                try { sessionStorage.removeItem(this.storageKey); } catch { /* Storage is optional. */ }
            }
            if (destination.pathname.endsWith('/dashboard')) this.completed(destination.pathname);
            else window.location.assign(destination.pathname + destination.search);
        } catch {
            this.fail('Connection interrupted. Your details are still here. Check your connection before trying again.');
        } finally {
            this.sending = false;
            this.busy = false;
            this.form.removeAttribute('aria-busy');
            this.submit.textContent = originalLabel;
            if (this.form.contains(this.submit)) this.controls();
        }
    }
}

owl.whenReady(() => {
    document.querySelectorAll('[data-onboarding]').forEach(form => new PlazyOnboarding(form));
});
