const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements={};
function el(){return {value:'',textContent:'',children:[],append(x){this.children.push(x)},after(){}}}
for(const id of ['#project-hours-per-day','#project-crew-size','#metric-person-days','#floating-estimate-total'])elements[id]=el();
const ctx={$:id=>elements[id],state:{projectData:{project:{name:'Project <One>',currency:'AUD'},totals:{hours:80,quoted:200}}},fmtNumber:n=>n.toFixed(2),fmtMoney:n=>String(n),document:{createElement:el,createTextNode:text=>({textContent:text})}};
vm.createContext(ctx);
const source=fs.readFileSync('assets/estimate_extras.js','utf8');
vm.runInContext(source.slice(0,source.indexOf('function refreshFloatingTotal')),ctx);ctx.refreshFloatingTotal=()=>{};
for(const [hours,crew,expected] of [[8,2,'10.00 person-days · 5.00 crew working days'],[10,4,'8.00 person-days · 2.00 crew working days'],[0,4,'— person-days · — crew working days']]){
 elements['#project-hours-per-day'].value=String(hours);elements['#project-crew-size'].value=String(crew);ctx.previewEstimateTimeSummary();assert.equal(elements['#metric-person-days'].textContent,expected);
}
assert.equal(elements['#floating-estimate-total'].children[0].textContent,'Project <One>');
assert.equal(ctx.state.projectData.totals.hours,80);
console.log('Live day calculations, invalid input, and plain-text project name passed.');
