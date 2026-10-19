'use strict';
/* Presentation routing only; datasets, classifiers and export logic are unchanged. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const go = target => {
    const node = document.querySelector(target);
    if (!node) return;
    if (typeof showPage === 'function') showPage('explore');
    requestAnimationFrame(() => {
      node.scrollIntoView({block:'start',behavior:reduce.matches?'instant':'smooth'});
      history.replaceState(null,'',target === '#explore-page' ? '#explore' : target);
    });
  };
  document.querySelectorAll('.header .section-link').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    go(link.getAttribute('href'));
  }));
  document.querySelector('.brand').addEventListener('click', event => {
    event.preventDefault();
    go('#explore-page');
  });
  document.querySelector('.header [data-page="explore"]').addEventListener('click', () => {
    requestAnimationFrame(() => { document.querySelector('#explore-page').scrollIntoView({block:'start',behavior:reduce.matches?'instant':'smooth'}); history.replaceState(null,'','#explore'); });
  });
  document.querySelectorAll('.explore-shortcuts button').forEach(button => button.addEventListener('click', () => {
    if (!button.id.includes('elections')) go('#explore-page');
  }));
  const mapNode = document.querySelector('#map');
  let previousWidth = 0;
  let ready = false;
  const observer = new ResizeObserver(() => {
    const atlas = window.atlas;
    if (!atlas?.map) return;
    const width = mapNode.clientWidth;
    atlas.map.invalidateSize({pan:false});
    if (!ready || Math.abs(width - previousWidth) > 180) {
      if (atlas.state.theme === 'reference' && atlas.state.bounds) atlas.map.fitBounds(atlas.state.bounds,{padding:[34,34],maxZoom:11.5,animate:false});
      previousWidth = width;
      ready = true;
    }
  });
  observer.observe(mapNode);
  // Initialization can finish after the first resize notification.
  const status = document.querySelector('#data-status');
  const initialized = new MutationObserver(() => {
    if (!window.atlas?.map || ready) return;
    window.atlas.map.invalidateSize({pan:false});
    if (window.atlas.state.theme === 'reference') window.atlas.map.fitBounds(window.atlas.state.bounds,{padding:[34,34],maxZoom:11.5,animate:false});
    ready = true;
    previousWidth = mapNode.clientWidth;
    initialized.disconnect();
  });
  initialized.observe(status,{childList:true,characterData:true,subtree:true});
  // Preserve and honor direct links to the long-form sections.
  if (['#terrain-explorer','#geography-story','#elevation-lab'].includes(location.hash)) {
    requestAnimationFrame(() => go(location.hash));
  }
})();
