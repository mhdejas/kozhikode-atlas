/* Point inspection uses published numeric rasters, never basemap colours. */
'use strict';
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const R = 6378137;
  function utm43(lon, lat) {
    const rad=Math.PI/180, p=lat*rad, e2=0.0066943799901413165, ep=e2/(1-e2), k=.9996;
    const n=R/Math.sqrt(1-e2*Math.sin(p)**2), t=Math.tan(p)**2, c=ep*Math.cos(p)**2, a=Math.cos(p)*(lon-75)*rad;
    const m=R*((1-e2/4-3*e2**2/64-5*e2**3/256)*p-(3*e2/8+3*e2**2/32+45*e2**3/1024)*Math.sin(2*p)+(15*e2**2/256+45*e2**3/1024)*Math.sin(4*p)-35*e2**3/3072*Math.sin(6*p));
    return [500000+k*n*(a+(1-t+c)*a**3/6+(5-18*t+t*t+72*c-58*ep)*a**5/120),k*(m+n*Math.tan(p)*(a*a/2+(5-t+9*c+4*c*c)*a**4/24+(61-58*t+t*t+600*c-330*ep)*a**6/720))];
  }
  function segmentSquared(p,a,b) {
    const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;
    const t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0;
    return (p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2;
  }
  function geometrySquared(p,g) {
    if(g.type==='Point')return (p[0]-g.coordinates[0])**2+(p[1]-g.coordinates[1])**2;
    if(g.type==='MultiPoint')return Math.min(...g.coordinates.map(q=>(p[0]-q[0])**2+(p[1]-q[1])**2));
    const lines=g.type==='LineString'?[g.coordinates]:g.type==='MultiLineString'||g.type==='Polygon'?g.coordinates:g.type==='MultiPolygon'?g.coordinates.flat():[];
    let best=Infinity;for(const line of lines)for(let i=1;i<line.length;i++)best=Math.min(best,segmentSquared(p,line[i-1],line[i]));return best;
  }
  function insideRing(p,ring) {let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if(((a[1]>p[1])!==(b[1]>p[1]))&&(p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]))yes=!yes;}return yes;}
  function insideGeometry(p,g) {const polys=g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];return polys.some(rings=>insideRing(p,rings[0])&&!rings.slice(1).some(r=>insideRing(p,r)));}
  const json=async url=>{const r=await fetch(url);if(!r.ok)throw Error('Inspector data could not load.');return r.json();};
  async function pixels(url) {const image=new Image();image.src=url;await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Inspector raster could not load.'));});const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);return {data:ctx.getImageData(0,0,canvas.width,canvas.height).data,width:canvas.width,height:canvas.height};}
  const api={utm43,segmentSquared,geometrySquared,insideGeometry}; window.AtlasInspectorMath=api;
  function init(atlas) {
    if(atlas.inspector)return;
    const map=atlas.map,wrap=document.querySelector('.map-wrap'),tools=document.querySelector('.map-tools');if(!map||!wrap||!tools)return;
    const toggle=document.createElement('button');toggle.id='inspect-toggle';toggle.type='button';toggle.textContent='Inspect map';toggle.setAttribute('aria-pressed','true');toggle.title='Click any point on the map to inspect its data';tools.prepend(toggle);
    const centre=document.createElement('button');centre.id='inspect-centre';centre.type='button';centre.textContent='Inspect centre';centre.title='Inspect the map centre without clicking the map';toggle.after(centre);
    const panel=document.createElement('section');panel.className='point-inspector';panel.hidden=true;panel.setAttribute('aria-label','Map point inspector');
    panel.innerHTML='<header><div><span>Point inspector</span><h2>A place, in detail</h2></div><button type="button" class="inspect-close" aria-label="Close point inspector">×</button></header><div class="inspect-body" aria-live="polite"></div><details class="inspect-coordinate-entry"><summary>Enter coordinates</summary><form><label>Latitude<input name="latitude" aria-label="Inspector latitude" type="number" step="any" min="-85" max="85" required></label><label>Longitude<input name="longitude" aria-label="Inspector longitude" type="number" step="any" min="-180" max="180" required></label><button type="submit">Inspect point</button></form></details>';
    wrap.append(panel);L.DomEvent.disableClickPropagation(panel);L.DomEvent.disableScrollPropagation(panel);
    let enabled=true,marker=null,request=0,bundlePromise=null,last=null;
    const body=panel.querySelector('.inspect-body');
    async function bundle() {
      if(!bundlePromise)bundlePromise=Promise.all([json('data/inspector.json'),json('data/inspector-features.json')]).then(async ([meta,features])=>{
        const grids={};for(const [id,d] of Object.entries(meta.datasets))grids[id]=await pixels('data/'+d.image);
        return {meta,features,grids};
      }).catch(e=>{bundlePromise=null;throw e;});
      return bundlePromise;
    }
    function close(){panel.hidden=true;if(marker){map.removeLayer(marker);marker=null;}wrap.classList.remove('inspector-open');}
    const source=(label,url,date)=>`<small>${url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>`:escape(label)}<span>${escape(date)}</span></small>`;
    function row(label,value,note,src){return `<div class="inspect-reading"><dt>${escape(label)}</dt><dd>${escape(value)}</dd>${note?`<p>${escape(note)}</p>`:''}${src}</div>`;}
    function sample(meta,grids,id,lat,lng) {
      const g=meta.grid,d=meta.datasets[id],im=grids[id],b=g.bounds3857;
      const x=R*lng*Math.PI/180,y=R*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
      const col=Math.floor((x-b[0])/(b[2]-b[0])*g.width),r=Math.floor((b[3]-y)/(b[3]-b[1])*g.height);
      if(col<0||r<0||col>=g.width||r>=g.height)return null;
      const i=(r*g.width+col)*4,raw=d.encoding==='uint8'?im.data[i]:im.data[i]*256+im.data[i+1];
      return raw===d.nodata?null:raw*(d.scale??1)+(d.offset??0);
    }
    async function inspect(latlng) {
      const token=++request;last={lat:latlng.lat,lng:latlng.lng};panel.hidden=false;wrap.classList.add('inspector-open');
      document.querySelector('#info-panel')?.classList.remove('open');map.closePopup();
      if(marker)map.removeLayer(marker);marker=L.circleMarker(latlng,{radius:7,color:'#fff',weight:2,fillColor:'#1c658e',fillOpacity:1,interactive:false}).addTo(map);
      panel.querySelector('[name=latitude]').value=latlng.lat.toFixed(5);panel.querySelector('[name=longitude]').value=latlng.lng.toFixed(5);
      body.innerHTML='<p class="inspect-loading" role="status">Reading the atlas data…</p>';
      panel.scrollTop=0;
      try {
        const {meta,features,grids}=await bundle();if(token!==request)return;
        const boundary=atlas.state.data.features.find(f=>f.properties.kind==='boundary');
        const inside=boundary&&insideGeometry([latlng.lng,latlng.lat],boundary.geometry);
        const e=inside?sample(meta,grids,'elevation',latlng.lat,latlng.lng):null,s=inside?sample(meta,grids,'slope',latlng.lat,latlng.lng):null,l=inside?sample(meta,grids,'landcover',latlng.lat,latlng.lng):null;
        const ls=inside&&meta.datasets.landslide?sample(meta,grids,'landslide',latlng.lat,latlng.lng):null;
        const pt=utm43(latlng.lng,latlng.lat);let nearest=null,dist=Infinity;
        if(inside)for(const f of features.features){const d=geometrySquared(pt,f.geometry);if(d<dist){dist=d;nearest=f;}}
        const coords=`${Math.abs(latlng.lat).toFixed(5)}° ${latlng.lat<0?'S':'N'}, ${Math.abs(latlng.lng).toFixed(5)}° ${latlng.lng<0?'W':'E'}`;
        const datasetRow=(id,label,value,note)=>{const d=meta.datasets[id];return row(label,value,note,source(d.source,d.sourceUrl,d.period||d.date));};
        const classes=meta.datasets.landcover.classCodes||meta.classCodes||{};
        const metres=Math.sqrt(dist),distance=metres>=1000?`${(metres/1000).toFixed(2)} km`:`${Math.round(metres/10)*10} m`;
        body.innerHTML=`<p class="inspect-coverage ${inside?'':'outside'}">${inside?'Within the Kozhikode district boundary':'Outside district coverage · no raster values assigned'}</p><dl>`+
          row('Coordinates',coords,'Selected map position, not a GPS measurement.',source('WGS 84 / map selection','',new Date().toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})))+
          datasetRow('elevation','Surface elevation',e==null?'No data':`${Math.round(e).toLocaleString()} m`,e==null?'No valid district pixel.':'EGM2008 height · includes canopy and buildings.')+
          datasetRow('slope','Surface slope',s==null?'No data':`${s.toFixed(1)}°`,s==null?'No valid district pixel.':'90 m metric analysis · DSM-derived, not a site survey.')+
          datasetRow('landcover','Land cover',l==null?'No data':classes[String(l)]||`Class ${l}`,l==null?'No valid district pixel.':`WorldCover class ${l} · modelled, not ground verified.`)+
          (meta.datasets.landslide?datasetRow('landslide','Landslide susceptibility',ls==null?(inside?'No data':'Outside district coverage'):meta.datasets.landslide.classCodes[String(ls)]+(ls<4?' susceptibility':''),'GSI zones, not a probability or live warning. Low or unmapped does not mean safe. Approx. 100 m query cells cannot assess a property; runout may extend beyond zones.'):'')+
          row('Nearest named feature',nearest?nearest.name:'Not queried outside coverage',nearest?`${distance} straight-line to mapped ${nearest.kind} geometry · nearest in this atlas, not every real-world feature.`:'Named-feature coverage is limited to the district dataset.',source('© OpenStreetMap contributors',nearest?.osm_id?`https://www.openstreetmap.org/${nearest.geometry.type==='Point'?'node':'way'}/${nearest.osm_id}`:'https://www.openstreetmap.org/copyright',nearest?.date||features.date||'Snapshot 19 Oct 2026'))+
          '</dl><p class="inspect-method">Raster values are sampled from the atlas’s approximately 100 m query grid, not native-resolution or live observations. Dates refer to each source product; the DEM release date is not its acquisition date.</p><button type="button" class="inspect-copy">Copy coordinates</button>';
        body.querySelector('.inspect-copy').onclick=async()=>{const b=body.querySelector('.inspect-copy');try{await navigator.clipboard.writeText(`${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`);b.textContent='Copied';}catch{b.textContent=`${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;}};
        panel.scrollTop=0;
        api.last={coordinates:last,inside,elevation:e,slope:s,landcover:l,landslide:ls,nearest:nearest?.name,distanceMetres:nearest?metres:null};
      } catch(error) {if(token!==request)return;body.innerHTML='<p class="inspect-error">Point data could not load. Check your connection, then select the point again.</p>';}
    }
    toggle.onclick=()=>{enabled=!enabled;toggle.setAttribute('aria-pressed',String(enabled));wrap.classList.toggle('inspection-enabled',enabled);if(!enabled)close();};
    centre.onclick=()=>inspect(map.getCenter());panel.querySelector('.inspect-close').onclick=()=>{request++;close();toggle.focus({preventScroll:true});};
    panel.querySelector('form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget,lat=Number(form.elements.latitude.value),lng=Number(form.elements.longitude.value);if(!Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>85||Math.abs(lng)>180){body.textContent='Enter a valid latitude (−85 to 85) and longitude (−180 to 180).';return;}const ll=L.latLng(lat,lng);map.panTo(ll);inspect(ll);};
    map.on('click',event=>{if(enabled)inspect(event.latlng);});
    map.getContainer().addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.target.closest('a,button,input')){event.preventDefault();inspect(map.getCenter());}});
    panel.addEventListener('keydown',event=>{if(event.key==='Escape'){request++;close();toggle.focus({preventScroll:true});}});
    wrap.classList.add('inspection-enabled');atlas.inspector={inspect,close,math:api};
  }
  if(window.atlas?.map)init(window.atlas);else document.addEventListener('atlas-ready',()=>init(window.atlas),{once:true});
})();
