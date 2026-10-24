export class ApiError extends Error {
    constructor(path,method,status,detail,statusText='') {
        const endpoint=String(path).split('?')[0];
        const missingRoute=status===404 && (!detail || detail==='Not Found');
        const message=status===401?'登录已失效，请重新登录':missingRoute
            ? `接口未加载（${method} ${endpoint}），请重启后端服务后刷新页面`
            : detail && typeof detail==='object' ? (detail.message||JSON.stringify(detail))
            : detail||`${method} ${endpoint} 请求失败（${status}${statusText?' '+statusText:''}）`;
        super(message);
        this.name='ApiError';this.status=status;this.path=endpoint;this.method=method;
        this.code=missingRoute?'MISSING_ENDPOINT':'HTTP_ERROR';
    }
}
export async function api(path, method = 'GET', body) {
    const response = await fetch(path, {method, credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    const data = await response.json().catch(()=>null);
    if (!response.ok) throw new ApiError(path,method,response.status,data?.detail,response.statusText);
    return data;
}
export async function requireAutomationBackend(){
    const health=await api('/health');
    if(health?.capabilities?.automation!==true){
        const error=new Error('后端尚未加载自动化功能，请重启后端服务后刷新页面');
        error.code='BACKEND_OUTDATED';throw error;
    }
}
export const terminal = status => ['completed', 'failed', 'stopped', 'expired', 'cancelled'].includes(status);
export const statusLabels = {pending:'排队中',running:'执行中',pausing:'正在暂停',paused:'已暂停',waiting_for_user:'等待接管',interrupted:'已中断',completed:'执行结束',failed:'失败',stopped:'已停止',expired:'已过期',cancelled:'已取消',passed:'已验证完成',inconclusive:'待核验',not_requested:'未验证',recording:'录制中',finished:'录制结束'};
