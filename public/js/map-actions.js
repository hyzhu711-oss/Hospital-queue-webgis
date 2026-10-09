"use strict";
(function(root){
  const multi=new Set(["fit_bounds","highlight","filter","rank","compare"]);
  const single=new Set(["open_popup","fly_to"]);
  function validateActions(actions,entities){
    if(!Array.isArray(actions)||actions.length>20)throw new Error("Invalid map action list");
    const allowed=new Set(entities.map(h=>h.hospital_id));
    for(const action of actions){
      if(!action||typeof action!=="object"||Array.isArray(action))throw new Error("Invalid map action");
      const isMulti=multi.has(action.type),isSingle=single.has(action.type);
      if(!isMulti&&!isSingle)throw new Error("Unsupported map action");
      const key=isMulti?"hospital_ids":"hospital_id";
      if(Object.keys(action).length!==2||!Object.hasOwn(action,key))throw new Error("Unexpected map action arguments");
      const ids=isMulti?action[key]:[action[key]];
      const minimum=action.type==="compare"?2:1,maximum=action.type==="compare"?20:200;
      if(!Array.isArray(ids)||ids.length<minimum||ids.length>maximum||new Set(ids).size!==ids.length)throw new Error("Invalid hospital set");
      if(ids.some(id=>!Number.isInteger(id)||id<=0||id>2147483647||!allowed.has(id)))throw new Error("Unverified hospital ID in map action");
    }
    return actions;
  }
  async function applyActions(actions,entities,adapter){
    validateActions(actions,entities);
    adapter.prepare(entities);
    for(const action of actions)await adapter[action.type](action.hospital_ids||action.hospital_id);
  }
  const api={validateActions,applyActions};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  else root.QueueLensMapActions=api;
})(typeof window!=="undefined"?window:globalThis);
