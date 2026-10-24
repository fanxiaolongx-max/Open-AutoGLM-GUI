// Pure frame preparation: replay never sends an input event to a device.
export function markerForAction(action) {
    if (!action) return null;
    const start=action.element || action.start, end=action.end;
    if(!Array.isArray(start) || start.length<2)return null;
    const point=p=>p.slice(0,2).map(value=>Math.max(0,Math.min(100,Number(value)/10)));
    const [x,y]=point(start), [x2,y2]=Array.isArray(end)?point(end):[x,y];
    if(![x,y,x2,y2].every(Number.isFinite))return null;
    return {x,y,x2,y2,swipe:Array.isArray(end)};
}
export function buildTaskFrames(events,device) {
    const ordered=events.filter(e=>!device || e.device_id===device).slice().sort((a,b)=>a.seq-b.seq);
    return ordered.filter(e=>e.kind==='screen' && e.data.image_id).map(screen=>{
        const next=ordered.find(e=>e.seq>screen.seq && e.kind==='screen');
        const action=ordered.find(e=>e.seq>screen.seq && (!next||e.seq<next.seq) && e.kind==='action');
        return {...screen.data,seq:screen.seq,device_id:screen.device_id,
            action:action?.data.action,label:screen.data.final?'最终画面':`步骤 ${screen.data.step||'—'}`};
    });
}
export function buildDemoFrames(demo) {
    return (demo?.actions||[]).filter(a=>a.image_id).map((entry,index)=>{
        const d=entry.data||{};
        let action={action:entry.kind};
        if(d.start && d.width && d.height){
            const normalize=p=>[p[0]/d.width*1000,p[1]/d.height*1000];
            action.element=normalize(d.start);
            if(entry.kind==='swipe' && d.end){action.start=action.element;delete action.element;action.end=normalize(d.end);}
        }
        return {seq:index+1,image_id:entry.image_id,device_id:demo.device_id,
            width:d.width,height:d.height,action,label:`动作 ${index+1} · ${entry.kind}`};
    });
}
