'use strict';
/* Presentation enhancements only. Geographic data and analytical styles are unchanged. */
(() => {
  const q = selector => document.querySelector(selector);
  const workspace = q('#explore-page');
  const sidebar = q('#sidebar');
  const layersButton = q('#mobile-layers');
  const focusButton = q('#focus-map');
  const bookmarkDialog = q('#bookmark-dialog');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  function closeSidebar() {
    sidebar.classList.remove('open');
    layersButton.setAttribute('aria-expanded', 'false');
    layersButton.focus({preventScroll:true});
  }
  new MutationObserver(() => {
    layersButton.setAttribute('aria-expanded', String(sidebar.classList.contains('open')));
  }).observe(sidebar, {attributes:true,attributeFilter:['class']});
  layersButton.addEventListener('click', () => {
    if (sidebar.classList.contains('open')) q('#mobile-close').focus({preventScroll:true});
  });
  q('#mobile-close').addEventListener('click', () => layersButton.focus({preventScroll:true}));
  focusButton.addEventListener('click', () => {
    const expanded = workspace.classList.toggle('focus-map');
    document.body.classList.toggle('map-focused', expanded);
    focusButton.textContent = expanded ? 'Exit expanded map' : 'Expand map';
    focusButton.setAttribute('aria-pressed', String(expanded));
    requestAnimationFrame(() => window.atlas?.map.invalidateSize());
  });
  document.querySelectorAll('[data-quick-theme]').forEach(button => {
    button.addEventListener('click', () => {
      if (!window.atlas) return;
      window.atlas.selectTheme(button.dataset.quickTheme);
      if (innerWidth <= 760) workspace.scrollIntoView({block:'start',behavior:reducedMotion.matches?'instant':'smooth'});
    });
  });
  q('#quick-elections').addEventListener('click', () => {
    if (!window.atlas) return;
    showPage('explore');
    const launch = q('.elections-launch');
    if (launch?.getAttribute('aria-expanded') !== 'true') launch?.click();
    if (innerWidth <= 760) workspace.scrollIntoView({block:'start',behavior:reducedMotion.matches?'instant':'smooth'});
  });
  q('#bookmark-form').addEventListener('submit', event => {
    event.preventDefault();
    const input = q('#bookmark-name');
    if (!input.value.trim()) { input.setCustomValidity('Enter a name for this view.'); input.reportValidity(); return; }
    input.setCustomValidity('');
    if (persistBookmark(input.value)) bookmarkDialog.close();
  });
  q('#bookmark-name').addEventListener('input', event => event.target.setCustomValidity(''));
  q('#bookmark-cancel').onclick = q('#bookmark-dismiss').onclick = () => bookmarkDialog.close();
  bookmarkDialog.addEventListener('close', () => q('#bookmark-save').focus({preventScroll:true}));
  document.addEventListener('keydown', event => {
    const editing = event.target.matches('input,textarea,select,[contenteditable="true"]');
    if (event.key === '/' && !editing && !event.ctrlKey && !event.metaKey && !document.querySelector('dialog[open]') && !q('.elections-panel:not([hidden])')) {
      event.preventDefault();
      showPage('explore');
      if (innerWidth <= 760) sidebar.classList.add('open');
      q('#search').focus();
    }
    if (event.key === 'Escape') {
      if (workspace.classList.contains('focus-map') && !document.querySelector('dialog[open]')) focusButton.click();
      if (sidebar.classList.contains('open') && !q('.elections-panel:not([hidden])')) closeSidebar();
      q('#info-panel').classList.remove('open');
    }
  });
  // A true district outline, not a decorative invented geography.
  fetch('data/atlas.geojson').then(response => response.json()).then(data => {
    const feature = data.features.find(f => f.properties.kind === 'boundary');
    if (!feature) return;
    const rings = feature.geometry.type === 'MultiPolygon' ? feature.geometry.coordinates.flat(1) : feature.geometry.coordinates;
    const points = rings.flat(1);
    const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
    const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    const scale=Math.min(66/(maxX-minX),86/(maxY-minY));
    const xPad=(80-(maxX-minX)*scale)/2, yPad=(100-(maxY-minY)*scale)/2;
    const path=rings.map(r=>r.map((p,i)=>(i?'L':'M')+(xPad+(p[0]-minX)*scale).toFixed(1)+' '+(100-yPad-(p[1]-minY)*scale).toFixed(1)).join(' ')+'Z').join(' ');
    const node=document.createElementNS('http://www.w3.org/2000/svg','path');node.setAttribute('d',path);q('#district-mark')?.append(node);
  }).catch(()=>{});
})();
