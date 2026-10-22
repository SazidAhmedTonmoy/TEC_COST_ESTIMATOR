/* Shared Tenders + Estimating login. Zero API calls; pause when not visible. */
(() => {
  "use strict";
  const INTERVAL = 3000;
  function init() {
    const screen = document.getElementById('login-screen');
    if (!screen) return;
    const slides = [...screen.querySelectorAll('.login-slide')];
    const dots = [...screen.querySelectorAll('[data-login-slide]')];
    if (slides.length !== 3 || dots.length !== slides.length) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    let index = 0, timer = null;
    function visible() { return !document.hidden && !screen.classList.contains('hidden') && !document.body.classList.contains('app-loading'); }
    function change(next) {
      index = (next + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        const current = i === index;
        slide.classList.toggle('is-active', current);
        slide.setAttribute('aria-hidden', String(!current));
      });
      dots.forEach((dot, i) => {
        dot.classList.toggle('is-active', i === index);
        dot.setAttribute('aria-pressed', String(i === index));
      });
    }
    function pause() { if (timer !== null) clearInterval(timer); timer = null; }
    function sync() {
      pause();
      if (!reduce.matches && visible()) timer = setInterval(() => {
        if (visible() && !reduce.matches) change(index + 1);
        else sync();
      }, INTERVAL);
    }
    dots.forEach((dot, i) => dot.addEventListener('click', () => {
      change(i);
      sync();
    }));
    document.addEventListener('visibilitychange', sync);
    reduce.addEventListener?.('change', sync);
    // Login visibility is controlled by BOTH body.app-loading and screen.hidden.
    // Observe both so the timer starts after an unauthenticated bootstrap.
    const observer=new MutationObserver(sync);
    observer.observe(screen, {attributes: true, attributeFilter: ['class']});
    observer.observe(document.body, {attributes: true, attributeFilter: ['class']});
    window.addEventListener('pagehide', pause, {once: true});
    change(0);
    sync();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
