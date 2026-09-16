import {createMotionCharts} from './motion_charts.js';
import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';

const $=id=>document.getElementById(id);
const data=JSON.parse($('dataset').textContent),trials=data.trials;
let selected=Math.max(0,trials.findIndex(t=>t.success&&!t.excluded)),now=0,playing=false,previousWall=0,aggregate=false,view='oblique',heightScale=180;
const host=$('stage'),scene=new THREE.Scene();scene.background=new THREE.Color('#101922');
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;host.prepend(renderer.domElement);
const camera=new THREE.PerspectiveCamera(36,1,1,6000),controls=new OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;controls.dampingFactor=.09;controls.minDistance=350;controls.maxDistance=3000;controls.maxPolarAngle=Math.PI*.49;
scene.add(new THREE.HemisphereLight(0xf7fbff,0x33444f,2.4));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(400,900,200);scene.add(light);
const plate=new THREE.Mesh(new THREE.BoxGeometry(390,10,830),new THREE.MeshStandardMaterial({color:0x24394b,roughness:.85}));plate.position.y=-6;scene.add(plate);
const border=new THREE.LineSegments(new THREE.EdgesGeometry(plate.geometry),new THREE.LineBasicMaterial({color:0x879eab}));border.position.copy(plate.position);scene.add(border);
const gridCoordinates=[];for(let x=-195;x<=195;x+=50)gridCoordinates.push(x,-.6,-415,x,-.6,415);for(let z=-415;z<=415;z+=50)gridCoordinates.push(-195,-.6,z,195,-.6,z);
const grid=new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(gridCoordinates,3)),new THREE.LineBasicMaterial({color:0x537187,transparent:true,opacity:.65}));scene.add(grid);
function ring(radius,color){const n=new THREE.Mesh(new THREE.RingGeometry(Math.max(0,radius-1.4),radius+1.4,64),new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,transparent:true,opacity:.85}));n.rotation.x=-Math.PI/2;n.position.y=-.1;scene.add(n);return n}
const startRing=ring(32,0x8194a3),targetRing=ring(40,0x9165d7);
const cursorGroup=new THREE.Group();scene.add(cursorGroup);
const cursor=new THREE.Mesh(new THREE.SphereGeometry(5,16,12),new THREE.MeshBasicMaterial({color:0x38d5e8}));cursorGroup.add(cursor);
const drop=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineDashedMaterial({color:0x859faf,dashSize:7,gapSize:5}));cursorGroup.add(drop);
let traceGroup=new THREE.Group(),pointCloud=null,lines=[],projectionLines=[],records=[],hoverAxes=new THREE.Group();scene.add(traceGroup);scene.add(hoverAxes);
const horizontalAxes=new THREE.Group();scene.add(horizontalAxes);
function textSprite(text,color='#c1d5e5',size=30){const canvas=document.createElement('canvas');canvas.width=512;canvas.height=64;const c=canvas.getContext('2d');c.font='40px -apple-system,sans-serif';c.fillStyle=color;c.textAlign='center';c.textBaseline='middle';c.fillText(text,256,32);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const n=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthTest:false}));n.scale.set(size*8,size,1);return n}
function label(group,text,x,y,z,size=20){const s=textSprite(text,undefined,size*2.3);s.position.set(x,y,z);group.add(s)}
for(const [x,name] of [[-195,'0'],[0,'195'],[195,'390']])label(horizontalAxes,name,x,0,452,17);
for(const [z,name] of [[-415,'0'],[0,'415'],[415,'830']])label(horizontalAxes,name,-232,0,z,17);
label(horizontalAxes,'X · 手机局部坐标（pt）',0,0,495,19);label(horizontalAxes,'Y · 手机局部坐标（pt）',-450,0,0,19);
label(horizontalAxes,'手机页面 390 × 830',0,0,-465,20);
function disposeGroup(group){group.traverse(n=>{n.geometry?.dispose();if(n.material){for(const m of (Array.isArray(n.material)?n.material:[n.material])){m.map?.dispose();m.dispose()}}});scene.remove(group)}
function axes(){disposeGroup(hoverAxes);hoverAxes=new THREE.Group();scene.add(hoverAxes);const axis=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(245,0,-415),new THREE.Vector3(245,heightScale,-415)]),new THREE.LineBasicMaterial({color:0x7897b1}));hoverAxes.add(axis);for(const v of [0,.5,1])label(hoverAxes,String(v),280,v*heightScale,-415,18);label(hoverAxes,'悬停 Z · API 原值',280,heightScale+40,-415,20);hoverAxes.visible=view!=='top'}
function position(p,flat=false){return [p[1]-1171,flat||p[4]===1?0:p[3]*heightScale,p[2]-609]}
function makeLine(positions,color,times,projection=false){const geometry=new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(positions,3));const line=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color,transparent:projection,opacity:projection ? .28 : 1,depthWrite:!projection}));line.userData.times=times;traceGroup.add(line);(projection?projectionLines:lines).push(line);return line}
function activeTrials(){return aggregate?trials.filter(t=>!t.excluded&&( $('aggregateFilter').value!=='success'||t.success)):[trials[selected]]}
function buildGeometry(){disposeGroup(traceGroup);traceGroup=new THREE.Group();scene.add(traceGroup);lines=[];projectionLines=[];records=[];const points=[],colors=[];
 for(const t of activeTrials()){
  for(const seg of t.segments){for(let k=1;k<seg.length;k++){const a=t.points[seg[k-1]],b=t.points[seg[k]],kind=a[4];let line=lines.find(n=>n.userData.kind===kind);if(!line){line=makeLine([],kind===0?0x38d5e8:0xf08336,[]);line.userData.kind=kind;line.userData.positions=[]}line.userData.positions.push(...position(a),...position(b));line.userData.times.push(b[0]);
   if(kind===0){let flat=projectionLines[0];if(!flat){flat=makeLine([],0x607789,[],true);flat.userData.positions=[]}flat.userData.positions.push(...position(a,true),...position(b,true));flat.userData.times.push(b[0])}
  }}
  for(const p of t.points){points.push(...position(p));const color=new THREE.Color(p[4]===0?0x38d5e8:0xf08336);colors.push(color.r,color.g,color.b);records.push({p,t})}
 }
 for(const n of [...lines,...projectionLines])n.geometry.setAttribute('position',new THREE.Float32BufferAttribute(n.userData.positions,3));
 pointCloud=new THREE.Points(new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(points,3)).setAttribute('color',new THREE.Float32BufferAttribute(colors,3)),new THREE.PointsMaterial({size:3.2,vertexColors:true,sizeAttenuation:true}));traceGroup.add(pointCloud);pointCloud.visible=$('dots').checked;
 traceGroup.scale.y=view==='top'?0:1;
 const t=trials[selected];startRing.visible=!aggregate&&!t.excluded;targetRing.visible=!aggregate&&!t.excluded;
 targetRing.geometry.dispose();targetRing.geometry=new THREE.RingGeometry(t.target[2]/2-1.4,t.target[2]/2+1.4,64);targetRing.position.set(t.target[0]-1171,-.1,t.target[1]-609);
 axes();update()}
function stop(){playing=false;$('play').textContent='播放'}
function select(i){stop();aggregate=false;selected=Math.max(0,Math.min(trials.length-1,i));const t=trials[selected];now=t.duration;$('trial').value=selected;$('seek').max=t.duration;$('seek').value=now;$('title').textContent=`第 ${t.index} / ${t.total} 次`;$('status').textContent=t.excluded?'手指误触 · 已排除':t.success?'成功':(data.errors[t.error]||t.error);$('status').className=t.success&&!t.excluded?'':'fail';$('task').textContent=t.task;$('condition').textContent=`距离 ${t.distance} pt · 直径 ${t.target[2]} pt · ${t.target[1]<609?'向上':'向下'}`;
 $('stats').replaceChildren();for(const [value,name] of [[(t.duration/1000).toFixed(2)+' s','原记录时长'],[t.points.length,'手机 Pencil 样本'],[t.points.filter(p=>p[4]===0).length,'悬停样本'],[t.points.filter(p=>p[4]===1).length,'接触样本']]){const b=document.createElement('div');b.className='stat';const v=document.createElement('b');v.textContent=value;const n=document.createElement('span');n.textContent=name;b.append(v,n);$('stats').append(b)}
 $('events').replaceChildren();for(const e of t.events){const n=document.createElement('div');n.className='event';const time=document.createElement('span');time.textContent=(e.t/1000).toFixed(3)+' s';const text=document.createElement('strong');text.style.fontWeight='400';text.textContent=(data.labels[e.type]||e.type)+(e.error?' · '+(data.errors[e.error]||e.error):'');n.append(time,text);n.onclick=()=>{stop();now=Math.max(0,e.t);$('seek').value=now;update()};$('events').append(n)}
 $('coverage').textContent=t.excluded?'本次因手指输入排除，不纳入轨迹分析。':t.touchWindows.length?t.touchWindows.map(w=>`${(w.t/1000).toFixed(3)} s 接触前 600 ms：${w.samples} 个手机区域悬停点；${w.rangeStartsBefore600ms?'记录起始早于窗口':'记录范围未覆盖完整窗口'}。`).join(' '):'没有手机区域内的 Pencil 接触事件。';
 [...$('session').children].forEach((n,j)=>n.classList.toggle('selected',j===selected));$('aggregate').textContent='汇总轨迹';$('aggregate').classList.remove('active');$('seek').disabled=false;$('play').disabled=t.excluded;$('touchjump').disabled=!t.touchWindows.length;$('all').disabled=t.excluded;buildGeometry()}
function update(){const t=trials[selected];
 // Single-trial records are monotonic. Aggregate mode always uses complete geometry.
 for(const n of [...lines,...projectionLines]){let count=n.userData.times.length;if(!aggregate){count=0;for(const time of n.userData.times){if(time>now)break;count++}}n.geometry.setDrawRange(0,count*2)}
 projectionLines.forEach(n=>n.visible=$('projection').checked);
 let visibleCount=records.length;if(!aggregate){visibleCount=0;for(const r of records){if(r.p[0]>now)break;visibleCount++}}pointCloud.geometry.setDrawRange(0,visibleCount);pointCloud.visible=$('dots').checked;
 const p=visibleCount?records[visibleCount-1].p:null;cursorGroup.visible=!aggregate&&!!p&&!t.excluded&&p[5]!=='ENDED'&&p[5]!=='CANCELLED'&&now-p[0]<=100;
 if(cursorGroup.visible){const xyz=position(p);if(view==='top')xyz[1]=0;cursor.position.set(...xyz);cursor.material.color.setHex(p[4]===0?0x38d5e8:0xf08336);drop.geometry.dispose();drop.geometry=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...xyz),new THREE.Vector3(xyz[0],0,xyz[2])]);drop.computeLineDistances();drop.visible=$('projection').checked&&view!=='top';$('reading').textContent=`${p[4]===0?'Pencil 悬停':'Pencil 接触'} · X ${(p[1]-976).toFixed(1)} / Y ${(p[2]-194).toFixed(1)} pt · Z ${p[3]===null?'接触平面':p[3].toFixed(3)} · 原始序号 ${p[6]}`}
 else $('reading').textContent=aggregate?`汇总 ${activeTrials().length} 条保留试次轨迹；关闭汇总后可逐次播放。`:t.excluded?'本次轨迹已排除，原失败记录保留。':'此时没有连续可用的手机区域位置样本。';
 $('time').textContent=aggregate?'汇总视图 · 完整轨迹':`${(now/1000).toFixed(3)} / ${(t.duration/1000).toFixed(3)} s`;
 const appeared=t.events.find(e=>e.type==='TARGET_DISPLAY_FRAME')||t.events.find(e=>e.type==='TARGET_APPEAR');targetRing.material.opacity=appeared && now>=appeared.t ? .95 : .22;
 [...$('events').children].forEach((n,j)=>n.classList.toggle('active',!aggregate&&t.events[j].t<=now&&(j===t.events.length-1||t.events[j+1].t>now)));
 drawHeight()}
function drawHeight(){motionCharts.draw(trials[selected],now,aggregate)}
function setView(next){view=next;controls.enableRotate=view!=='top';camera.up.set(...(view==='top'?[0,0,-1]:[0,1,0]));controls.target.set(0,view==='top'?0:60,0);camera.position.set(...(view==='top'?[0,1650,.01]:[760,920,980]));controls.update();$('oblique').classList.toggle('active',view!=='top');$('top').classList.toggle('active',view==='top');$('modeNote').textContent=view==='top'?'手机页面 · 俯视投影':'手机平面 + 悬停高度';traceGroup.scale.y=view==='top'?0:1;hoverAxes.visible=view!=='top';update()}
function resize(){const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();drawHeight()}
const raycaster=new THREE.Raycaster();raycaster.params.Points.threshold=7;const pointer=new THREE.Vector2();let lastHover=0;
renderer.domElement.addEventListener('pointermove',e=>{if(performance.now()-lastHover<40)return;lastHover=performance.now();const bounds=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-bounds.left)/bounds.width*2-1,-(e.clientY-bounds.top)/bounds.height*2+1);raycaster.setFromCamera(pointer,camera);const match=pointCloud.visible?raycaster.intersectObject(pointCloud)[0]:null;const tip=$('tooltip');if(!match){tip.style.display='none';return}const r=records[match.index],p=r.p;tip.textContent=`第 ${r.t.index} 次 · ${p[4]===0?'悬停':'接触'}\n${(p[0]/1000).toFixed(3)} s · X ${(p[1]-976).toFixed(1)}, Y ${(p[2]-194).toFixed(1)} pt\nZ ${p[3]===null?'接触平面':p[3].toFixed(3)} · 序号 ${p[6]}`;tip.style.whiteSpace='pre-line';tip.style.display='block';tip.style.left=Math.min(host.clientWidth-250,e.clientX-bounds.left+15)+'px';tip.style.top=Math.min(host.clientHeight-95,e.clientY-bounds.top+15)+'px'});
renderer.domElement.addEventListener('pointerleave',()=>$('tooltip').style.display='none');
const valid=trials.filter(t=>!t.excluded);$('summary').textContent=`${valid.length} 次保留试次 · ${valid.filter(t=>t.success).length} 次成功 · ${valid.filter(t=>!t.success).length} 次失败 · ${data.sampleCount.toLocaleString()} 个手机区域 Pencil 样本`;
const ex=data.exclusions;$('filterSummary').textContent=`排除 ${ex.fingerInput||0} 个手指样本及第 ${data.excludedTrials.join('、')} 次误触试验；另排除 ${ex.outsidePhone||0} 个手机区域外样本。`;
$('source').textContent=`来源 ${data.file} · SHA-256 ${data.sha256} · Three.js ${data.threeVersion}`;
trials.forEach((t,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`第 ${t.index} / ${t.total} 次 · ${t.excluded?'误触已排除':t.success?'成功':(data.errors[t.error]||t.error)}`;$('trial').append(o);const n=document.createElement('button');n.textContent=t.index;n.className=t.excluded?'excluded':t.success?'':'fail';n.onclick=()=>select(i);$('session').append(n)});
$('trial').onchange=()=>select(Number($('trial').value));$('prev').onclick=()=>select(selected-1);$('next').onclick=()=>select(selected+1);$('seek').oninput=()=>{stop();now=Number($('seek').value);update()};$('play').onclick=()=>{if(playing){stop();return}if(aggregate)return;if(now>=trials[selected].duration)now=0;playing=true;previousWall=0;$('play').textContent='暂停'};
$('all').onclick=()=>{stop();now=trials[selected].duration;$('seek').value=now;update()};$('touchjump').onclick=()=>{stop();now=Math.max(0,trials[selected].touchWindows[0].t-600);$('seek').value=now;update()};$('projection').onchange=update;$('dots').onchange=update;
$('heightScale').oninput=()=>{heightScale=Number($('heightScale').value);$('scaleValue').textContent=heightScale;buildGeometry()};$('oblique').onclick=()=>setView('oblique');$('top').onclick=()=>setView('top');$('reset').onclick=()=>setView(view);

function showAggregateContext(){
 const list=activeTrials(),ps=list.flatMap(t=>t.points);
 $('title').textContent='手机轨迹汇总';$('status').textContent=`保留 ${list.length} 次`;$('status').className='';
 $('task').textContent='先悬空指准目标，再点击';$('condition').textContent=$('aggregateFilter').value==='success'?'仅成功试次 · 手机区域 Pencil':'所有保留试次 · 手机区域 Pencil';
 $('stats').replaceChildren();for(const [value,name] of [[list.length,'汇总试次'],[ps.length.toLocaleString(),'手机 Pencil 样本'],[list.filter(t=>t.success).length,'成功试次'],[list.filter(t=>!t.success).length,'失败试次']]){const b=document.createElement('div');b.className='stat';const v=document.createElement('b');v.textContent=value;const n=document.createElement('span');n.textContent=name;b.append(v,n);$('stats').append(b)}
 $('events').replaceChildren();$('coverage').textContent='返回单次查看事件时间线和点击前 600 ms 的数据覆盖。';
}
$('aggregate').onclick=()=>{stop();if(aggregate){select(selected);return}aggregate=true;showAggregateContext();$('aggregate').textContent=aggregate?'返回单次':'汇总轨迹';$('aggregate').classList.toggle('active',aggregate);$('seek').disabled=aggregate;$('play').disabled=aggregate||trials[selected].excluded;$('touchjump').disabled=aggregate||!trials[selected].touchWindows.length;$('all').disabled=aggregate||trials[selected].excluded;buildGeometry()};$('aggregateFilter').onchange=()=>{if(aggregate){showAggregateContext();buildGeometry()}};
const motionCharts=createMotionCharts(data,time=>{stop();now=time;$('seek').value=now;update()});
new ResizeObserver(resize).observe(host);select(selected);setView('oblique');resize();
renderer.setAnimationLoop(wall=>{if(playing){if(previousWall)now=Math.min(trials[selected].duration,now+(wall-previousWall)*Number($('speed').value));previousWall=wall;$('seek').value=now;update();if(now>=trials[selected].duration)stop()}controls.update();renderer.render(scene,camera)});
