/** @odoo-module **/

owl.whenReady(() => {
    const header = document.querySelector('.plazy-site-header');
    if (!header) return;
    const main = document.querySelector('main');
    if (main && !main.id) main.id = 'plazy-main';
    const menu = header.querySelector('.plazy-mobile-nav');
    const closeMenu = (restoreFocus = false) => {
        if (!menu?.open) return;
        menu.open = false;
        if (restoreFocus) menu.querySelector('summary').focus();
    };
    menu?.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', () => closeMenu());
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeMenu(true);
    });
    document.addEventListener('click', (event) => {
        if (!menu?.contains(event.target)) closeMenu();
    });
    header.addEventListener('focusout', (event) => {
        if (!header.contains(event.relatedTarget)) closeMenu();
    });

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const hero = document.querySelector('.plazy-home-hero');
    let pending = false;
    const update = () => {
        header.classList.toggle('is-scrolled', window.scrollY > 12);
        if (hero) hero.style.backgroundPositionY = motion.matches ? '' : `calc(50% + ${Math.min(window.scrollY * .06, 28)}px)`;
        pending = false;
    };
    window.addEventListener('scroll', () => {
        if (!pending) {
            pending = true;
            window.requestAnimationFrame(update);
        }
    }, {passive: true});
    motion.addEventListener('change', () => {
        if (motion.matches) document.documentElement.classList.remove('plazy-motion');
        update();
    });
    update();

    if (!motion.matches && 'IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                }
            }
        }, {threshold: .08});
        document.documentElement.classList.add('plazy-motion');
        document.querySelectorAll('[data-plazy-reveal]').forEach((element) => observer.observe(element));
    }
});
