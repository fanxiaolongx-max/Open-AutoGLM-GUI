import {api} from './api.js?v=20261024-context-preview';
export const isTerminal = status => ['completed','failed','stopped','expired','cancelled'].includes(status);
export const submitTask = request => api('/api/tasks/run','POST',request);
export const taskSnapshot = id => api(`/api/tasks/${id}`);
export const taskEvents = (id,after=0) => api(`/api/tasks/${id}/events?after=${after}&limit=500`);
export const taskControl = (id,action,note='') => api(`/api/tasks/${id}/${action}`,'POST',action==='resume'?{note}:{});
