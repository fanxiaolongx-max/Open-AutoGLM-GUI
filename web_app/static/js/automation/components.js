import {api} from './api.js?v=20261024-context-preview';
const fetchPin=(id,pinned)=>api(`/api/automation/images/${id}/pin`,'POST',{pinned});
// Components share the main application's authentication, device selection and preview.
const {inject,toRefs,computed,ref,watch} = Vue;
function shared(){return toRefs(inject('automation'));}
export const AutomationRecipes = { emits:['schedule'], setup:shared,template:`
<section class="automation-section panel">
<div class="row">
<button class="primary" @click="newRecipe">新建配方</button>
<label class="upload">导入 JSON<input type="file" accept="application/json,.json" @change="importRecipe">
</label>
</div>
<div class="columns">
<div class="panel">
<h2>配方库</h2>
<article v-for="r in recipes" class="execution">
<button class="link" @click="editRecipe(r)">{{r.name}}</button>
<p>修订 {{r.revision}} · {{r.archived?'已归档':r.verified?'已试运行验证':'待试运行'}}</p>
<p v-if="r.last_run">最近：{{labels[r.last_run.status]}} · {{r.last_run.device_ids.join(', ')}}</p>
<div class="row">
<button @click="$emit('schedule',r)">设为定时任务</button>
<button @click="recipeAction(r,'copy')">复制</button>
<button @click="recipeAction(r,'export')">导出</button>
<button @click="recipeAction(r,'archive')" :disabled="r.archived">归档</button>
</div>
</article>
<p v-if="!recipes.length">暂无配方，可从已完成任务或示教创建。</p>
</div>
<div class="panel" v-if="editingRecipe">
<h2>编辑配方</h2>
<label>名称<input v-model="editingRecipe.name">
</label>
<label>说明<textarea v-model="editingRecipe.description">
</textarea>
</label>
<label>目标应用（说明）<input v-model="editingRecipe.target_app">
</label>
<h3>参数</h3>
<div class="parameter" v-for="(p,i) in editingRecipe.parameters">
<input v-model="p.name" placeholder="参数名">
<select v-model="p.type">
<option v-for="type in ['text','number','date','time','enum']">{{type}}</option>
</select>
<input v-if="p.type==='enum'" :value="(p.options||[]).join(',')" @input="p.options=$event.target.value.split(',')" placeholder="枚举选项，逗号分隔">
<button @click="editingRecipe.parameters.splice(i,1)">移除</button>
</div>
<button @click="editingRecipe.parameters.push({name:'',type:'text'})">添加参数</button>
<h3>顺序步骤</h3>
<p class="muted">在指令中使用 {参数名}。写操作意图，执行时根据当前页面定位。</p>
<article v-for="(s,i) in editingRecipe.steps" class="execution">
<label>步骤 {{i+1}}<textarea v-model="s.content">
</textarea>
</label>
<div class="row">
<label>超时秒<input type="number" v-model.number="s.timeout" min="1" max="3600">
</label>
<label class="inline">
<input type="checkbox" v-model="s.repeatable">可重复执行</label>
<label class="inline">
<input type="checkbox" v-model="s.retry_once" :disabled="!s.repeatable">失败重试一次</label>
</div>
<label>本步验收（可选）<input v-model="s.acceptance">
</label>
<div class="row">
<button @click="moveStep(i,-1)">上移</button>
<button @click="moveStep(i,1)">下移</button>
<button @click="editingRecipe.steps.splice(i,1)">移除</button>
</div>
</article>
<button @click="editingRecipe.steps.push({content:'',timeout:180})">添加步骤</button>
<label>最终验收条件<input v-model="editingRecipe.acceptance">
</label>
<button class="primary" @click="saveRecipe">保存新修订</button>
<h3>试运行已保存的修订</h3>
<p class="muted">修改后请先保存。试运行成功会记录设备及修订号；应用升级后仍需重新检查。</p>
<label>设备<select v-model="recipeDevice">
<option v-for="d in devices" :value="d.id">{{d.name||d.id}}</option>
</select>
</label>
<label v-for="p in editingRecipe.parameters">{{p.name}}<select v-if="p.type==='enum'" v-model="parameterValues[p.name]">
<option v-for="o in p.options" :value="o">{{o}}</option>
</select>
<input v-else v-model="parameterValues[p.name]" :type="p.type==='number'?'number':p.type==='date'?'date':p.type==='time'?'time':'text'">
</label>
<button @click="runRecipe" :disabled="!editingRecipe.id||!recipeDevice">加入试运行队列</button>
</div>
</div>
</section>
`};
export const AutomationTriggers = {  setup:shared,template:`
<section class="automation-section panel">
<div class="columns">
<div class="panel">
<h2>{{trigger.id?'编辑条件规则':'新建条件规则'}}</h2>
<button @click="newTrigger">新建规则</button>
<label>名称<input v-model="trigger.name">
</label>
<label>触发条件<select v-model="trigger.kind">
<option value="online">设备由离线变为在线</option>
<option value="charging">设备开始充电</option>
<option value="recipe_completed">前置配方成功完成</option>
</select>
</label>
<label v-if="trigger.kind==='recipe_completed'">前置配方<select v-model="trigger.source_recipe">
<option v-for="r in recipes" :value="r.id">{{r.name}}</option>
</select>
</label>
<label>目标设备<select v-model="trigger.device_id">
<option v-for="d in devices" :value="d.id">{{d.name||d.id}}</option>
</select>
</label>
<label>执行配方<select v-model="trigger.recipe_id" @change="selectTriggerRecipe">
<option v-for="r in recipes.filter(r=>!r.archived)" :value="r.id">{{r.name}} · 修订 {{r.revision}}</option>
</select>
</label>
<label>固定修订号（空白使用当前修订）<input type="number" min="1" v-model.number="trigger.revision">
</label>
<button @click="bindLatest">显式绑定当前修订</button>
<label class="inline">
<input type="checkbox" v-model="trigger.enabled">启用规则</label>
<label v-for="parameter in triggerDefinition?.parameters||[]">{{parameter.name}}<select v-if="parameter.type==='enum'" v-model="triggerValues[parameter.name]">
<option v-for="option in parameter.options" :value="option">{{option}}</option>
</select>
<input v-else v-model="triggerValues[parameter.name]" :type="['number','date','time'].includes(parameter.type)?parameter.type:'text'">
</label>
<label>冷却秒数<input type="number" min="0" v-model.number="trigger.cooldown">
</label>
<button @click="saveTrigger">保存规则</button>
<p class="muted">服务启动时的初始状态不会触发；设备状态最多约 30 秒刷新一次。按时间执行的配方请使用上方原有定时任务表单。</p>
</div>
<div class="panel">
<h2>触发规则</h2>
<article v-for="r in triggers" class="execution">
<strong>{{r.name||r.kind}}</strong>
<p>{{r.enabled?'已启用':'已停用'}} · 固定修订 {{r.revision}} · 连续失败 {{r.failures}} 次</p>
<p>{{r.diagnostic}}</p>
<button @click="editTrigger(r)">编辑／重新启用</button>
<button @click="history(r)">查看历史</button>
<button @click="disableTrigger(r)" :disabled="!r.enabled">停用并取消待执行任务</button>
</article>
<h3>触发历史</h3>
<p v-for="h in triggerHistory">{{time(h.created)}} · {{h.state}} {{h.message}}</p>
</div>
</div>
</section>
`};
export const AutomationSettings = {  setup:shared,template:`
<section class="automation-section panel">
<template v-if="settings">
<h2>运行设置</h2>
<label>最多同时执行的设备数<input type="number" v-model.number="settings.concurrency" min="1" max="16">
</label>
<label>计划任务时区<input v-model="settings.timezone" placeholder="例如 Asia/Shanghai">
</label>
<label class="inline" v-for="[field,name] in [['enabled','允许提交自动任务'],['recipes_enabled','配方'],['demonstrations_enabled','示教'],['triggers_enabled','条件触发']]">
<input type="checkbox" v-model="settings[field]">{{name}}</label>
<p class="muted">关闭功能入口不终止已有任务；需要停止时请使用任务操作。截图默认保留 30 天，未固定截图上限 2GB。</p>
<button class="primary" @click="saveSettings">保存设置</button>
</template>
</section>
`};
export const AutomationDemos = {  emits:['replay'],setup:shared,template:`
<section class="automation-section panel">
<h2>操作示教记录</h2>
<p class="muted">在设备预览中开始示教。录制结束后，在这里检查动作并生成可编辑的配方。</p>
<div v-for="d in demos" class="row">
<button @click="selectedDemo=d">{{d.device_id}} · {{labels[d.status]||d.status}} · {{d.actions.length}} 个动作</button>
<button @click="$emit('replay',d.id)">手机回放</button>
</div>
<article v-if="selectedDemo">
<h3>{{selectedDemo.device_id}}</h3>
<div class="row">
<button @click="demoAction('pause')" :disabled="selectedDemo.status!=='recording'">暂停录制</button>
<button @click="demoAction('resume')" :disabled="selectedDemo.status!=='paused'">继续录制</button>
<button @click="demoAction('finish')" :disabled="!['recording','paused','interrupted'].includes(selectedDemo.status)">结束录制</button>
</div>
<p>暂停录制时的操作不会保存。关闭输入记录时也不保存关键截图。</p>
<details v-for="a in selectedDemo.actions">
<summary>{{a.kind}} · {{time(a.created)}}</summary>
<pre>{{JSON.stringify(a.data,null,2)}}</pre>
<img class="thumbnail" v-if="a.image_id" :src="'/api/automation/images/'+a.image_id" alt="示教关键画面">
</details>
<p class="muted">生成草稿会把动作和最多 12 张关键画面发送给当前配置的模型。生成后需人工检查并试运行。</p>
<button class="primary" @click="draftDemo" :disabled="selectedDemo.status!=='finished'||!selectedDemo.actions.length">生成配方草稿</button>
</article>
</section>
`};
export const AutomationTaskHistory = { emits:['open'], setup:shared,template:`
<section class="automation-section panel">
<h2>任务队列与历史</h2>
<p class="muted">同一设备按队列执行。点击任务可查看控制与执行状态。</p>
<button class="task" v-for="task in tasks" :key="task.id" @click="$emit('open',task.id)">
<strong>{{task.task_content}}</strong>
<span :class="task.status">{{labels[task.status]||task.status}} · {{task.progress}}%</span>
<small>{{taskSource(task)}} · {{time(task.start_time)}} · {{task.device_ids.join('、')}}</small>
</button>
<p v-if="!tasks.length" class="muted">暂无任务记录</p>
</section>
`};
export const AutomationTaskDetail = { emits:['preview','replay'], setup:shared,template:`
<section class="automation-section panel">
<template v-if="selectedTask">
<h2>{{selectedTask.task_content}}</h2>
<p>{{taskSource(selectedTask)}} · {{labels[selectedTask.status]||selectedTask.status}} · {{selectedTask.id}}</p>
<div class="row">
<button @click="$emit('preview',selectedTask.device_ids[0])">接管设备</button>
<button @click="control(selectedTask,'pause')" :disabled="!selectedTask.executions.some(c=>c.status==='running')">暂停</button>
<button @click="control(selectedTask,'resume')" :disabled="!selectedTask.executions.some(c=>['paused','waiting_for_user','interrupted'].includes(c.status))">继续／确认恢复</button>
<button @click="control(selectedTask,'stop')" :disabled="terminal(selectedTask.status)">停止此任务</button>
<button v-if="selectedTask.status==='completed'" @click="saveTaskRecipe">保存为配方</button>
<button v-if="terminal(selectedTask.status)" @click="$emit('replay',selectedTask.id)">在预览窗回放</button>
</div>
<label>人工处理说明<input v-model="resumeNote" placeholder="例如：已登录，请继续">
</label>
<p class="muted">需要接管时，打开当前设备预览进行操作；暂停状态下不会录制，除非你另外开始示教。</p>
<div class="execution" v-for="c in selectedTask.executions">
<strong>{{c.device_id}} · {{labels[c.status]||c.status}}</strong>
<p>{{c.message}}</p>
<p>子任务 {{Math.min(c.step_index+1,(c.steps||selectedTask.steps).length)}} / {{(c.steps||selectedTask.steps).length}} · {{c.tokens}} tokens · {{labels[c.verification.status]||c.verification.status}}</p>
<p v-if="c.verification.explanation">{{c.verification.explanation}}</p>
</div>
<details>
<summary>子任务与重新规划</summary>
<div v-for="(s,i) in selectedTask.steps" class="step">
<span>{{i+1}}. {{s.content}}</span>
<button @click="rerun(i)">从这里重新规划</button>
</div>
<p class="muted">将创建新任务。涉及提交、发送的步骤请先检查设备当前状态。</p>
</details>
  <details>
<summary>执行日志</summary>
<div v-for="event in events.filter(e=>e.kind!=='screen')">
<small>#{{event.seq}} · {{event.device_id}}</small>
<p>{{brief(event)}}</p>
</div>
</details>
  </template>
</section>
`};
export const AutomationRecorder = {  emits:['replay-demo'],setup:function(){const a=inject('automation');return {...toRefs(a),recordingAction(action){a.selectedDemo=a.recording;a.demoAction(action);}};},template:`
<section class="automation-section auto-recorder-section">
<div v-if="previewDevice" class="auto-recorder" @mousedown.stop @pointerdown.stop @keydown.stop>
    <p class="muted">仅记录当前 Web 预览操作。关键截图用于回放，也会保留屏幕上可见的输入内容。</p>
    <div class="row">
<label class="inline">
<input type="checkbox" v-model="recordText" :disabled="!!recording">保存输入文本</label>
<label class="inline"><input type="checkbox" v-model="recordImages" :disabled="!!recording">保存关键截图（用于回放）</label>
    <button v-if="!recording" @click="startDemo">开始示教</button>
    <template v-else>
<span>{{labels[recording.status]||recording.status}} · {{recording.actions.length}} 个动作</span>
    <button v-if="recording.status==='recording'" @click="recordingAction('pause')">暂停录制</button>
    <button v-else @click="recordingAction('resume')">继续录制</button>
    <button @click="recordingAction('finish')">结束示教</button>
</template>
</div>
    <div v-if="selectedDemo?.device_id===previewDevice && selectedDemo.status==='finished'" class="row">
<button @click="$emit('replay-demo',selectedDemo.id)">回放录制</button>
<button @click="draftDemo" :disabled="!selectedDemo.actions.length">生成配方</button>
</div>
<p class="muted">生成配方时才向当前模型发送动作及已保存画面，生成后可编辑。</p>
<details>
<summary>输入与应用启动</summary>
<div class="row">
<input v-model="text" placeholder="向手机输入文本">
<button @click="input('text')">输入</button>
</div>
<div class="row">
<input v-model="packageName" placeholder="应用包名">
<button @click="input('launch')">启动应用</button>
</div>
</details>
</div>
</section>
`};
export const AutomationTaskControls = { props:{taskId:String},emits:['open','preview','replay'], setup:function(props){const a=inject('automation');watch(()=>[props.taskId,a.ready],([id,ready])=>{if(ready)a.attempt(()=>a.ensureTask(id));},{immediate:true});return {...toRefs(a),note:ref(''),task:computed(()=>a.taskIndex[props.taskId])};},template:`
<section class="automation-section panel">
<div v-if="task" class="auto-control-bar" @click.stop>
    <span class="auto-state" :class="task.status">{{labels[task.status]||task.status}}</span>
    <span v-for="c in task.executions" class="muted">{{c.device_id}} · {{labels[c.verification.status]||c.verification.status}}</span>
    <div class="row">
        <button v-if="task.executions.some(c=>c.status==='running')" @click="control(task,'pause',note)">暂停</button>
        <button v-if="task.executions.some(c=>['paused','waiting_for_user','interrupted'].includes(c.status))" @click="control(task,'resume',note)">继续执行</button>
        <button v-if="!terminal(task.status)" @click="control(task,'stop',note)">停止此任务</button>
        <button @click="$emit('preview',task.device_ids[0])">接管设备</button>
        <button @click="$emit('open',task.id)">查看详情</button>
    </div>
    <label v-if="['paused','waiting_for_user','interrupted'].includes(task.status)">人工处理说明<input v-model="note" placeholder="例如：已登录，请继续">
</label>
    <p v-if="['pausing','paused','waiting_for_user','interrupted'].includes(task.status)" class="muted">{{task.executions.map(c=>c.message).filter(Boolean).join('；') || '请等待暂停确认，再在现有设备预览中操作。'}}</p>
</div>
</section>
`};
export const AutomationReplayControls = {setup:function(){const a=inject('automation');return {...toRefs(a),async pinCurrentFrame(pinned){if(a.currentFrame)await a.attempt(()=>fetchPin(a.currentFrame.image_id,pinned));},learnDemo(){a.selectedDemo=a.replayDemo;a.draftDemo();}};},template:`
<section class="automation-section auto-replay-section" @mousedown.stop @pointerdown.stop @keydown.stop data-no-preview-drag="1">
<p>
<strong>历史回放</strong> · 仅查看记录，不操作手机</p>
<label>记录来源<select v-model="replaySource" @change="stopPlayback">
<option value="task">自动任务</option>
<option value="demo">手动示教</option>
</select>
</label>
<label v-if="replaySource==='task'">任务<select :value="selectedTask?.id||''" @change="attempt(()=>selectReplayTask($event.target.value))">
<option value="" disabled>选择任务</option>
<option v-for="task in replayTasks" :value="task.id">{{task.task_content}}</option>
</select>
</label>
<label v-else>示教记录<select :value="replayDemo?.id||''" @change="attempt(()=>selectReplayDemo($event.target.value))">
<option value="" disabled>选择录制</option>
<option v-for="demo in demos.filter(d=>d.device_id===previewDevice)" :value="demo.id">{{time(demo.created)}} · {{demo.actions.length}} 个动作</option>
</select>
</label>
<div class="row">
<button @click="stepReplay(-1)" :disabled="!replayFrames.length||replayPosition===0">上一步</button>
<button @click="togglePlayback" :disabled="!replayFrames.length">{{playing?'暂停回放':'播放'}}</button>
<button @click="stepReplay(1)" :disabled="!replayFrames.length||replayPosition>=replayFrames.length-1">下一步</button>
</div>
<input class="replay-seek" type="range" min="0" :max="Math.max(0,replayFrames.length-1)" :value="replayPosition" @input="seekReplay($event.target.value)" :disabled="!replayFrames.length" aria-label="回放进度">
<div class="row">
<span>{{replayFrames.length?replayPosition+1:0}} / {{replayFrames.length}}</span>
<select v-model.number="replaySpeed" aria-label="回放速度">
<option :value="0.5">0.5×</option>
<option :value="1">1×</option>
<option :value="2">2×</option>
</select>
</div>
<p>{{currentFrame?.label||'暂无可回放画面'}}</p>
<p v-if="!replayFrames.length" class="muted">这份记录没有可回放截图。旧记录未保存的画面无法还原；请开启“保存关键截图”重新录制。</p>
<details v-if="replaySource==='demo' && replayDemo">
<summary>录制动作</summary>
<p v-if="replayDemo.capture_error" class="muted">{{replayDemo.capture_error}}</p>
<p v-for="(action,index) in replayDemo.actions">{{index+1}}. {{action.kind}}</p>
</details>
<div v-if="currentFrame" class="row">
<button @click="pinCurrentFrame(true)">保留截图</button>
<button @click="pinCurrentFrame(false)">取消保留</button>
</div>
<button v-if="replaySource==='task' && selectedTask?.status==='completed'" @click="saveTaskRecipe">保存为配方</button>
<button v-if="replaySource==='demo' && replayDemo?.status==='finished' && replayDemo.actions.length" @click="learnDemo">生成可编辑配方</button>
</section>
`};
