"use strict";
const Ajv=require("ajv");
const schema=require("../contracts/map-actions.schema.json");
const {validateActions,applyActions}=require("../public/js/map-actions");
const entities=[{hospital_id:1},{hospital_id:2}];
test.each(["fit_bounds","highlight","filter","rank","compare"])("validates shared %s action",type=>{
  const actions=[{type,hospital_ids:[1,2]}];expect(new Ajv().compile(schema)(actions)).toBe(true);expect(validateActions(actions,entities)).toEqual(actions);
});
test.each(["open_popup","fly_to"])("validates shared %s action",type=>{expect(validateActions([{type,hospital_id:1}],entities)).toHaveLength(1);});
test.each([[{type:"eval",hospital_id:1}],[{type:"highlight",hospital_ids:[999]}],[{type:"rank",hospital_ids:[1,1]}],[{type:"fly_to",hospital_id:1,url:"evil"}],[{type:"compare",hospital_ids:[1]}]])("rejects invalid action %j",actions=>{expect(()=>validateActions(actions,entities)).toThrow();});
test("validates the complete action batch before any map mutation",async()=>{
  const adapter={prepare:jest.fn(),highlight:jest.fn()};await expect(applyActions([{type:"highlight",hospital_ids:[1]},{type:"fly_to",hospital_id:999}],entities,adapter)).rejects.toThrow();expect(adapter.prepare).not.toHaveBeenCalled();
});
test("dispatches in the agent's action order",async()=>{
  const calls=[],adapter={prepare:()=>calls.push("prepare"),filter:()=>calls.push("filter"),fit_bounds:()=>calls.push("fit")};await applyActions([{type:"filter",hospital_ids:[1]},{type:"fit_bounds",hospital_ids:[1]}],entities,adapter);expect(calls).toEqual(["prepare","filter","fit"]);
});
