import {buildTaskFrames,buildDemoFrames,markerForAction} from './replay.js?v=20261024-context-preview';
import {submitTask,taskEvents,taskControl} from './tasks.js?v=20261024-context-preview';
import {saveRecipeRevision,trialRecipe,portableRecipe} from './recipes.js?v=20261024-context-preview';
import {api, terminal, statusLabels, requireAutomationBackend} from './api.js?v=20261024-context-preview';
const {ref,reactive,computed,onMounted,onUnmounted,watch} = Vue;
export function useAutomation(host = {}) {
    const tab=ref('tasks'), error=ref(''), notice=ref(''), devices=host.devices || ref([]), tasks=ref([]), recipes=ref([]), demos=ref([]), triggers=ref([]), settings=ref(null);
    const selectedDevices=ref([]), content=ref(''), acceptance=ref(''), plannedSteps=ref([]), parallel=ref(false), queueTimeout=ref(1800), selectedTask=ref(null), events=ref([]), filter=ref(''), selectedEvent=ref(null), resumeNote=ref('');
    const previewDevice=host.previewDevice || ref(''), canvas=ref(null), text=ref(''), packageName=ref(''), recordText=ref(false), recordImages=ref(true), selectedDemo=ref(null), triggerHistory=ref([]);
    const editingRecipe=ref(null), parameterValues=ref({}), recipeDevice=ref(''), triggerParams=ref('{}');
    const schedule=ref({name:'',recipe_id:'',device_id:'',daily_time:'09:00',busy_policy:'queue'});
    const triggerValues=ref({}),triggerDefinition=ref(null);
    const trigger=ref({name:'',kind:'online',device_id:'',recipe_id:'',source_recipe:'',enabled:true,cooldown:300});
    let timer, eventTimer, playTimer, refreshing=false, disposed=false, initializing=false;
    let lastError='',lastErrorAt=0;
    const ready=ref(false),backendUnavailable=ref(false);
    const replaySource=ref('task'),replayDemo=ref(null),replayPosition=ref(0),replaySpeed=ref(1),playing=ref(false);
    const replayFrames=computed(()=>replaySource.value==='demo'?buildDemoFrames(replayDemo.value):buildTaskFrames(events.value,previewDevice.value));
    const currentFrame=computed(()=>replayFrames.value[replayPosition.value]||null);
    const frameMarker=computed(()=>markerForAction(currentFrame.value?.action));
    const replayTasks=computed(()=>tasks.value.filter(t=>!previewDevice.value || t.device_ids.includes(previewDevice.value)));
    const taskIndex=reactive({});
    const authorized=()=>!host.active || host.active.value;
    function navigate(page){tab.value=page;host.navigate?.(page);}
    const labels=statusLabels;
    const filteredEvents=computed(()=>events.value.filter(e=>!filter.value || (filter.value==='errors' ? e.data.success===false || ['failed','interrupted'].includes(e.data.status) : e.kind===filter.value)));
    const recording=computed(()=>demos.value.find(d=>['recording','paused'].includes(d.status) && d.device_id===previewDevice.value));
    const replayImage=computed(()=>{
        if(!selectedEvent.value) return null;
        const e=selectedEvent.value;
        return events.value.filter(v=>v.seq<=e.seq && v.device_id===e.device_id && v.data.image_id).at(-1)?.data.image_id;
    });
    const overlay=computed(()=>{
        const a=selectedEvent.value?.data.action;
        if(!a) return null;
        const p=a.element || a.start, q=a.end;
        if(!Array.isArray(p)) return null;
        return {x:p[0]/10,y:p[1]/10,x2:q?.[0]/10,y2:q?.[1]/10,swipe:Array.isArray(q)};
    });
    async function attempt(fn){
        error.value='';
        try{return await fn();}
        catch(e){
            error.value=e.message;
            if(e.code==='BACKEND_OUTDATED' || (e.code==='MISSING_ENDPOINT' && ['/health','/api/automation/settings','/api/automation/tasks','/api/recipes','/api/demonstrations','/api/triggers'].includes(e.path))){
                ready.value=false;backendUnavailable.value=true;stop();
            }
            if(e.status===401)host.onUnauthorized?.();
            if(lastError!==e.message || Date.now()-lastErrorAt>15000){
                lastError=e.message;lastErrorAt=Date.now();host.notify?.(e.message,'error');
            }
        }
    }
    async function refresh(){
        if(refreshing || disposed || !authorized() || !ready.value) return; refreshing=true;
        try{
            const data=await Promise.all([api('/api/automation/tasks'),api('/api/recipes'),api('/api/demonstrations'),api('/api/triggers')]);
            if(disposed || !authorized()) return;
            [tasks.value,recipes.value,demos.value,triggers.value]=[data[0].tasks,data[1].recipes,data[2].demonstrations,data[3].triggers];
            tasks.value.forEach(task=>taskIndex[task.id]=task);
            const visibleIds=new Set(tasks.value.map(task=>task.id));
            const missing=Object.values(taskIndex).filter(task=>!visibleIds.has(task.id) && (!terminal(task.status)||task.id===selectedTask.value?.id));
            await Promise.all(missing.map(async task=>{taskIndex[task.id]=await api(`/api/tasks/${task.id}`);}));
            if(selectedTask.value){selectedTask.value=taskIndex[selectedTask.value.id]||selectedTask.value;await loadEvents();}
            if(selectedDemo.value) selectedDemo.value=demos.value.find(d=>d.id===selectedDemo.value.id)||selectedDemo.value;
        }finally{refreshing=false;}
    }
    async function loadEvents(){
        if(!selectedTask.value) return; const id=selectedTask.value.id;
        let cursor=events.value.at(-1)?.seq||0;
        while(true){const data=await taskEvents(id,cursor);
            if(selectedTask.value?.id!==id) return;
            const seen=new Set(events.value.map(e=>e.seq)); events.value.push(...data.events.filter(e=>!seen.has(e.seq)));
            cursor=data.cursor; if(data.events.length<500) break;}
        if(!selectedEvent.value) selectedEvent.value=events.value.at(-1)||null;
    }
    async function openTask(task){taskIndex[task.id]=task;selectedTask.value=task;events.value=[];selectedEvent.value=null;await attempt(loadEvents);}
    async function run(force=false){await attempt(async()=>{
        const result=await submitTask({task_content:content.value,device_ids:selectedDevices.value,steps:plannedSteps.value.length?plannedSteps.value:undefined,acceptance:acceptance.value||null,parallel:parallel.value,queue:true,queue_timeout:queueTimeout.value,force_run:force});
        notice.value='任务已保存到后端队列，可关闭此页面';await refresh();await openTask(tasks.value.find(t=>t.id===result.task_id));});}
    async function decompose(){await attempt(async()=>{const result=await api('/api/tasks/decompose','POST',{task_content:content.value});plannedSteps.value=result.todoList.map(s=>({...s,timeout:180,repeatable:false,retry_once:false}));});}
    async function control(task,action,note=resumeNote.value){await attempt(async()=>{taskIndex[task.id]=await taskControl(task.id,action,note);await refresh();});}
    async function pinReplay(pinned){if(replayImage.value)await attempt(async()=>{await api(`/api/automation/images/${replayImage.value}/pin`,'POST',{pinned});notice.value=pinned?'截图已固定保留':'已取消固定';});}
    async function rerun(index){await attempt(async()=>{const t=await api(`/api/tasks/${selectedTask.value.id}/rerun`,'POST',{step_index:index});await refresh();await openTask(t);});}
    function recipeFromPlan(){editingRecipe.value={name:content.value,description:'',parameters:[],steps:JSON.parse(JSON.stringify(plannedSteps.value.length?plannedSteps.value:[{content:content.value,timeout:180}])),acceptance:acceptance.value};navigate('recipes');}
    function newRecipe(){editingRecipe.value={name:'新配方',description:'',parameters:[],steps:[{content:'',timeout:180,repeatable:false,retry_once:false}],acceptance:''};parameterValues.value={};}
    function editRecipe(r){editingRecipe.value=JSON.parse(JSON.stringify(r));parameterValues.value={};}
    function moveStep(i,delta){const a=editingRecipe.value.steps; if(i+delta>=0&&i+delta<a.length) [a[i],a[i+delta]]=[a[i+delta],a[i]];}
    async function saveRecipe(){await attempt(async()=>{const r=editingRecipe.value;const saved=await saveRecipeRevision(r);editingRecipe.value=saved;await refresh();notice.value='配方已保存为新修订，请试运行验证';});}
    async function runRecipe(){await attempt(async()=>{const r=editingRecipe.value;if(!r.id)throw new Error('请先保存配方');const t=await trialRecipe(r.id,recipeDevice.value,parameterValues.value);navigate('tasks');await refresh();await openTask(t);await host.openTask?.(t.id);});}
    async function recipeAction(r,action){await attempt(async()=>{if(action==='export'){const data=await portableRecipe(r.id);const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='recipe.json';a.click();URL.revokeObjectURL(url);}else{await api(`/api/recipes/${r.id}${action==='archive'?'':'/copy'}`,action==='archive'?'DELETE':'POST',{});await refresh();}});}
    async function importRecipe(e){await attempt(async()=>{const file=e.target.files[0];if(file)editRecipe(await api('/api/recipes/import','POST',JSON.parse(await file.text())));await refresh();});e.target.value='';}
    async function saveTaskRecipe(){await attempt(async()=>{editRecipe(await api(`/api/recipes/from-task/${selectedTask.value.id}`,'POST',{}));navigate('recipes');await refresh();});}
    async function connectPreview(){await host.openPreview?.(previewDevice.value);}
    async function input(kind){await attempt(async()=>{await api(`/api/automation/devices/${encodeURIComponent(previewDevice.value)}/input`,'POST',{kind,text:text.value,package:packageName.value});});}
    async function startDemo(){await attempt(async()=>{selectedDemo.value=await api('/api/demonstrations','POST',{device_id:previewDevice.value,record_text:recordText.value,record_images:recordImages.value});await refresh();});}
    async function demoAction(action){await attempt(async()=>{selectedDemo.value=await api(`/api/demonstrations/${selectedDemo.value.id}/${action}`,'POST',{});await refresh();});}
    async function draftDemo(){await attempt(async()=>{notice.value='正在根据示教生成草稿…';const draft=await api(`/api/demonstrations/${selectedDemo.value.id}/draft`,'POST',{name:''});editRecipe(draft);navigate('recipes');notice.value='请检查操作意图、参数和验收条件，保存后试运行';});}
    async function saveTrigger(){await attempt(async()=>{await api(trigger.value.id?`/api/triggers/${trigger.value.id}`:'/api/triggers',trigger.value.id?'PUT':'POST',{...trigger.value,revision:trigger.value.revision||undefined,parameters:triggerValues.value});await refresh();});}
    function editTrigger(rule){trigger.value=JSON.parse(JSON.stringify(rule));triggerValues.value=JSON.parse(JSON.stringify(rule.parameters||{}));}
    function newTrigger(){trigger.value={name:'',kind:'online',device_id:'',recipe_id:'',source_recipe:'',enabled:true,cooldown:300};triggerValues.value={};}
    function selectTriggerRecipe(){
        const recipe=recipes.value.find(r=>r.id===trigger.value.recipe_id);
        trigger.value.revision=recipe?.revision;triggerValues.value={};
        for(const p of recipe?.parameters||[])if(p.default!==undefined)triggerValues.value[p.name]=p.default;
    }
    watch(()=>[trigger.value.recipe_id,trigger.value.revision],async([id,revision])=>{
        triggerDefinition.value=null;if(!id || !authorized())return;
        await attempt(async()=>{
            let recipe=recipes.value.find(r=>r.id===id)||await api(`/api/recipes/${id}`);
            if(revision && recipe.revision!==revision)recipe=(await api(`/api/recipes/${id}/revisions`)).revisions.find(r=>r.revision===revision);
            if(trigger.value.recipe_id===id && trigger.value.revision===revision)triggerDefinition.value=recipe;
        });
    });
    function bindLatest(){trigger.value.revision=recipes.value.find(r=>r.id===trigger.value.recipe_id)?.revision;}
    async function disableTrigger(rule){await attempt(async()=>{await api(`/api/triggers/${rule.id}?cancel_pending=true`,'DELETE');await refresh();});}
    async function history(rule){await attempt(async()=>{triggerHistory.value=(await api(`/api/triggers/${rule.id}/history`)).history;});}
    async function saveSchedule(){await attempt(async()=>{await api('/api/scheduler/tasks','POST',{name:schedule.value.name,task_content:'配方定时执行',recipe_id:schedule.value.recipe_id,recipe_parameters:JSON.parse(triggerParams.value),devices:[schedule.value.device_id],daily_time:schedule.value.daily_time,busy_policy:schedule.value.busy_policy,timezone:settings.value.timezone,schedule_type:'daily'});notice.value='已创建，可在主界面的定时任务中管理';});}
    async function saveSettings(){await attempt(async()=>{settings.value=await api('/api/automation/settings','PUT',settings.value);notice.value='设置已保存';});}
    function brief(e){if(e.kind==='screen')return e.data.final?'最终画面':'步骤画面';if(e.kind==='action')return e.data.action?.action||e.data.action?._metadata;return e.data.message||e.data.reason||e.data.status||e.data.content||e.kind;}
    function taskSource(task){const opt=task?.options||{};if(opt.trial)return '试运行';if(opt.is_scheduled||opt.task_type==='scheduled')return '定时任务';if(opt.trigger_id)return '条件触发';if(opt.task_type==='chat')return '对话任务';if(opt.recipe_id)return '配方执行';return '手动任务';}
    function time(value){return new Date(value*1000).toLocaleString();}
    function stopPlayback(){clearInterval(playTimer);playing.value=false;}
    function seekReplay(value){stopPlayback();replayPosition.value=Math.max(0,Math.min(replayFrames.value.length-1,Number(value)||0));}
    function stepReplay(delta){seekReplay(replayPosition.value+delta);}
    function togglePlayback(){
        if(playing.value){stopPlayback();return;}
        if(!replayFrames.value.length)return;
        if(replayPosition.value>=replayFrames.value.length-1)replayPosition.value=0;
        playing.value=true;
        playTimer=setInterval(()=>{
            if(replayPosition.value>=replayFrames.value.length-1){stopPlayback();return;}
            replayPosition.value++;
        },800/Number(replaySpeed.value));
    }
    watch(()=>replayFrames.value.map(frame=>frame.image_id).join(':'),()=>seekReplay(0));
    watch(replaySpeed,()=>{if(playing.value){stopPlayback();togglePlayback();}});
    async function selectReplayTask(id){
        stopPlayback();replaySource.value='task';
        const task=await ensureTask(id);if(task)await openTask(task);
    }
    async function selectReplayDemo(id){
        stopPlayback();replaySource.value='demo';
        replayDemo.value=demos.value.find(d=>d.id===id)||await api(`/api/demonstrations/${id}`);
    }
    async function ensureTask(id){
        if(!id || !authorized() || !ready.value)return;
        if(!taskIndex[id])taskIndex[id]=await api(`/api/tasks/${encodeURIComponent(id)}`);
        return taskIndex[id];
    }
    function handleEvent(event){
        if(!authorized() || event.type!=='automation_event')return;
        if(selectedTask.value?.id===event.task_id && !events.value.some(e=>e.seq===event.seq)){
            events.value.push(event);events.value.sort((a,b)=>a.seq-b.seq);
        }
        if(['submitted','state','subtask','device_finished','task_finished','verification'].includes(event.kind)){
            clearTimeout(eventTimer);eventTimer=setTimeout(()=>attempt(refresh),120);
        }
    }
    async function initialize(){
        if(initializing || !authorized() || disposed)return;
        initializing=true;
        try{
            await requireAutomationBackend();
            settings.value=await api('/api/automation/settings');
            if(!authorized() || disposed)return;
            ready.value=true;backendUnavailable.value=false;
            await refresh();
            if(!recipeDevice.value && devices.value.length)recipeDevice.value=devices.value[0].id;
            const deepLink=new URLSearchParams(location.search).get('task_id');
            if(deepLink)await host.openTask?.(deepLink);
            clearInterval(timer);timer=setInterval(()=>{if(!document.hidden)attempt(refresh);},2000);
        }finally{initializing=false;}
    }
    function stop(){clearInterval(timer);clearTimeout(eventTimer);timer=null;stopPlayback();}
    if(host.active)watch(host.active,enabled=>{
        stop();
        if(enabled){attempt(initialize);}
        else {ready.value=false;backendUnavailable.value=false;lastError='';lastErrorAt=0;tasks.value=[];recipes.value=[];demos.value=[];triggers.value=[];settings.value=null;selectedTask.value=null;events.value=[];selectedDemo.value=null;editingRecipe.value=null;parameterValues.value={};triggerValues.value={};text.value='';packageName.value='';resumeNote.value='';error.value='';notice.value='';Object.keys(taskIndex).forEach(key=>delete taskIndex[key]);}
    },{immediate:true});
    else onMounted(()=>attempt(initialize));
    watch(notice,message=>{if(message)host.notify?.(message,'success');});
    onUnmounted(()=>{disposed=true;stop();});
    return {tab,error,notice,ready,backendUnavailable,reconnect:()=>attempt(ready.value?refresh:initialize),devices,tasks,recipes,demos,triggers,settings,selectedDevices,content,acceptance,plannedSteps,parallel,queueTimeout,selectedTask,events,filter,selectedEvent,resumeNote,previewDevice,canvas,text,packageName,recordText,recordImages,selectedDemo,triggerHistory,editingRecipe,parameterValues,recipeDevice,triggerParams,schedule,trigger,triggerValues,triggerDefinition,selectTriggerRecipe,labels,filteredEvents,recording,replayImage,overlay,terminal,replaySource,replayDemo,replayPosition,replaySpeed,playing,replayFrames,currentFrame,frameMarker,replayTasks,stopPlayback,seekReplay,stepReplay,togglePlayback,selectReplayTask,selectReplayDemo,taskIndex,ensureTask,handleEvent,attempt,refresh:()=>attempt(refresh),openTask,run,decompose,control,pinReplay,rerun,recipeFromPlan,newRecipe,editRecipe,moveStep,saveRecipe,runRecipe,recipeAction,importRecipe,saveTaskRecipe,connectPreview,input,startDemo,demoAction,draftDemo,saveTrigger,editTrigger,newTrigger,bindLatest,disableTrigger,history,saveSchedule,saveSettings,brief,taskSource,time};
}
