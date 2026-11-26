/* Shared by Estimator and Tenders. Examples are local illustrations. */
(() => {
  function init() {
    const host = document.createElement('div');
    host.innerHTML = `
      <button type="button" id="guide-launch" aria-haspopup="dialog">? Help</button>
      <dialog id="flow-guide" aria-labelledby="guide-title">
        <header><h2 id="guide-title">TEC Flow User Guide</h2><button type="button" data-close>Close</button></header>
        <label>Find a task<input type="search" placeholder="Try Breakdown, contacts or chase-up" autofocus></label>
        <div class="guide-layout"><nav aria-label="Guide topics"></nav><article aria-live="polite"></article></div>
      </dialog>`;
    document.body.append(host);
    const launch = host.querySelector('#guide-launch');
    const dialog = host.querySelector('dialog');
    const search = dialog.querySelector('input');
    const nav = dialog.querySelector('nav');
    const article = dialog.querySelector('article');
    let topics = [];
    let selected = location.pathname.startsWith('/tenders') ? 'first-follow-up' : 'first-estimate';
    let stage = 0;

    function node(tag, text) {
      const element = document.createElement(tag);
      element.textContent = text;
      return element;
    }

    function showArticle(topic) {
      article.replaceChildren(node('small', topic.group), node('h3', topic.title));
      if (topic.walkthrough.length) {
        const [label, instruction, fields] = topic.walkthrough[stage];
        const figure = document.createElement('figure');
        figure.append(node('figcaption', 'Worked example · ' + (stage + 1) + ' of ' + topic.walkthrough.length));
        const preview = document.createElement('dl');
        for (const [name, value] of fields) {
          preview.append(node('dt', name), node('dd', value));
        }
        if (stage === 0) {
          const screenshot = document.createElement('img');
          const estimate = topic.id === 'first-estimate';
          screenshot.src = estimate ? '/assets/guide-catalog-search.png' : '/assets/guide-tender-search.png';
          screenshot.alt = estimate ? 'Estimate search with 12 x downlight entered and Qty showing 12.' : 'Project Chase-up search with Example office fitout entered.';
          figure.append(screenshot);
        }
        figure.append(preview);
        article.append(figure, node('h4', label), node('p', instruction));
        const controls = document.createElement('div');
        controls.className = 'guide-controls';
        for (const [name, offset] of [['Previous', -1], ['Next step', 1]]) {
          const button = node('button', name);
          button.disabled = !topic.walkthrough[stage + offset];
          button.onclick = () => {
            stage += offset;
            showArticle(topic);
            const buttons = article.querySelectorAll('.guide-controls button');
            const preferred = buttons[offset < 0 ? 0 : 1];
            (preferred.disabled ? article.querySelector('button:enabled') : preferred).focus();
          };
          controls.append(button);
        }
        article.append(controls);
      } else {
        const steps = document.createElement('ol');
        topic.steps.forEach(step => steps.append(node('li', step)));
        article.append(steps);
      }
      article.append(node('aside', topic.note));
      article.scrollTop = 0;
    }

    function render() {
      const terms = search.value.trim().toLowerCase().split(/\s+/);
      const hits = topics.filter(topic => {
        const body = [topic.title, topic.group, topic.note, ...topic.steps].join(' ').toLowerCase();
        return terms.every(word => body.includes(word));
      });
      nav.replaceChildren();
      if (!hits.length) {
        article.textContent = 'No matching topics. Try a shorter search or clear the search field.';
        return;
      }
      if (!hits.some(item => item.id === selected)) {
        selected = hits[0].id;
        stage = 0;
      }
      let group;
      for (const topic of hits) {
        if (group !== topic.group) {
          group = topic.group;
          nav.append(node('h4', group));
        }
        const button = node('button', topic.title);
        button.setAttribute('aria-current', String(selected === topic.id));
        button.onclick = () => {
          selected = topic.id;
          stage = 0;
          nav.querySelector('[aria-current="true"]')?.setAttribute('aria-current', 'false');
          button.setAttribute('aria-current', 'true');
          showArticle(topic);
        };
        nav.append(button);
      }
      showArticle(hits.find(item => item.id === selected));
    }

    async function load() {
      search.disabled = true;
      article.textContent = 'Loading guide…';
      try {
        const response = await fetch('/api/help/guide', {credentials: 'same-origin'});
        if (!response.ok) throw Error(response.status === 401 ? 'Sign in to open the guide.' : 'The guide could not be loaded.');
        const data = await response.json();
        topics = data.sections.flatMap(group => group.articles.map(topic => ({...topic, group: group.title})));
        search.disabled = false;
        render();
        if (dialog.open) search.focus();
      } catch (error) {
        article.textContent = error.message + ' ';
        const retry = node('button', 'Try again');
        retry.onclick = load;
        article.append(retry);
      }
    }
    launch.onclick = () => {
      dialog.showModal();
      if (!topics.length) load();
      else search.focus();
    };
    dialog.querySelector('[data-close]').onclick = () => dialog.close();
    search.oninput = render;
    const app = document.getElementById('authenticated-app');
    if (app) {
      const sync = () => {
        launch.hidden = !state.user || state.user.must_change_password || app.classList.contains('hidden');
        if (launch.hidden && dialog.open) dialog.close();
      };
      new MutationObserver(sync).observe(app, {attributes: true, attributeFilter: ['class']});
      sync();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
