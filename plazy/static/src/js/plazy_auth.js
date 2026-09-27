/** @odoo-module **/

/* global owl */

const {Component, mount, whenReady, xml} = owl;

class AccountTypeSelector extends Component {
    select(type) {
        window.location.assign(`/plazy/signup?account_type=${type}`);
    }

    static template = xml`
        <div class="plazy-role-picker">
            <p>New to Plazy?</p>
            <div class="plazy-role-actions">
                <button type="button" t-on-click="() => this.select('player')">Join as Player</button>
                <button type="button" t-on-click="() => this.select('team')">Register a Team</button>
            </div>
        </div>`;
}

class AdminDestinationSelector extends Component {
    openBackend() {
        window.location.assign('/odoo');
    }

    openPlazyAdmin() {
        window.location.assign('/plazy/admin/dashboard');
    }

    static template = xml`
        <section class="plazy-admin-choice" aria-labelledby="plazy-admin-choice-title">
            <p class="plazy-eyebrow">ADMIN ACCESS</p>
            <h1 id="plazy-admin-choice-title">Choose your workspace</h1>
            <p>Select where you want to continue.</p>
            <div class="plazy-admin-choice-grid">
                <button type="button" class="plazy-admin-choice-option" t-on-click="() => this.openBackend()">
                    <span class="plazy-admin-choice-mark">O</span>
                    <span><strong>Backend</strong><small>Open the standard Odoo workspace</small></span>
                </button>
                <button type="button" class="plazy-admin-choice-option" t-on-click="() => this.openPlazyAdmin()">
                    <span class="plazy-admin-choice-mark">P</span>
                    <span><strong>Plazy Admin</strong><small>Open the Plazy management dashboard</small></span>
                </button>
            </div>
        </section>`;
}

whenReady(() => {
    const target = document.getElementById('plazy-auth-role');
    if (target) {
        mount(AccountTypeSelector, target);
    }
    const adminTarget = document.getElementById('plazy-admin-destination');
    if (adminTarget) {
        const fallback = document.getElementById('plazy-admin-choice-fallback');
        Promise.resolve(mount(AdminDestinationSelector, adminTarget)).then(() => {
            fallback?.setAttribute('hidden', 'hidden');
        }).catch(() => {
            // The server-rendered chooser remains usable if an asset fails to load.
        });
    }
    document.querySelectorAll('.plazy-registration-form, .plazy-reset-email-form').forEach((form) => {
        const email = form.querySelector('input[name="email"]');
        const message = form.querySelector('.plazy-email-message');
        const validateEmail = () => {
            const value = email.value.trim();
            const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
            email.classList.toggle('is-invalid', Boolean(value) && !valid);
            email.setCustomValidity(value && !valid ? 'Enter a valid email address.' : '');
            message.classList.toggle('is-visible', Boolean(value) && !valid);
            message.textContent = value && !valid ? 'Enter a valid email address.' : '';
            return valid;
        };
        email.addEventListener('input', validateEmail);
        email.addEventListener('blur', validateEmail);
        form.addEventListener('submit', (event) => {
            if (!validateEmail() || !email.value.trim()) {
                event.preventDefault();
                email.focus();
            }
        });
    });
    document.querySelectorAll('.plazy-otp-form').forEach((form) => {
        form.addEventListener('submit', (event) => {
            const button = event.submitter;
            if (!button) return;
            button.disabled = true;
            button.classList.add('is-loading');
            button.dataset.label = button.textContent;
            button.textContent = button.value === 'resend' ? 'Sending...' : 'Verifying...';
        });
    });
    document.querySelectorAll('.plazy-otp-resend').forEach((button) => {
        let remaining = 30;
        button.disabled = true;
        const updateLabel = () => {
            button.textContent = remaining > 0 ? `Resend OTP in ${remaining}s` : 'Resend OTP';
            button.disabled = remaining > 0;
        };
        updateLabel();
        const countdown = window.setInterval(() => {
            remaining -= 1;
            updateLabel();
            if (remaining <= 0) {
                window.clearInterval(countdown);
            }
        }, 1000);
    });
    document.querySelectorAll('[data-plazy-password-form]').forEach((form) => {
        const password = form.querySelector('input[name="password"]');
        const confirmation = form.querySelector('input[name="confirm_password"]');
        const validatePasswordMatch = () => {
            const mismatch = Boolean(confirmation.value) && password.value !== confirmation.value;
            confirmation.setCustomValidity(mismatch ? 'New password and confirm password must match.' : '');
            confirmation.classList.toggle('is-invalid', mismatch);
        };
        password.addEventListener('input', validatePasswordMatch);
        confirmation.addEventListener('input', validatePasswordMatch);
        form.addEventListener('submit', validatePasswordMatch);
    });
    document.querySelectorAll('[data-plazy-password-toggle]').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.plazyPasswordToggle);
            if (!input) return;
            const reveal = input.type === 'password';
            input.type = reveal ? 'text' : 'password';
            button.textContent = reveal ? 'Hide' : 'Show';
            button.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
        });
    });
});
