import {api} from './api.js?v=20261024-context-preview';
export const saveRecipeRevision = recipe => api(recipe.id?`/api/recipes/${recipe.id}`:'/api/recipes',recipe.id?'PUT':'POST',recipe);
export const trialRecipe = (id,device,parameters) => api(`/api/recipes/${id}/run`,'POST',{device_ids:[device],parameters,trial:true});
export const portableRecipe = id => api(`/api/recipes/${id}/export`);
