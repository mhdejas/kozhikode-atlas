'use strict';
(() => {
  const host=document.querySelector('#terrain-viewport');
  if(!host)return;
  const card=document.querySelector('.terrain-card'), status=document.querySelector('#terrain-loading');
  const buttons={spin:document.querySelector('#terrain-spin'),top:document.querySelector('#terrain-top'),reset:document.querySelector('#terrain-reset'),left:document.querySelector('#terrain-left'),right:document.querySelector('#terrain-right'),wire:document.querySelector('#terrain-wire')};
  const relief=document.querySelector('#terrain-relief'), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let data, model, engine, visible=false, frame=0, last=0, disposed=false;
  const view={yaw:.85,tilt:.98,exaggeration:6,spin:!reduced.matches,wire:false,zoom:1,contours:false,colour:true,labels:true,selected:-1};
  const bins=['#440154','#3b528b','#21918c','#5ec962','#fde725'];
  const bin=h=>h<50?0:h<200?1:h<500?2:h<1000?3:4;
  const setSpin=value=>{view.spin=value&&!reduced.matches;buttons.spin.textContent=reduced.matches?'Rotation paused':view.spin?'Pause rotation':'Start rotation';buttons.spin.setAttribute('aria-pressed',String(view.spin));schedule();};
  function schedule(){if(!frame&&engine&&visible&&!document.hidden&&!disposed)frame=requestAnimationFrame(tick);}
  function tick(time){frame=0;if(!engine||!visible||document.hidden||disposed)return;const dt=Math.min((time-last)/1000,.05);last=time;if(view.spin)view.yaw+=dt*.10;engine.render(view,dt);card.dataset.frames=String((Number(card.dataset.frames)||0)+1);if(view.spin)schedule();}
  function resize(){if(!engine)return;engine.resize();schedule();}
  function fail(message){status.hidden=false;status.textContent=message;status.setAttribute('role','status');card.dataset.renderer='unavailable';delete card.dataset.loading;document.querySelector('#terrain-fallback-note')?.replaceChildren(document.createTextNode('The 2D atlas below remains available.'));}
  function buildModel(d){
    const [minX,minY,maxX,maxY]=d.extent,span=Math.max(maxX-minX,maxY-minY),unit=10/span;
    const centerX=(minX+maxX)/2,centerY=(minY+maxY)/2;
    const world=(x,y,h=0)=>[(x-centerX)*unit,h*unit,-(y-centerY)*unit];
    const positions=[];
    for(let r=0;r<d.height;r++)for(let c=0;c<d.width;c++){
      const x=minX+(c+.5)*(maxX-minX)/d.width,y=maxY-(r+.5)*(maxY-minY)/d.height;
      positions.push(world(x,y,d.heights[r*d.width+c]??0));
    }
    const triangles=[];
    for(let r=0;r<d.height-1;r++)for(let c=0;c<d.width-1;c++){
      const a=r*d.width+c,b=a+1,k=a+d.width,l=k+1;
      for(const t of [[a,k,b],[b,k,l]])if(t.every(i=>d.heights[i]!==null&&Number.isFinite(d.heights[i])))triangles.push(t);
    }
    const rings=(d.boundary||[]).map(r=>r.map(p=>world(p[0],p[1],0)));
    const places=(d.places||[]).filter(p=>Number.isFinite(p.height)).map(p=>({...p,point:world(p.easting,p.northing,p.height)}));
    const contours=[];
    for(const level of [50,200,500,1000,1500,2000])for(const t of triangles){const hits=[];for(const [i,j] of [[0,1],[1,2],[2,0]]){const a=t[i],b=t[j],ha=d.heights[a],hb=d.heights[b];if((ha<level&&hb>=level)||(hb<level&&ha>=level)){const f=(level-ha)/(hb-ha);hits.push([positions[a][0]+f*(positions[b][0]-positions[a][0]),level*unit,positions[a][2]+f*(positions[b][2]-positions[a][2])]);}}if(hits.length===2)contours.push(hits);}
    return {positions,triangles,rings,places,unit,contours};
  }
  function software(model,canvas){
    const ctx=canvas.getContext('2d');if(!ctx)throw Error('Canvas unavailable');
    let width=0,height=0,dpr=1,drag=null,dragStart=null,hits=[];
    function resize(){width=Math.max(1,host.clientWidth);height=Math.max(1,host.clientHeight);dpr=Math.min(devicePixelRatio||1,1.5);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';}
    function render(v){
      if(!width||!height)return;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
      const cy=Math.cos(v.yaw),sy=Math.sin(v.yaw),ct=Math.cos(v.tilt),st=Math.sin(v.tilt),scale=Math.min(width/14,height/10)*v.zoom;
      const project=p=>{const x=p[0]*cy+p[2]*sy,z=-p[0]*sy+p[2]*cy,y=p[1]*v.exaggeration;return [width*.47+x*scale,height*.53-(y*ct-z*st)*scale,y*st+z*ct];};
      // A neutral drafting grid, not a water or land classification.
      ctx.lineWidth=.65;ctx.strokeStyle='#54748244';
      for(let i=-6;i<=6;i++){const a=project([i,-.055,-6]),b=project([i,-.055,6]),c=project([-6,-.055,i]),d=project([6,-.055,i]);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.moveTo(c[0],c[1]);ctx.lineTo(d[0],d[1]);ctx.stroke();}
      for(const ring of model.rings){ctx.beginPath();ring.forEach((p,i)=>{const a=project([p[0],-.045,p[2]]);i?ctx.lineTo(a[0],a[1]):ctx.moveTo(a[0],a[1]);});ctx.closePath();ctx.fillStyle='#082332';ctx.fill();ctx.strokeStyle='#467b8b';ctx.lineWidth=1;ctx.stroke();}
      const points=model.positions.map(project);
      const ordered=model.triangles.map(t=>({t,z:(points[t[0]][2]+points[t[1]][2]+points[t[2]][2])/3})).sort((a,b)=>a.z-b.z);
      for(const {t} of ordered){
        const a=model.positions[t[0]],b=model.positions[t[1]],c=model.positions[t[2]],h=(data.heights[t[0]]+data.heights[t[1]]+data.heights[t[2]])/3;
        const u=[b[0]-a[0],(b[1]-a[1])*v.exaggeration,b[2]-a[2]],w=[c[0]-a[0],(c[1]-a[1])*v.exaggeration,c[2]-a[2]];
        let nx=u[1]*w[2]-u[2]*w[1],ny=u[2]*w[0]-u[0]*w[2],nz=u[0]*w[1]-u[1]*w[0];if(ny<0){nx=-nx;ny=-ny;nz=-nz;}const len=Math.hypot(nx,ny,nz)||1;
        const light=.55+.45*Math.max(0,(nx*-.35+ny*.8+nz*.4)/len);
        const hex=v.colour?bins[bin(h)]:'#9bb8a5',rgb=[1,3,5].map(i=>Math.round(parseInt(hex.slice(i,i+2),16)*light));
        ctx.beginPath();t.forEach((index,i)=>{const p=points[index];i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});ctx.closePath();ctx.fillStyle=`rgb(${rgb.join(',')})`;ctx.fill();
        ctx.strokeStyle=v.wire?'#c7f5ef66':ctx.fillStyle;ctx.lineWidth=v.wire?.5:.4;ctx.stroke();
      }
      if(v.contours){ctx.strokeStyle='#f1e4b7aa';ctx.lineWidth=.65;for(const segment of model.contours){const a=project(segment[0]),b=project(segment[1]);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}}
      hits=[];
      ctx.font='11px "DM Sans",Arial,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
      const north=project([0,0,-5.8]);ctx.fillStyle='#b7d5df';ctx.fillText('N',north[0],Math.max(60,north[1]));
      for(const [index,place] of model.places.entries()){if(!v.labels&&index!==v.selected)continue;const p=project([place.point[0],place.point[1]+.003,place.point[2]]);if(p[0]<20||p[0]>width-115||p[1]<60||p[1]>height-40)continue;hits.push({index,x:p[0],y:p[1]});if(index===v.selected){ctx.strokeStyle='#ffe4a4';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(p[0],p[1],7,0,Math.PI*2);ctx.stroke();}ctx.fillStyle=index===v.selected?'#ffe4a4':'#d9f9fb';ctx.beginPath();ctx.arc(p[0],p[1],index===v.selected?3:2,0,Math.PI*2);ctx.fill();ctx.font='10px "DM Sans",Arial,sans-serif';ctx.textAlign='left';ctx.strokeStyle='#102e3e';ctx.lineWidth=3;ctx.strokeText(place.name,p[0]+6,p[1]-4);ctx.fillText(place.name,p[0]+6,p[1]-4);}
    }
    canvas.addEventListener('pointerdown',e=>{dragStart={x:e.clientX,y:e.clientY};drag={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);setSpin(false);});
    canvas.addEventListener('pointermove',e=>{if(!drag)return;view.yaw+=(e.clientX-drag.x)*.009;if(e.pointerType!=='touch')view.tilt=Math.max(.15,Math.min(1.45,view.tilt+(e.clientY-drag.y)*.008));drag={x:e.clientX,y:e.clientY};schedule();});
    canvas.addEventListener('pointerup',e=>{if(dragStart&&Math.hypot(e.clientX-dragStart.x,e.clientY-dragStart.y)<6){const box=canvas.getBoundingClientRect(),x=e.clientX-box.left,y=e.clientY-box.top;const hit=hits.find(p=>Math.hypot(p.x-x,p.y-y)<17);if(hit)selectFeature(hit.index);}drag=null;dragStart=null;});
    for(const name of ['pointercancel','lostpointercapture'])canvas.addEventListener(name,()=>{drag=null;dragStart=null;});
    resize();return {render,resize,dispose(){ctx.clearRect(0,0,width,height);}};
  }
  async function webgl(model,canvas,context){
    const THREE=await import('./vendor/three/three.module.js');
    const {OrbitControls}=await import('./vendor/three/OrbitControls.js');
    const renderer=new THREE.WebGLRenderer({canvas,context,antialias:true,alpha:true,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5));renderer.outputColorSpace=THREE.SRGBColorSpace;
    const scene=new THREE.Scene();
    const camera=new THREE.PerspectiveCamera(37,1,.1,100);camera.position.set(10,10,13);
    const controls=new OrbitControls(camera,canvas);controls.enableDamping=false;controls.enablePan=false;controls.enableZoom=false;controls.minPolarAngle=.18;controls.maxPolarAngle=1.4;controls.target.set(0,.5,0);
    controls.addEventListener('start',()=>setSpin(false));controls.addEventListener('change',()=>{if(!syncing){const delta=camera.position.clone().sub(controls.target);view.yaw=Math.atan2(delta.x,delta.z);view.tilt=Math.PI/2-Math.acos(delta.y/delta.length());schedule();}});
    let syncing=false;
    const geometry=new THREE.BufferGeometry();const vertices=new Float32Array(model.positions.flat());geometry.setAttribute('position',new THREE.BufferAttribute(vertices,3));geometry.setIndex(model.triangles.flat());
    const colors=[];for(const h of data.heights){const c=new THREE.Color(bins[bin(h??0)]);colors.push(c.r,c.g,c.b);}geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geometry.computeVertexNormals();
    const material=new THREE.MeshStandardMaterial({vertexColors:true,roughness:.9,metalness:0,side:THREE.DoubleSide});const mesh=new THREE.Mesh(geometry,material);scene.add(mesh);
    scene.add(new THREE.HemisphereLight(0xe7f9ff,0x233d43,2));const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(-6,12,5);scene.add(sun);
    const grid=new THREE.GridHelper(13,13,0x426678,0x284c5b);grid.position.y=-.12;scene.add(grid);
    const ringObjects=model.rings.map(r=>{const g=new THREE.BufferGeometry().setFromPoints(r.map(p=>new THREE.Vector3(p[0],-.08,p[2])));const line=new THREE.LineLoop(g,new THREE.LineBasicMaterial({color:0x78b8bd}));scene.add(line);return line;});
    const contourGeometry=new THREE.BufferGeometry().setFromPoints(model.contours.flat().map(p=>new THREE.Vector3(...p)));const contourLines=new THREE.LineSegments(contourGeometry,new THREE.LineBasicMaterial({color:0xf4e2ae,transparent:true,opacity:.75}));scene.add(contourLines);
    const markers=model.places.map((p,index)=>{const dot=new THREE.Mesh(new THREE.SphereGeometry(.055,8,6),new THREE.MeshBasicMaterial({color:0xd4e5d1}));dot.userData.index=index;scene.add(dot);return dot;});
    const raycaster=new THREE.Raycaster();canvas.addEventListener('click',event=>{const r=canvas.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2(((event.clientX-r.left)/r.width)*2-1,-((event.clientY-r.top)/r.height)*2+1),camera);const hit=raycaster.intersectObjects(markers).find(x=>x.object.visible);if(hit)selectFeature(hit.object.userData.index);});
    let exaggeration=-1,colour=true;
    function resize(){const w=Math.max(1,host.clientWidth),h=Math.max(1,host.clientHeight);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
    function render(v){syncing=true;if(exaggeration!==v.exaggeration){for(let i=0;i<model.positions.length;i++)vertices[i*3+1]=model.positions[i][1]*v.exaggeration;geometry.attributes.position.needsUpdate=true;geometry.computeVertexNormals();exaggeration=v.exaggeration;}material.wireframe=v.wire;if(colour!==v.colour){material.vertexColors=v.colour;material.color.set(v.colour?0xffffff:0x9bb8a5);material.needsUpdate=true;colour=v.colour;}contourLines.visible=v.contours;contourLines.scale.y=v.exaggeration;markers.forEach((dot,i)=>{const p=model.places[i].point;dot.position.set(p[0],p[1]*v.exaggeration+.08,p[2]);dot.visible=v.labels||i===v.selected;dot.scale.setScalar(i===v.selected?1.9:1);dot.material.color.set(i===v.selected?0xffe4a4:0xd4e5d1);});const radius=17/v.zoom;camera.position.set(Math.sin(v.yaw)*Math.cos(v.tilt)*radius,Math.sin(v.tilt)*radius+.5,Math.cos(v.yaw)*Math.cos(v.tilt)*radius);controls.update();renderer.render(scene,camera);syncing=false;}
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();cancelAnimationFrame(frame);frame=0;fail('3D rendering paused. Reload this page or use the 2D atlas below.');});
    resize();return {render,resize,dispose(){controls.dispose();scene.traverse(o=>{o.geometry?.dispose();if(o.material)Array.isArray(o.material)?o.material.forEach(m=>m.dispose()):o.material.dispose();});renderer.dispose();}};
  }
  async function start(){
    if(engine||card.dataset.loading)return;card.dataset.loading='true';
    try{
      const response=await fetch('data/terrain-3d.json');if(!response.ok)throw Error('Missing relief data');data=await response.json();
      if(data.heights.length!==data.width*data.height||data.extent.length!==4)throw Error('Invalid relief data');
      model=buildModel(data);let canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Interactive 3D relief of Kozhikode. Arrow keys rotate, plus and minus zoom. Buttons provide equivalent controls.');canvas.setAttribute('role','img');canvas.tabIndex=0;
      let gl=null;try{gl=canvas.getContext('webgl2',{antialias:true,powerPreference:'low-power'});}catch(e){}
      if(gl){try{engine=await webgl(model,canvas,gl);card.dataset.renderer='webgl';}catch(e){canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Interactive software-rendered 3D relief of Kozhikode');canvas.setAttribute('role','img');canvas.tabIndex=0;engine=software(model,canvas);card.dataset.renderer='canvas';}}
      else{engine=software(model,canvas);card.dataset.renderer='canvas';}
      host.prepend(canvas);status.hidden=true;card.dataset.ready='true';
      document.querySelector('#terrain-fallback-note').textContent=card.dataset.renderer==='canvas'?'Lightweight 3D renderer':'Interactive WebGL relief';
      const spacing=data.gridSpacingM||[];document.querySelector('#terrain-data-note').textContent=`Approx. ${Math.round(Math.max(...spacing))} m display grid · UTM 43N · EGM2008 heights. Exaggeration changes shape, not metre labels.`;
      canvas.addEventListener('keydown',event=>{let handled=true;setSpin(false);switch(event.key){case'ArrowLeft':view.yaw-=.18;break;case'ArrowRight':view.yaw+=.18;break;case'ArrowUp':view.tilt=Math.min(1.45,view.tilt+.12);break;case'ArrowDown':view.tilt=Math.max(.15,view.tilt-.12);break;case'+':case'=':view.zoom=Math.min(1.6,view.zoom+.1);break;case'-':view.zoom=Math.max(.65,view.zoom-.1);break;default:handled=false;}if(handled){event.preventDefault();schedule();}});
      const picker=document.querySelector('#terrain-feature');picker.replaceChildren(new Option('Select a mapped location','-1'));model.places.forEach((p,i)=>picker.add(new Option(p.name,String(i))));picker.disabled=false;picker.addEventListener('change',()=>selectFeature(Number(picker.value)));
      window.AtlasTerrain={setView(preset){if(Number.isFinite(preset.yaw))view.yaw=preset.yaw;if(Number.isFinite(preset.tilt))view.tilt=preset.tilt;if(Number.isFinite(preset.zoom))view.zoom=Math.max(.65,Math.min(1.6,preset.zoom));setSpin(false);schedule();},selectFeature};
      resize();setSpin(!reduced.matches);schedule();
    }catch(error){fail('The 3D relief could not load. Reload to try again, or explore the 2D atlas below.');}
  }
  function selectFeature(index){view.selected=index;const p=model?.places[index];document.querySelector('#terrain-feature').value=String(index);document.querySelector('#terrain-feature-detail').textContent=p?`${p.name} · approx. ${Math.round(p.height)} m EGM2008 · ${Math.round(p.easting).toLocaleString('en')} E / ${Math.round(p.northing).toLocaleString('en')} N (UTM 43N). Display-grid sample, not a survey.`:'Choose a named location, or select a visible marker on the terrain.';setSpin(false);schedule();}
  for(const [id,delta] of [['terrain-zoom-in',.15],['terrain-zoom-out',-.15]])document.querySelector('#'+id).addEventListener('click',()=>{view.zoom=Math.max(.65,Math.min(1.6,view.zoom+delta));schedule();});
  for(const [id,key] of [['terrain-contours','contours'],['terrain-colour','colour'],['terrain-labels','labels']])document.querySelector('#'+id).addEventListener('click',event=>{view[key]=!view[key];event.currentTarget.setAttribute('aria-pressed',String(view[key]));if(key==='colour')document.querySelector('.terrain-legend').hidden=!view.colour;schedule();});
  buttons.spin.addEventListener('click',()=>setSpin(!view.spin));
  buttons.top.addEventListener('click',()=>{setSpin(false);view.tilt=1.45;view.yaw=0;schedule();});
  buttons.reset.addEventListener('click',()=>{view.yaw=.85;view.tilt=.98;view.zoom=1;view.exaggeration=6;view.wire=false;relief.value='6';document.querySelector('#terrain-relief-value').value='6×';buttons.wire.setAttribute('aria-pressed','false');setSpin(false);schedule();});
  buttons.left.addEventListener('click',()=>{setSpin(false);view.yaw-=.3;schedule();});buttons.right.addEventListener('click',()=>{setSpin(false);view.yaw+=.3;schedule();});
  buttons.wire.addEventListener('click',()=>{view.wire=!view.wire;buttons.wire.setAttribute('aria-pressed',String(view.wire));schedule();});
  relief.addEventListener('input',()=>{view.exaggeration=Number(relief.value);document.querySelector('#terrain-relief-value').value=relief.value+'×';schedule();});
  const onReducedMotionChange=()=>{setSpin(false);buttons.spin.disabled=reduced.matches;buttons.spin.title=reduced.matches?'Automatic rotation is disabled by your reduced-motion preference.':'';schedule();};
  (reduced.addEventListener||reduced.addListener).call(reduced,'change',onReducedMotionChange);
  buttons.spin.disabled=reduced.matches;buttons.spin.title=reduced.matches?'Automatic rotation is disabled by your reduced-motion preference.':'';setSpin(!reduced.matches);
  new ResizeObserver(resize).observe(host);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){start();last=performance.now();schedule();}else{cancelAnimationFrame(frame);frame=0;}},{rootMargin:'80px'}).observe(host);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else{last=performance.now();schedule();}});
  window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);frame=0;disposed=true;engine?.dispose();});
  window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
})();
