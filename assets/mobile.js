/* Estimator mobile navigation: accessible slide-out drawer, like Tenders. */
function initEstimatorMobileNavigation() {
  const sidebar = document.querySelector('#authenticated-app > .sidebar');
  const button = document.getElementById('mobile-menu-button');
  const backdrop = document.getElementById('estimator-menu-backdrop');
  const authenticated = document.getElementById('authenticated-app');
  if (!sidebar || !button || !backdrop || !authenticated) return;
  const mobile = window.matchMedia('(max-width: 820px)');
  const originalLabel = button.innerHTML;
  let opened = false;
  button.setAttribute('aria-label', 'Open navigation menu');
  function setOpen(next, restoreFocus = false) {
    const open = Boolean(next && mobile.matches && !authenticated.classList.contains('hidden'));
    if (open === opened) return;
    opened = open;
    sidebar.classList.toggle('menu-open', open);
    document.body.classList.toggle('estimator-menu-open', open);
    backdrop.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
    button.innerHTML = open ? '<span aria-hidden="true">×</span>' : originalLabel;
    if (restoreFocus && !open && mobile.matches && !authenticated.classList.contains('hidden')) button.focus();
  }
  button.addEventListener('click', () => setOpen(!opened));
  backdrop.addEventListener('click', () => setOpen(false, true));
  sidebar.addEventListener('click', event => {
    if (event.target.closest('a[href]')) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && opened) { event.preventDefault(); setOpen(false, true); }
  });
  window.addEventListener('hashchange', () => setOpen(false));
  mobile.addEventListener?.('change', () => setOpen(false));
  new MutationObserver(() => {
    if (authenticated.classList.contains('hidden')) setOpen(false);
  }).observe(authenticated, {attributes:true, attributeFilter:['class']});
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initEstimatorMobileNavigation, {once:true});
else initEstimatorMobileNavigation();
