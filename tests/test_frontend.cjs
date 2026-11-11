// Teste opcional, com Node.js, do fluxo após o cadastro. Não usa navegador nem rede.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const python = fs.readFileSync(path.join(__dirname, '..', 'ouvidoria.py'), 'utf8');
const match = python.match(/['"]app\.js['"]:\s*r?(['"]{3})([\s\S]*?)\1/);
assert(match, 'Não foi possível encontrar o JavaScript embutido.');
const script = match[2].slice(0, match[2].lastIndexOf('if (DEMO) {'));
const elements = new Map();

function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      value: '',
      hidden: false,
      disabled: false,
      classList: { toggle() {} },
      setAttribute() {},
      focus() {},
      replaceChildren() {},
      reset() {
        for (const name of ['email', 'password', 'confirmPassword']) element(name).value = '';
      },
    });
  }
  return elements.get(id);
}

const context = vm.createContext({
  document: { getElementById: element, querySelectorAll: () => [] },
  location: { protocol: 'http:' },
  setTimeout: () => 1,
  clearTimeout() {},
});
vm.runInContext(script, context);
vm.runInContext(`
  let requests = [];
  let entered = 0;
  api = async (url) => {
    requests.push(url);
    return url === '/api/me' ? {email:'teste@camporeal.edu.br',role:'aluno'} : {ok:true};
  };
  loggedIn = async () => { entered += 1; };
`, context);

async function submit() {
  element('email').value = 'teste@camporeal.edu.br';
  element('password').value = 'SenhaTeste123!';
  element('confirmPassword').value = 'SenhaTeste123!';
  element('loginForm').onsubmit({ preventDefault() {} });
  await new Promise(setImmediate);
}

(async () => {
  vm.runInContext('setRegisterMode(true)', context);
  await submit();
  assert.equal(vm.runInContext('JSON.stringify(requests)', context), '["/api/register"]');
  assert.equal(vm.runInContext('entered', context), 0);
  assert.equal(vm.runInContext('user', context), null);
  assert.equal(vm.runInContext('registerMode', context), false);
  assert.equal(element('email').value, '');
  assert.equal(element('password').value, '');
  assert(element('toast').textContent.includes('Conta criada'));

  await submit();
  assert.equal(vm.runInContext('JSON.stringify(requests)', context), '["/api/register","/api/login","/api/me"]');
  assert.equal(vm.runInContext('entered', context), 1);
  console.log('Cadastro limpa os campos e não entra; o acesso só acontece após o segundo envio.');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
