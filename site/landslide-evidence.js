'use strict';
/* Historical observations and evidence contracts; no new susceptibility model. */
(() => {
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const load = async path => { const r = await fetch(path); if (!r.ok) throw Error(`Evidence unavailable (${r.status})`); return r.json(); };
  async function init(atlas) {
    if (!atlas || !atlas.map || atlas.__landslideEvidenceInit) return;
    const tools = document.querySelector('.map-tools');
    const mapWrap = document.querySelector('.map-wrap');
    if (!tools || !mapWrap) return;
    atlas.__landslideEvidenceInit = true;
    const evidenceButton = document.createElement('button');
    evidenceButton.type = 'button'; evidenceButton.id = 'landslide-evidence'; evidenceButton.textContent = 'Landslide evidence';
    evidenceButton.setAttribute('aria-haspopup', 'dialog'); tools.append(evidenceButton);
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.id = 'historical-landslides';
    toggle.textContent = '2018 recorded landslides'; toggle.setAttribute('aria-pressed', 'false'); tools.append(toggle);
    const status = document.createElement('div'); status.className = 'historical-landslide-note'; status.hidden = true;
    status.setAttribute('role', 'status'); mapWrap.append(status);
    const dialog = document.createElement('dialog'); dialog.id = 'landslide-evidence-dialog'; dialog.setAttribute('aria-labelledby', 'evidence-heading');
    dialog.innerHTML = '<form method="dialog"><button class="dialog-close" aria-label="Close landslide evidence">×</button></form><h2 id="evidence-heading">What the landslide evidence can tell us</h2><p class="rights-warning"><strong>GSI rights unresolved.</strong> Non-official atlas. Web-display and redistribution permission is not established; attribution and this caveat do not grant permission. Source: GSI 2022 / Kerala State Disaster Management Authority (KSDMA).</p><div class="evidence-content" aria-live="polite">Loading source evidence…</div>';
    document.body.append(dialog);
    let bundle, inventoryLayer, shown = false;
    const linkUrl = value => /^https?:\/\//i.test(String(value ?? '')) ? String(value) : '';
    const getBundle = () => bundle ||= Promise.all([load('data/landslide-research.json'), load('data/landslide-inventory-provenance.json'), load('data/landslide-inventory-2018.geojson')]).catch(e => {bundle = null; throw e;});
    const showEvidence = async () => {
      if (!dialog.open) dialog.showModal();
      try {
        const [research, provenance, rawGeo] = await getBundle();
        const geo = rawGeo && Array.isArray(rawGeo.features) ? rawGeo : {type:'FeatureCollection',features:[]};
        dialog.querySelector('.evidence-content').innerHTML = `<p class="evidence-verdict">${esc(research.verdict)}</p>${(Array.isArray(research.sections) ? research.sections : []).map(s => `<section><h3>${esc(s.title)}</h3>${(Array.isArray(s.paragraphs) ? s.paragraphs : []).map(p => `<p>${esc(p)}</p>`).join('')}${Array.isArray(s.sources) && s.sources.length ? `<ul class="evidence-links">${s.sources.map(x => { const url=linkUrl(x.url); return url ? `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a></li>` : ''; }).join('')}</ul>` : ''}</section>`).join('')}<section><h3>Download the licensed historical evidence</h3><p>${geo.features.length} initiation-point records fall inside the atlas district boundary. These are 2018 historical observations, not a complete present-day inventory or runout footprints. No absence of points means safe land.</p><p>C.J. van Westen (2020), DANS, version 2.0, CC BY 4.0. Atlas adaptation: district selection, field reduction and WGS 84 GeoJSON conversion; source geometry retained.</p><p><a href="data/landslide-inventory-2018.geojson" download>2018 district points (GeoJSON)</a> · <a href="data/landslide-inventory-provenance.json" download>Inventory provenance and QA</a> · <a href="data/landslide-research.json" download>Research evidence record</a></p></section>`;
        const review = research.publicSourceReview;
        if (review) {
          const audit = document.createElement('section');
          audit.className = 'public-source-audit';
          const renderLinks = (values, label) => (Array.isArray(values) ? values : []).map((url, i) => { const safe = linkUrl(url); return safe ? `<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer">${label} ${i + 1}</a>` : ''; }).filter(Boolean).join(' · ');
          audit.innerHTML = `<h3>Source-by-source download and reuse checks</h3><p>${esc(review.researchMode)}</p>${(Array.isArray(review.candidates) ? review.candidates : []).map(c => `<details><summary>${esc(c.name)}</summary><p><strong>Decision:</strong> ${esc(c.decision)}</p>${[['Coverage',c.geography],['Scale / resolution',c.scaleResolution],['Date',c.date],['Method',c.method],['Reuse',c.license],['Validation',c.validation]].map(([label,value]) => `<p><strong>${esc(label)}:</strong> ${esc(value)}</p>`).join('')}<p>${renderLinks(c.assets, 'Public asset / access record')}</p><p>${renderLinks(c.sources, 'Source')}</p></details>`).join('')}`;
          dialog.querySelector('.evidence-content').append(audit);
        }
      } catch (e) { dialog.querySelector('.evidence-content').textContent = e.message + '. The existing atlas layers remain available; retry this panel.'; }
    };
    evidenceButton.onclick = showEvidence;
    toggle.onclick = async () => {
      if (shown) { atlas.map.removeLayer(inventoryLayer); shown = false; toggle.setAttribute('aria-pressed', 'false'); status.hidden = true; return; }
      toggle.disabled = true;
      try {
        const [, , geo] = await getBundle();
        if (!inventoryLayer) {
          if (!atlas.map.getPane('historicalLandslides')) { atlas.map.createPane('historicalLandslides'); atlas.map.getPane('historicalLandslides').style.zIndex = 460; }
          const typeNames = {DF:'Debris flow',SS:'Surficial slide',RF:'Rock fall'};
          inventoryLayer = L.geoJSON(geo, {pane:'historicalLandslides',pointToLayer:(f,ll) => L.circleMarker(ll, {pane:'historicalLandslides',radius:5,color:'#102f4c',weight:2,fillColor:'#f8fcff',fillOpacity:1,bubblingMouseEvents:false}),onEachFeature:(f,l) => l.bindPopup(`<strong>Recorded 2018 landslide</strong><br>Record ${esc(f.properties.record_id)}<br>${esc(typeNames[f.properties.type] || f.properties.type || 'Type not supplied')}<br>Mapping source: ${esc(f.properties.source_method || 'See provenance')}<p>Initiation point, not landslide extent. Positional accuracy is not quantified here. Historical observation; not a warning or property assessment.</p><a href="https://doi.org/10.17026/dans-x6c-y7x2" target="_blank" rel="noopener noreferrer">van Westen 2020 · CC BY 4.0</a>`)});
        }
        inventoryLayer.addTo(atlas.map); shown = true; toggle.setAttribute('aria-pressed','true'); status.hidden = false;
        status.textContent = `○ ${geo.features.length} recorded 2018 initiation points · historical, not live · CC BY 4.0 · not included in map exports`;
      } catch(e) { status.hidden = false; status.textContent = e.message + '. Historical overlay could not load; retry.'; }
      finally { toggle.disabled = false; }
    };
    const refresh = () => {
      const host = document.querySelector('#info-details');
      if (!host) return;
      if (atlas.state.theme === 'landslide' && !host.querySelector('.landslide-evidence-summary')) {
        const summary = document.createElement('section'); summary.className = 'landslide-evidence-summary';
        summary.innerHTML = '<h3>Precision has a limit</h3><p>GSI national zonation is regional-scale (1:50,000). The district download does not state its original raster cell size or local positional accuracy. The atlas’s ~100 m cells are display samples, not a safety boundary.</p><p>2022 source snapshot ≠ 2025 packaging date. District-specific independent validation and redistribution permission remain unresolved.</p><button type="button">Read the research and data gaps</button>';
        const result = document.createElement('p');
        result.textContent = 'Public-source review: no verified finer, openly reusable replacement found. Research only; no further outreach.';
        summary.insertBefore(result, summary.querySelector('button'));
        summary.querySelector('button').onclick = showEvidence; host.prepend(summary);
      }
    };
    new MutationObserver(refresh).observe(document.querySelector('#info-title'), {childList:true,subtree:true,characterData:true}); refresh();
    const documentHost = document.querySelector('#document-page');
    const addSourceEvidence = () => {
      if (!documentHost || documentHost.hidden || !documentHost.querySelector('.dataset-card') || documentHost.querySelector('#source-landslide-evidence')) return;
      const card = document.createElement('article'); card.id = 'source-landslide-evidence'; card.className = 'dataset-card';
      card.innerHTML = '<h3>Landslide research and licensed 2018 event records</h3><p class="rights-warning"><strong>GSI rights unresolved.</strong> Non-official atlas. Web-display and redistribution permission is not established; attribution and this caveat do not grant permission. Source: GSI 2022 / Kerala State Disaster Management Authority (KSDMA).</p><p>The GSI programme scale is 1:50,000, not property scale. A separate historical overlay uses the 2018 Kerala inventory, van Westen (2020), DANS version 2.0, CC BY 4.0. Its points are observations, not a new hazard model.</p><p><a href="data/landslide-inventory-2018.geojson" download>Download district historical points</a> · <a href="data/landslide-inventory-provenance.json" download>Provenance and district-selection QA</a></p><button type="button">Read landslide research and remaining gaps</button>';
      card.querySelector('button').onclick = showEvidence; documentHost.append(card);
    };
    new MutationObserver(addSourceEvidence).observe(documentHost, {childList:true}); addSourceEvidence();
    atlas.landslideEvidence = {show:showEvidence,toggleHistorical:() => toggle.click(),get historicalVisible(){return shown;},get inventoryLayer(){return inventoryLayer;}};
  }
  if (window.atlas?.map) init(window.atlas); else document.addEventListener('atlas-ready', () => init(window.atlas), {once:true});
})();
