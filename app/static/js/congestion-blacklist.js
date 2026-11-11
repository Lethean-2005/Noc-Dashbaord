// Persistent congestion exclusions; all row identity is validated server-side.
(function () {
    let trigger = null;
    let blacklistRequest = null;
    function close(modal) {
        modal.style.display = 'none';
        if (modal.id === 'congestionBlacklistModal' && blacklistRequest) {
            blacklistRequest.abort();
            blacklistRequest = null;
        }
        if (trigger && trigger.isConnected) trigger.focus();
    }
    function show(modal, button) {
        if (typeof closeAlarmActionMenus === 'function') closeAlarmActionMenus();
        const actionWrap = button.closest('.alarm-action-wrap');
        trigger = actionWrap ? actionWrap.querySelector('.alarm-action-trigger') : button;
        modal.style.display = 'block';
        const closeButton = modal.querySelector('[data-congestion-close]');
        if (closeButton) closeButton.focus();
    }
    document.addEventListener('click', function (event) {
        const button = event.target.closest('[data-congestion-exclude]');
        if (button) {
            const modal = document.getElementById('congestionExcludeModal');
            const form = document.getElementById('congestionExcludeForm');
            form.elements.remark.value = '';
            form.elements.id.value = button.dataset.id;
            form.elements.source.value = button.dataset.source;
            form.elements.return_to.value = location.pathname + location.search;
            document.getElementById('congestionExcludeLabel').textContent = button.dataset.label;
            document.getElementById('congestionExcludeExplanation').textContent =
                'Hide congestion only for interface ' + button.dataset.interface +
                ' on this device. Other interfaces and alarm types remain visible. Restore it from Blacklist.';
            show(modal, button);
            return;
        }
        const listButton = event.target.closest('[data-congestion-blacklist]');
        if (listButton) {
            const modal = document.getElementById('congestionBlacklistModal');
            const body = document.getElementById('congestionBlacklistBody');
            body.textContent = 'Loading exclusions...';
            show(modal, listButton);
            if (blacklistRequest) blacklistRequest.abort();
            const controller = new AbortController();
            blacklistRequest = controller;
            fetch('/alarms/congestion/blacklist', { signal: controller.signal, cache: 'no-store' }).then(function (response) {
                if (!response.ok) throw new Error('Unable to load exclusions. Please try again.');
                return response.text();
            }).then(function (html) {
                if (blacklistRequest !== controller) return;
                body.innerHTML = html;
                body.querySelectorAll('input[name="return_to"]').forEach(function (input) {
                    input.value = location.pathname + location.search;
                });
            }).catch(function (error) {
                if (error.name !== 'AbortError' && blacklistRequest === controller) body.textContent = error.message;
            }).finally(function () {
                if (blacklistRequest === controller) blacklistRequest = null;
            });
            return;
        }
        const closeButton = event.target.closest('[data-congestion-close]');
        if (closeButton) close(closeButton.closest('.modal'));
        else if (event.target.matches('#congestionExcludeModal, #congestionBlacklistModal')) close(event.target);
    });
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        ['congestionExcludeModal', 'congestionBlacklistModal'].forEach(function (id) {
            const modal = document.getElementById(id);
            if (modal && modal.style.display === 'block') close(modal);
        });
    });
})();
