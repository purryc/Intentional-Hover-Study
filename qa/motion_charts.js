const $ = id => document.getElementById(id);
const metrics = [
  ['speed','平面速度','pt/s'], ['distance','到目标中心的距离','pt'],
  ['z','悬停高度 Z','API 原值'], ['acceleration','切向加速度 · 速度变化率','pt/s²']
];

export function createMotionCharts(data, onSeek) {
  let lastTrial, lastNow=0, lastAggregate=false, signature='', cached=[];
  const curvesFor=t=>data.kinematics.trials[String(t.index)];
  function medianTrend(segment) {
    if ($('motionStyle').value==='raw') return segment;
    return segment.map(p=>{
      const values=segment.filter(q=>Math.abs(q[0]-p[0])<=40).map(q=>q[1]).sort((a,b)=>a-b);
      const n=values.length;
      return [p[0],n%2?values[(n-1)/2]:(values[n/2-1]+values[n/2])/2,p[2]];
    });
  }
  function draw(trial, now, aggregate) {
    lastTrial=trial;lastNow=now;lastAggregate=aggregate;
    const aligned=aggregate||$('motionMode').value==='align';
    const list=aligned?data.trials.filter(t=>!t.excluded&&curvesFor(t).touchMs!==null&&
      ($('motionScope').value==='all'||(t.success? 'success':'fail')===$('motionScope').value)&&
      ($('motionDistance').value==='all'||String(t.distance)===$('motionDistance').value)&&
      ($('motionSize').value==='all'||String(t.target[2])===$('motionSize').value)):[trial];
    for (const id of ['motionScope','motionDistance','motionSize']) $(id).disabled=!aligned;
    const touch=curvesFor(trial).touchMs;
    $('motionSummary').textContent=aligned?`落笔对齐：${list.length} 次有有效 Pencil 接触的试验 · 0 ms 为每次首次落笔 · 窗口 −600 至 +100 ms · 淡线为各试次，亮线为当前试次（若符合筛选）。`:
      trial.excluded?'误触试次已排除，没有运动曲线。':`第 ${trial.index} 次 · ${touch===null?'没有有效落笔事件':`首次落笔 ${(touch/1000).toFixed(3)} s`} · 青色悬停，橙色接触 · 点击曲线可跳转回放。`;
    const key=[trial.index,aligned,$('motionScope').value,$('motionDistance').value,$('motionSize').value,$('motionStyle').value,
      ...metrics.map(([name])=>$('motion-'+name).clientWidth)].join('|');
    if(key!==signature){
      signature=key;cached=[];
      for(const [name,title,unit] of metrics){
        const canvas=$('motion-'+name),w=canvas.clientWidth,h=150,dpr=Math.min(devicePixelRatio,2);
        if(!w)continue;
        canvas.width=w*dpr;canvas.height=h*dpr;
        const background=document.createElement('canvas');background.width=canvas.width;background.height=canvas.height;
        const c=background.getContext('2d');c.scale(dpr,dpr);c.fillStyle='#101922';c.fillRect(0,0,w,h);
        const minX=aligned?-600:0,maxX=aligned?100:Math.max(1,trial.duration);
        const x=v=>64+(v-minX)/(maxX-minX)*(w-82);
        const sets=list.flatMap(t=>curvesFor(t).curves[name].map(seg=>({t,points:medianTrend(seg).map(p=>[p[0]-(aligned?curvesFor(t).touchMs:0),p[1],p[2]]).filter(p=>p[0]>=minX&&p[0]<=maxX)})));
        const values=sets.flatMap(s=>s.points.map(p=>p[1]));
        let minY=name==='acceleration'?Math.min(0,...values):0,maxY=name==='z'?1:Math.max(1,...values);
        if(name==='acceleration'){const extent=Math.max(1,Math.abs(minY),Math.abs(maxY));minY=-extent;maxY=extent}
        const y=v=>30+(maxY-v)/(maxY-minY)*88;
        c.font='12px -apple-system,sans-serif';c.fillStyle='#cfdfed';c.fillText(`${title}（${unit}）`,64,17);
        c.font='10px -apple-system,sans-serif';
        for(let i=0;i<=2;i++){const v=minY+(maxY-minY)*i/2;c.strokeStyle='#2a3c50';c.beginPath();c.moveTo(64,y(v));c.lineTo(w-18,y(v));c.stroke();c.fillStyle='#a5bcd2';c.fillText(Math.abs(v)>=1000?v.toExponential(1):v.toFixed(name==='z'?1:0),4,y(v)+4)}
        for(let i=0;i<=4;i++){const v=minX+(maxX-minX)*i/4;c.fillText(aligned?`${v.toFixed(0)} ms`:`${(v/1000).toFixed(2)} s`,Math.min(w-48,x(v)-15),140)}
        const marker=aligned?0:touch;
        if(marker!==null){c.strokeStyle='#ff9854';c.setLineDash([4,4]);c.beginPath();c.moveTo(x(marker),26);c.lineTo(x(marker),120);c.stroke();c.setLineDash([])}
        // Each source segment is drawn separately, including after filtering.
        for(const set of sets.sort((a,b)=>(a.t.index===trial.index)-(b.t.index===trial.index))){
          if(!set.points.length)continue;
          c.strokeStyle=aligned&&set.t.index!==trial.index?'#86b8c955':set.points[0][2]===0?'#38d5e8':'#ff9854';
          c.lineWidth=aligned&&set.t.index!==trial.index?1:1.7;c.beginPath();
          set.points.forEach((p,i)=>i?c.lineTo(x(p[0]),y(p[1])):c.moveTo(x(p[0]),y(p[1])));c.stroke();
          if(set.points.length===1){c.fillStyle=c.strokeStyle;c.fillRect(x(set.points[0][0])-1,y(set.points[0][1])-1,2,2)}
        }
        if(!values.length){c.fillStyle='#a5bcd2';c.fillText('当前筛选没有可用数据',64,70)}
        cached.push({canvas,background,x,dpr,minX,maxX});
      }
    }
    for(const item of cached){const c=item.canvas.getContext('2d');c.setTransform(1,0,0,1,0,0);c.drawImage(item.background,0,0);
      if(!aligned&&!trial.excluded){c.scale(item.dpr,item.dpr);c.strokeStyle='#f0f6ff';c.beginPath();c.moveTo(item.x(now),26);c.lineTo(item.x(now),120);c.stroke()}}
  }
  $('accelerationDetails').ontoggle=()=>{if(lastTrial)draw(lastTrial,lastNow,lastAggregate)};
  for(const id of ['motionMode','motionScope','motionDistance','motionSize','motionStyle']) $(id).onchange=()=>draw(lastTrial,lastNow,lastAggregate);
  for(const [name] of metrics) $('motion-'+name).onclick=e=>{
    if(lastAggregate||$('motionMode').value==='align'||lastTrial.excluded)return;
    const bounds=e.currentTarget.getBoundingClientRect(),ratio=(e.clientX-bounds.left-64)/(bounds.width-82);
    onSeek(Math.max(0,Math.min(lastTrial.duration,ratio*lastTrial.duration)));
  };
  return {draw};
}
