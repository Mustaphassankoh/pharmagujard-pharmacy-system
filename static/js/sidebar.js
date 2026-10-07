document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-nav-group]').forEach((group) => {
        const toggle = group.querySelector('.nav-toggle');
        const chevronUse = toggle && toggle.querySelector('use');
        if (!toggle || !chevronUse) return;

        const isActive = group.dataset.active === 'true';
        const storageKey = `pharmaguard-nav-${group.dataset.navGroup}`;

        const setExpanded = (expanded) => {
            group.classList.toggle('is-open', expanded);
            toggle.setAttribute('aria-expanded', String(expanded));
            chevronUse.setAttribute('href', expanded ? '#icon-chevron-down' : '#icon-chevron-right');
        };

        let expanded = true;
        try {
            expanded = isActive || localStorage.getItem(storageKey) !== 'collapsed';
        } catch (error) {
            expanded = true;
        }
        setExpanded(expanded);

        toggle.addEventListener('click', () => {
            const nextExpanded = toggle.getAttribute('aria-expanded') !== 'true';
            setExpanded(nextExpanded);
            try {
                localStorage.setItem(storageKey, nextExpanded ? 'expanded' : 'collapsed');
            } catch (error) {
                // The navigation remains usable when browser storage is unavailable.
            }
        });
    });
});
