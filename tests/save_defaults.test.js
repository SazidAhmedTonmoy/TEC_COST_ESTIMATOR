const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/app.js','utf8'),ctx={state:{appSettings:{}}};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function defaultSaveMode('),source.indexOf('async function loadSettings(')),ctx);
assert.equal(ctx.defaultSaveMode(true,{id:1}),'estimate');
for(const mode of ['estimate','new','update']){ctx.state.appSettings.default_save_mode=mode;assert.equal(ctx.defaultSaveMode(true,{id:1}),mode);assert.equal(ctx.defaultSaveMode(false,{id:1}),'new');assert.equal(ctx.defaultSaveMode(true,null),'new');}
ctx.state.appSettings.default_save_mode='update';assert.equal(ctx.defaultSaveMode(true,{}),'estimate');
console.log('Save destination defaults and unavailable-option fallback passed.');
