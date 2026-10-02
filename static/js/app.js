/* JARVIS v7.0 - app.js (full rewrite, defensive) */
(function(){
'use strict';

var STATE={BOOT:'boot',IDLE:'idle',LISTENING:'listening',
           THINKING:'thinking',SPEAKING:'speaking',
           TOOL:'tool_call',ERROR:'error'};
var state=STATE.BOOT;
var busy=false;
var muted=false;
var micActive=false;
var mediaRecorder=null;
var audioChunks=[];
var uptimeSec=0;

var $=function(id){return document.getElementById(id);};
var on=function(id,ev,fn){var e=$(id);if(e)e.addEventListener(ev,fn);};
var setText=function(id,v){var e=$(id);if(e)e.textContent=v;};
var setHTML=function(id,v){var e=$(id);if(e)e.innerHTML=v;};
var addCls=function(id,c){var e=$(id);if(e)e.classList.add(c);};
var rmCls=function(id,c){var e=$(id);if(e)e.classList.remove(c);};

function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function ts(){
  var n=new Date();
  return [n.getHours(),n.getMinutes(),n.getSeconds()]
    .map(function(x){return String(x).padStart(2,'0');}).join(':');
}

function addLog(msg,cls){
  try{
    var log=$('log');if(!log)return;
    var d=document.createElement('div');
    d.className='log-entry '+(cls||'');
    d.innerHTML='<span class="t">'+ts()+'</span>'+esc(msg);
    log.appendChild(d);
    while(log.children.length>200)log.removeChild(log.firstChild);
    log.scrollTop=log.scrollHeight;
  }catch(e){console.warn('addLog',e);}
}

function addStreamingLog(cls){
  try{
    var log=$('log');if(!log)return null;
    var d=document.createElement('div');
    d.className='log-entry '+(cls||'bot');
    log.appendChild(d);
    log.scrollTop=log.scrollHeight;
    return d;
  }catch(e){return null;}
}

function setState(next){
  if(state===next)return;
  state=next;
  try{document.body.dataset.state=next;}catch(e){}
  var labels={boot:'BOOTING',idle:'ONLINE',listening:'LISTENING',
    thinking:'PROCESSING',speaking:'SPEAKING',tool_call:'TOOL CALL',error:'ERROR'};
  setText('status-text',labels[next]||labels.idle);
  var tags={boot:'INITIALIZING',idle:'SYSTEM ONLINE',listening:'LISTENING',
    thinking:'PROCESSING',speaking:'SPEAKING',tool_call:'TOOL CALL',error:'ERROR'};
  setText('tagline',tags[next]||tags.idle);
}

function initCanvas(){
  try{
    var canvas=document.getElementById('orb');
    if(!canvas)return;
    var ctx=canvas.getContext('2d');
    var particlesCanvas=document.getElementById('particles');
    var particles=[];
    var W,H,CX,CY,DPR,orbTime=0;

    function resize(){
      DPR=Math.min(window.devicePixelRatio||1,2);
      W=window.innerWidth;H=window.innerHeight;
      CX=W/2;CY=H*0.42;
      canvas.width=W*DPR;canvas.height=H*DPR;
      canvas.style.width=W+'px';canvas.style.height=H+'px';
      ctx.setTransform(DPR,0,0,DPR,0,0);
      if(particlesCanvas){
        particlesCanvas.width=W*DPR;particlesCanvas.height=H*DPR;
        particlesCanvas.style.width=W+'px';particlesCanvas.style.height=H+'px';
        var pctx=particlesCanvas.getContext('2d');
        pctx.setTransform(DPR,0,0,DPR,0,0);pctx.clearRect(0,0,W,H);
        particles=[];
        for(var i=0;i<80;i++){
          particles.push({x:Math.random()*W,y:Math.random()*H,
            r:Math.random()*1.4+0.3,vx:(Math.random()-0.5)*0.15,
            vy:(Math.random()-0.5)*0.15,a:Math.random()*0.5+0.15,
            tw:Math.random()*Math.PI*2});
        }
      }
    }

    resize();
    window.addEventListener('resize',resize);

    function draw(){
      orbTime+=0.016;
      ctx.clearRect(0,0,W,H);
      var accent=getComputedStyle(document.documentElement).getPropertyValue('--theme-accent').trim()||'#8b3fff';
      var hue=getComputedStyle(document.documentElement).getPropertyValue('--theme-hue').trim()||'290';
      var R=Math.min(W,H)*0.13;
      var st=document.body.dataset.state||'idle';
      var active=st==='listening'||st==='speaking';
      var thinking=st==='thinking'||st==='tool_call';
      var pulse=1+Math.sin(orbTime*(active?3:thinking?5:1.2))*(active?0.06:0.03);
      var r=R*pulse;

      var g1=ctx.createRadialGradient(CX,CY,0,CX,CY,r*3);
      g1.addColorStop(0,'hsla('+hue+',100%,70%,0.35)');
      g1.addColorStop(0.4,'hsla('+hue+',100%,55%,0.12)');
      g1.addColorStop(1,'hsla('+hue+',100%,40%,0)');
      ctx.fillStyle=g1;ctx.beginPath();ctx.arc(CX,CY,r*3,0,Math.PI*2);ctx.fill();

      var g2=ctx.createRadialGradient(CX,CY-r*0.2,0,CX,CY,r);
      g2.addColorStop(0,'hsla('+hue+',100%,98%,0.95)');
      g2.addColorStop(0.35,'hsla('+hue+',90%,70%,0.85)');
      g2.addColorStop(1,'hsla('+hue+',80%,40%,0.35)');
      ctx.fillStyle=g2;ctx.beginPath();ctx.arc(CX,CY,r,0,Math.PI*2);ctx.fill();

      ctx.beginPath();ctx.arc(CX,CY,r,0,Math.PI*2);
      ctx.strokeStyle='hsla('+hue+',100%,85%,0.7)';ctx.lineWidth=1;ctx.stroke();

      var ringSpeeds=[0.3,-0.45],ringScales=[2.4,3.0],ringTilts=[0.35,-0.55],ringSquash=[0.32,-0.36];
      for(var k=0;k<2;k++){
        var baseR=R*ringScales[k],tilt=ringTilts[k],squash=ringSquash[k];
        ctx.save();ctx.translate(CX,CY);ctx.rotate(tilt);ctx.scale(1,Math.abs(squash));
        ctx.beginPath();ctx.ellipse(0,0,baseR,baseR,0,0,Math.PI*2);
        ctx.strokeStyle='hsla('+hue+',80%,70%,0.18)';ctx.lineWidth=0.8;ctx.stroke();
        ctx.setLineDash([2,6]);
        ctx.beginPath();ctx.ellipse(0,0,baseR*0.96,baseR*0.96,0,0,Math.PI*2);
        ctx.strokeStyle='hsla('+hue+',90%,75%,0.3)';ctx.lineWidth=0.6;ctx.stroke();
        ctx.setLineDash([]);
        var n=12,speed=ringSpeeds[k]*(thinking?4:active?2:1);
        for(var i=0;i<n;i++){
          var a=(i/n)*Math.PI*2+orbTime*speed;
          var px=Math.cos(a)*baseR,py=Math.sin(a)*baseR*Math.abs(squash);
          var rx=px*Math.cos(tilt)-py*Math.sin(tilt),ry=px*Math.sin(tilt)+py*Math.cos(tilt);
          var alpha=0.4+0.4*Math.sin(orbTime*2+i);
          ctx.beginPath();ctx.arc(rx,ry,1.2,0,Math.PI*2);
          ctx.fillStyle='hsla('+(hue+20)+',100%,85%,'+alpha+')';ctx.fill();
        }
        ctx.restore();
      }

      if(particlesCanvas){
        var pctx=particlesCanvas.getContext('2d');
        pctx.clearRect(0,0,W,H);
        for(var j=0;j<particles.length;j++){
          var p=particles[j];
          p.x+=p.vx;p.y+=p.vy;p.tw+=0.02;
          if(p.x<0)p.x=W;if(p.x>W)p.x=0;
          if(p.y<0)p.y=H;if(p.y>H)p.y=0;
          var tw=0.6+Math.sin(p.tw)*0.4;
          pctx.beginPath();pctx.arc(p.x,p.y,p.r,0,Math.PI*2);
          pctx.fillStyle='hsla('+hue+',80%,75%,'+(p.a*tw)+')';pctx.fill();
        }
      }
      requestAnimationFrame(draw);
    }
    draw();
  }catch(e){console.warn('canvas',e);}
}

function applyTheme(hue,accent){
  try{
    if(hue!=null)document.documentElement.style.setProperty('--theme-hue',hue);
    if(accent)document.documentElement.style.setProperty('--theme-accent',accent);
  }catch(e){}
}

async function loadPrefs(){
  try{
    var r=await fetch('/api/prefs');var d=await r.json();
    var p=d.prefs||{};applyTheme(p.hue,p.accent);return p;
  }catch(e){console.warn('loadPrefs',e);return{};}
}

async function loadInfo(){
  try{
    var r=await fetch('/api/info');var info=await r.json();
    setText('side-model',info.model_label||info.model||'--');
    var v=info.voice;
    setText('side-voice',v&&v.label?v.label:(typeof v==='string'?v:'--'));
    setText('side-mood',info.mood||'--');
    if(info.theme)applyTheme(info.theme.hue,info.theme.accent);
    return info;
  }catch(e){console.warn('loadInfo',e);return null;}
}

async function loadMemory(){
  try{
    var r=await fetch('/api/memory');var d=await r.json();
    setText('side-memory',(d.facts||[]).length+' facts');
  }catch(e){setText('side-memory','--');}
}

var modelCycle=[];var modelCycleIdx=0;
var voiceCycle=[];var voiceCycleIdx=0;
var moodCycle=[];var moodCycleIdx=0;

async function loadModels(){
  try{
    var r=await fetch('/api/models');var d=await r.json();
    var active=d.active||'auto';
    modelCycle=['auto'].concat((d.models||[]).map(function(m){return m.id;}));
    modelCycle=Array.from(new Set(modelCycle));
    var i=modelCycle.indexOf(active);modelCycleIdx=i>=0?i:0;
    updateModelUI();
    var sideBlock=document.querySelector('#side-model');
    if(sideBlock&&!sideBlock.dataset.wired){
      sideBlock.dataset.wired='1';sideBlock.style.cursor='pointer';
      sideBlock.addEventListener('click',cycleModel);
    }
    var chips=document.getElementById('model-chips');if(chips)chips.innerHTML='';
  }catch(e){console.warn('loadModels',e);}
}

function updateModelUI(){
  var current=modelCycle[modelCycleIdx]||'auto';
  var label=current==='auto'?'Auto':current.replace('deepseek-','').replace(':free',' \u25CF').replace('qwen3.8-flash','qwen 3.8').replace('mimo-v2.5','mimo').replace('v4.1-flash','Flash').replace('v4-flash','V4');
  var el=document.getElementById('side-model');if(el)el.textContent=label;
}

async function cycleModel(){
  if(!modelCycle.length)return;
  modelCycleIdx=(modelCycleIdx+1)%modelCycle.length;
  var next=modelCycle[modelCycleIdx];
  updateModelUI();
  try{
    var r=await fetch('/api/model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:next})});
    var d=await r.json();
    if(d.ok&&d.theme){
      document.documentElement.style.setProperty('--theme-hue',d.theme.hue);
      document.documentElement.style.setProperty('--theme-accent',d.theme.accent);
    }
    addLog('Model \u2192 '+next,'system');
  }catch(e){console.warn('cycleModel',e);}
}

async function loadVoices(){
  try{
    var r=await fetch('/api/voices');var d=await r.json();
    voiceCycle=(d.voices||[]).map(function(v){return v.key;});
    voiceCycleIdx=Math.max(0,voiceCycle.indexOf(d.active||'oliver'));
    updateVoiceUI();
    var sideBlock=document.querySelector('#side-voice');
    if(sideBlock&&!sideBlock.dataset.wired){
      sideBlock.dataset.wired='1';sideBlock.style.cursor='pointer';
      sideBlock.addEventListener('click',cycleVoice);
    }
  }catch(e){console.warn('loadVoices',e);}
}

function updateVoiceUI(){
  var key=voiceCycle[voiceCycleIdx]||'ryan';
  var label=key.charAt(0).toUpperCase()+key.slice(1);
  var el=document.getElementById('side-voice');if(el)el.textContent=label;
}

async function cycleVoice(){
  if(!voiceCycle.length)return;
  voiceCycleIdx=(voiceCycleIdx+1)%voiceCycle.length;
  var next=voiceCycle[voiceCycleIdx];
  updateVoiceUI();
  try{
    await fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:next})});
    addLog('Voice \u2192 '+next,'system');
  }catch(e){console.warn('cycleVoice',e);}
}

async function loadMoods(){
  try{
    var r=await fetch('/api/info');var info=await r.json();
    moodCycle=(info.moods||[]).map(function(m){return m.name;});
    moodCycleIdx=Math.max(0,moodCycle.indexOf(info.mood||'thinking'));
    updateMoodUI();
    var sideBlock=document.querySelector('#side-mood');
    if(sideBlock&&!sideBlock.dataset.wired){
      sideBlock.dataset.wired='1';sideBlock.style.cursor='pointer';
      sideBlock.addEventListener('click',cycleMood);
    }
  }catch(e){console.warn('loadMoods',e);}
}

function updateMoodUI(){
  var el=document.getElementById('side-mood');if(el)el.textContent=moodCycle[moodCycleIdx]||'thinking';
}

async function cycleMood(){
  if(!moodCycle.length)return;
  moodCycleIdx=(moodCycleIdx+1)%moodCycle.length;
  var next=moodCycle[moodCycleIdx];
  updateMoodUI();
  try{
    await fetch('/api/mood',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:next})});
    addLog('Mood \u2192 '+next,'system');
  }catch(e){console.warn('cycleMood',e);}
}

async function updateStats(){
  try{
    var r=await fetch('/api/stats');var s=await r.json();
    setText('st-cpu',s.cpu>=0?s.cpu+'%':'--');
    setText('st-ram',s.ram>=0?s.ram+'%':'--');
    setText('st-bat',s.battery>=0?s.battery+'%':'--');
    setText('st-net',s.net>=0?s.net+'MB':'--');
  }catch(e){
    setText('st-cpu','--');setText('st-ram','--');
    setText('st-bat','--');setText('st-net','--');
  }
}

function startStatsLoop(){updateStats();setInterval(updateStats,3000);}

function startUptime(){
  setInterval(function(){
    uptimeSec++;
    var h=String(Math.floor(uptimeSec/3600)).padStart(2,'0');
    var m=String(Math.floor((uptimeSec%3600)/60)).padStart(2,'0');
    var s=String(uptimeSec%60).padStart(2,'0');
    setText('side-uptime',h+':'+m+':'+s);
  },1000);
}

function startClock(){
  var tick=function(){
    var n=new Date();
    var p=function(v){return String(v).padStart(2,'0');};
    setText('clock',p(n.getHours())+':'+p(n.getMinutes())+':'+p(n.getSeconds()));
  };tick();setInterval(tick,1000);
}

function initWaveform(){
  try{
    var wf=$('waveform');if(!wf)return;wf.innerHTML='';
    for(var i=0;i<28;i++){
      var bar=document.createElement('div');bar.className='bar';
      bar.style.height=(8+Math.random()*12)+'px';wf.appendChild(bar);
    }
    setInterval(function(){
      var bars=wf.children;
      for(var i=0;i<bars.length;i++){bars[i].style.height=(6+Math.random()*28)+'px';}
    },120);
  }catch(e){}
}

async function startRecording(){
  try{
    var stream=await navigator.mediaDevices.getUserMedia({audio:true});
    mediaRecorder=new MediaRecorder(stream,{mimeType:'audio/webm;codecs=opus'});
    audioChunks=[];
    mediaRecorder.ondataavailable=function(e){if(e.data.size>0)audioChunks.push(e.data);};
    mediaRecorder.onstop=async function(){
      stream.getTracks().forEach(function(t){t.stop();});
      if(!audioChunks.length)return;
      var blob=new Blob(audioChunks,{type:'audio/webm'});
      var fd=new FormData();fd.append('audio',blob,'recording.webm');
      try{
        addLog('Transcribing...','system');
        var r=await fetch('/api/transcribe',{method:'POST',body:fd});
        var d=await r.json();
        if(d.text&&d.text.trim()){addLog(d.text,'user');sendCommand(d.text);}
        else{addLog('No speech detected.','warn');}
      }catch(err){addLog('Transcribe error: '+err.message,'error');}
    };
    mediaRecorder.start();micActive=true;
    addCls('btn-mic','recording');setText('btn-mic','\u25CF RECORDING');
    setState(STATE.LISTENING);addLog('Mic recording...','system');
  }catch(err){addLog('Mic error: '+err.message,'error');}
}

function stopRecording(){
  if(mediaRecorder&&mediaRecorder.state!=='inactive'){try{mediaRecorder.stop();}catch(e){}}
  micActive=false;rmCls('btn-mic','recording');setText('btn-mic','\u25C9 MIC');
  setState(STATE.IDLE);setText('tagline','SYSTEM ONLINE');
}

function speakText(text){
  if(muted||!text)return;
  try{
    window.speechSynthesis.cancel();
    var u=new SpeechSynthesisUtterance(text);u.rate=1.0;
    u.onend=function(){setState(STATE.IDLE);setText('tagline','SYSTEM ONLINE');};
    u.onerror=function(){setState(STATE.IDLE);setText('tagline','SYSTEM ONLINE');};
    window.speechSynthesis.speak(u);
  }catch(e){}
}

function toggleMute(){
  muted=!muted;
  if(muted){
    rmCls('btn-voice','active');setText('btn-voice','\u25CB VOICE');
    try{window.speechSynthesis.cancel();}catch(e){}
    addLog('Voice muted.','system');
  }else{
    addCls('btn-voice','active');setText('btn-voice','\u25C9 VOICE');
    addLog('Voice unmuted.','system');
  }
}

function stopSpeak(){
  try{window.speechSynthesis.cancel();}catch(e){}
  fetch('/api/stop-speak',{method:'POST'}).catch(function(){});
  setState(STATE.IDLE);setText('tagline','SYSTEM ONLINE');
}

var thinkingBuffer='';
function resetThinking(){
  thinkingBuffer='';setHTML('think-body','<div class="think-empty">Thinking...</div>');
  addCls('thinkpanel','active');
}
function appendThinking(delta){
  try{
    var body=$('think-body');if(!body||!delta)return;
    thinkingBuffer+=delta;
    var empty=body.querySelector('.think-empty');if(empty)empty.remove();
    var span=document.createElement('span');span.className='think-chunk';
    span.textContent=delta;body.appendChild(span);body.scrollTop=body.scrollHeight;
  }catch(e){}
}
function finishThinking(){
  rmCls('thinkpanel','active');
  if(!thinkingBuffer){setHTML('think-body','<div class="think-empty">Idle. Speak or type to see the reasoning stream.</div>');}
}

var SLASH_CMDS=[
  {cmd:'/clear',desc:'Clear the log'},{cmd:'/voice',desc:'Toggle voice output'},
  {cmd:'/mood',desc:'Set current mood'},{cmd:'/personality',desc:'Set personality preset'},
  {cmd:'/search',desc:'Deep web search'},{cmd:'/browse',desc:'Browse a URL'},
  {cmd:'/skills',desc:'List loaded skills'},{cmd:'/tools',desc:'List available tools'},
  {cmd:'/context',desc:'Show session context'},{cmd:'/model',desc:'Switch AI model'},
  {cmd:'/voice-list',desc:'List available voices'},{cmd:'/settings',desc:'Open settings panel'},
  {cmd:'/council',desc:'Run a council — /council <question>'},
  {cmd:'/levels',desc:'Show council levels'},
  {cmd:'/outcomes',desc:'Show outcome memory stats'},
  {cmd:'/verify',desc:'Cross-check the last answer'},
  {cmd:'/agents',desc:'Run parallel multi-agent session'},
  {cmd:'/dream',desc:'Run Dream Mode now'},
  {cmd:'/dream-dry',desc:'Preview Dream Mode (no changes)'},
  {cmd:'/dream-last',desc:'Show last Dream report'},
  {cmd:'/clipboard',desc:'Recent clipboard items'},
  {cmd:'/contacts',desc:'List contacts'},
  {cmd:'/reminders',desc:'Pending reminders'},
  {cmd:'/ocr',desc:'Extract text from screen'},
  {cmd:'/focus',desc:'Focus lock — /focus 60'},
  {cmd:'/snippets',desc:'List snippets'},
  {cmd:'/layouts',desc:'Window layouts'},
  {cmd:'/cleanurl',desc:'Clean clipboard URL'},
  {cmd:'/timesum',desc:'Time tracking summary'},
  {cmd:'/help',desc:'Show available commands'}
];
var slashIdx=-1;

function openSlash(filter){
  var el=$('slash-menu');if(!el)return;
  var items=SLASH_CMDS.filter(function(c){return !filter||c.cmd.indexOf(filter)>=0;});
  if(!items.length){closeSlash();return;}
  slashIdx=0;
  el.innerHTML=items.map(function(c,i){
    return '<div class="slash-item'+(i===0?' selected':'')+'" data-cmd="'+esc(c.cmd)+'">'+
    '<span class="cmd">'+esc(c.cmd)+'</span><span class="desc">'+esc(c.desc)+'</span></div>';
  }).join('');el.classList.add('open');
}
function closeSlash(){var el=$('slash-menu');if(el)el.classList.remove('open');slashIdx=-1;}
function navSlash(dir){
  var el=$('slash-menu');if(!el||!el.classList.contains('open'))return;
  var items=el.querySelectorAll('.slash-item');if(!items.length)return;
  items[slashIdx]&&items[slashIdx].classList.remove('selected');
  slashIdx=(slashIdx+dir+items.length)%items.length;
  items[slashIdx]&&items[slashIdx].classList.add('selected');
  items[slashIdx]&&items[slashIdx].scrollIntoView({block:'nearest'});
}
function pickSlash(){
  var el=$('slash-menu');if(!el||!el.classList.contains('open'))return;
  var items=el.querySelectorAll('.slash-item');
  var item=items[slashIdx];
  if(item){
    var cmd=item.getAttribute('data-cmd');closeSlash();
    var cmdEl=$('cmd');if(cmdEl)cmdEl.value='';handleSlash(cmd);
  }
}
function handleSlash(cmd){
  if(cmd==='/clear'){var log=$('log');if(log)log.innerHTML='';addLog('Log cleared.','system');}
  else if(cmd==='/voice')toggleMute();
  else if(cmd==='/settings')openSettings();
  else if(cmd==='/levels'||cmd.indexOf('/levels ')===0){showLevels();}
  else if(cmd==='/council'||cmd.indexOf('/council ')===0){runCouncil(cmd.slice(8).trim());}
  else if(cmd==='/outcomes'){showOutcomes();}
  else if(cmd.indexOf('/verify')===0){runVerify(cmd.slice(7).trim());}
  else if(cmd==='/agents'||cmd.indexOf('/agents ')===0){runAgents(cmd.slice(8).trim());}
  else if(cmd==='/dream'||cmd==='/dream-dry'){runDream(cmd==='/dream-dry');}
  else if(cmd==='/dream-last'){showDreamLast();}
  else if(cmd==='/clipboard'){showClipboard();}
  else if(cmd==='/contacts'){showContacts();}
  else if(cmd==='/reminders'){showReminders();}
  else if(cmd==='/ocr'){runOcr();}
  else if(cmd==='/focus'||cmd.indexOf('/focus ')===0){runFocus(cmd.slice(6).trim());}
  else if(cmd==='/snippets'){showSnippets();}
  else if(cmd==='/layouts'){showLayouts();}
  else if(cmd==='/cleanurl'){runCleanUrl();}
  else if(cmd==='/timesum'){showTimeSum();}
  else sendCommand(cmd);
}
async function showClipboard(){
  try{
    var r=await fetch('/api/clipboard/recent').then(function(x){return x.json();});
    var items=r.items||[];
    if(!items.length)addLog('Clipboard empty.','system');
    else{
      addLog('Clipboard ('+items.length+'):','system');
      items.slice(-8).forEach(function(it){
        addLog('  ['+it.type+'] '+((it.preview||'').slice(0,60)),'system');});
    }
  }catch(e){}
}
async function showContacts(){
  try{
    var r=await fetch('/api/contacts').then(function(x){return x.json();});
    var c=r.contacts||[];
    if(!c.length)addLog('No contacts.','system');
    else c.slice(0,10).forEach(function(x){
      addLog('  '+x.name+(x.phone?' — '+x.phone:''),'system');});
  }catch(e){}
}
async function showReminders(){
  try{
    var r=await fetch('/api/reminders').then(function(x){return x.json();});
    var items=r.reminders||[];
    if(!items.length)addLog('No pending reminders.','system');
    else items.forEach(function(x){
      addLog('  '+x.due_at.slice(11,16)+' — '+x.text.slice(0,60),'system');});
  }catch(e){}
}
async function runOcr(){
  addLog('Capturing screen...','system');
  try{
    var r=await fetch('/api/ocr/screen',{method:'POST'}).then(function(x){return x.json();});
    addLog(r.ok?r.text.slice(0,1000):('OCR failed: '+(r.text||'unknown')),r.ok?'bot':'warn');
  }catch(e){addLog('OCR error: '+e.message,'warn');}
}
async function runFocus(arg){
  try{
    if(!arg){
      var r=await fetch('/api/focus/status').then(function(x){return x.json();});
      addLog('Focus: '+(r.active?'ON until '+r.until:'off'),'system');
    }else{
      var mins=parseInt(arg)||60;
      var r2=await fetch('/api/focus/start',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({minutes:mins})}).then(function(x){return x.json();});
      addLog(r2.ok?('Focus ON for '+mins+' min.'):'Focus already active.','system');
    }
  }catch(e){}
}
async function showSnippets(){
  try{
    var r=await fetch('/api/snippets').then(function(x){return x.json();});
    var items=r.snippets||[];
    if(!items.length)addLog('No snippets.','system');
    else items.slice(0,10).forEach(function(s){
      addLog('  #'+s.id+' '+s.title+(s.language?' ['+s.language+']':''),'system');});
  }catch(e){}
}
async function showLayouts(){
  try{
    var r=await fetch('/api/layouts').then(function(x){return x.json();});
    var items=r.layouts||[];
    if(!items.length)addLog('No layouts.','system');
    else items.forEach(function(l){addLog('  '+l.name,'system');});
  }catch(e){}
}
async function runCleanUrl(){
  try{
    var r=await fetch('/api/url/clean',{method:'POST'}).then(function(x){return x.json();});
    addLog(r.ok?('Cleaned: '+r.after):('Clean failed: '+r.error),r.ok?'bot':'warn');
  }catch(e){}
}
async function showTimeSum(){
  try{
    var r=await fetch('/api/time/summary?hours=24').then(function(x){return x.json();});
    var items=r.entries||[];
    if(!items.length)addLog('No time entries yet.','system');
    else items.slice(0,8).forEach(function(x){
      addLog('  '+x.app+': '+Math.round(x.seconds/60)+' min','system');});
  }catch(e){}
}
async function runCouncil(arg){
  if(!arg){addLog('Usage: /council <question>','warn');return;}
  addLog('Running council on: "'+arg+'"','system');
  setState(STATE.THINKING);
  try{
    var body={question:arg,level:'council'};
    var r=await fetch('/api/council/run',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)}).then(function(x){return x.json();});
    if(r.needs_confirmation){
      var msg='Council "'+r.level+'" costs ~$'+r.cost_estimate+' and takes ~'+r.timeout+'s. Run it?';
      addLog(msg,'system');
      setState(STATE.IDLE);
      if(!confirm(msg))return;
      setState(STATE.THINKING);
      body.confirm=true;
      r=await fetch('/api/council/run',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)}).then(function(x){return x.json();});
    }
    if(r.ok){
      addLog('Council answer ('+r.confidence+'% conf, '+r.ok_count+'/'+r.total_count+' models, '+r.elapsed+'s):','system');
      addLog(r.answer,'bot');
      speakText(r.answer);
    }else{
      addLog('Council failed: '+(r.error||'unknown'),'warn');
    }
  }catch(e){addLog('Council error: '+e.message,'warn');}
  setState(STATE.IDLE);
}
async function showLevels(){
  try{
    var r=await fetch('/api/council/levels').then(function(x){return x.json();});
    addLog('Council levels:','system');
    (r.levels||[]).forEach(function(l){
      addLog('  L'+l.level+' '+l.name+': '+l.models+' models, ~'+l.timeout+'s, ~$'+l.cost_estimate,'system');});
  }catch(e){}
}
async function showOutcomes(){
  try{
    var r=await fetch('/api/outcomes/stats').then(function(x){return x.json();});
    addLog('Outcomes: '+r.total+' total | '+r.accepted+' accepted | '+
           r.rejected+' rejected | '+r.pending+' pending','system');
    if(r.rejected>0){
      var rl=await fetch('/api/outcomes/rejected').then(function(x){return x.json();});
      (rl.rejected||[]).slice(0,3).forEach(function(rj){
        addLog('  X '+(rj.question||'').slice(0,60),'warn');});
    }
  }catch(e){addLog('Outcomes error: '+e.message,'warn');}
}
async function runVerify(arg){
  var q=null,a=null;
  if(arg&&arg.indexOf('||')>=0){var p=arg.split('||');q=p[0].trim();a=p[1].trim();}
  if(!q||!a){
    try{
      var h=await fetch('/api/history/default').then(function(x){return x.json();});
      var msgs=h.messages||[];
      for(var i=msgs.length-1;i>=0;i--){if(msgs[i].role==='assistant'&&msgs[i].content){a=msgs[i].content;break;}}
      for(var j=msgs.length-1;j>=0;j--){if(msgs[j].role==='user'&&msgs[j].content){q=msgs[j].content;break;}}
    }catch(e){}
  }
  if(!q||!a){addLog('Usage: /verify <question> || <answer> (or chat first)','warn');return;}
  addLog('Reality-checking last answer…','system');
  try{
    var r=await fetch('/api/reality-check',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,answer:a})}).then(function(x){return x.json();});
    addLog('Reality check: agree='+r.agree+', confidence='+r.confidence+'%'+
           (r.note?' — '+r.note:''), r.agree==='no'?'warn':'system');
    if(r.escalate_to_council)addLog('Sources disagree — consider /council '+q,'warn');
  }catch(e){addLog('Verify error: '+e.message,'warn');}
}

async function runAgents(arg){
  if(!arg){addLog('Usage: /agents <complex question>','warn');return;}
  addLog('Running agents on: "'+arg+'"','system');
  setState(STATE.THINKING);
  try{
    var r=await fetch('/api/agents/run',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:arg})}).then(function(x){return x.json();});
    if(r.ok){
      addLog('Agents ('+r.ok_tasks+'/'+r.tasks+' ok, '+r.elapsed+'s):','system');
      (r.sub_results||[]).forEach(function(s,i){
        var mark=s.ok?'✓':'✗';
        addLog('  '+mark+' Task '+(i+1)+': '+((s.task||'').slice(0,60))+' ('+s.elapsed+'s)','system');});
      addLog(r.answer,'bot');
      speakText(r.answer);
    }else{
      addLog('Agents failed: '+(r.error||'unknown'),'warn');
    }
  }catch(e){addLog('Agents error: '+e.message,'warn');}
  setState(STATE.IDLE);
}
async function runDream(dry){
  addLog(dry?'Previewing Dream Mode...':'Running Dream Mode...','system');
  setState(STATE.THINKING);
  try{
    var r=await fetch('/api/dream/run',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dry_run:dry})}).then(function(x){return x.json();});
    if(r.ok){
      var folders=r.folders||[];
      var total=folders.reduce(function(a,f){return a+(f.moved||0);},0);
      addLog('Dream done in '+r.elapsed+'s. '+total+' file(s) moved.','system');
      folders.forEach(function(f){
        addLog('  '+f.folder+': '+f.moved+' moved, '+f.skipped+' skipped','system');});
      if(r.backup)addLog('Backup: '+(r.backup.ok?'ok':'skip'),'system');
      if(r.day_summary)addLog('Day summary: '+r.day_summary,'bot');
    }else{
      addLog('Dream skipped: '+(r.reason||'unknown'),'warn');
    }
  }catch(e){addLog('Dream error: '+e.message,'warn');}
  setState(STATE.IDLE);
}
async function showDreamLast(){
  try{
    var r=await fetch('/api/dream/last').then(function(x){return x.json();});
    if(r&&r.started_at){
      addLog('Last Dream: '+r.started_at+' ('+r.elapsed+'s)','system');
      var folders=r.folders||[];
      var total=folders.reduce(function(a,f){return a+(f.moved||0);},0);
      addLog('  '+total+' files organized','system');
      if(r.day_summary)addLog('  Summary: '+r.day_summary,'bot');
    }else{
      addLog('No Dream reports yet.','system');
    }
  }catch(e){}
}
async function sendCommand(text){
  if(busy||!text||!text.trim())return;
  busy=true;resetThinking();
  var cmdEl=$('cmd');if(cmdEl)cmdEl.value='';
  addLog(text,'user');setState(STATE.THINKING);
  var streamEl=null;var full='';
  try{
    var res=await fetch('/api/command',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:text})});
    if(!res.ok)throw new Error('HTTP '+res.status);
    var reader=res.body.getReader();var dec=new TextDecoder();var buf='';
    while(true){
      var result=await reader.read();if(result.done)break;
      buf+=dec.decode(result.value,{stream:true});
      var parts=buf.split('\n\n');buf=parts.pop();
      for(var i=0;i<parts.length;i++){
        var part=parts[i];
        if(part.indexOf('data: ')!==0)continue;
        var payload=part.slice(6);if(payload==='[DONE]')continue;
        try{
          var obj=JSON.parse(payload);
          if(obj.route)addLog('Route: '+obj.route,'system');
          if(obj.reasoning)appendThinking(obj.reasoning);
          if(obj.delta){
            if(!streamEl)streamEl=addStreamingLog(obj.source==='skill'?'skill':'bot');
            full+=obj.delta;if(streamEl)streamEl.textContent=full;
            var logEl=$('log');if(logEl)logEl.scrollTop=logEl.scrollHeight;
            if(state===STATE.THINKING)setState(STATE.SPEAKING);
          }
          if(obj.tool_call){
            setState(STATE.TOOL);
            addLog('\u2699 '+obj.tool_call.name+'('+JSON.stringify(obj.tool_call.args||{})+')','tool');
            (function(){var s=state;setTimeout(function(){if(state===STATE.TOOL)setState(STATE.THINKING);},1200);})();
          }
          if(obj.tool_result){
            addLog('\u2714 '+(obj.tool_result.summary||JSON.stringify(obj.tool_result).slice(0,120)),'tool');
          }
          if(obj.error)addLog('\u2718 '+obj.error,'error');
          if(obj.speak){setState(STATE.SPEAKING);speakText(obj.speak);}
        }catch(e){}
      }
    }
  }catch(err){addLog('Error: '+err.message,'error');}
  finally{
    busy=false;
    finishThinking();
    // Only reset to IDLE if we're not currently speaking
    if(state!==STATE.SPEAKING&&state!==STATE.IDLE){
      setState(STATE.IDLE);setText('tagline','SYSTEM ONLINE');
    }
  }
}

function openSettings(){addCls('modal-settings','open');loadTab('model');var _t=document.querySelector('.modal-tabs .tab.active');if(_t)_t.focus({preventScroll:true});}
function closeSettings(){rmCls('modal-settings','open');}

function loadTab(name){
  document.querySelectorAll('.tab').forEach(function(t){
    t.classList.toggle('active',t.getAttribute('data-tab')===name);
  });
  document.querySelectorAll('.tab-panel').forEach(function(p){
    p.classList.toggle('active',p.getAttribute('data-panel')===name);
  });
  var inner=$('panel-'+name);if(!inner)return;
  var endpoints={model:'/api/models',voice:'/api/voices',mood:'/api/info',
    personality:'/api/personality',skills:'/api/skills',tools:'/api/tools',
    mcp:'/api/mcp',appearance:'/api/prefs',audio:'/api/prefs',
    general:'/api/prefs',about:'/api/info',council:'/api/council/levels',
    capture:'/api/contacts',workspace:'/api/layouts',
    clipboard:'/api/clipboard/recent',dream:'/api/dream/status'};
  fetch(endpoints[name]||'/api/info')
    .then(function(r){return r.json();})
    .then(function(data){inner.innerHTML=renderTab(name,data);})
    .catch(function(){inner.innerHTML='<div style="color:var(--red)">Failed to load</div>';});
}

function renderTab(name,data){
  if(name==='model'){
    var models=data.models||[];
    if(!models.length)return '<div class="empty-state">No models</div>';
    return '<div class="set-list">'+models.map(function(m){
      return '<div class="set-row"><div class="label">'+esc(m.id)+
        '<small>'+(m.free?'Free':'Paid')+(m.rank?' Rank:'+m.rank:'')+'</small></div>'+
        '<div class="actions"><button class="dbtn'+(m.id===data.active?' active':'')+
        '" data-action="select-model" data-model="'+esc(m.id)+'">SELECT</button></div></div>';
    }).join('')+'</div>';
  }
  if(name==='voice'){
    var voices=data.voices||[];
    return '<div class="set-list">'+voices.map(function(v){
      return '<div class="set-row"><div class="label">'+esc(v.label)+
        '<small>'+esc(v.desc||'')+' | '+esc(v.id)+'</small></div>'+
        '<div class="actions"><button class="dbtn'+(v.key===data.active?' active':'')+
        '" data-action="select-voice" data-key="'+esc(v.key)+'">SELECT</button></div></div>';
    }).join('')+'</div>';
  }
  if(name==='skills'){
    var skills=data.skills||[];
    return '<div class="set-list">'+skills.map(function(s){
      return '<div class="set-row"><div class="label">'+esc(s.name)+
        '<small>'+esc(s.description||'')+'</small></div>'+
        '<div class="actions"><button class="dbtn'+(s.enabled?' on':'')+
        '" data-action="toggle-skill" data-name="'+esc(s.name)+
        '" data-enabled="'+(!s.enabled)+'">'+(s.enabled?'ON':'OFF')+'</button></div></div>';
    }).join('')+'</div>';
  }
  if(name==='tools'){
    var tools=data.tools||[];
    return '<div class="set-list">'+tools.map(function(t){
      return '<div class="set-row"><div class="label">'+esc(t.name||t)+
        '<small>'+esc(t.description||'')+'</small></div></div>';
    }).join('')+'</div>';
  }
  if(name==='mcp'){
    var servers=data.servers||[];
    if(!servers.length)return '<div class="empty-state">No MCP servers</div>';
    return '<div class="set-list">'+servers.map(function(s){
      return '<div class="set-row"><div class="label">'+esc(s.name||s)+
        '<small>'+esc(s.status||s.command||'')+'</small></div></div>';
    }).join('')+'</div>';
  }
  if(name==='personality'){
    var cur=data.current||{};var presets=data.presets||[];
    var html='<div class="set-list">';
    html+='<div class="set-row"><div class="label">Preset<small>'+esc(cur.preset||'default')+'</small></div></div>';
    html+='<div class="set-row"><div class="label">Formality<small>'+esc(String(cur.formality!=null?cur.formality:50))+'%</small></div></div>';
    html+='<div class="set-row"><div class="label">Humor<small>'+esc(String(cur.humor!=null?cur.humor:50))+'%</small></div></div>';
    html+='<div class="set-row"><div class="label">Verbosity<small>'+esc(String(cur.verbosity!=null?cur.verbosity:50))+'%</small></div></div>';
    html+='</div>';
    if(presets.length){html+='<div style="margin-top:12px;color:var(--dim);font-size:9px;letter-spacing:2px">PRESETS</div><div class="set-list" style="margin-top:8px">';
      presets.forEach(function(p){
        html+='<div class="set-row"><div class="label">'+esc(p.name||p)+'</div>'+
          '<div class="actions"><button class="dbtn" data-action="select-personality" data-name="'+esc(p.name||p)+'">SELECT</button></div></div>';
      });html+='</div>';}
    return html;
  }
  if(name==='appearance'){
    var prefs=data.prefs||{};
    return '<div class="set-list">'+
      '<div class="set-row"><div class="label">Theme hue<small>'+esc(String(prefs.hue||290))+'</small></div></div>'+
      '<div class="set-row"><div class="label">Compact mode<small>'+(prefs.compact_mode?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Animation intensity<small>'+esc(prefs.anim_intensity||'vivid')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Font scale<small>'+esc(String(prefs.font_scale||1))+'</small></div></div>'+
      '</div>';
  }
function prefToggle(key,on,label,sub){
  return '<div class="set-row"><div class="label">'+esc(label)+
    '<small>'+esc(sub||(on?'On':'Off'))+'</small></div>'+
    '<div class="actions"><button class="dbtn'+(on?' on':'')+
    '" data-action="set-pref" data-key="'+esc(key)+
    '" data-value="'+(!on)+'">'+(on?'ON':'OFF')+'</button></div></div>';
}
  if(name==='audio'){
    var p2=data.prefs||{};
    var dl=p2.duck_level!=null?p2.duck_level:0.25;
    return '<div class="set-list">'+
      '<div class="set-row"><div class="label">Sound effects<small>'+(p2.sound_effects?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Wake chime<small>'+(p2.wake_chime?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Voice rate offset<small>'+esc(String(p2.voice_rate_offset||0))+'</small></div></div>'+
      prefToggle('ducking_enabled',!!p2.ducking_enabled,'Audio ducking','Lower other apps while JARVIS speaks')+
      '<div class="set-row"><div class="label">Duck level<small>'+Math.round(dl*100)+'%</small></div>'+
      '<div class="actions"><button class="dbtn" data-action="cycle-duck" data-level="'+dl+'">CYCLE</button></div></div>'+
      '</div>';
  }
  if(name==='general'){
    var p3=data.prefs||{};
    return '<div class="set-list">'+
      '<div class="set-row"><div class="label">Autostart<small>'+(p3.autostart_enabled?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">System tray<small>'+(p3.tray_enabled?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Hotkey (Ctrl+Alt+J)<small>'+(p3.hotkey_enabled?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Wake word<small>'+(p3.wake_word_enabled?'On':'Off')+'</small></div></div>'+
      prefToggle('briefings_enabled',!!p3.briefings_enabled,'Morning briefing','Spoken daily briefing')+
      '<div class="set-row"><div class="label">Briefing hour<small>'+esc(String(p3.briefing_hour!=null?p3.briefing_hour:8))+':00</small></div>'+
      '<div class="actions"><input id="input-briefing-hour" type="number" min="0" max="23" value="'+esc(String(p3.briefing_hour!=null?p3.briefing_hour:8))+'" style="width:52px;background:#000;color:#fff;border:1px solid var(--border);border-radius:4px;padding:6px;">'+
      '<button class="dbtn" data-action="set-hour">SET</button></div></div>'+
      prefToggle('sentinel_enabled',!!p3.sentinel_enabled,'Folder sentinel','Master switch for watched folders')+
      prefToggle('autonomy_enabled',!!p3.autonomy_enabled,'Autonomy','Background agent loop (supervised)')+
      prefToggle('dnd',!!p3.dnd,'Do not disturb','Silence unprompted speech')+
      prefToggle('desktop_control_enabled',!!p3.desktop_control_enabled,'Desktop control','Mouse/keyboard/window control')+
      '<div class="set-row"><div class="label">Auto summarize<small>'+(p3.auto_summarize?'On':'Off')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Toasts<small>'+(p3.notify_toasts?'On':'Off')+'</small></div></div>'+
      '</div>';
  }
  if(name==='about'){
    return '<div class="set-list">'+
      '<div class="set-row"><div class="label">Version<small>v7.0</small></div></div>'+
      '<div class="set-row"><div class="label">Model<small>'+esc(data.model||'--')+'</small></div></div>'+
      '<div class="set-row"><div class="label">Skills<small>'+esc(String((data.skills||[]).length))+'</small></div></div>'+
      '<div class="set-row"><div class="label">Voice<small>'+esc(data.voice&&data.voice.label?data.voice.label:'--')+'</small></div></div>'+
      '</div>';
  }
  if(name==='council'){renderCouncilPanel();return '<div style="color:var(--dim)">Loading…</div>';}
  if(name==='capture'){renderCapturePanel();return '<div style="color:var(--dim)">Loading…</div>';}
  if(name==='workspace'){renderWorkspacePanel();return '<div style="color:var(--dim)">Loading…</div>';}
  if(name==='clipboard'){renderClipboardPanel();return '<div style="color:var(--dim)">Loading…</div>';}
  if(name==='dream'){renderDreamPanel();return '<div style="color:var(--dim)">Loading…</div>';}
  return '<div style="color:var(--dim)">Panel: '+esc(name)+'</div>';
}

function savePref(key,value){
  return fetch('/api/prefs',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:key,value:value})}).then(function(r){return r.json();});
}

async function renderCouncilPanel(){
  const el = document.getElementById('panel-council');
  if(!el)return;
  let levels = [];
  try {
    const r = await fetch('/api/council/levels').then(r => r.json());
    levels = r.levels || [];
  } catch {}
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Council Levels</div>
      <div class="set-list">
        ${levels.map(l => `
          <div class="set-row">
            <div class="label">L${l.level} — ${l.name}
              <small>${l.models} model${l.models===1?'':'s'} · ~${l.timeout}s · ~$${l.cost_estimate.toFixed(3)}</small>
            </div>
            <div class="actions">
              <button data-test="${l.name}">TEST</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Quick Test</div>
      <div style="display:flex;gap:8px">
        <input type="text" id="council-test-q" placeholder="Ask a question..."
               style="flex:1;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:8px 10px;border-radius:3px;outline:none">
        <button id="council-test-go" class="dbtn">RUN</button>
      </div>
      <div id="council-test-result" style="margin-top:10px;font-size:10px"></div>
    </div>
  `;
  el.querySelectorAll('[data-test]').forEach(b => {
    b.addEventListener('click', async () => {
      const name = b.dataset.test;
      addLog(`Testing ${name}...`, 'system');
      try {
        const r = await fetch('/api/council/run', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({question: 'What is 2+2?', level: name, confirm: true})
        }).then(r => r.json());
        addLog(r.ok ? `✓ ${name}: ${r.confidence}% conf in ${r.elapsed}s`
                    : `✗ ${name} failed`, r.ok ? 'system' : 'warn');
      } catch (e){ addLog(`✗ ${name}: ${e.message}`, 'warn'); }
    });
  });
  const inp = document.getElementById('council-test-q');
  const go = document.getElementById('council-test-go');
  if (go) go.addEventListener('click', async () => {
    const q = inp.value.trim();
    if (!q) return;
    const res = document.getElementById('council-test-result');
    res.innerHTML = '<span style="color:var(--dim)">Running council…</span>';
    try {
      const r = await fetch('/api/council/run', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({question: q, level: 'council'})
      }).then(r => r.json());
      res.innerHTML = r.ok
        ? `<div class="info-badge">${r.confidence}% confidence</div> <div class="info-badge dim">${r.ok_count}/${r.total_count} models · ${r.elapsed}s</div><div style="margin-top:8px;color:var(--text);white-space:pre-wrap">${r.answer}</div>`
        : `<span style="color:#ff5c7a">✗ ${r.error || 'failed'}</span>`;
    } catch (e){ res.innerHTML = `<span style="color:#ff5c7a">✗ ${e.message}</span>`; }
  });
}

async function renderCapturePanel(){
  const el = document.getElementById('panel-capture');
  if(!el)return;
  let contacts = [], reminders = [];
  try {
    contacts = (await fetch('/api/contacts').then(r => r.json())).contacts || [];
  } catch {}
  try {
    reminders = (await fetch('/api/reminders').then(r => r.json())).reminders || [];
  } catch {}
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Quick Capture</div>
      <div style="display:flex;gap:8px">
        <input type="text" id="capture-input" placeholder="remind me in 10 minutes to call Ali"
               style="flex:1;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:8px 10px;border-radius:3px;outline:none">
        <button id="capture-go" class="dbtn">CAPTURE</button>
      </div>
      <div id="capture-result" style="margin-top:8px;font-size:10px"></div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Contacts <span class="info-badge dim">${contacts.length}</span></div>
      <div class="set-list" style="max-height:150px;overflow:auto">
        ${contacts.length ? contacts.slice(0,20).map(c => `
          <div class="set-row">
            <div class="label">${c.name}<small>${c.phone || c.email || 'no contact info'}</small></div>
          </div>
        `).join('') : '<div class="empty-state">No contacts yet.</div>'}
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Reminders <span class="info-badge dim">${reminders.length}</span></div>
      <div class="set-list" style="max-height:150px;overflow:auto">
        ${reminders.length ? reminders.slice(0,20).map(r => `
          <div class="set-row">
            <div class="label">${r.text}<small>${r.due_at.slice(11,16)} · ${r.due_at.slice(0,10)}</small></div>
          </div>
        `).join('') : '<div class="empty-state">No reminders.</div>'}
      </div>
    </div>
  `;
  const inp = document.getElementById('capture-input');
  const go = document.getElementById('capture-go');
  if (go) go.addEventListener('click', async () => {
    const text = inp.value.trim();
    if (!text) return;
    const res = document.getElementById('capture-result');
    try {
      const r = await fetch('/api/capture', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({text})
      }).then(r => r.json());
      res.innerHTML = `<span style="color:${r.ok ? '#4ade80' : '#ff5c7a'}">${r.reply}</span>`;
      inp.value = '';
      if (r.ok) setTimeout(renderCapturePanel, 800);
    } catch (e){ res.innerHTML = `<span style="color:#ff5c7a">${e.message}</span>`; }
  });
}

async function renderWorkspacePanel(){
  const el = document.getElementById('panel-workspace');
  if(!el)return;
  let layouts = [], time = [], focus = {};
  try { layouts = (await fetch('/api/layouts').then(r => r.json())).layouts || []; } catch {}
  try { time = (await fetch('/api/time/summary?hours=24').then(r => r.json())).entries || []; } catch {}
  try { focus = await fetch('/api/focus/status').then(r => r.json()); } catch {}
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Focus Lock
        <span class="info-badge ${focus.active ? '' : 'dim'}">${focus.active ? 'ON until ' + (focus.until || '').slice(11,16) : 'off'}</span>
      </div>
      <div style="display:flex;gap:8px">
        <input type="number" id="focus-mins" value="60" min="5" max="480"
               style="width:80px;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:8px 10px;border-radius:3px;outline:none">
        <button id="focus-start" class="dbtn">START</button>
        <button id="focus-stop" class="dbtn">STOP</button>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Window Layouts</div>
      <div class="set-list" style="max-height:140px;overflow:auto">
        ${layouts.length ? layouts.map(l => `
          <div class="set-row">
            <div class="label">${l.name}</div>
            <div class="actions">
              <button data-restore="${l.name}">LOAD</button>
            </div>
          </div>
        `).join('') : '<div class="empty-state">No saved layouts.</div>'}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <input type="text" id="layout-name" placeholder="layout name"
               style="flex:1;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:8px 10px;border-radius:3px;outline:none">
        <button id="layout-save" class="dbtn">SAVE CURRENT</button>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Time Tracking (24h)</div>
      <div class="set-list" style="max-height:160px;overflow:auto">
        ${time.length ? time.slice(0,10).map(t => `
          <div class="set-row">
            <div class="label">${t.app}<small>${Math.round(t.seconds/60)} min</small></div>
          </div>
        `).join('') : '<div class="empty-state">No time entries yet.</div>'}
      </div>
    </div>
  `;
  const fs = document.getElementById('focus-start');
  const fx = document.getElementById('focus-stop');
  if (fs) fs.addEventListener('click', async () => {
    const m = parseInt(document.getElementById('focus-mins').value) || 60;
    await fetch('/api/focus/start', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({minutes: m}) });
    renderWorkspacePanel();
  });
  if (fx) fx.addEventListener('click', async () => {
    await fetch('/api/focus/stop', { method:'POST' });
    renderWorkspacePanel();
  });
  el.querySelectorAll('[data-restore]').forEach(b => {
    b.addEventListener('click', async () => {
      await fetch('/api/layouts/restore', { method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name: b.dataset.restore}) });
      addLog(`Restored layout: ${b.dataset.restore}`, 'system');
    });
  });
  const ls = document.getElementById('layout-save');
  if (ls) ls.addEventListener('click', async () => {
    const name = document.getElementById('layout-name').value.trim();
    if (!name) return;
    await fetch('/api/layouts/save', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name}) });
    renderWorkspacePanel();
  });
}

async function renderClipboardPanel(){
  const el = document.getElementById('panel-clipboard');
  if(!el)return;
  let items = [];
  try {
    items = (await fetch('/api/clipboard/recent').then(r => r.json())).items || [];
  } catch {}
  const types = {};
  items.forEach(i => { types[i.type] = (types[i.type] || 0) + 1; });
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Recent Clipboard</div>
      <div style="margin-bottom:10px">
        ${Object.entries(types).map(([k, v]) =>
          `<span class="info-badge dim">${k}: ${v}</span>`).join(' ')}
      </div>
      <div class="set-list" style="max-height:400px;overflow:auto">
        ${items.length ? items.slice().reverse().map(i => `
          <div class="set-row">
            <div class="label">[${i.type}] ${(i.preview || '').slice(0,80)}
              <small>${i.ts.slice(11,16)} · ${i.length} chars</small>
            </div>
          </div>
        `).join('') : '<div class="empty-state">Clipboard empty.</div>'}
      </div>
    </div>
  `;
}

async function renderDreamPanel(){
  const el = document.getElementById('panel-dream');
  if(!el)return;
  let status = {}, last = {};
  try { status = await fetch('/api/dream/status').then(r => r.json()); } catch {}
  try { last = await fetch('/api/dream/last').then(r => r.json()); } catch {}
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Dream Mode
        <span class="info-badge ${status.enabled ? '' : 'dim'}">${status.enabled ? 'enabled' : 'disabled'}</span>
      </div>
      <div class="set-list">
        <div class="set-row">
          <div class="label">Enabled
            <small>Run nightly autonomous routine</small>
          </div>
          <label class="toggle">
            <input type="checkbox" id="dream-enable" ${status.enabled ? 'checked' : ''}>
            <span class="slider"></span>
          </label>
        </div>
        <div class="set-row">
          <div class="label">Active window
            <small>Only runs during these hours</small>
          </div>
          <div style="display:flex;gap:6px;align-items:center">
            <input type="number" id="dream-start" min="0" max="23" value="${status.start_hour || 3}"
                   style="width:60px;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:6px 8px;border-radius:3px;outline:none">
            <span style="color:var(--dim)">→</span>
            <input type="number" id="dream-end" min="0" max="23" value="${status.end_hour || 5}"
                   style="width:60px;background:rgba(0,0,0,.4);border:1px solid var(--border);color:#fff;font-family:var(--mono);font-size:11px;padding:6px 8px;border-radius:3px;outline:none">
          </div>
        </div>
        <div class="set-row">
          <div class="label">Manual actions</div>
          <div class="actions">
            <button id="dream-dry">DRY RUN</button>
            <button id="dream-run">RUN NOW</button>
          </div>
        </div>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Last Report</div>
      ${last.started_at ? `
        <div style="font-size:10px;color:var(--dim)">
          ${last.started_at} · ${last.elapsed || 0}s
        </div>
        ${last.folders ? last.folders.map(f =>
          `<div style="font-size:10px;margin-top:6px">${f.folder}: ${f.moved} moved, ${f.skipped} skipped</div>`
        ).join('') : ''}
        ${last.day_summary ? `<div class="mini-code">${last.day_summary}</div>` : ''}
      ` : '<div class="empty-state">No reports yet.</div>'}
    </div>
  `;
  const en = document.getElementById('dream-enable');
  if (en) en.addEventListener('change', async (e) => {
    await savePref('dream_enabled', e.target.checked);
  });
  const ds = document.getElementById('dream-start');
  if (ds) ds.addEventListener('change', async (e) => {
    await savePref('dream_start_hour', parseInt(e.target.value));
  });
  const de = document.getElementById('dream-end');
  if (de) de.addEventListener('change', async (e) => {
    await savePref('dream_end_hour', parseInt(e.target.value));
  });
  const dd = document.getElementById('dream-dry');
  if (dd) dd.addEventListener('click', async () => {
    addLog('Dream dry run...', 'system');
    const r = await fetch('/api/dream/run', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({dry_run: true}) }).then(r => r.json());
    addLog(JSON.stringify(r).slice(0, 200), 'system');
  });
  const dr = document.getElementById('dream-run');
  if (dr) dr.addEventListener('click', async () => {
    addLog('Running Dream Mode...', 'system');
    const r = await fetch('/api/dream/run', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({dry_run: false}) }).then(r => r.json());
    addLog(JSON.stringify(r).slice(0, 200), 'system');
    renderDreamPanel();
  });
}

function openDrawer(){
  addCls('drawer-history','open');
  fetch('/api/history').then(function(r){return r.json();}).then(function(data){
    var body=$('drawer-body');if(!body)return;
    var sessions=data.sessions||data||[];
    if(!sessions.length){body.innerHTML='<div style="color:var(--dim);padding:20px">No history yet.</div>';return;}
    body.innerHTML=sessions.map(function(s){
      return '<div class="set-row" style="cursor:pointer" data-sid="'+esc(s.id||s.sid||'')+'">'+
        '<div class="label">'+esc(s.summary||s.id||'Session')+
        '<small>'+esc(s.date||s.timestamp||'')+'</small></div></div>';
    }).join('');
  }).catch(function(){
    var body=$('drawer-body');if(body)body.innerHTML='<div style="color:var(--red)">Failed to load</div>';
  });
}
function closeDrawer(){rmCls('drawer-history','open');}

/* ---------- DEV MODE (drawer: live files, endpoint calls, logs) ---------- */
var devPid=null,devOrig='';
function devToggle(force){
  var d=$('dev-drawer');if(!d)return;
  var open=(typeof force==='boolean')?force:!d.classList.contains('open');
  d.classList.toggle('open',open);
  if(open)devLoadFiles();
}
function devTab(name){
  document.querySelectorAll('#dev-drawer [data-devtab]').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-devtab')===name);});
  document.querySelectorAll('#dev-drawer [data-devpanel]').forEach(function(p){p.classList.toggle('hidden',p.getAttribute('data-devpanel')!==name);});
  if(name==='logs')devLogs();
}
async function devLoadFiles(){
  var sel=$('dev-file');if(!sel)return;
  try{
    var r=await fetch('/api/harness/files').then(function(x){return x.json();});
    var files=r.files||[];
    sel.innerHTML=files.map(function(f){return '<option>'+esc(f)+'</option>';}).join('');
    if(files.length)devRead();
  }catch(e){}
}
async function devRead(){
  var sel=$('dev-file'),ed=$('dev-editor');if(!sel||!ed||!sel.value)return;
  try{
    var r=await fetch('/api/harness/file?path='+encodeURIComponent(sel.value)).then(function(x){return x.json();});
    devOrig=r.content||'';ed.value=devOrig;
    $('dev-diff').textContent='';$('dev-apply').disabled=true;devPid=null;
  }catch(e){}
}
async function devPropose(){
  var sel=$('dev-file'),ed=$('dev-editor');if(!sel||!ed)return;
  if(!ed.value||ed.value===devOrig){$('dev-diff').textContent='No changes.';return;}
  try{
    var r=await fetch('/api/harness/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:sel.value,old:devOrig,new:ed.value,reason:$('dev-reason').value||'dev drawer edit'})}).then(function(x){return x.json();});
    if(r.error){$('dev-diff').textContent='✗ '+r.error;return;}
    devPid=r.id;$('dev-diff').textContent=r.diff||'(no diff)';$('dev-apply').disabled=false;
  }catch(e){$('dev-diff').textContent='✗ '+e.message;}
}
async function devApply(){
  if(!devPid)return;
  try{
    var r=await fetch('/api/harness/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:devPid})}).then(function(x){return x.json();});
    $('dev-diff').textContent=r.ok?('✓ applied, backup: '+(r.backup||'')):('✗ '+(r.error||'failed'));
    if(r.ok){devPid=null;$('dev-apply').disabled=true;devRead();}
  }catch(e){$('dev-diff').textContent='✗ '+e.message;}
}
async function devSend(){
  var m=$('dev-method').value,p=$('dev-path').value.trim()||'/api/skills',b=$('dev-body').value.trim();
  var out=$('dev-result');out.textContent='…';
  try{
    var opt={method:m,headers:{'Content-Type':'application/json'}};
    if(m==='POST')opt.body=b||'{}';
    var r=await fetch(p,opt);var t=await r.text();
    try{t=JSON.stringify(JSON.parse(t),null,1);}catch(e){}
    out.textContent=r.status+'\n'+t.slice(0,3000);
  }catch(e){out.textContent='✗ '+e.message;}
}
async function devLogs(){
  var f=$('dev-logfile').value,out=$('dev-logout');out.textContent='…';
  try{
    var r=await fetch('/api/logs/tail?file='+encodeURIComponent(f)+'&lines=120').then(function(x){return x.json();});
    out.textContent=(r.lines||[]).join('\n')||'(empty)';
    out.scrollTop=out.scrollHeight;
  }catch(e){out.textContent='✗ '+e.message;}
}
(function devWire(){
  var b=$('btn-dev');if(b)b.addEventListener('click',function(){devToggle();});
  var c=$('dev-close');if(c)c.addEventListener('click',function(){devToggle(false);});
  document.querySelectorAll('#dev-drawer [data-devtab]').forEach(function(t){t.addEventListener('click',function(){devTab(t.getAttribute('data-devtab'));});});
  var s=$('dev-file');if(s)s.addEventListener('change',devRead);
  var p=$('dev-propose');if(p)p.addEventListener('click',devPropose);
  var a=$('dev-apply');if(a)a.addEventListener('click',devApply);
  var se=$('dev-send');if(se)se.addEventListener('click',devSend);
  var l=$('dev-logs');if(l)l.addEventListener('click',devLogs);
})();

function updateCodeToggle(enabled){
  var btn=document.getElementById('code-toggle');
  if(!btn)return;
  btn.classList.toggle('on',!!enabled);
  btn.title=enabled
    ?'Code Mode is ON — full file + terminal control'
    :'Code Mode is OFF — click to enable';
}

async function openOpenCodeTab(tab,url){
  for(var i=0;i<60;i++){
    await new Promise(function(res){setTimeout(res,1000);});
    try{
      var resp=await fetch('/api/opencode/ready');
      if(resp.status===404)return 'stale';
      var st=await resp.json();
      if(st&&st.ready){
        if(tab&&!tab.closed){tab.location.href=url;}
        else{window.open(url,'_blank','noopener');}
        addLog('OpenCode web opened in new tab.','system');
        return true;
      }
    }catch(e){}
  }
  return false;
}

async function toggleCodeMode(){
  try{
    var cur=await fetch('/api/prefs').then(function(r){return r.json();});
    var was=!!cur.prefs?.code_mode_enabled;
    var next=!was;
    if(next){
      var ok=confirm(
        'Enable Code Mode?\n\n'+
        '\u2022 Opens a terminal running `opencode web`\n'+
        '\u2022 Opens the OpenCode web UI in a new tab\n'+
        '\u2022 JARVIS gains coding + file + terminal access');
      if(!ok)return;
      var tab=null;
      try{tab=window.open('about:blank','_blank');}catch(e){tab=null;}
      await fetch('/api/prefs',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key:'code_mode_enabled',value:next})
      });
      addLog('Opening OpenCode terminal\u2026','system');
      var resp=await fetch('/api/opencode/web',{method:'POST'});
      if(resp.status===404){
        if(tab)tab.close();
        addLog('JARVIS server is outdated \u2014 restart it (close the window, double-click start.bat), then press CODE again.','warn');
        updateCodeToggle(next);
        return;
      }
      var r={};try{r=await resp.json();}catch(e){}
      if(!r.ok&&!r.url){
        if(tab)tab.close();
        addLog('OpenCode launch failed: '+(r.error||r.detail||'unknown'),
               'warn');
        updateCodeToggle(next);
        return;
      }
      addLog('Waiting for OpenCode web\u2026','system');
      var opened=await openOpenCodeTab(tab,r.url);
      if(opened==='stale'){
        if(tab)tab.close();
        addLog('JARVIS server is outdated \u2014 restart it (close the window, double-click start.bat), then press CODE again.','warn');
      }else if(!opened){
        if(tab)tab.close();
        addLog('Timed out waiting for '+r.url+' \u2014 open it manually.',
               'warn');
      }
    }else{
      await fetch('/api/prefs',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key:'code_mode_enabled',value:next})
      });
      await fetch('/api/opencode/stop',{method:'POST'});
      addLog('Code Mode off. (Terminal server left running \u2014 close its window to stop it.)','system');
    }
    updateCodeToggle(next);
  }catch(e){console.warn('toggleCodeMode',e);}
}

async function loadCodeMode(){
  try{
    var r=await fetch('/api/prefs').then(function(r){return r.json();});
    var enabled=!!r.prefs?.code_mode_enabled;
    updateCodeToggle(enabled);
    if(enabled){
      fetch('/api/opencode/start',{method:'POST'}).catch(function(){});
    }
  }catch(e){}
}

async function boot(){
  addLog('Initializing JARVIS kernel...','system');
  initCanvas();
  await loadPrefs();
  await loadCodeMode();
  await loadInfo();
  await loadMemory();
  await loadModels();
  await loadVoices();
  await loadMoods();
  startStatsLoop();startUptime();startClock();initWaveform();
  addLog('JARVIS online. Type / for commands.','system');
  setTimeout(function(){setState(STATE.IDLE);},1200);
  fetch('/api/greeting').then(function(r){return r.json();}).then(function(d){
    if(d.greeting)addLog(d.greeting,'bot');
  }).catch(function(){});
}

/* Event listeners */
document.addEventListener('DOMContentLoaded',function(){
  on('cmd','keydown',function(e){
    if(e.key==='Enter'){
      e.preventDefault();
      var val=($('cmd')?$('cmd').value:'').trim();
      if(!val)return;
      var sm=$('slash-menu');
      if(sm&&sm.classList.contains('open'))pickSlash();
      else if(val.charAt(0)==='/')handleSlash(val);
      else sendCommand(val);
      return;
    }
    if(e.key==='ArrowDown'){e.preventDefault();navSlash(1);return;}
    if(e.key==='ArrowUp'){e.preventDefault();navSlash(-1);return;}
    if(e.key==='Escape'){closeSlash();}
  });
  on('cmd','input',function(){
    var val=$('cmd')?$('cmd').value:'';
    if(val.charAt(0)==='/')openSlash(val);else closeSlash();
  });
  on('btn-mic','click',function(){if(micActive)stopRecording();else startRecording();});
  document.addEventListener('keydown',function(e){
    if(e.ctrlKey&&e.key==='m'){e.preventDefault();if(!micActive)startRecording();}
  });
  document.addEventListener('keyup',function(e){
    if(e.ctrlKey&&e.key==='m'){e.preventDefault();if(micActive)stopRecording();}
  });
  on('btn-voice','click',toggleMute);
  on('btn-stop','click',stopSpeak);
  on('btn-clear','click',function(){var l=$('log');if(l)l.innerHTML='';addLog('Log cleared.','system');});
  on('btn-settings','click',openSettings);
  on('btn-modal-close','click',closeSettings);
  on('modal-settings','click',function(e){if(e.target&&e.target.id==='modal-settings')closeSettings();});
  document.querySelectorAll('.tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      var t=tab.getAttribute('data-tab');if(t)loadTab(t);
    });
  });
  on('btn-history','click',openDrawer);
  on('btn-drawer-close','click',closeDrawer);
  on('drawer-history','click',function(e){if(e.target&&e.target.id==='drawer-history')closeDrawer();});
  on('think-toggle','click',function(e){e.stopPropagation();if($('thinkpanel'))$('thinkpanel').classList.toggle('expanded');});
  on('think-head','click',function(){$('thinkpanel')&&$('thinkpanel').classList.toggle('expanded');});

  var codeBtn=document.getElementById('code-toggle');
  if(codeBtn)codeBtn.addEventListener('click',toggleCodeMode);

  document.querySelectorAll('.side-block').forEach(function(block){
    block.addEventListener('mousemove',function(e){
      var r=block.getBoundingClientRect();
      block.style.setProperty('--mx',((e.clientX-r.left)/r.width*100)+'%');
      block.style.setProperty('--my',((e.clientY-r.top)/r.height*100)+'%');
    });
  });

  document.addEventListener('click',function(e){
    var target=e.target;
    if(target.getAttribute&&target.getAttribute('data-action')==='select-model'){
      switchModel(target.getAttribute('data-model'));
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='select-voice'){
      var key=target.getAttribute('data-key');
      fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key:key})}).then(function(r){return r.json();}).then(function(d){
        if(d.ok&&d.voice){setText('side-voice',d.voice.label||key);addLog('Voice: '+key,'system');}
      }).catch(function(){});
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='toggle-skill'){
      var sname=target.getAttribute('data-name');
      var senabled=target.getAttribute('data-enabled')==='true';
      fetch('/api/skill',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name:sname,enabled:senabled})}).then(function(){loadTab('skills');}).catch(function(){});
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='select-personality'){
      var pname=target.getAttribute('data-name');
      fetch('/api/personality/preset',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name:pname})}).then(function(){loadTab('personality');}).catch(function(){});
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='set-pref'){
      var pkey=target.getAttribute('data-key');
      var pval=target.getAttribute('data-value');
      var val=(pval==='true')?true:((pval==='false')?false:pval);
      (function(){
        var t=document.querySelector('.tab.active');
        var tab=t?t.getAttribute('data-tab'):'general';
        fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({key:pkey,value:val})}).then(function(){loadTab(tab);}).catch(function(){});
      })();
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='cycle-duck'){
      var cur=parseFloat(target.getAttribute('data-level'))||0.25;
      var levels=[0.1,0.25,0.5];
      var next=levels[0];
      for(var i=0;i<levels.length;i++){if(levels[i]>cur+0.001){next=levels[i];break;}}
      fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key:'duck_level',value:next})}).then(function(){loadTab('audio');}).catch(function(){});
    }
    if(target.getAttribute&&target.getAttribute('data-action')==='set-hour'){
      var inp=document.getElementById('input-briefing-hour');
      var h=inp?parseInt(inp.value,10):8;
      if(isNaN(h))h=8;h=Math.max(0,Math.min(23,h));
      fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key:'briefing_hour',value:h})}).then(function(){
          fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({key:'briefings_enabled',value:true})}).then(function(){loadTab('general');}).catch(function(){});
        }).catch(function(){});
    }
  });

  boot();
});

})();
