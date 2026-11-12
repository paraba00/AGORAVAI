// Verifica as etapas de interface sem enviar dados à rede.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

const python = fs.readFileSync(path.join(__dirname, '..', 'ouvidoria.py'), 'utf8');
const match = python.match(/['"]app\.js['"]:\s*r?(['"]{3})([\s\S]*?)\1/);
assert(match);
const source = match[2].slice(0, match[2].lastIndexOf('if (DEMO) {'));
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value:'', textContent:'', innerHTML:'', hidden:false, disabled:false, checked:false, open:false,
    classList:{toggle(){}}, setAttribute(){}, focus(){}, replaceChildren(){}, append(){},
    showModal(){this.open=true;},
    close(){this.open=false;this.onclose?.();},
    reset(){ for(const name of ['email','password','confirmPassword']) element(name).value=''; },
  });
  return elements.get(id);
}
class FakeFormData {
  constructor(form){ this.data=form.data || {}; }
  *[Symbol.iterator](){yield* Object.entries(this.data);}
}
const context=vm.createContext({
  document:{getElementById:element,createElement:()=>({}),querySelectorAll:selector=>selector==='dialog[open]'?[...elements.values()].filter(e=>e.open):[]},
  location:{protocol:'http:'},crypto:webcrypto,FormData:FakeFormData,setTimeout:()=>1,clearTimeout(){},
});
vm.runInContext(source,context);
vm.runInContext(`
let requests=[]; let entered=0;
api=async (url,data)=>{
 requests.push({url,data});
 if(url==='/api/register')return {recovery_code:'CR-TESTE-CADASTRO'};
 if(url==='/api/recover')return {recovery_code:'CR-NOVO-CODIGO'};
 if(url==='/api/identity')return {email:'titular@camporeal.edu.br'};
 if(url==='/api/tickets')return {id:'CR-TESTE'};
 return {ok:true};
};
loggedIn=async()=>{entered++;};
`,context);
const tick=()=>new Promise(setImmediate);
const event=(form)=>({preventDefault(){},currentTarget:form,submitter:{disabled:false}});

(async()=>{
  vm.runInContext('setRegisterMode(true)',context);
  element('email').value='aluno@camporeal.edu.br';
  element('password').value='SenhaTeste123!';element('confirmPassword').value='SenhaTeste123!';
  element('loginForm').onsubmit(event());await tick();
  assert.equal(vm.runInContext('entered',context),0);
  assert.equal(element('recoveryCodeDialog').open,true);
  assert.equal(element('recoveryCodeText').textContent,'CR-TESTE-CADASTRO');
  assert.equal(element('closeRecoveryCode').disabled,true);
  element('savedRecoveryCode').checked=true;element('savedRecoveryCode').onchange();element('closeRecoveryCode').onclick();
  assert.equal(element('recoveryCodeText').textContent,'');

  element('forgotPassword').onclick();assert.equal(element('recoverDialog').open,true);
  element('recoverEmail').value='aluno@camporeal.edu.br';element('recoverCode').value='CR-CODIGO';
  element('recoverPassword').value='NovaSenha123!';element('recoverConfirm').value='NovaSenha123!';
  element('recoverForm').onsubmit(event());await tick();
  assert.equal(vm.runInContext('requests.at(-1).url',context),'/api/recover');
  assert.equal(element('recoveryCodeText').textContent,'CR-NOVO-CODIGO');
  assert.equal(vm.runInContext('user',context),null);
  element('savedRecoveryCode').checked=true;element('closeRecoveryCode').onclick();

  vm.runInContext(`
  user={role:'diretor'};
  tickets=[{id:'CR-TESTE',subject:'Relato',kind:'Reclamação',sector:'Geral',body:'Relato de exemplo.',created:1,anonymous:1,status:'Recebida',messages:[]}];
  let actions=[];action=(label,handler)=>actions.push({label,handler});
  showDetail('CR-TESTE');
  `,context);
  const before=vm.runInContext('requests.length',context);
  await vm.runInContext('actions.find(a=>a.label.includes("Justificar")).handler()',context);
  assert.equal(vm.runInContext('requests.length',context),before);
  assert.equal(element('identityReasonDialog').open,true);
  element('identityReason').value='Consulta necessária para encaminhar corretamente este atendimento.';
  vm.runInContext('refresh=async()=>{};',context);
  element('identityReasonForm').onsubmit(event());await tick();
  assert.equal(vm.runInContext('requests.at(-1).url',context),'/api/identity');
  assert(vm.runInContext('requests.at(-1).data.reason.length',context)>=20);

  vm.runInContext('showDetail=()=>{};user={role:"aluno"};',context);
  const form=element('ticketForm');
  form.data={subject:'Relato para revisão',body:'Conteúdo suficientemente detalhado.',kind:'Reclamação',sector:'Infraestrutura'};
  element('anonymous').checked=true;
  const initial=vm.runInContext('requests.length',context);
  form.onsubmit(event(form));
  assert.equal(element('confirmTicketDialog').open,true);
  assert.equal(vm.runInContext('requests.length',context),initial);
  element('backToTicket').onclick();
  assert.equal(vm.runInContext('pendingTicket',context),null);
  assert.equal(vm.runInContext('requests.length',context),initial);
  form.onsubmit(event(form));
  element('confirmTicketForm').onsubmit(event());await tick();
  assert.equal(vm.runInContext('requests.at(-1).url',context),'/api/tickets');
  assert.equal(vm.runInContext('requests.at(-1).data.confirmed',context),true);
  assert.equal(vm.runInContext('pendingTicket',context),null);
  assert(element('toast').textContent.includes('Envio confirmado'));
  console.log('Interface validada: código único, recuperação, justificativa e revisão antes do envio.');
})().catch(error=>{console.error(error);process.exitCode=1;});
