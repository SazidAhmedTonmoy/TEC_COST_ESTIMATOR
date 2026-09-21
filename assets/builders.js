/* Optional project builders. One name per row; punctuation is part of a name. */
function projectBuilders(project = {}) {
  const values = Array.isArray(project.builders) ? project.builders : String(project.client || '').split(/\r?\n/);
  const seen = new Set();
  return values.map(name => String(name || '').trim().replace(/\s+/g, ' ')).filter(name => {
    const key = name.toLocaleLowerCase();
    if (!name || seen.has(key)) return false;
    seen.add(key); return true;
  });
}
function builderText(project, empty = '') { return projectBuilders(project).join(', ') || empty; }
function readBuilderEditor(id) {
  return Array.from(document.querySelectorAll(`#${id} [data-builder-name]`), input => input.value).filter(name => name.trim());
}
function updateBuilderRows(editor) {
  const rows = editor.querySelectorAll('.builder-row');
  rows.forEach((row, index) => {
    const input = row.querySelector('input'), button = row.querySelector('button');
    input.id = `${editor.id}-name-${index + 1}`;
    input.setAttribute('aria-label', `Builder ${index + 1}`);
    button.setAttribute('aria-label', `Remove builder ${index + 1}`);
  });
  editor.querySelector('[data-builder-add]').disabled = rows.length >= 100;
}
function appendBuilderRow(editor, name = '', focus = false) {
  const rows = editor.querySelector('[data-builder-rows]');
  if (rows.children.length >= 100) return;
  const row = document.createElement('div'); row.className = 'builder-row';
  const input = document.createElement('input');
  input.type = 'text'; input.dataset.builderName = ''; input.value = name;
  input.maxLength = 500; input.placeholder = 'Builder name'; input.autocomplete = 'off';
  const remove = document.createElement('button');
  remove.type = 'button'; remove.className = 'icon-button builder-remove';
  remove.dataset.builderRemove = ''; remove.textContent = '\u00d7'; remove.title = 'Remove builder';
  row.append(input, remove); rows.append(row); updateBuilderRows(editor);
  if (focus) input.focus();
}
function renderBuilderEditor(id, names = [], editable = true) {
  const editor = document.getElementById(id); if (!editor) return;
  editor.disabled = !editable;
  editor.querySelector('[data-builder-rows]').replaceChildren();
  (names.length ? names : ['']).forEach(name => appendBuilderRow(editor, name));
  const add = editor.querySelector('[data-builder-add]');
  add.hidden = !editable;
  editor.querySelectorAll('[data-builder-remove]').forEach(button => { button.hidden = !editable; });
  if (!editable && !names.length) editor.querySelector('input').placeholder = 'No builder assigned';
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-builder-editor]').forEach(editor => renderBuilderEditor(editor.id));
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-builder-add], [data-builder-remove]');
    if (!button) return;
    const editor = button.closest('[data-builder-editor]');
    if (!editor || editor.disabled || button.disabled) return;
    if (button.hasAttribute('data-builder-add')) {
      appendBuilderRow(editor, '', true);
    } else {
      const row = button.closest('.builder-row');
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      if (!editor.querySelector('.builder-row')) appendBuilderRow(editor, '', true);
      else { updateBuilderRows(editor); next?.querySelector('input').focus(); }
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !event.target.matches('[data-builder-name]') || event.isComposing) return;
    event.preventDefault();
    const row = event.target.closest('.builder-row'), editor = row.closest('[data-builder-editor]');
    if (editor.disabled) return;
    if (row.nextElementSibling) row.nextElementSibling.querySelector('input').focus();
    else if (event.target.value.trim()) appendBuilderRow(editor, '', true);
  });
});
