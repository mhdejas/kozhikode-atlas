/* Flood evidence section for the Kozhikode Atlas, built from EARTHSIM-Omega outputs.
   Renders into <section id="flood-evidence">. Map buttons reuse the atlas's own
   themes (flood-*) and point inspector. All numbers come from site/data/floods/*.json
   or from the EARTHSIM-Omega reports linked below. */
(() => {
  const PROJECT = 'https://github.com/mhdejas/earthsim-omega';
  const ATLAS_ZIP = 'https://github.com/mhdejas/kozhikode-atlas/archive/refs/heads/main.zip';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tag = e => `<span class="fe-tag ${e}">${e}</span>`;
  const fmt = n => Number(n).toLocaleString('en-IN');
  const day = d => new Date(d + 'T00:00:00').toLocaleDateString('en-GB', {day:'numeric', month:'short', year:'numeric'});
  const json = url => fetch(url).then(r => { if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); });

  const LAYERS = [
    {id:'flood-2018', ev:'observed', name:'Flood seen by radar · 14 Aug 2018', text:'Open water the Sentinel-1 satellite saw newly flooded, across almost the whole district.'},
    {id:'flood-2019', ev:'observed', name:'Flood seen by radar · 10 Aug 2019', text:'Same method a year later. This pass only covered the eastern 14% of the district.'},
    {id:'flood-low-land', ev:'modelled', name:'Low land near streams', text:'How high each spot sits above the stream it drains to. Dark blue = within 0.5 m.'},
    {id:'flood-susceptibility', ev:'modelled', name:'Flood susceptibility rank', text:'A statistical score fit on 2018 flooding, ranked within the district.'},
    {id:'flood-hindcast-2019', ev:'simulated', name:'Simulated flood · Aug 2019', text:'Peak depths a physics model produced from the real 1–10 Aug 2019 rain.'}
  ];

  function goToMap(id, latlng) {
    const atlas = window.atlas; if (!atlas) return;
    atlas.selectTheme(id);
    (document.querySelector('.map-wrap') || document.getElementById('explore-page'))?.scrollIntoView({behavior:'smooth', block:'start'});
    setTimeout(() => {
      atlas.map.invalidateSize();
      if (latlng) { atlas.map.setView(latlng, 14); atlas.inspector?.inspect(L.latLng(latlng[0], latlng[1])); }
    }, 450);
  }

  function rainChart(data, year) {
    const days = data.daily.filter(d => d.date.startsWith(String(year)));
    const W = 760, H = 230, L0 = 34, B = 24, T = 10, max = 160;
    const bw = (W - L0 - 6) / days.length, y = v => T + (H - T - B) * (1 - Math.min(v, max) / max);
    const grid = [0, 50, 100, 150].map(v => `<line x1="${L0}" x2="${W - 4}" y1="${y(v)}" y2="${y(v)}" stroke="#e3eaee"/><text x="${L0 - 5}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="#7b8d97">${v}</text>`).join('');
    const bars = days.map((d, i) => `<rect x="${(L0 + i * bw + .5).toFixed(1)}" y="${y(d.era5).toFixed(1)}" width="${Math.max(bw - 1, 1).toFixed(1)}" height="${(H - B - y(d.era5)).toFixed(1)}" fill="${d.era5 >= data.heavy_threshold_mm ? '#1d3f52' : '#9fb8c6'}"><title>${day(d.date)}: ${d.era5} mm measured (ERA5)${d.fc1 == null ? '' : `, ${d.fc1} mm forecast a day ahead`}</title></rect>`).join('');
    const dots = days.map((d, i) => d.fc1 == null ? '' : `<circle cx="${(L0 + (i + .5) * bw).toFixed(1)}" cy="${y(d.fc1).toFixed(1)}" r="2.2" fill="#e07b00"/>`).join('');
    const months = days.map((d, i) => d.date.endsWith('-01') ? `<text x="${(L0 + i * bw).toFixed(1)}" y="${H - 7}" font-size="10" fill="#627682">${new Date(d.date).toLocaleDateString('en-GB', {month:'short'})}</text>` : '').join('');
    const trig = `<line x1="${L0}" x2="${W - 4}" y1="${y(data.trigger_mm)}" y2="${y(data.trigger_mm)}" stroke="#e07b00" stroke-dasharray="5 4"/><text x="${W - 6}" y="${y(data.trigger_mm) - 4}" text-anchor="end" font-size="10" fill="#9a5300">50 mm trigger</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily district rain in the ${year} monsoon: measured bars and forecast dots">${grid}${bars}${trig}${dots}${months}<text x="4" y="${T + 4}" font-size="10" fill="#627682">mm</text></svg>`;
  }

  function render(el, rain, outlook, prov) {
    const csi = prov.heldOutCsi_2019_08_10, maxCsi = 0.04;
    const scoreRow = (label, v, ci, cls = '') => `<div class="fe-row"><span>${label}</span><div class="fe-bar">${ci ? `<b style="left:${ci[0] / maxCsi * 100}%;width:${(ci[1] - ci[0]) / maxCsi * 100}%"></b>` : ''}<i class="${cls}" style="width:${v / maxCsi * 100}%"></i></div><span>${v.toFixed(3)}</span></div>`;
    const heavy = rain.heavy_days;
    const patches = prov.observedFloods['flood-2018'].largest_patches;
    const scen = outlook.scenarios, pick = k => scen.find(s => s.member.includes(k)) || {};
    const lo = pick('p10'), mid = pick('deterministic'), hi = pick('p90');
    const level = outlook.level_next_72h;
    const issued = new Date(outlook.issued_ist).toLocaleString('en-GB', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});

    el.innerHTML = `<div class="fe-wrap">
  <div class="fe-eyebrow">Flood evidence · from the EARTHSIM-Ω project</div>
  <h2>Where Kozhikode has flooded, and how far to trust each map.</h2>
  <p class="fe-lead">Satellite radar caught real floods in 2018 and 2019. Terrain and computer models suggest where water could go. Below, each layer is labelled by what kind of evidence it is, with its accuracy shown honestly.</p>
  <div class="fe-notice" role="note"><span class="fe-icon" aria-hidden="true">!</span><div><strong>Research, not a warning.</strong><p>Nothing here is an official flood warning or a safe-land designation. For warnings and decisions, follow IMD, CWC and KSDMA / Kozhikode DDMA.</p>
    <div class="fe-official"><a href="https://mausam.imd.gov.in/" target="_blank" rel="noopener noreferrer">IMD weather warnings ↗</a><a href="https://ffs.india-water.gov.in/" target="_blank" rel="noopener noreferrer">CWC flood forecasts ↗</a><a href="https://sdma.kerala.gov.in/" target="_blank" rel="noopener noreferrer">KSDMA ↗</a></div></div></div>
  <ul class="fe-key" aria-label="Evidence labels">
    <li>${tag('observed')} seen by a satellite</li><li>${tag('modelled')} worked out from terrain or statistics</li><li>${tag('simulated')} a physics model replaying past rain</li><li>${tag('forecast')} about rain that had not fallen yet</li></ul>

  <div class="fe-block"><h3>See it on the map</h3><p>Each button switches the main map above to that layer. Then tap any spot on the map: the point card shows all five flood readings for it.</p>
    <div class="fe-cards">${LAYERS.map(l => `<article class="fe-card"><div class="fe-thumb"><img src="data/floods/${l.id}.png" alt="" loading="lazy"></div><div class="fe-body">${tag(l.ev)}<strong>${esc(l.name)}</strong><p>${esc(l.text)}</p><button type="button" class="fe-show" data-fe-theme="${l.id}">Show on map</button></div></article>`).join('')}</div></div>

  <div class="fe-block"><h3>Where the radar saw flooding on 14 August 2018 ${tag('observed')}</h3>
    <p>${prov.observedFloods['flood-2018'].flooded_km2} km² of newly flooded open water in ${fmt(prov.observedFloods['flood-2018'].patch_count)} separate patches. This pass came before the 14–16 August rain peak, so the real flood was bigger. The largest patches:</p>
    <ul class="fe-places">${patches.map(p => `<li><span>${p.area_km2.toFixed(2)} km²<small>${p.near_km < 1 ? 'at' : `${p.near_km} km from`} ${esc(p.near)}</small></span><button type="button" class="fe-btn ghost" data-fe-theme="flood-2018" data-fe-lat="${p.lat}" data-fe-lon="${p.lon}">Show</button></li>`).join('')}</ul></div>

  <div class="fe-block"><h3>How reliable are the flood maps?</h3>
    <p>Each map was tested against radar flooding on 10 August 2019, a day the model never saw. The score (CSI) runs from 0 to 1: the share of the combined “mapped or seen” area where map and radar agree. Every map scores low here, partly because radar misses water under trees and buildings. The official KSDMA map came out on top.</p>
    <div class="fe-score">${scoreRow('Official KSDMA 25-year flood map', csi.ksdma_25yr_footprint, null, 'official')}${scoreRow('EARTHSIM flood model (tuned)', csi.calibrated_model, csi.calibrated_model_95ci)}${scoreRow('Simple rule: land ≤ 0.5 m above a stream', csi.hand_le_0_5m)}${scoreRow('EARTHSIM flood model (default)', csi.default_model)}</div>
    <p style="font-size:12.5px;color:#627682;margin-top:8px">Shaded band: 95% range for the tuned model (${csi.calibrated_model_95ci[0]}–${csi.calibrated_model_95ci[1]}). The tuned model also over-predicted: about 21 km² wet against 2.26 km² seen in 2018.</p></div>

  <div class="fe-block"><h3>Would a rain alarm have worked? ${tag('observed')} ${tag('forecast')}</h3>
    <p>We replayed the 2024–2026 monsoons. Bars show rain that actually fell across the district each day; orange dots show what the ECMWF forecast said one day earlier. In a fair test, the alarm level was picked using two monsoons and scored on the third, three times over. The scores below come from that test.</p>
    <div class="fe-stats"><div class="fe-stat"><b>${prov.rainTrigger_1day_2024_2026.caught} of ${prov.rainTrigger_1day_2024_2026.heavy_days}</b><span>very heavy rain days (64.5 mm or more) were flagged a day ahead in the fair test</span></div><div class="fe-stat"><b>${prov.rainTrigger_1day_2024_2026.false_alarm_ratio}</b><span>false-alarm ratio: ${prov.rainTrigger_1day_2024_2026.false_alarms} of the alarms came on days that stayed below heavy</span></div><div class="fe-stat"><b>Missed</b><span>30 Jul 2024, the Vilangad landslide day: forecast 29 mm, measured 69 mm</span></div></div>
    <div style="margin-top:16px"><div class="fe-years" role="group" aria-label="Monsoon year">${rain.years.map((yr, i) => `<button type="button" data-fe-year="${yr}" aria-pressed="${i === 0}">${yr}</button>`).join('')}</div>
    <div class="fe-chart"><div class="fe-chart-host">${rainChart(rain, rain.years[0])}</div><div class="fe-chart-key"><span><i style="background:#9fb8c6"></i>Measured rain (ERA5)</span><span><i style="background:#1d3f52"></i>Very heavy day</span><span><i style="background:#e07b00;border-radius:50%;width:8px;height:8px"></i>Forecast a day ahead</span></div></div></div>
    <div class="fe-table-wrap"><table class="fe-table"><thead><tr><th>Very heavy rain day</th><th>Measured</th><th>Forecast a day ahead</th><th>Alarm?</th></tr></thead><tbody>${heavy.map(h => `<tr><td>${day(h.date)}</td><td>${h.era5_mm} mm</td><td>${h.forecast_1day_mm == null ? '—' : h.forecast_1day_mm + ' mm'}</td><td>${h.flagged == null ? '—' : h.flagged ? '<span class="fe-yes">Yes</span>' : '<span class="fe-no">Missed</span>'}</td></tr>`).join('')}</tbody></table></div>
    <p style="font-size:12.5px;color:#627682;margin-top:8px">The table and dashed line use the 50 mm alarm level now in use. On these days it flags ${heavy.filter(h => h.flagged).length} of ${heavy.length} and raises ${rain.daily.filter(d => d.fc1 != null && d.fc1 >= rain.trigger_mm && d.era5 < rain.heavy_threshold_mm).length} false alarms, but it was chosen using these same days, so the fair-test score above is the one to trust. Measured rain: ${esc(rain.truth)}. Forecast: ${esc(rain.model)} via Open-Meteo. Days run ${esc(rain.day_definition)}.</p></div>

  <div class="fe-block"><h3>A sample outlook, frozen in time ${tag('forecast')}</h3>
    <p>This is a snapshot of one experimental run issued ${esc(issued)} IST. It is <strong>not live</strong> and is out of date by the time you read it. October rain was never part of the accuracy test above.</p>
    <p><span class="fe-level ${level === 'GREEN' ? 'green' : ''}">Next 72 hours: ${esc(level)}</span> <span style="font-size:13px;color:#627682">Based on rain triggers; ground already had ${outlook.antecedent_5day_mm} mm in the previous 5 days.</span></p>
    <div class="fe-table-wrap"><table class="fe-table"><thead><tr><th>Day ending 08:30 IST</th><th>Main forecast</th><th>Ensemble range (low · middle · high)</th><th>Chance of heavy rain</th><th>Level</th></tr></thead><tbody>${outlook.days.filter(d => d.lead_day <= 4).map(d => `<tr><td>${day(d.day_ending_0830_ist)}${d.in_progress ? ' (in progress)' : ''}</td><td>${d.deterministic_mm} mm</td><td>${d.ensemble_p10_p50_p90_mm.join(' · ')} mm</td><td>${Math.round(d.prob_heavy * 100)}%</td><td><span class="fe-pill ${esc(d.rain_level)}">${esc(d.rain_level)}</span></td></tr>`).join('')}</tbody></table></div>
    <p style="margin-top:14px">If that rain fell, the flood model (240 m cells, water 2 m or deeper) gave this range ${tag('simulated')}:</p>
    <div class="fe-table-wrap"><table class="fe-table"><thead><tr><th>Scenario</th><th>Rain in 72 h</th><th>Area under 2 m+ water</th><th>Buildings</th><th>Schools</th><th>Hospitals</th></tr></thead><tbody>${[['Drier case', lo], ['Main forecast', mid], ['Wetter case', hi]].map(([n, s]) => `<tr><td>${n}</td><td>${s.rain_72h_mm} mm</td><td>${s.wet_km2} km²</td><td>${fmt(s.buildings)}</td><td>${s.schools}</td><td>${s.hospitals}</td></tr>`).join('')}</tbody></table></div>
    <p style="font-size:12.5px;color:#627682;margin-top:8px">Building and facility counts use OpenStreetMap (© OpenStreetMap contributors, ODbL): the district has 240,990 mapped buildings, 2,307 schools and 719 hospitals. In the main forecast, 36 of the 62 km² falls on land cells (under 10% mapped water), so most of it is not just rivers filling up.</p></div>

  <div class="fe-block"><h3>Figures from the project</h3><p>Tap a figure to open it full size.</p>
    <div class="fe-figs">${prov.figures.map(f => `<figure><a href="data/${esc(f.file)}" target="_blank" rel="noopener"><img src="data/${esc(f.file)}" alt="${esc(f.title)}" loading="lazy"></a><figcaption>${tag(f.evidence)}${esc(f.title)}</figcaption></figure>`).join('')}</div></div>

  <div class="fe-block" id="flood-run-it"><h3>Run it yourself</h3><p>Pick the level you are comfortable with. None of them need an account or an API key.</p>
    <div class="fe-steps">
      <div class="fe-step"><h4>1 · Just look</h4><p>Nothing to install. Use the map buttons above, or open the <strong>Map</strong> tab, pick a flood layer under <em>Map themes</em>, and tap anywhere for a point reading.</p></div>
      <div class="fe-step"><h4>2 · Run the atlas on your computer</h4><ol><li>Install <a href="https://www.python.org/downloads/" target="_blank" rel="noopener noreferrer">Python 3</a> if you do not have it.</li><li>Download the <a href="${ATLAS_ZIP}">atlas ZIP</a> and unzip it.</li><li>Open a terminal in the unzipped folder and run:<code class="fe-code">python3 -m http.server 8000 --directory site</code>On Windows, type <code>py</code> instead of <code>python3</code>.</li><li>Open <code>http://localhost:8000</code> in your browser.</li></ol><p>Opening <code>index.html</code> by double-click will not work: browsers block the data files without a local server.</p></div>
      <div class="fe-step"><h4>3 · Rebuild the flood layers</h4><ol><li>Get <a href="${PROJECT}" target="_blank" rel="noopener noreferrer">EARTHSIM-Ω</a> and follow its README to install and run the pipeline (terrain, flood_obs, flood_susceptibility, hindcast).</li><li>From the atlas folder, run:<code class="fe-code">python scripts/prepare_floods.py --earthsim ../earthsim-omega</code></li><li>Start the local server again. Every input is checksummed in <a href="data/floods/provenance.json">provenance.json</a>.</li></ol></div>
    </div></div>
  <p class="fe-foot">Data: Copernicus Sentinel-1 (via Microsoft Planetary Computer), Copernicus DEM GLO-30, ERA5 and ECMWF IFS forecasts (via Open-Meteo), OpenStreetMap, KSDMA flood map for comparison. Methods and full results: <a href="${PROJECT}" target="_blank" rel="noopener noreferrer">EARTHSIM-Ω on GitHub</a>.</p>
</div>`;

    el.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.feTheme) goToMap(b.dataset.feTheme, b.dataset.feLat ? [Number(b.dataset.feLat), Number(b.dataset.feLon)] : null);
      if (b.dataset.feYear) {
        el.querySelectorAll('[data-fe-year]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        el.querySelector('.fe-chart-host').innerHTML = rainChart(rain, Number(b.dataset.feYear));
      }
    });
  }

  function init() {
    const el = document.getElementById('flood-evidence'); if (!el || el.dataset.ready) return;
    el.dataset.ready = '1';
    Promise.all([json('data/floods/rain-replay.json'), json('data/floods/outlook-2026-10-23.json'), json('data/floods/provenance.json')])
      .then(([rain, outlook, prov]) => render(el, rain, outlook, prov))
      .catch(() => { el.innerHTML = '<div class="fe-wrap"><p>Flood evidence could not load. Check your connection and reload the page.</p></div>'; });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
