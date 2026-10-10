'use strict';
const $ = id => document.getElementById(id);
const TOKEN = document.querySelector('meta[name="ac8-token"]').content;
let language = localStorage.getItem('ac8-lang') === 'en' ? 'en' : 'zh';
let currentGame = '', currentAuthor = null, currentInspection = null;
let desktopMode = false, exportBusy = false;
let playerBusy = false, authorBusy = false, libraryBusy = false, libraryLoading = false;
let bindingBusy = false, bindingProfile = null, bindingOptions = [], bindingSequence = 0, bindingNotice = null;
let libraryData = {installed: [], removed: [], game_running: false};
let libraryView = 'installed', libraryRequest = 0;
const statuses = {}, planeNames = {};
const L = {
 zh: {
  playerTab:'玩家导入',libraryTab:'涂装管理',authorTab:'作者制作',gamePath:'游戏目录',chooseGame:'选择游戏目录',
  playerTitle:'导入涂装',playerDrop:'将涂装包拖到这里',choosePack:'选择涂装包',authorTitle:'制作涂装包',authorDrop:'拖入已经做好的涂装',chooseSkin:'选择现成涂装',
  skinInfo:'涂装信息',skinName:'涂装名称',authorName:'作者名称',buttonText:'按钮文字',buttonColors:'按钮颜色',backgroundColor:'按钮颜色',textColor:'文字颜色',
  bindings:'贴图绑定',texture:'贴图资源',slots:'材质槽',parameter:'参数',more:'高级设置',providerId:'作者编号',skinId:'涂装编号',build:'生成涂装包',
  libraryTitle:'涂装库',refresh:'刷新',allAircraft:'全部机型',installedView:'已安装',removedView:'已移除',selected:'已选择',manual:'手动安装',incomplete:'文件不完整',
  remove:'删除',restore:'恢复',openFolder:'打开目录',emptyInstalled:'还没有安装涂装',emptyRemoved:'没有已移除的涂装',emptyFilter:'该机型下没有涂装',
  failed:'操作未完成',saved:'游戏目录已保存',desktopOnly:'请在桌面程序中选择游戏目录。',
  receiving:'正在接收文件',processing:'正在处理涂装',installed:'涂装已安装',installedHelp:'下次离线启动游戏后，在对应机型的 LIVERY 中选择。',
  recognized:'涂装已识别',fillBelow:'请核对下方信息后生成涂装包。',existingBind:'已找到原有绑定，请核对材质槽。',su57Bind:'已建议 Su-57 BaseColor 材质槽，请核对。',manualBind:'请填写该机型实际使用的材质槽和参数。',
  omit:n=>'有 '+n+' 张贴图未绑定，将不加入成品。我确认它们不需要使用。',needInfo:'请填写涂装名称和作者。',needButton:'按钮文字需要 1–3 个字母或汉字。',confirmOmit:'请确认未绑定贴图不需要使用，或补全绑定。',badSlots:'材质槽请使用整数，多个槽用逗号分隔。',
  building:'正在生成涂装包',built:'涂装包已生成',verified:'已核对转换前后的贴图数据。',download:'下载涂装包',connectedFail:'无法连接本地工具',timeout:'操作等待超时，请刷新查看结果。',
  guide:'使用说明',guideTitle:'使用说明',close:'关闭',guide1:'玩家：退出游戏，将 .ac8skin.zip 拖入“玩家导入”，无需解压。',guide2:'作者：拖入一个 ZIP，或同名 UTOC / UCAS / PAK 文件。',guide3:'核对机型、材质槽和按钮信息后生成涂装包。',guide4:'离线启动游戏，在对应机型的 LIVERY 中选择涂装。STD 交还原版换肤控制。',guide5:'涂装管理：按机型筛选。点击“删除”会把本工具安装的涂装移入恢复区；如需撤销，切到“已移除”页点击“恢复”。恢复后需要在游戏里重新选择。手动安装的涂装可打开目录核对。',guideOffline:'仅用于离线单机。安装、删除或恢复前，请完全退出游戏。',
  chooseDirectory:'请先选择游戏目录',unknownAuthor:'未知作者',unknownAircraft:'未知机型',inProgress:'另一个操作正在进行，请稍后再试。'
 },
 en: {
  playerTab:'Import',libraryTab:'Library',authorTab:'Create',gamePath:'Game folder',chooseGame:'Choose game folder',
  playerTitle:'Import a livery',playerDrop:'Drop your livery package here',choosePack:'Choose package',authorTitle:'Create a livery package',authorDrop:'Drop your finished livery here',chooseSkin:'Choose source livery',
  skinInfo:'Livery details',skinName:'Livery name',authorName:'Author',buttonText:'Button label',buttonColors:'Button colors',backgroundColor:'Button color',textColor:'Text color',
  bindings:'Texture bindings',texture:'Texture asset',slots:'Slots',parameter:'Parameter',more:'Advanced settings',providerId:'Author ID',skinId:'Livery ID',build:'Build package',
  libraryTitle:'Livery library',refresh:'Refresh',allAircraft:'All aircraft',installedView:'Installed',removedView:'Removed',selected:'Selected',manual:'Manual install',incomplete:'Incomplete files',
  remove:'Remove',restore:'Restore',openFolder:'Open folder',emptyInstalled:'No liveries installed yet',emptyRemoved:'No removed liveries',emptyFilter:'No liveries for this aircraft',
  failed:'Operation incomplete',saved:'Game folder saved.',desktopOnly:'Select the game folder in the desktop app.',
  receiving:'Receiving files',processing:'Processing livery',installed:'Livery installed',installedHelp:'Restart AC8 offline, select the matching aircraft and choose this livery under LIVERY.',
  recognized:'Livery detected',fillBelow:'Check the details below, then build the package.',existingBind:'Existing bindings found. Check the material slots.',su57Bind:'Su-57 BaseColor slots were suggested. Check them.',manualBind:'Enter the actual material slots and parameters for this aircraft.',
  omit:n=>n+' unbound texture(s) will be omitted. I confirm they are not needed.',needInfo:'Enter the livery name and author.',needButton:'Use 1–3 English letters or Han characters for the button label.',confirmOmit:'Confirm that unbound textures are not needed, or complete their bindings.',badSlots:'Use integers for slots, separated by commas.',
  building:'Building livery package',built:'Livery package created',verified:'Texture data was verified before and after conversion.',download:'Download package',connectedFail:'Could not connect to the local tool',timeout:'The operation timed out. Refresh to check its result.',
  guide:'Guide',guideTitle:'Quick guide',close:'Close',guide1:'Players: exit AC8, then drop the .ac8skin.zip into Import. Do not extract it.',guide2:'Authors: drop one ZIP or matching UTOC / UCAS / PAK files.',guide3:'Check the aircraft, material slots and button details, then build the package.',guide4:'Start AC8 offline and select the livery under LIVERY for its aircraft. STD returns control to the native skin system.',guide5:'Library: filter by aircraft. Remove moves liveries installed by this tool into recovery storage. To undo, open Removed and click Restore. Select the restored livery again in-game. Open the folder to inspect manually installed liveries.',guideOffline:'Offline single-player only. Fully exit AC8 before installing, removing or restoring liveries.',
  chooseDirectory:'Choose your game folder first',unknownAuthor:'Unknown author',unknownAircraft:'Unknown aircraft',inProgress:'Another operation is in progress. Try again shortly.'
 }
};
Object.assign(L.zh,{saving:'正在保存涂装包',exportSaved:'涂装包已保存',saveCancelled:'已取消保存，可再次点击下载',desktopNotReady:'桌面窗口尚未准备完成，请稍后重试。'});
Object.assign(L.en,{saving:'Saving package',exportSaved:'Package saved',saveCancelled:'Save cancelled. You can download again.',desktopNotReady:'The desktop window is not ready. Please try again shortly.'});
Object.assign(L.zh,{captureBindings:'读取当前机体',refreshBindings:'读取保存记录',importBindings:'导入记录',exportBindings:'导出记录',materialList:'材质与原贴图',selectOriginal:'选择对应的原贴图',noBindingProfile:'此机型还没有材质记录。',profileLoaded:'已载入材质记录',captureWorking:'正在读取游戏中的原生材质…',profileFailed:'材质读取未完成',noParameters:'没有可枚举的贴图参数',profileFileTooLarge:'绑定记录不得超过 256 KB。',profileSlots:'槽位',profileMaterial:'材质',profileTexture:'原贴图',profileParameter:'参数',guideBindings:'材质读取：安装新版游戏 MOD 后离线启动，进入对应机型选机页并使用原生涂装（已启用 MOD 时先选 STD）；在作者页点击“读取当前机体”。也可在游戏按 F7 保存后点击“读取保存记录”。选择原贴图自动填写绑定，退出游戏后再打包。记录可导入或导出；更换游戏版本、机型或原生涂装后应重新采集。'});
Object.assign(L.en,{captureBindings:'Capture aircraft',refreshBindings:'Load saved record',importBindings:'Import record',exportBindings:'Export record',materialList:'Materials & original textures',selectOriginal:'Choose the matching original texture',noBindingProfile:'No material record for this aircraft yet.',profileLoaded:'Material record loaded',captureWorking:'Reading native materials from the game…',profileFailed:'Material capture incomplete',noParameters:'No enumerable texture parameters',profileFileTooLarge:'Binding records must not exceed 256 KB.',profileSlots:'Slots',profileMaterial:'Material',profileTexture:'Original texture',profileParameter:'Parameter',guideBindings:'Install the updated in-game MOD, restart AC8 offline, select the matching aircraft with native materials (choose STD if a MOD is active), then click Capture aircraft in Create. Alternatively, press F7 in-game and Load saved record. Choose an original texture to fill the binding. Exit AC8 before building. Records can be imported and exported. Recapture after changing the game build, aircraft or native variant.'});
const tr = (key,...args) => typeof L[language][key] === 'function' ? L[language][key](...args) : (L[language][key] || key);
const both = key => ({zh:L.zh[key],en:L.en[key]});
const localized = value => value && typeof value === 'object' ? (value[language] || value.en || '') : String(value || '');
class UiError extends Error {
 constructor(value){super(localized(value));this.translations=value;}
}
function remoteError(data){return new UiError(data.error_i18n || data.error || both('failed'));}
function errorDetail(error){return error.translations || error.message || String(error);}
function planeName(id){return planeNames[id] || id?.replace(/^PP\d{4}_/,'').toUpperCase() || tr('unknownAircraft');}
function bytes(size){return size>=1048576?(size/1048576).toFixed(1)+' MB':size>=1024?(size/1024).toFixed(1)+' KB':size+' B';}
function busy(){return playerBusy||authorBusy||libraryBusy||exportBusy||bindingBusy;}
function updateBusy(){
 $('player-browse').disabled=busy();$('author-browse').disabled=busy();$('build').disabled=busy();$('choose-game').disabled=busy();
 $('library-refresh').disabled=busy()||libraryLoading;
 for(const id of ['binding-capture','binding-refresh','binding-import'])$(id).disabled=busy()||!currentInspection;
}
async function api(path,body){
 let response;
 try{response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'X-AC8-Token':TOKEN,'X-AC8-Language':language,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});}
 catch(error){throw new UiError(both('connectedFail'));}
 const data=await response.json();if(!response.ok)throw remoteError(data);return data;
}
function status(kind,title,detail='',working=false,error=false,action=null){statuses[kind]={title,detail,working,error,action};renderStatus(kind);}
function renderStatus(kind){
 const box=$(kind+'-status'),state=statuses[kind];if(!state){box.className='status';box.replaceChildren();return;}
 box.className='status visible'+(state.error?' error':'');box.replaceChildren();
 const top=document.createElement('div');top.className='top';
 if(state.working){const spin=document.createElement('span');spin.className='spinner';top.append(spin);}
 const title=document.createElement('strong');title.textContent=typeof state.title==='string'?tr(state.title):localized(state.title);top.append(title);box.append(top);
 if(state.detail){const p=document.createElement('p');p.textContent=localized(state.detail);box.append(p);}
 if(state.action){
  if(state.action.download){const link=document.createElement('a');link.href='/download/'+state.action.id+'?token='+encodeURIComponent(TOKEN);link.download=state.action.name;link.textContent=tr('download');link.onclick=event=>{if(desktopMode){event.preventDefault();saveAuthorPackage(state.action);}else if(busy()){event.preventDefault();}};box.append(link);}
 }
}
async function saveAuthorPackage(action){
 if(busy())return;
 exportBusy=true;updateBusy();status('author','saving','',true,false,action);
 try{
  if(!window.pywebview?.api?.save_author_package)throw new UiError(both('desktopNotReady'));
  const result=await window.pywebview.api.save_author_package(action.id);
  if(result.error)throw remoteError(result);
  status('author',result.cancelled?'saveCancelled':'exportSaved',result.path||'',false,false,action);
 }catch(error){status('author','failed',errorDetail(error),false,true,action);}
 finally{exportBusy=false;updateBusy();}
}
function applyLanguage(){
 document.documentElement.lang=language==='en'?'en':'zh-CN';
 document.querySelectorAll('[data-i18n]').forEach(e=>{const key=e.dataset.i18n;if(key in L[language])e.textContent=tr(key);});
 $('zh').classList.toggle('active',language==='zh');$('en').classList.toggle('active',language==='en');
 $('aircraft-filter').setAttribute('aria-label',tr('allAircraft'));
 for(const kind of ['player','author','library'])renderStatus(kind);
 if(currentInspection){updateBindingMessage(currentInspection);updateOmitted();}
 renderBindingProfile();
 renderLibrary();
}
for(const lang of ['zh','en'])$(lang).onclick=()=>{language=lang;localStorage.setItem('ac8-lang',lang);applyLanguage();};
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b===button));
 document.querySelectorAll('.section').forEach(s=>s.classList.toggle('active',s.id===button.dataset.tab));
 if(button.dataset.tab==='library')loadLibrary();
});
async function initialize(){
 try{const state=await api('/api/state');desktopMode=state.desktop;currentGame=state.game;$('game-path').value=currentGame;await loadLibrary(false);}
 catch(error){status('player','failed',errorDetail(error),false,true);}
}
$('choose-game').onclick=async()=>{
 if(busy())return;$('choose-game').disabled=true;$('settings-result').textContent='';
 try{
  if(!window.pywebview?.api?.choose_game_folder)throw new UiError(both('desktopOnly'));
  const result=await window.pywebview.api.choose_game_folder();if(result.error)throw remoteError(result);
  if(!result.cancelled){currentGame=result.game;$('game-path').value=currentGame;$('settings-result').textContent=tr('saved');libraryData={installed:[],removed:[],game_running:false};await loadLibrary();}
 }catch(error){$('settings-result').textContent=localized(errorDetail(error));}finally{updateBusy();}
};
async function poll(id,kind){
 for(let i=0;i<2400;i++){
  const job=await api('/api/job/'+id);
  if(job.state==='done')return job.result;
  if(job.state==='error')throw remoteError(job);
  if(kind!=='library')status(kind,job.message_i18n||both('processing'),'',true);
  await new Promise(resolve=>setTimeout(resolve,350));
 }
 throw new UiError(both('timeout'));
}
async function upload(files,kind){
 const job=await api('/api/new',{kind});
 for(const file of files){
  status(kind,'receiving',file.name,true);
  const response=await fetch('/api/upload/'+job.id+'?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-AC8-Token':TOKEN,'X-AC8-Language':language},body:file});
  const data=await response.json();if(!response.ok)throw remoteError(data);
 }
 await api('/api/inspect',{id:job.id});return {id:job.id,result:await poll(job.id,kind)};
}
async function handle(files,kind){
 if(!files.length||busy())return;
 if(kind==='author'){authorBusy=true;currentAuthor=null;currentInspection=null;$('author-form').classList.add('hidden');}else playerBusy=true;updateBusy();
 try{
  const item=await upload(Array.from(files),kind);
  if(kind==='player'){
   const header=item.result.name+' · '+planeName(item.result.aircraft_id)+'\n';
   const help=item.result.message_i18n||both('installedHelp');
   status(kind,'installed',{zh:header+help.zh,en:header+help.en});
  }else{currentAuthor=item.id;currentInspection=item.result;showAuthor(item.result);status(kind,'recognized',both('fillBelow'));}
 }catch(error){status(kind,'failed',errorDetail(error),false,true);}
 finally{playerBusy=false;authorBusy=false;updateBusy();await loadLibrary(false);}
}
for(const kind of ['author','player']){
 const drop=$(kind+'-drop'),input=$(kind+'-file');
 $(kind+'-browse').onclick=()=>input.click();input.onchange=()=>{handle(input.files,kind);input.value='';};
 drop.ondragover=e=>{e.preventDefault();if(!busy())drop.classList.add('over');};drop.ondragleave=()=>drop.classList.remove('over');
 drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');handle(e.dataTransfer.files,kind);};
}
function updateSample(){
 const bg=$('button-bg').value.toUpperCase(),fg=$('button-fg').value.toUpperCase();
 $('button-sample').textContent=$('button-text').value||'SKY';$('button-sample').style.background=bg;$('button-sample').style.color=fg;
 $('button-bg-value').textContent=bg;$('button-fg-value').textContent=fg;
}
['button-text','button-bg','button-fg'].forEach(id=>$(id).oninput=updateSample);
function updateBindingMessage(info){$('binding-message').textContent=info.existing?tr('existingBind'):info.profile?tr('su57Bind'):tr('manualBind');}
function showAuthor(info){
 $('author-form').classList.remove('hidden');$('aircraft-tag').textContent=planeName(info.aircraft_id);const old=info.existing||{},source=info.source_identity||{};
 for(const [id,value] of Object.entries({'skin-name':old.name||source.id?.replace(/[_-]+/g,' ')||'','skin-author':old.author||source.provider_id||'','provider-id':old.provider_id||source.provider_id||'','skin-id':old.id||source.id||'','button-text':old.button?.text||'MOD','button-bg':old.button?.background_color||'#286B97','button-fg':old.button?.text_color||'#ffffff'}))$(id).value=value;
 updateSample();updateBindingMessage(info);$('assets').replaceChildren();
 for(const row of info.assets){
  const div=document.createElement('div');div.className='asset';div.dataset.asset=row.asset;
  const name=document.createElement('span');name.className='asset-name';name.textContent=row.asset.split('/').slice(-2).join('/');
  const slots=document.createElement('input');slots.className='slots';slots.value=row.slots.join(', ');slots.placeholder='—';slots.oninput=updateOmitted;slots.setAttribute('aria-label',tr('slots'));
  const parameter=document.createElement('input');parameter.className='parameter';parameter.value=row.parameter;parameter.setAttribute('aria-label',tr('parameter'));
  div.append(name,slots,parameter);$('assets').append(div);
 }updateOmitted();
 bindingProfile=null;bindingOptions=[];bindingNotice=null;renderBindingProfile();loadBindingRecord();
}
function updateOmitted(){
 const checked=$('omit-accept')?.checked||false,n=[...$('assets').children].filter(r=>!r.querySelector('.slots').value.trim()).length,box=$('omitted-notice');
 box.classList.toggle('hidden',!n);box.replaceChildren();if(n){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.id='omit-accept';check.checked=checked;label.append(check,document.createTextNode(tr('omit',n)));box.append(label);}
}
function bindingMessage(value,error=false){bindingNotice={value,error};renderBindingProfile();}
function renderBindingProfile(){
 const state=$('binding-state');state.classList.toggle('error',!!bindingNotice?.error);
 state.textContent=bindingNotice?localized(bindingNotice.value):currentInspection?tr(bindingProfile?'profileLoaded':'noBindingProfile'):'';
 const list=$('binding-list');list.replaceChildren();$('binding-inventory').classList.toggle('hidden',!bindingProfile);
 const link=$('binding-export');link.classList.toggle('hidden',!bindingProfile);
 if(bindingProfile){
  link.href='/download-binding/'+encodeURIComponent(bindingProfile.aircraft_id)+'?token='+encodeURIComponent(TOKEN);
  link.download=bindingProfile.aircraft_id+'.bindings.json';
  for(const row of bindingProfile.materials){
   const card=document.createElement('div');card.className='binding-material';
   const title=document.createElement('b');title.textContent=tr('profileSlots')+' '+row.slot+' · '+tr('profileMaterial');
   const material=document.createElement('code');material.textContent=row.material;card.append(title,material);
   for(const item of row.parameters){const parameter=document.createElement('strong'),texture=document.createElement('code');parameter.textContent=item.parameter;texture.textContent=item.texture;card.append(parameter,texture);}
   if(!row.parameters.length){const empty=document.createElement('code');empty.textContent=tr('noParameters');card.append(empty);}
   list.append(card);
  }
 }
 for(const row of $('assets').children){
  row.querySelector('.binding-picker')?.remove();row.querySelector('.binding-detail')?.remove();
  const slots=row.querySelector('.slots'),parameter=row.querySelector('.parameter');
  slots.setAttribute('aria-label',tr('slots'));parameter.setAttribute('aria-label',tr('parameter'));
  if(!bindingProfile)continue;
  const select=document.createElement('select');select.className='binding-picker';select.setAttribute('aria-label',tr('selectOriginal'));
  select.add(new Option(tr('selectOriginal'),''));
  bindingOptions.forEach((option,index)=>select.add(new Option(tr('profileSlots')+' '+option.slots.join(', ')+' · '+option.parameter+' · '+option.texture.split('/').pop(),String(index))));
  const detail=document.createElement('div');detail.className='binding-detail';
  const sync=()=>{
   const values=slots.value.split(',').map(s=>s.trim()).filter(Boolean).map(Number).sort((a,b)=>a-b);
   const index=bindingOptions.findIndex(option=>parameter.value.trim()===option.parameter&&JSON.stringify(values)===JSON.stringify([...option.slots].sort((a,b)=>a-b)));
   select.value=index<0?'':String(index);detail.textContent=index<0?'':bindingOptions[index].texture;
  };
  select.onchange=()=>{if(select.value===''){detail.textContent='';return;}const option=bindingOptions[Number(select.value)];slots.value=option.slots.join(', ');parameter.value=option.parameter;detail.textContent=option.texture;updateOmitted();};
  slots.oninput=()=>{updateOmitted();sync();};parameter.oninput=sync;sync();row.append(select,detail);
 }
}
function acceptBindingProfile(result){
 bindingProfile=result.profile||null;bindingOptions=result.choices||[];bindingNotice=null;
 if(bindingProfile)for(const row of $('assets').children){
  if(row.querySelector('.slots').value.trim())continue;
  const matches=bindingOptions.filter(option=>option.texture.split('.')[0]===row.dataset.asset.split('.')[0]);
  if(matches.length===1){row.querySelector('.slots').value=matches[0].slots.join(', ');row.querySelector('.parameter').value=matches[0].parameter;}
 }
 renderBindingProfile();updateOmitted();
}
async function loadBindingRecord(){
 if(!currentInspection)return;
 const sequence=++bindingSequence,plane=currentInspection.aircraft_id;
 try{const result=await api('/api/bindings/'+encodeURIComponent(plane));if(sequence===bindingSequence&&currentInspection?.aircraft_id===plane)acceptBindingProfile(result);}
 catch(error){if(sequence===bindingSequence)bindingMessage(errorDetail(error),true);}
}
$('binding-refresh').onclick=async()=>{if(busy())return;bindingBusy=true;updateBusy();try{await loadBindingRecord();}finally{bindingBusy=false;updateBusy();}};
$('binding-capture').onclick=async()=>{
 if(busy()||!currentInspection)return;
 ++bindingSequence;bindingBusy=true;updateBusy();bindingMessage(both('captureWorking'));
 try{const job=await api('/api/bindings/capture',{aircraft_id:currentInspection.aircraft_id});acceptBindingProfile(await poll(job.id,'library'));}
 catch(error){bindingMessage(errorDetail(error),true);}finally{bindingBusy=false;updateBusy();}
};
$('binding-import').onclick=()=>{if(!busy())$('binding-file').click();};
$('binding-file').onchange=async()=>{
 const file=$('binding-file').files[0];$('binding-file').value='';if(!file||busy()||!currentInspection)return;
 ++bindingSequence;bindingBusy=true;updateBusy();
 try{if(file.size>262144)throw new UiError(both('profileFileTooLarge'));const profile=JSON.parse(await file.text());acceptBindingProfile(await api('/api/bindings/import',{aircraft_id:currentInspection.aircraft_id,profile}));}
 catch(error){bindingMessage(errorDetail(error),true);}finally{bindingBusy=false;updateBusy();}
};
$('binding-export').onclick=event=>{if(busy()){event.preventDefault();return;}if(desktopMode){event.preventDefault();saveBindingRecord();}};
async function saveBindingRecord(){
 if(!bindingProfile||busy())return;bindingBusy=true;updateBusy();
 try{if(!window.pywebview?.api?.save_binding_profile)throw new UiError(both('desktopNotReady'));const result=await window.pywebview.api.save_binding_profile(bindingProfile.aircraft_id);if(result.error)throw remoteError(result);}
 catch(error){bindingMessage(errorDetail(error),true);}finally{bindingBusy=false;updateBusy();}
}
$('build').onclick=async()=>{
 if(busy()||!currentAuthor)return;
 try{
  const name=$('skin-name').value.trim(),author=$('skin-author').value.trim(),text=$('button-text').value.trim();
  if(!name||!author)throw new UiError(both('needInfo'));if(!/^[A-Za-z\p{Script=Han}]{1,3}$/u.test(text))throw new UiError(both('needButton'));
  if($('omit-accept')&&!$('omit-accept').checked)throw new UiError(both('confirmOmit'));
  const mappings=[...$('assets').children].map(row=>{const raw=row.querySelector('.slots').value.trim();if(raw&&!/^\d+(?:\s*,\s*\d+)*$/.test(raw))throw new UiError(both('badSlots'));return {asset:row.dataset.asset,slots:raw?raw.split(',').map(Number):[],parameter:row.querySelector('.parameter').value.trim()};});
  authorBusy=true;updateBusy();status('author','building','',true);
  await api('/api/build',{id:currentAuthor,metadata:{name,author,provider_id:$('provider-id').value.trim(),id:$('skin-id').value.trim(),button:{text,background_color:$('button-bg').value.toUpperCase(),text_color:$('button-fg').value.toUpperCase()},mappings}});
  const result=await poll(currentAuthor,'author');
  const header=result.manifest.name+' · '+bytes(result.bytes)+'\n';status('author','built',{zh:header+L.zh.verified,en:header+L.en.verified},false,false,{download:true,id:currentAuthor,name:result.name});
  $('provider-id').value=result.manifest.provider_id;$('skin-id').value=result.manifest.id;
 }catch(error){status('author','failed',errorDetail(error),false,true);}finally{authorBusy=false;updateBusy();}
};
async function loadLibrary(showError=true){
 if(libraryLoading||busy())return;
 const request=++libraryRequest,game=currentGame;libraryLoading=true;updateBusy();
 try{
  if(!game)throw new UiError(both('chooseDirectory'));
  const result=await api('/api/library');if(request!==libraryRequest||game!==currentGame)return;
  libraryData=result;renderLibrary();
 }catch(error){if(showError)status('library','failed',errorDetail(error),false,true);}
 finally{libraryLoading=false;updateBusy();}
}
function renderLibrary(){
 const filter=$('aircraft-filter'),old=filter.value;
 const planes=[...new Set([...libraryData.installed,...libraryData.removed].map(row=>row.aircraft_id))].sort();
 filter.replaceChildren(new Option(tr('allAircraft'),''));for(const plane of planes)filter.add(new Option(planeName(plane),plane));if(planes.includes(old))filter.value=old;
 $('installed-count').textContent=libraryData.installed.length;$('removed-count').textContent=libraryData.removed.length;
 $('view-installed').classList.toggle('active',libraryView==='installed');$('view-removed').classList.toggle('active',libraryView==='removed');
 const rows=libraryData[libraryView].filter(row=>!filter.value||row.aircraft_id===filter.value),list=$('library-list');list.replaceChildren();
 if(!rows.length){const empty=document.createElement('div');empty.className='empty-library';empty.textContent=filter.value?tr('emptyFilter'):tr(libraryView==='installed'?'emptyInstalled':'emptyRemoved');list.append(empty);return;}
 for(const item of rows){
  const row=document.createElement('article');row.className='livery-row';
  const chip=document.createElement('div');chip.className='livery-chip';chip.textContent=item.button?.text||'MOD';
  chip.style.background=/^#[\da-f]{6}$/i.test(item.button?.background_color)?item.button.background_color:'#286B97';chip.style.color=/^#[\da-f]{6}$/i.test(item.button?.text_color)?item.button.text_color:'#FFFFFF';
  const info=document.createElement('div');info.className='livery-info';const title=document.createElement('h3');title.textContent=item.name;
  const meta=document.createElement('div');meta.className='livery-meta';meta.textContent=(item.author||tr('unknownAuthor'))+' · '+planeName(item.aircraft_id)+(item.bytes?' · '+bytes(item.bytes):'');info.append(title,meta);
  const tags=document.createElement('div');tags.className='livery-tags';
  for(const [show,key,warn] of [[item.selected,'selected',false],[!item.managed,'manual',true],[item.managed&&(!item.complete||item.damaged||item.interrupted),'incomplete',true]])if(show){const tag=document.createElement('span');tag.className='livery-tag'+(warn?' warning':'');tag.textContent=tr(key);tags.append(tag);}
  if(tags.childNodes.length)info.append(tags);
  const action=document.createElement('button');action.className='livery-action '+(libraryView==='removed'?'secondary':item.managed?'danger':'secondary');
  const kind=libraryView==='removed'?'restore':item.managed?'remove':'openFolder';action.textContent=tr(kind);
  action.disabled=busy()||(kind!=='openFolder'&&libraryData.game_running);
  action.onclick=()=>{if(kind==='remove')libraryAction('remove',item.identity);else if(kind==='restore')libraryAction('restore',item.removal_id);else openFolder(item.identity);};
  row.append(chip,info,action);list.append(row);
 }
}
$('aircraft-filter').onchange=renderLibrary;$('library-refresh').onclick=()=>loadLibrary();
for(const view of ['installed','removed'])$('view-'+view).onclick=()=>{libraryView=view;renderLibrary();loadLibrary(false);};
async function openFolder(identity){
 try{if(!window.pywebview?.api?.open_skin_folder)throw new UiError(both('desktopOnly'));const result=await window.pywebview.api.open_skin_folder(identity);if(result.error)throw remoteError(result);}
 catch(error){status('library','failed',errorDetail(error),false,true);}
}
async function libraryAction(kind,id){
 if(busy())return;libraryBusy=true;updateBusy();renderLibrary();
 try{
  delete statuses.library;renderStatus('library');
  const job=await api('/api/library/'+kind,kind==='remove'?{identity:id}:{removal_id:id});await poll(job.id,'library');
 }catch(error){status('library','failed',errorDetail(error),false,true);}
 finally{libraryBusy=false;updateBusy();await loadLibrary();renderStatus('library');}
}
$('guide-open').onclick=()=>$('guide-modal').classList.remove('hidden');$('guide-close').onclick=()=>$('guide-modal').classList.add('hidden');
$('guide-modal').onclick=e=>{if(e.target===$('guide-modal'))$('guide-modal').classList.add('hidden');};
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('guide-modal').classList.add('hidden');});
applyLanguage();initialize();
