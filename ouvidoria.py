"""OUVIDORIA CAMPO REAL — ACESSO SIMPLES COM E-MAIL E SENHA
Requer Python 3.10 ou superior; nenhuma biblioteca extra.
Iniciar: python ouvidoria.py
Gerenciar contas ou redefinir senhas: python ouvidoria.py --contas
Demonstração fictícia: python ouvidoria.py --demo
Endereço padrão: http://localhost:8000
Não é necessário configurar SMTP, Gmail ou arquivo .env.
O cadastro público é sempre de aluno. Supervisor e diretor são criados no menu local.
O domínio institucional é conferido; a titularidade do e-mail não é comprovada.
Contas com histórico da versão antiga devem ser criadas pelo responsável no menu local.
"""
import hashlib  # Calcula hashes dos códigos e das sessões.
import hmac  # Compara hashes sem revelar diferenças de tempo.
import json  # Converte dados entre JSON e objetos Python.
import os  # Lê configurações do ambiente.
import re  # Valida o endereço institucional completo.
import secrets  # Gera códigos, protocolos e sessões imprevisíveis.
import sqlite3  # Persiste os registros em banco de dados local.
import time  # Controla expiração e limites de acesso.
from contextlib import contextmanager  # Garante fechamento das conexões ao banco.
from http.cookies import SimpleCookie  # Interpreta o cookie de sessão.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # Atende HTTP.
from pathlib import Path  # Trabalha com caminhos de arquivos.
from urllib.parse import urlparse  # Separa o caminho da URL.


import getpass  # Lê senhas no terminal sem exibir os caracteres.

# Conteúdos do navegador embutidos no programa Python.
ASSETS = {
    # Conteúdo comentado de app.js.
    'app.js': r''''use strict'; // Evita variáveis criadas por engano.
const $ = id => document.getElementById(id); // Facilita localizar elementos pelo identificador.
const DEMO = location.protocol === 'file:'; // Ativa o demonstrador somente quando o arquivo é aberto diretamente.
const statuses = ['Recebida', 'Em análise', 'Respondida', 'Resolvida']; // Define a ordem das situações.
const demoEmails = {aluno:'aluno.exemplo@camporeal.edu.br',supervisor:'supervisor.exemplo@camporeal.edu.br',diretor:'diretor.exemplo@camporeal.edu.br'}; // Contas fictícias, sem validade no servidor.
let user = null, tickets = [], activeId = null, registerMode = false, archiveView = false, toastTimer; // Guarda o estado da tela, sem armazenar a sessão real.
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])); // Impede que relatos sejam interpretados como HTML.
const date = value => new Date(value * 1000).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo',dateStyle:'short',timeStyle:'short'}); // Mostra datas no horário de Brasília.
const badge = status => `<span class="badge ${['','analysis','answered','solved'][statuses.indexOf(status)] || ''}">${escapeHTML(status)}</span>`; // Gera o marcador de situação.
function notify(message, error = false) { // Exibe um retorno acessível sobre uma ação.
  $('toast').textContent = (error ? 'Atenção: ' : '') + message; // Usa texto simples para evitar injeção de HTML.
  $('toast').className = 'toast' + (error ? ' error' : ''); // Diferencia erros visualmente.
  $('toast').hidden = false; // Mostra a notificação.
  clearTimeout(toastTimer); // Reinicia o tempo quando chega outra mensagem.
  toastTimer = setTimeout(() => $('toast').hidden = true, 6500); // Oculta depois de permitir a leitura.
}
async function busy(button, task) { // Evita envio repetido e apresenta erros.
  button.disabled = true; // Bloqueia o controle enquanto aguarda a resposta.
  try { await task(); } catch (error) { notify(error.message || 'Não foi possível concluir.', true); } // Exibe a falha com clareza.
  finally { button.disabled = false; } // Restaura o botão mesmo após erros.
}
function demoData() { // Carrega apenas registros fictícios do navegador.
  try { return JSON.parse(localStorage.getItem('camporeal-demo-v1')) || seedDemo(); } // Recupera o exemplo salvo.
  catch { return seedDemo(); } // Recria os exemplos se o armazenamento estiver indisponível.
}
function saveDemo(data) { // Salva o estado da demonstração sem simular segurança real.
  try { localStorage.setItem('camporeal-demo-v1', JSON.stringify(data)); } // Persiste somente no navegador local.
  catch { throw new Error('O navegador bloqueou o armazenamento local. Abra o arquivo em outro navegador.'); } // Informa restrições do navegador.
}
function seedDemo() { // Cria manifestações fictícias para explorar as telas.
  const now = Date.now() / 1000; // Usa o horário da abertura do demonstrador.
  return [ // Define exemplos de atendimento.
    {id:'CR-DEMO-001',email:demoEmails.aluno,anonymous:true,kind:'Reclamação',subject:'Iluminação no estacionamento',sector:'Infraestrutura',body:'A iluminação perto da saída do estacionamento precisa de manutenção. Seria possível verificar as lâmpadas desse trecho?',status:'Respondida',created:now-172800,messages:[{author:'Ouvidoria Campo Real',body:'Exemplo de resposta: encaminhamos o pedido à manutenção. Você pode acompanhar e nos informar se o problema foi resolvido.',created:now-86400}]}, // Exemplo anônimo com resposta.
    {id:'CR-DEMO-002',email:demoEmails.aluno,anonymous:false,kind:'Sugestão',subject:'Mais horários para grupos de estudo',sector:'Ensino e aprendizagem',body:'Gostaria de sugerir mais horários para utilização das salas por grupos de estudo durante o período de provas.',status:'Em análise',created:now-86400,messages:[]}, // Exemplo identificado em análise.
    {id:'CR-DEMO-003',email:'outro.aluno@camporeal.edu.br',anonymous:true,kind:'Elogio',subject:'Atendimento da biblioteca',sector:'Geral',body:'Quero registrar um elogio pelo apoio da equipe da biblioteca na pesquisa dos materiais para as atividades.',status:'Recebida',created:now-3600,messages:[]} // Exemplo que aparece somente para a equipe.
  ];
}
async function demoAPI(path, data) { // Reproduz o fluxo com dados locais; não substitui a API protegida.
  if (path === '/api/me') { if (!user) throw new Error('Entre para continuar.'); return user; } // Retorna o perfil fictício atual.
  if (path === '/api/logout') { user = null; return {ok:true}; } // Encerra a demonstração da sessão.
  const list = demoData().map(t => ({...t, archived: t.archived ?? (t.status === 'Resolvida')})); // Recupera os protocolos locais.
  if (path === '/api/tickets' && !data) return list.filter(t => user.role !== 'aluno' || t.email === user.email).map(t => ({...t,identity:!t.anonymous || user.role === 'aluno' ? t.email : null,email:undefined})); // Oculta dados no fluxo de demonstração.
  if (path === '/api/tickets') { // Registra um exemplo de manifestação.
    const item = {...data,id:'CR-DEMO-' + Math.random().toString(16).slice(2,10).toUpperCase(),email:user.email,created:Date.now()/1000,status:'Recebida',archived:false,messages:[]}; // Associa a conta fictícia.
    list.unshift(item); saveDemo(list); return {id:item.id}; // Persiste o exemplo.
  }
  const item = list.find(t => t.id === data.id); // Localiza o protocolo selecionado.
  if (!item) throw new Error('Protocolo não encontrado.'); // Trata exemplos removidos.
  if (path === '/api/identity') { if(user.role !== 'diretor') throw new Error('Somente o diretor pode consultar.'); return {email:item.email}; } // Demonstra a consulta restrita.
  if (path === '/api/reply') { item.archived = false; item.messages.push({author:user.role === 'aluno' ? 'Aluno' : 'Ouvidoria Campo Real',body:data.body,created:Date.now()/1000}); item.status = user.role === 'aluno' ? 'Em análise' : 'Respondida'; } // Acrescenta uma mensagem fictícia.
  if (path === '/api/status') { item.archived = data.status === 'Resolvida'; item.status = data.status; item.messages.push({author:'Sistema',body:'Situação alterada para ' + data.status.toLowerCase() + '.',created:Date.now()/1000}); } // Registra o andamento do exemplo.
  if (path === '/api/archive') { if (user.role === 'aluno') throw new Error('Somente a equipe pode arquivar.'); item.archived = data.archived; item.status = data.archived ? 'Resolvida' : 'Em análise'; item.messages.push({author:'Sistema',body:data.archived ? 'Manifestação resolvida e arquivada pelo atendimento.' : 'Manifestação desarquivada para nova análise.',created:Date.now()/1000}); } // Demonstra o arquivo compartilhado da equipe.
  saveDemo(list); return {ok:true}; // Confirma a alteração local.
}
async function api(path, data) { // Centraliza a comunicação com o servidor real ou a prévia.
  if (DEMO) return demoAPI(path, data); // Mantém a simulação separada da aplicação real.
  const response = await fetch(path, {method:data ? 'POST' : 'GET',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':user?.csrf || ''},body:data ? JSON.stringify(data) : undefined}); // Envia sessão por cookie e token CSRF.
  const result = await response.json(); // Interpreta a resposta.
  if (!response.ok) { // Trata os erros antes de atualizar a interface.
    if (response.status === 401) loggedOut(); // Volta ao acesso quando a sessão vence.
    throw new Error(result.error || 'Não foi possível concluir a solicitação.'); // Exibe o erro retornado pelo servidor.
  }
  return result; // Entrega os dados autorizados.
}
function loggedOut() { // Restaura a apresentação pública.
  user = null; tickets = []; activeId = null; archiveView = false; resetLogin(); $('sectorFilter').value = ''; $('search').value = ''; $('statusFilter').value = ''; // Descarta dados privados da memória da tela.
  $('workspace').hidden = true; $('welcome').hidden = false; $('how').hidden = false; // Mostra a entrada.
  $('account').replaceChildren(); $('ticketList').replaceChildren(); $('detailContent').replaceChildren(); // Limpa os dados exibidos.
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()); // Fecha janelas privadas.
}
async function loggedIn() { // Monta a área do perfil autenticado.
  $('welcome').hidden = true; $('how').hidden = true; $('workspace').hidden = false; // Alterna para o painel.
  const student = user.role === 'aluno'; // Identifica a experiência do aluno.
  $('panelLabel').textContent = student ? 'ÁREA DO ALUNO' : 'GESTÃO DA OUVIDORIA'; // Nomeia a área atual.
  $('panelTitle').textContent = student ? 'Minhas manifestações' : 'Central de manifestações'; // Adapta o título ao perfil.
  $('panelDescription').textContent = student ? 'Acompanhe cada conversa, do primeiro contato à solução.' : 'Acolha os relatos, acompanhe os protocolos e responda aos alunos.'; // Explica a tarefa principal.
  archiveView = false; $('archivedTab').hidden = student; $('sectorFilterField').hidden = student; $('sectorFilter').value = ''; $('search').value = ''; $('statusFilter').value = ''; // Limpa filtros ao trocar de perfil e mostra os controles somente à equipe.
  $('newTicket').hidden = !student; // Restringe a criação ao perfil de aluno na interface.
  $('account').innerHTML = `<strong>${escapeHTML(user.role)}</strong><span>${escapeHTML(user.email)}</span> <button class="text-button" id="logout" type="button">Sair</button>`; // Mostra os dados da própria sessão.
  $('logout').onclick = event => busy(event.currentTarget, async () => {await api('/api/logout', {}); loggedOut();}); // Invalida a sessão no servidor.
  await refresh(); // Busca as manifestações autorizadas.
}
async function refresh() { // Atualiza os protocolos e os indicadores.
  tickets = await api('/api/tickets'); // Recebe apenas registros permitidos pelo servidor.
  $('stats').innerHTML = [['Total de manifestações',tickets.length],['Em atendimento',tickets.filter(t => ['Recebida','Em análise'].includes(t.status)).length],['Respondidas',tickets.filter(t => t.status === 'Respondida').length],['Resolvidas',tickets.filter(t => t.status === 'Resolvida').length]].map(([label,count]) => `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`).join(''); // Resume os registros recebidos.
  const selectedSector = $('sectorFilter').value; // Mantém o filtro ativo após responder ou arquivar.
  const sectors = [...new Set([...Array.from($('sector').options, option => option.value), ...tickets.map(t => t.sector)])].sort((a,b) => a.localeCompare(b, 'pt-BR')); // Inclui as áreas do formulário e áreas antigas do banco.
  $('sectorFilter').innerHTML = '<option value="">Todas as áreas</option>' + sectors.map(sector => `<option value="${escapeHTML(sector)}">${escapeHTML(sector)}</option>`).join(''); // Escapa os textos antes de montar as opções.
  $('sectorFilter').value = selectedSector; // Preserva a área escolhida nas duas abas.
  renderList(); // Reaplica os filtros atuais.
}
function renderList() { // Exibe resultados de busca e situação.
  const search = $('search').value.trim().toLocaleLowerCase('pt-BR'); // Normaliza a consulta digitada.
  const staff = user?.role !== 'aluno'; // O aluno continua consultando todos os próprios protocolos, inclusive resolvidos.
  $('allTab').classList.toggle('active', !archiveView); $('archivedTab').classList.toggle('active', archiveView); // Destaca a aba atual.
  $('allTab').setAttribute('aria-pressed', String(!archiveView)); $('archivedTab').setAttribute('aria-pressed', String(archiveView)); // Anuncia a escolha a leitores de tela.
  const filtered = tickets.filter(t => (!staff || Boolean(t.archived) === archiveView) && (!staff || !$('sectorFilter').value || t.sector === $('sectorFilter').value) && (!$('statusFilter').value || t.status === $('statusFilter').value) && (t.subject + ' ' + t.id).toLocaleLowerCase('pt-BR').includes(search)); // Combina aba, área, situação e busca sem alterar permissões de acesso.
  $('ticketList').innerHTML = filtered.length ? filtered.map(t => `<button type="button" class="ticket-card" data-ticket="${escapeHTML(t.id)}"><div><span class="protocol">${escapeHTML(t.id)}</span><h3>${escapeHTML(t.subject)}</h3><span class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${t.anonymous ? 'Identidade restrita ao diretor' : 'Manifestação identificada'}</span></div>${badge(t.status)}${t.archived ? '<span class="badge">Arquivada</span>' : ''}</button>`).join('') : `<div class="empty"><h3>${archiveView ? 'Nenhuma manifestação arquivada nesta busca.' : 'Nenhuma manifestação por aqui.'}</h3><p>Ajuste os filtros${staff ? ' ou consulte a outra aba' : ' ou crie uma nova manifestação'}.</p></div>`; // Exibe cartões ou um estado vazio.
}
function showDetail(id) { // Abre o histórico do protocolo selecionado.
  activeId = id; // Guarda o alvo das próximas ações.
  const t = tickets.find(item => item.id === id); // Busca somente na lista autorizada recebida.
  if (!t) return; // Evita abrir um protocolo ausente.
  $('detailProtocol').textContent = t.id; $('detailSubject').textContent = t.subject; // Usa texto simples para protocolo e título.
  const identity = t.anonymous ? 'Identidade restrita ao diretor' : `Identificado: ${t.identity || ''}`; // Não tenta deduzir o autor anônimo.
  $('detailContent').innerHTML = `${badge(t.status)}${t.archived ? ' <span class="badge">Arquivada</span>' : ''}<p class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${escapeHTML(identity)}</p><p class="detail-body">${escapeHTML(t.body)}</p><h3>Histórico de atendimento</h3>${t.messages.length ? t.messages.map(m => `<div class="message ${m.author === 'Ouvidoria Campo Real' ? 'staff' : ''}"><strong>${escapeHTML(m.author)}</strong><span class="meta"> · ${date(m.created)}</span><p>${escapeHTML(m.body)}</p></div>`).join('') : '<p class="form-note">Aguardando atendimento. As respostas aparecerão aqui.</p>'}`; // Exibe relatos como texto escapado.
  $('detailActions').replaceChildren(); // Limpa ações e identidades reveladas em aberturas anteriores.
  if (user.role === 'aluno') { // Mostra as ações de confirmação do aluno.
    action(t.status === 'Resolvida' ? 'Pedir nova análise' : '✓ Foi resolvido', () => updateStatus(t.status === 'Resolvida' ? 'Em análise' : 'Resolvida')); // Permite encerrar ou reabrir o atendimento.
    if (t.status === 'Respondida') action('Ainda não foi resolvido', () => updateStatus('Em análise')); // Permite contestar a solução proposta.
  } else { // Mostra as ações de atendimento.
    if (t.archived) action('Desarquivar e retomar atendimento', () => updateArchive(false)); // Retoma sem perder nenhuma mensagem.
    else { action('Marcar em análise', () => updateStatus('Em análise')); action('Resolver e arquivar', () => updateArchive(true)); } // A conclusão pela equipe arquiva automaticamente. // Atualiza o andamento institucional.
    if (user.role === 'diretor' && t.anonymous) action('Consultar autoria restrita', async () => { // Exige consulta explícita do diretor.
      const result = await api('/api/identity', {id:activeId}); // O servidor autoriza e registra a consulta.
      const note = document.createElement('p'); note.className = 'form-note'; note.textContent = `Autoria: ${result.email}. Consulta registrada${DEMO ? ' apenas ilustrativa na demonstração' : ' na auditoria do servidor'}.`; // Mostra a identidade sem inserir HTML.
      $('detailActions').append(note); // Mantém a informação dentro da janela atual.
    });
  }
  $('replyForm').hidden = user.role !== 'aluno' && Boolean(t.archived); // A equipe retoma antes de enviar outra resposta; o aluno ainda pode complementar.
  $('replyForm').reset(); // Remove rascunhos de outros protocolos.
  if (!$('detailDialog').open) $('detailDialog').showModal(); // Usa uma janela com foco controlado pelo navegador.
}
function action(label, handler) { // Cria um botão de ação sem eventos HTML embutidos.
  const button = document.createElement('button'); button.type = 'button'; button.className = 'button'; button.textContent = label; // Define aparência e rótulo.
  button.onclick = () => busy(button, handler); $('detailActions').append(button); // Trata erros e cliques repetidos.
}
async function updateStatus(status) { // Solicita a alteração autorizada de situação.
  await api('/api/status', {id:activeId,status}); await refresh(); showDetail(activeId); notify('Situação atualizada.'); // Recarrega o estado confirmado pelo servidor.
}
async function updateArchive(archived) { // Resolve e arquiva ou retoma uma manifestação na fila compartilhada da equipe.
  await api('/api/archive', {id:activeId,archived}); await refresh(); $('detailDialog').close(); // A mudança só aparece depois da confirmação do servidor.
  notify(archived ? 'Manifestação resolvida e movida para Arquivadas.' : 'Manifestação desarquivada e devolvida ao atendimento.'); // Indica em qual aba encontrar o protocolo.
}
function setRegisterMode(enabled) { // Alterna entre entrar e criar conta, sem segunda etapa por e-mail.
  registerMode = enabled; $('confirmField').hidden = !enabled; $('confirmPassword').required = enabled; // Solicita confirmação somente no cadastro.
  $('password').autocomplete = enabled ? 'new-password' : 'current-password'; // Ajuda o gerenciador de senhas do navegador.
  $('loginButton').textContent = enabled ? 'Criar minha conta →' : 'Entrar →'; // Explica exatamente o que o botão fará.
  $('toggleRegister').textContent = enabled ? 'Já tenho conta. Entrar' : 'Primeiro acesso? Criar conta de aluno'; // Oferece retorno à tela de entrada.
  $('forgotPassword').hidden = enabled; $('password').value = ''; $('confirmPassword').value = ''; // Limpa senhas ao trocar a operação.
}
$('loginForm').onsubmit = event => { // Faz cadastro ou acesso com e-mail e senha.
  event.preventDefault(); // Evita recarregar a página.
  busy($('loginButton'), async () => { // Impede cliques repetidos durante a autenticação.
    const email = $('email').value.trim().toLowerCase(); const password = $('password').value; // Preserva os caracteres da senha, inclusive espaços.
    if (!/^[^\s@]+@camporeal\.edu\.br$/.test(email)) throw new Error('Use seu e-mail @camporeal.edu.br.'); // Oferece validação imediata do domínio.
    if (registerMode && password !== $('confirmPassword').value) throw new Error('As senhas precisam ser iguais.'); // Evita cadastrar uma senha digitada incorretamente.
    if (DEMO) { user = {email,role:'aluno'}; await loggedIn(); resetLogin(); return; } // No demonstrador, toda conta digitada continua fictícia.
    await api(registerMode ? '/api/register' : '/api/login', {email,password}); // O servidor define o perfil e verifica a senha.
    user = await api('/api/me'); await loggedIn(); resetLogin(); // Entra direto após o cadastro ou a senha correta.
  });
};
function resetLogin() { // Remove as credenciais da tela depois do acesso.
  $('loginForm').reset(); setRegisterMode(false); // Volta ao modo padrão de entrada.
}
$('toggleRegister').onclick = () => setRegisterMode(!registerMode); // Permite criar somente contas de aluno pelo site.
$('forgotPassword').onclick = () => notify('Peça ao responsável pela instalação para redefinir sua senha pelo menu python ouvidoria.py --contas.'); // Não usa links ou códigos de recuperação por e-mail.
$('newTicket').onclick = () => { $('ticketForm').reset(); $('composeDialog').showModal(); }; // Abre um formulário limpo.
$('ticketForm').onsubmit = event => { // Envia uma manifestação.
  event.preventDefault(); // Preserva a navegação atual.
  busy(event.submitter, async () => { // Impede protocolos duplicados por clique repetido.
    const payload = Object.fromEntries(new FormData(event.currentTarget)); payload.anonymous = $('anonymous').checked; // Converte os campos e a escolha de anonimato.
    const result = await api('/api/tickets', payload); $('composeDialog').close(); await refresh(); showDetail(result.id); notify('Manifestação registrada. Guarde seu protocolo: ' + result.id); // Exibe confirmação e acompanhamento.
  });
};
$('replyForm').onsubmit = event => { // Envia uma resposta ou complemento.
  event.preventDefault(); // Mantém o protocolo aberto.
  busy(event.submitter, async () => { await api('/api/reply', {id:activeId,body:$('replyBody').value.trim()}); await refresh(); showDetail(activeId); notify('Mensagem enviada.'); }); // Atualiza o histórico após confirmação.
};
$('ticketList').onclick = event => { const card = event.target.closest('[data-ticket]'); if (card) showDetail(card.dataset.ticket); }; // Abre o cartão clicado.
$('search').oninput = renderList; $('statusFilter').onchange = renderList; $('sectorFilter').onchange = renderList; // Reaplica filtros ao editar os controles.
$('allTab').onclick = () => { archiveView = false; renderList(); }; // Volta à lista principal preservando os filtros.
$('archivedTab').onclick = () => { if (user?.role === 'aluno') return; archiveView = true; renderList(); }; // Permite consultar o arquivo somente na interface da equipe.
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close()); // Liga os botões de fechar às janelas.
if (DEMO) { // Configura somente o arquivo de demonstração.
  $('demoBanner').hidden = false; $('demoAccounts').hidden = false; $('loginButton').textContent = 'Explorar como aluno →'; $('password').required = false; // Identifica claramente a simulação.
  document.querySelectorAll('[data-demo]').forEach(button => button.onclick = () => busy(button, async () => {user = {email:demoEmails[button.dataset.demo],role:button.dataset.demo}; await loggedIn();})); // Permite explorar os três perfis fictícios.
} else { // Ao abrir pelo servidor, tenta recuperar uma sessão já validada.
  api('/api/me').then(async result => {user = result; await loggedIn();}).catch(error => { if (error.message && !error.message.includes('Entre com') && !error.message.includes('expirou')) notify(error.message, true); }); // Mostra a entrada se não houver sessão.
}
''',
    # Conteúdo comentado de assets/logo-azul.svg.
    'assets/logo-azul.svg': r'''<!-- Reprodução vetorial de referência baseada na marca anexada; substituir pelo arquivo oficial para publicação. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 335" role="img" aria-label="Centro Universitário Campo Real, excelência no ensino superior">
<!-- Estrela amarela da identidade visual. -->
<polygon fill="#ffdd00" points="575,0 606,66 678,74 625,123 639,197 575,160 509,197 523,123 470,74 544,66"/>
<!-- Nome superior e nome principal em fonte serifada. -->
<g fill="#004c70" text-anchor="middle" font-family="Georgia,Times New Roman,serif" font-weight="bold">
<text x="335" y="141" font-size="40">CENTRO</text>
<text x="335" y="187" font-size="40">UNIVERSITÁRIO</text>
<text x="340" y="282" font-size="98" textLength="675" lengthAdjust="spacingAndGlyphs">CAMPO REAL</text>
<text x="340" y="330" font-size="37" textLength="675" lengthAdjust="spacingAndGlyphs">EXCELÊNCIA NO ENSINO SUPERIOR</text>
</g>
</svg>''',
    # Conteúdo comentado de assets/logo-branca.svg.
    'assets/logo-branca.svg': r'''<!-- Reprodução vetorial de referência baseada na marca anexada; substituir pelo arquivo oficial para publicação. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 335" role="img" aria-label="Centro Universitário Campo Real, excelência no ensino superior">
<!-- Estrela amarela da identidade visual. -->
<polygon fill="#ffdd00" points="575,0 606,66 678,74 625,123 639,197 575,160 509,197 523,123 470,74 544,66"/>
<!-- Nome superior e nome principal em fonte serifada. -->
<g fill="#ffffff" text-anchor="middle" font-family="Georgia,Times New Roman,serif" font-weight="bold">
<text x="335" y="141" font-size="40">CENTRO</text>
<text x="335" y="187" font-size="40">UNIVERSITÁRIO</text>
<text x="340" y="282" font-size="98" textLength="675" lengthAdjust="spacingAndGlyphs">CAMPO REAL</text>
<text x="340" y="330" font-size="37" textLength="675" lengthAdjust="spacingAndGlyphs">EXCELÊNCIA NO ENSINO SUPERIOR</text>
</g>
</svg>''',
    # Conteúdo comentado de index.html.
    'index.html': r'''<!doctype html> <!-- Usa o padrão HTML atual. -->
<html lang="pt-BR"> <!-- Informa o idioma para leitores de tela. -->
<head> <!-- Reúne as configurações da página. -->
<meta charset="utf-8"> <!-- Permite acentos em português. -->
<meta name="viewport" content="width=device-width, initial-scale=1"> <!-- Adapta a página ao celular. -->
<title>Ouvidoria | Campo Real</title> <!-- Define o nome da aba. -->
<meta name="description" content="Ouvidoria Campo Real: manifeste-se e acompanhe seu atendimento."> <!-- Descreve o site. -->
<link rel="stylesheet" href="style.css"> <!-- Carrega as cores e o layout. -->
<script src="app.js" defer></script> <!-- Executa as interações depois de carregar o HTML. -->
</head>
<body> <!-- Inicia a parte visível. -->
<div id="demoBanner" class="demo-banner" hidden>Demonstração local • Dados fictícios • Não envie informações pessoais.</div> <!-- Distingue a prévia do sistema real. -->
<header class="header"> <!-- Identifica a instituição. -->
<a class="brand" href="#inicio" aria-label="Campo Real, início"><img src="assets/logo-azul.svg" alt="Centro Universitário Campo Real" width="220" height="108"></a> <!-- Exibe a marca. -->
<div class="header-label"><span class="eyebrow">CENTRO UNIVERSITÁRIO</span><strong>Ouvidoria</strong></div> <!-- Nomeia o serviço. -->
<div id="account" class="account"></div> <!-- Recebe o perfil conectado e o botão de saída. -->
</header>
<main id="inicio"> <!-- Agrupa o conteúdo principal. -->
<section id="welcome" class="welcome"> <!-- Apresenta o canal de escuta. -->
<div class="intro"><span class="eyebrow light">OUVIDORIA CAMPO REAL</span><h1>Sua voz faz<br>parte da mudança<span>.</span></h1><p>Um espaço para ouvir você, acolher suas ideias e construir uma faculdade cada vez melhor.</p><div class="intro-points"><span>✓ Escuta com respeito</span><span>✓ Acompanhamento por protocolo</span></div><div class="intro-bottom"><span class="small-star" aria-hidden="true">✦</span><p>Reclamações, críticas, sugestões e elogios.<br><strong>Toda manifestação importa.</strong></p></div></div> <!-- Explica a proposta do atendimento. -->
<div class="login-card"><span class="step-label">SEU ESPAÇO DE ESCUTA</span><h2>Vamos conversar?</h2><p>Entre com seu e-mail institucional e senha. No primeiro acesso, crie sua conta de aluno.</p>
<form id="loginForm"> <!-- Acesso direto com e-mail e senha, sem serviço de envio. -->
<label for="email">E-mail institucional</label><input id="email" type="email" required maxlength="254" autocomplete="username"> <!-- Mantém o campo vazio e exige endereço institucional. -->
<label for="password">Senha</label><input id="password" type="password" required minlength="8" maxlength="128" autocomplete="current-password"> <!-- Não exibe a senha digitada. -->
<div id="confirmField" hidden><label for="confirmPassword">Confirmar senha</label><input id="confirmPassword" type="password" minlength="8" maxlength="128" autocomplete="new-password"></div> <!-- Confere a senha antes de cadastrar. -->
<button id="loginButton" class="button primary" type="submit">Entrar →</button> <!-- Envia o acesso ao servidor Python. -->
<button id="toggleRegister" type="button" class="text-button">Primeiro acesso? Criar conta de aluno</button> <!-- Permite cadastro sem escolher permissões administrativas. -->
<button id="forgotPassword" type="button" class="text-button">Esqueci minha senha</button> <!-- Orienta recuperação pelo responsável, sem SMTP. -->
<p id="authHint" class="form-note">Use seu e-mail @camporeal.edu.br. O cadastro verifica o domínio, mas não comprova a titularidade do e-mail.</p> <!-- Explica o limite do modelo escolhido. -->
</form>
<div id="demoAccounts" class="demo-accounts" hidden><p>Explore os perfis fictícios:</p><button type="button" data-demo="aluno">Aluno</button><button type="button" data-demo="supervisor">Supervisor</button><button type="button" data-demo="diretor">Diretor</button></div> <!-- Oferece perfis apenas no arquivo de demonstração. -->
<div class="privacy-note"><span aria-hidden="true">◈</span><p><strong>Você escolhe como se identificar.</strong><br>Na opção anônima, sua identidade fica oculta para a equipe de atendimento e pode ser consultada somente pelo diretor. O login continua obrigatório.</p></div> <!-- Explica o limite do anonimato antes do acesso. -->
</div>
</section>
<section id="workspace" class="workspace" hidden> <!-- Mostra o painel após o login. -->
<div class="workspace-heading"><div><span id="panelLabel" class="eyebrow">ÁREA DO ALUNO</span><h1 id="panelTitle">Minhas manifestações</h1><p id="panelDescription">Acompanhe cada conversa, do primeiro contato à solução.</p></div><button id="newTicket" class="button primary" type="button">＋ Nova manifestação</button></div> <!-- Apresenta o painel apropriado ao perfil. -->
<div id="stats" class="stats"></div> <!-- Resume os protocolos por situação. -->
<div class="toolbar"><div class="tabs" role="group" aria-label="Listas de manifestações"><button id="allTab" class="tab active" type="button" aria-pressed="true">Todas as manifestações</button><button id="archivedTab" class="tab" type="button" aria-pressed="false" hidden>Arquivadas</button></div><div class="filters"><div id="sectorFilterField" hidden><label class="sr-only" for="sectorFilter">Filtrar área da manifestação</label><select id="sectorFilter"><option value="">Todas as áreas</option></select></div><label class="sr-only" for="search">Buscar manifestações</label><input id="search" type="search" placeholder="Buscar assunto ou protocolo"><label class="sr-only" for="statusFilter">Filtrar situação</label><select id="statusFilter"><option value="">Todas as situações</option><option>Recebida</option><option>Em análise</option><option>Respondida</option><option>Resolvida</option></select></div></div> <!-- Permite localizar manifestações. -->
<div id="ticketList" class="ticket-list"></div> <!-- Recebe a lista filtrada. -->
</section>
<section id="how" class="how"><div><span class="eyebrow">SIMPLES, DO COMEÇO AO FIM</span><h2>Da sua voz à nossa ação.</h2></div><div class="how-step"><span>01</span><h3>Conte o que aconteceu</h3><p>Escolha o tipo de manifestação e compartilhe seu relato.</p></div><div class="how-step"><span>02</span><h3>Acompanhe a resposta</h3><p>Consulte o protocolo e converse com a ouvidoria.</p></div><div class="how-step"><span>03</span><h3>Ajude a concluir</h3><p>Informe se foi resolvido ou peça uma nova análise.</p></div></section> <!-- Explica o fluxo de atendimento. -->
</main>
<footer><div class="footer-brand"><img src="assets/logo-branca.svg" alt="Campo Real" width="100" height="50"><p>Ouvidoria</p></div><p>Escutar. Acolher. Transformar.</p></footer> <!-- Fecha a página com a identidade institucional. -->
<dialog id="composeDialog"> <!-- Contém o formulário de nova manifestação. -->
<div class="dialog-header"><div><span class="eyebrow">ESTAMOS AQUI PARA OUVIR</span><h2>Nova manifestação</h2></div><button class="close" data-close="composeDialog" type="button" aria-label="Fechar formulário">×</button></div> <!-- Oferece título e fechamento acessível. -->
<form id="ticketForm"><div class="form-row"><div><label for="kind">Tipo de manifestação</label><select id="kind" name="kind"><option>Reclamação</option><option>Crítica</option><option>Sugestão</option><option>Elogio</option><option>Solicitação</option></select></div><div><label for="sector">Área relacionada</label><select id="sector" name="sector"><option>Geral</option><option>Coordenação de curso</option><option>Atendimento / Secretaria</option><option>Infraestrutura</option><option>Financeiro</option><option>Ensino e aprendizagem</option><option>Outros</option></select></div></div> <!-- Classifica o relato. -->
<label for="subject">Assunto</label><input id="subject" name="subject" minlength="5" maxlength="120" placeholder="Resuma sua manifestação" required> <!-- Resume o assunto em até 120 caracteres. -->
<label for="body">Seu relato</label><textarea id="body" name="body" minlength="20" maxlength="5000" rows="5" placeholder="Conte o que aconteceu e como podemos ajudar. Mínimo de 20 caracteres." required></textarea> <!-- Recebe o relato completo. -->
<label class="anonymous-option"><input id="anonymous" name="anonymous" type="checkbox"><span><strong>Enviar de forma anônima para o atendimento</strong><small>Supervisores não verão seu e-mail. Somente o diretor poderá consultar sua identidade; a consulta ficará registrada. Evite escrever seu nome no relato.</small></span></label> <!-- Solicita a escolha informada sobre a identificação. -->
<p class="form-note">Você poderá consultar o protocolo e receber respostas mesmo na opção anônima.</p><button class="button primary" type="submit">Enviar manifestação →</button> <!-- Registra a manifestação. -->
</form>
</dialog>
<dialog id="detailDialog"> <!-- Exibe o protocolo e sua conversa. -->
<div class="dialog-header"><div><span id="detailProtocol" class="eyebrow"></span><h2 id="detailSubject"></h2></div><button class="close" data-close="detailDialog" type="button" aria-label="Fechar manifestação">×</button></div> <!-- Mostra a identificação do protocolo. -->
<div id="detailContent"></div><div id="detailActions" class="detail-actions"></div> <!-- Recebe dados, respostas e controles autorizados. -->
<form id="replyForm"><label for="replyBody">Escrever uma mensagem</label><textarea id="replyBody" rows="3" minlength="3" maxlength="5000" required placeholder="Continue a conversa por aqui..."></textarea><button class="button primary" type="submit">Enviar mensagem →</button></form> <!-- Permite responder e complementar. -->
</dialog>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div> <!-- Anuncia sucessos e erros sem usar alertas invasivos. -->
</body>
</html>
''',
    # Conteúdo comentado de style.css.
    'style.css': r'''/* Define a identidade visual: azul principal, branco e amarelo nos detalhes. */
:root { --blue:#004c70; --navy:#06344d; --yellow:#ffdd00; --ink:#17394b; --muted:#637683; --line:#dce5ea; --paper:#f5f8fa; --radius:14px; font-family:Arial,Helvetica,sans-serif; color:var(--ink); background:var(--paper); }
/* Inclui bordas no cálculo de tamanho para evitar transbordamento. */
* { box-sizing:border-box; }
/* Remove margens padrão e melhora a leitura. */
body { margin:0; line-height:1.5; }
/* Garante que os elementos ocultos não apareçam por outras regras. */
[hidden] { display:none!important; }
/* Mantém a tipografia dos controles consistente. */
button,input,textarea,select { font:inherit; }
/* Torna os botões reconhecíveis e confortáveis ao toque. */
button { cursor:pointer; min-height:44px; }
/* Exibe um foco visível para navegação por teclado. */
:focus-visible { outline:3px solid #b08d00; outline-offset:3px; }
/* Bloqueia cliques repetidos durante solicitações. */
button:disabled { opacity:.6; cursor:wait; }
/* Destaca que o arquivo aberto localmente é só uma demonstração. */
.demo-banner { padding:9px 20px; text-align:center; background:#fff4bc; color:#665100; font-size:12px; font-weight:700; }
/* Organiza o cabeçalho institucional. */
.header { min-height:116px; padding:15px 6%; background:white; display:flex; align-items:center; gap:30px; border-bottom:1px solid var(--line); }
/* Mantém a proporção da marca. */
.brand img { display:block; width:205px; height:86px; object-fit:contain; }
/* Separa o nome do serviço da marca. */
.header-label { border-left:1px solid var(--line); padding-left:28px; }
/* Destaca o nome Ouvidoria. */
.header-label strong { display:block; font-size:24px; letter-spacing:-.5px; }
/* Padroniza as pequenas chamadas em letras maiúsculas. */
.eyebrow,.step-label { font-size:10px; font-weight:700; letter-spacing:1.8px; }
/* Alinha os dados da sessão à direita. */
.account { margin-left:auto; text-align:right; font-size:12px; overflow-wrap:anywhere; }
/* Identifica o perfil conectado. */
.account strong { display:block; color:var(--blue); text-transform:capitalize; }
/* Cria o bloco de apresentação e acesso. */
.welcome { max-width:1320px; margin:46px auto 0; display:grid; grid-template-columns:1.14fr 1fr; padding:0 48px; }
/* Usa o azul como área principal da composição. */
.intro { padding:56px 48px 36px; color:white; background:var(--blue); border-radius:18px 0 0 18px; position:relative; overflow:hidden; }
/* Insere um detalhe gráfico discreto no fundo. */
.intro:after { content:'✦'; position:absolute; right:-56px; bottom:-170px; font-size:440px; color:#ffffff08; pointer-events:none; }
/* Clareia a chamada sobre o fundo azul. */
.light { color:#bed6e1; }
/* Define os títulos principais. */
h1 { font-size:48px; line-height:1.12; letter-spacing:-1.8px; margin:24px 0; }
/* Aplica amarelo apenas ao detalhe do título. */
h1 span { color:var(--yellow); }
/* Ajusta o texto de apresentação. */
.intro>p { color:#d6e7ee; max-width:350px; font-size:16px; line-height:1.7; }
/* Organiza os benefícios de forma compacta. */
.intro-points { display:flex; flex-direction:column; gap:9px; margin:26px 0 40px; font-size:12px; color:#e8f1f5; }
/* Finaliza a apresentação com uma assinatura visual. */
.intro-bottom { display:flex; align-items:center; gap:16px; border-top:1px solid #ffffff28; padding-top:22px; position:relative; z-index:1; }
/* Exibe uma pequena estrela amarela. */
.small-star { color:var(--yellow); font-size:37px; }
/* Ajusta a assinatura institucional. */
.intro-bottom p { font-size:11px; color:#c6dce6; margin:0; line-height:1.8; }
/* Constrói o cartão de autenticação. */
.login-card { background:white; border:1px solid var(--line); border-left:0; border-radius:0 18px 18px 0; padding:48px 44px 36px; }
/* Aplica cor aos subtítulos pequenos. */
.step-label { color:var(--blue); }
/* Padroniza títulos secundários. */
h2 { font-size:28px; line-height:1.2; letter-spacing:-.8px; margin:14px 0; }
/* Suaviza os textos auxiliares. */
.login-card>p,.workspace-heading p,.how p { color:var(--muted); font-size:13px; }
/* Separa o formulário da introdução. */
#loginForm { margin-top:28px; }
/* Mantém os rótulos sempre visíveis. */
label { display:block; font-size:12px; font-weight:700; margin:15px 0 7px; }
/* Padroniza os campos do formulário. */
input:not([type=checkbox]),select,textarea { width:100%; border:1px solid #cddae2; border-radius:8px; padding:12px 13px; background:white; color:var(--ink); font-size:13px; min-height:45px; }
/* Permite aumentar a área de relato verticalmente. */
textarea { resize:vertical; }
/* Define a aparência compartilhada dos botões. */
.button { border:1px solid var(--line); border-radius:8px; padding:12px 19px; font-size:12px; font-weight:700; display:inline-flex; align-items:center; justify-content:center; gap:15px; background:white; color:var(--blue); }
/* Destaca as ações principais em azul. */
.primary { background:var(--blue); border-color:var(--blue); color:white; }
/* Aumenta a percepção de interação ao passar o mouse. */
.primary:hover { background:var(--navy); }
/* Expande o botão de acesso dentro do cartão. */
#loginButton { width:100%; margin-top:18px; justify-content:space-between; }
/* Estiliza ações secundárias como texto. */
.text-button { border:0; background:none; padding:4px; color:var(--blue); font-size:12px; text-decoration:underline; }
/* Explica o anonimato em um quadro discreto. */
.privacy-note { border-top:1px solid var(--line); margin-top:28px; padding-top:20px; display:flex; align-items:flex-start; gap:12px; }
/* Dá destaque ao ícone de privacidade. */
.privacy-note>span { color:#a88b00; font-size:24px; }
/* Mantém o aviso de privacidade legível. */
.privacy-note p { margin:0; font-size:11px; line-height:1.7; color:var(--muted); }
/* Destaca a escolha de identificação. */
.privacy-note strong { color:var(--ink); }
/* Organiza os perfis do demonstrador. */
.demo-accounts { border:1px dashed #c5ad3e; border-radius:8px; padding:10px; margin-top:18px; }
/* Reduz o texto auxiliar do demonstrador. */
.demo-accounts p { font-size:11px; margin:0 0 5px; }
/* Mantém os botões de demonstração compactos. */
.demo-accounts button { border:0; background:#eef4f7; border-radius:5px; color:var(--blue); padding:6px 10px; margin:2px; font-size:11px; }
/* Explica o fluxo em quatro colunas. */
.how { max-width:1224px; margin:42px auto 40px; padding:0 48px; display:grid; grid-template-columns:1.1fr 1fr 1fr 1fr; gap:30px; }
/* Mantém o título explicativo compacto. */
.how h2 { font-size:23px; margin-top:10px; }
/* Separa as etapas com linhas verticais. */
.how-step { border-left:1px solid var(--line); padding-left:24px; }
/* Numera as etapas com o azul da marca. */
.how-step>span { color:var(--blue); font-weight:700; font-size:12px; border-bottom:3px solid var(--yellow); padding-bottom:4px; }
/* Ajusta o título de cada etapa. */
h3 { font-size:13px; margin:18px 0 6px; }
/* Usa um tamanho confortável nas descrições. */
.how-step p { margin:0; font-size:11px; }
/* Alinha as informações do rodapé. */
footer { border-top:1px solid var(--line); display:flex; justify-content:space-between; padding:18px 6%; color:#c6dce6; font-size:11px; background:var(--navy); align-items:center; }
/* Aplica amarelo à separação no rodapé. */
footer span { color:#c4a300; margin:0 7px; }
/* Centraliza a área autenticada. */
.workspace { max-width:1200px; margin:42px auto; padding:0 32px; min-height:55vh; }
/* Distribui o título e a ação de criar protocolo. */
.workspace-heading { display:flex; justify-content:space-between; align-items:center; gap:20px; }
/* Ajusta o título do painel. */
.workspace h1 { font-size:34px; margin:10px 0; letter-spacing:-1px; }
/* Distribui os indicadores de acompanhamento. */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:28px 0; }
/* Cria cartões discretos para os indicadores. */
.stat { background:white; border:1px solid var(--line); border-radius:10px; padding:18px 22px; }
/* Destaca os números dos indicadores. */
.stat strong { display:block; font-size:29px; line-height:1.2; color:var(--blue); }
/* Descreve cada indicador. */
.stat span { color:var(--muted); font-size:12px; }
/* Reúne filtros e abas. */
.toolbar { display:flex; justify-content:space-between; align-items:center; gap:15px; border-bottom:1px solid var(--line); padding-bottom:14px; }
/* Identifica a aba atual com detalhe amarelo. */
.tab { border:0; background:none; color:var(--blue); border-bottom:3px solid var(--yellow); font-weight:700; font-size:12px; }
/* Coloca os filtros lado a lado. */
.filters { display:flex; gap:10px; }
/* Limita a largura dos filtros em telas grandes. */
.filters input { max-width:230px; }
/* Cria espaçamento entre os protocolos. */
.ticket-list { display:grid; gap:12px; margin-top:20px; }
/* Torna cada protocolo um botão com texto alinhado. */
.ticket-card { display:flex; align-items:center; justify-content:space-between; gap:20px; text-align:left; background:white; border:1px solid var(--line); border-radius:10px; padding:22px; width:100%; color:var(--ink); }
/* Evidencia o cartão interativo. */
.ticket-card:hover { border-color:#5d94ad; box-shadow:0 3px 12px #004c7009; }
/* Ajusta o título de cada manifestação. */
.ticket-card h3 { margin:7px 0; font-size:16px; overflow-wrap:anywhere; }
/* Exibe os metadados em tamanho menor. */
.meta { color:var(--muted); font-size:11px; }
/* Destaca os protocolos com a cor institucional. */
.protocol { color:var(--blue); font-size:10px; font-weight:700; letter-spacing:.5px; }
/* Define os marcadores de situação. */
.badge { display:inline-block; border-radius:20px; padding:5px 10px; background:#eef3f6; color:#526d7c; font-size:10px; font-weight:700; white-space:nowrap; }
/* Diferencia os protocolos em análise. */
.badge.analysis { background:#fff4c9; color:#826a00; }
/* Diferencia os protocolos respondidos. */
.badge.answered { background:#e4f0fb; color:#235b8a; }
/* Diferencia os protocolos solucionados. */
.badge.solved { background:#e5f3eb; color:#28734c; }
/* Apresenta estados vazios sem deixar o painel em branco. */
.empty { text-align:center; padding:45px 20px; background:white; border:1px dashed var(--line); border-radius:10px; color:var(--muted); }
/* Define as janelas acessíveis dos formulários. */
dialog { border:0; border-radius:16px; padding:30px; width:min(660px,94vw); max-height:90vh; color:var(--ink); box-shadow:0 20px 90px #032c4960; }
/* Escurece o fundo enquanto uma janela está aberta. */
dialog::backdrop { background:#052c46a6; }
/* Alinha o cabeçalho da janela e o botão de fechamento. */
.dialog-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
/* Mantém assuntos compridos dentro da janela. */
.dialog-header h2 { overflow-wrap:anywhere; font-size:25px; }
/* Destaca o botão de fechar sem competir com as ações. */
.close { border:0; background:#eef3f6; border-radius:50%; width:38px; min-height:38px; flex-shrink:0; font-size:24px; color:var(--blue); }
/* Distribui campos relacionados em duas colunas. */
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
/* Explica a opção anônima junto à caixa de seleção. */
.anonymous-option { display:flex; gap:12px; align-items:flex-start; padding:16px; border:1px solid var(--line); border-radius:8px; background:var(--paper); }
/* Dimensiona o controle de anonimato. */
.anonymous-option input { margin-top:3px; width:18px; height:18px; accent-color:var(--blue); flex-shrink:0; }
/* Apresenta os limites do anonimato em texto normal. */
.anonymous-option small { display:block; color:var(--muted); font-weight:400; margin-top:5px; font-size:11px; line-height:1.6; }
/* Padroniza notas dos formulários. */
.form-note { font-size:11px; color:var(--muted); }
/* Separa a descrição original do histórico. */
.detail-body { white-space:pre-wrap; overflow-wrap:anywhere; background:var(--paper); border-radius:10px; padding:18px; font-size:13px; }
/* Garante que mensagens não ultrapassem a tela. */
.message { border-left:3px solid var(--line); padding:9px 14px; margin:15px 0; font-size:13px; overflow-wrap:anywhere; }
/* Preserva quebras de linha nas respostas. */
.message p { white-space:pre-wrap; margin:7px 0; }
/* Destaca as respostas institucionais. */
.message.staff { border-color:var(--blue); background:#f2f7fa; }
/* Organiza as ações de acompanhamento. */
.detail-actions { display:flex; flex-wrap:wrap; gap:8px; padding:16px 0; border-top:1px solid var(--line); margin-top:20px; }
/* Mostra notificações com contraste e largura limitada. */
.toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%); background:var(--navy); color:white; padding:15px 22px; border-radius:9px; box-shadow:0 5px 22px #0002; max-width:min(580px,92vw); font-size:13px; z-index:50; }
/* Diferencia erros sem depender apenas de cor. */
.toast.error { background:#873c32; }
/* Mantém rótulos acessíveis sem ocupar espaço visual. */
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
/* Ajusta o layout para tablets. */
@media(max-width:950px) { .welcome{padding:0 24px}.intro{padding:40px 28px}.login-card{padding:36px 28px}h1{font-size:39px}.how{padding:0 28px;gap:18px}.header{padding:14px 24px;gap:20px}.brand img{width:170px}.header-label{padding-left:20px}.toolbar{align-items:flex-start;flex-direction:column}.filters{width:100%}.filters input{max-width:none} }
/* Empilha os elementos para celulares. */
@media(max-width:650px) { .header{min-height:95px;flex-wrap:wrap;gap:12px}.brand img{width:145px;height:65px}.header-label{padding-left:15px}.header-label strong{font-size:20px}.eyebrow{font-size:9px}.account{width:100%;text-align:left;border-top:1px solid var(--line);padding-top:8px}.account strong{display:inline;margin-right:10px}.welcome{grid-template-columns:1fr;margin-top:22px;padding:0 16px}.intro{border-radius:14px 14px 0 0;padding:32px 26px}.intro h1{font-size:38px}.intro-points{margin-bottom:22px}.intro-bottom{padding-top:18px}.login-card{border-left:1px solid var(--line);border-top:0;border-radius:0 0 14px 14px;padding:30px 26px}.how{grid-template-columns:1fr;padding:0 22px;margin-top:30px}.how-step{padding:0 0 0 18px}.how-step h3{margin-top:10px}.workspace{padding:0 16px;margin-top:24px}.workspace-heading{align-items:flex-start;flex-direction:column}.workspace h1{font-size:29px}.stats{grid-template-columns:1fr 1fr;gap:10px}.stat{padding:16px}.filters{flex-direction:column}.ticket-card{padding:17px;gap:8px;align-items:flex-start}.ticket-card h3{font-size:14px}.ticket-card>.badge{font-size:9px}.form-row{grid-template-columns:1fr;gap:0}dialog{padding:22px}.detail-actions .button{flex:1}footer{padding:16px 22px;gap:12px;font-size:10px} }

/* Alinha a versão branca da marca no rodapé azul. */
.footer-brand { display:flex; align-items:center; gap:22px; }
/* Mantém a proporção da segunda versão da marca. */
.footer-brand img { object-fit:contain; }

/* Facilita encontrar os atalhos da conta abaixo do botão principal. */
#toggleRegister,#forgotPassword { display:block; text-align:left; margin-top:8px; }

/* Permite alternar as abas e combinar três filtros em telas menores. */
.tabs { display:flex; flex-wrap:wrap; gap:14px; }
/* Marca somente a aba selecionada com a cor de detalhe. */
.tab { border-bottom-color:transparent; }
/* Mantém um indicador visível de seleção. */
.tab.active { border-bottom-color:var(--yellow); }
/* Evita que a área aumente a barra além da tela. */
.filters { flex-wrap:wrap; }
/* Mantém o seletor de área legível entre os demais filtros. */
#sectorFilterField { min-width:170px; flex:1; }
/* Permite que os indicadores de arquivamento se ajustem no celular. */
.ticket-card { flex-wrap:wrap; }
/* Evita esticar campos para fora do painel em telas pequenas. */
@media(max-width:650px) { #sectorFilterField { width:100%; } }
''',
    # Conteúdo comentado de DEMONSTRACAO.html.
    'DEMONSTRACAO.html': r'''<!doctype html> <!-- Usa o padrão HTML atual. -->
<html lang="pt-BR"> <!-- Informa o idioma para leitores de tela. -->
<head> <!-- Reúne as configurações da página. -->
<meta charset="utf-8"> <!-- Permite acentos em português. -->
<meta name="viewport" content="width=device-width, initial-scale=1"> <!-- Adapta a página ao celular. -->
<title>Ouvidoria | Campo Real</title> <!-- Define o nome da aba. -->
<meta name="description" content="Ouvidoria Campo Real: manifeste-se e acompanhe seu atendimento."> <!-- Descreve o site. -->
<style>
/* Define a identidade visual: azul principal, branco e amarelo nos detalhes. */
:root { --blue:#004c70; --navy:#06344d; --yellow:#ffdd00; --ink:#17394b; --muted:#637683; --line:#dce5ea; --paper:#f5f8fa; --radius:14px; font-family:Arial,Helvetica,sans-serif; color:var(--ink); background:var(--paper); }
/* Inclui bordas no cálculo de tamanho para evitar transbordamento. */
* { box-sizing:border-box; }
/* Remove margens padrão e melhora a leitura. */
body { margin:0; line-height:1.5; }
/* Garante que os elementos ocultos não apareçam por outras regras. */
[hidden] { display:none!important; }
/* Mantém a tipografia dos controles consistente. */
button,input,textarea,select { font:inherit; }
/* Torna os botões reconhecíveis e confortáveis ao toque. */
button { cursor:pointer; min-height:44px; }
/* Exibe um foco visível para navegação por teclado. */
:focus-visible { outline:3px solid #b08d00; outline-offset:3px; }
/* Bloqueia cliques repetidos durante solicitações. */
button:disabled { opacity:.6; cursor:wait; }
/* Destaca que o arquivo aberto localmente é só uma demonstração. */
.demo-banner { padding:9px 20px; text-align:center; background:#fff4bc; color:#665100; font-size:12px; font-weight:700; }
/* Organiza o cabeçalho institucional. */
.header { min-height:116px; padding:15px 6%; background:white; display:flex; align-items:center; gap:30px; border-bottom:1px solid var(--line); }
/* Mantém a proporção da marca. */
.brand img { display:block; width:205px; height:86px; object-fit:contain; }
/* Separa o nome do serviço da marca. */
.header-label { border-left:1px solid var(--line); padding-left:28px; }
/* Destaca o nome Ouvidoria. */
.header-label strong { display:block; font-size:24px; letter-spacing:-.5px; }
/* Padroniza as pequenas chamadas em letras maiúsculas. */
.eyebrow,.step-label { font-size:10px; font-weight:700; letter-spacing:1.8px; }
/* Alinha os dados da sessão à direita. */
.account { margin-left:auto; text-align:right; font-size:12px; overflow-wrap:anywhere; }
/* Identifica o perfil conectado. */
.account strong { display:block; color:var(--blue); text-transform:capitalize; }
/* Cria o bloco de apresentação e acesso. */
.welcome { max-width:1320px; margin:46px auto 0; display:grid; grid-template-columns:1.14fr 1fr; padding:0 48px; }
/* Usa o azul como área principal da composição. */
.intro { padding:56px 48px 36px; color:white; background:var(--blue); border-radius:18px 0 0 18px; position:relative; overflow:hidden; }
/* Insere um detalhe gráfico discreto no fundo. */
.intro:after { content:'✦'; position:absolute; right:-56px; bottom:-170px; font-size:440px; color:#ffffff08; pointer-events:none; }
/* Clareia a chamada sobre o fundo azul. */
.light { color:#bed6e1; }
/* Define os títulos principais. */
h1 { font-size:48px; line-height:1.12; letter-spacing:-1.8px; margin:24px 0; }
/* Aplica amarelo apenas ao detalhe do título. */
h1 span { color:var(--yellow); }
/* Ajusta o texto de apresentação. */
.intro>p { color:#d6e7ee; max-width:350px; font-size:16px; line-height:1.7; }
/* Organiza os benefícios de forma compacta. */
.intro-points { display:flex; flex-direction:column; gap:9px; margin:26px 0 40px; font-size:12px; color:#e8f1f5; }
/* Finaliza a apresentação com uma assinatura visual. */
.intro-bottom { display:flex; align-items:center; gap:16px; border-top:1px solid #ffffff28; padding-top:22px; position:relative; z-index:1; }
/* Exibe uma pequena estrela amarela. */
.small-star { color:var(--yellow); font-size:37px; }
/* Ajusta a assinatura institucional. */
.intro-bottom p { font-size:11px; color:#c6dce6; margin:0; line-height:1.8; }
/* Constrói o cartão de autenticação. */
.login-card { background:white; border:1px solid var(--line); border-left:0; border-radius:0 18px 18px 0; padding:48px 44px 36px; }
/* Aplica cor aos subtítulos pequenos. */
.step-label { color:var(--blue); }
/* Padroniza títulos secundários. */
h2 { font-size:28px; line-height:1.2; letter-spacing:-.8px; margin:14px 0; }
/* Suaviza os textos auxiliares. */
.login-card>p,.workspace-heading p,.how p { color:var(--muted); font-size:13px; }
/* Separa o formulário da introdução. */
#loginForm { margin-top:28px; }
/* Mantém os rótulos sempre visíveis. */
label { display:block; font-size:12px; font-weight:700; margin:15px 0 7px; }
/* Padroniza os campos do formulário. */
input:not([type=checkbox]),select,textarea { width:100%; border:1px solid #cddae2; border-radius:8px; padding:12px 13px; background:white; color:var(--ink); font-size:13px; min-height:45px; }
/* Permite aumentar a área de relato verticalmente. */
textarea { resize:vertical; }
/* Define a aparência compartilhada dos botões. */
.button { border:1px solid var(--line); border-radius:8px; padding:12px 19px; font-size:12px; font-weight:700; display:inline-flex; align-items:center; justify-content:center; gap:15px; background:white; color:var(--blue); }
/* Destaca as ações principais em azul. */
.primary { background:var(--blue); border-color:var(--blue); color:white; }
/* Aumenta a percepção de interação ao passar o mouse. */
.primary:hover { background:var(--navy); }
/* Expande o botão de acesso dentro do cartão. */
#loginButton { width:100%; margin-top:18px; justify-content:space-between; }
/* Estiliza ações secundárias como texto. */
.text-button { border:0; background:none; padding:4px; color:var(--blue); font-size:12px; text-decoration:underline; }
/* Explica o anonimato em um quadro discreto. */
.privacy-note { border-top:1px solid var(--line); margin-top:28px; padding-top:20px; display:flex; align-items:flex-start; gap:12px; }
/* Dá destaque ao ícone de privacidade. */
.privacy-note>span { color:#a88b00; font-size:24px; }
/* Mantém o aviso de privacidade legível. */
.privacy-note p { margin:0; font-size:11px; line-height:1.7; color:var(--muted); }
/* Destaca a escolha de identificação. */
.privacy-note strong { color:var(--ink); }
/* Organiza os perfis do demonstrador. */
.demo-accounts { border:1px dashed #c5ad3e; border-radius:8px; padding:10px; margin-top:18px; }
/* Reduz o texto auxiliar do demonstrador. */
.demo-accounts p { font-size:11px; margin:0 0 5px; }
/* Mantém os botões de demonstração compactos. */
.demo-accounts button { border:0; background:#eef4f7; border-radius:5px; color:var(--blue); padding:6px 10px; margin:2px; font-size:11px; }
/* Explica o fluxo em quatro colunas. */
.how { max-width:1224px; margin:42px auto 40px; padding:0 48px; display:grid; grid-template-columns:1.1fr 1fr 1fr 1fr; gap:30px; }
/* Mantém o título explicativo compacto. */
.how h2 { font-size:23px; margin-top:10px; }
/* Separa as etapas com linhas verticais. */
.how-step { border-left:1px solid var(--line); padding-left:24px; }
/* Numera as etapas com o azul da marca. */
.how-step>span { color:var(--blue); font-weight:700; font-size:12px; border-bottom:3px solid var(--yellow); padding-bottom:4px; }
/* Ajusta o título de cada etapa. */
h3 { font-size:13px; margin:18px 0 6px; }
/* Usa um tamanho confortável nas descrições. */
.how-step p { margin:0; font-size:11px; }
/* Alinha as informações do rodapé. */
footer { border-top:1px solid var(--line); display:flex; justify-content:space-between; padding:18px 6%; color:#c6dce6; font-size:11px; background:var(--navy); align-items:center; }
/* Aplica amarelo à separação no rodapé. */
footer span { color:#c4a300; margin:0 7px; }
/* Centraliza a área autenticada. */
.workspace { max-width:1200px; margin:42px auto; padding:0 32px; min-height:55vh; }
/* Distribui o título e a ação de criar protocolo. */
.workspace-heading { display:flex; justify-content:space-between; align-items:center; gap:20px; }
/* Ajusta o título do painel. */
.workspace h1 { font-size:34px; margin:10px 0; letter-spacing:-1px; }
/* Distribui os indicadores de acompanhamento. */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:28px 0; }
/* Cria cartões discretos para os indicadores. */
.stat { background:white; border:1px solid var(--line); border-radius:10px; padding:18px 22px; }
/* Destaca os números dos indicadores. */
.stat strong { display:block; font-size:29px; line-height:1.2; color:var(--blue); }
/* Descreve cada indicador. */
.stat span { color:var(--muted); font-size:12px; }
/* Reúne filtros e abas. */
.toolbar { display:flex; justify-content:space-between; align-items:center; gap:15px; border-bottom:1px solid var(--line); padding-bottom:14px; }
/* Identifica a aba atual com detalhe amarelo. */
.tab { border:0; background:none; color:var(--blue); border-bottom:3px solid var(--yellow); font-weight:700; font-size:12px; }
/* Coloca os filtros lado a lado. */
.filters { display:flex; gap:10px; }
/* Limita a largura dos filtros em telas grandes. */
.filters input { max-width:230px; }
/* Cria espaçamento entre os protocolos. */
.ticket-list { display:grid; gap:12px; margin-top:20px; }
/* Torna cada protocolo um botão com texto alinhado. */
.ticket-card { display:flex; align-items:center; justify-content:space-between; gap:20px; text-align:left; background:white; border:1px solid var(--line); border-radius:10px; padding:22px; width:100%; color:var(--ink); }
/* Evidencia o cartão interativo. */
.ticket-card:hover { border-color:#5d94ad; box-shadow:0 3px 12px #004c7009; }
/* Ajusta o título de cada manifestação. */
.ticket-card h3 { margin:7px 0; font-size:16px; overflow-wrap:anywhere; }
/* Exibe os metadados em tamanho menor. */
.meta { color:var(--muted); font-size:11px; }
/* Destaca os protocolos com a cor institucional. */
.protocol { color:var(--blue); font-size:10px; font-weight:700; letter-spacing:.5px; }
/* Define os marcadores de situação. */
.badge { display:inline-block; border-radius:20px; padding:5px 10px; background:#eef3f6; color:#526d7c; font-size:10px; font-weight:700; white-space:nowrap; }
/* Diferencia os protocolos em análise. */
.badge.analysis { background:#fff4c9; color:#826a00; }
/* Diferencia os protocolos respondidos. */
.badge.answered { background:#e4f0fb; color:#235b8a; }
/* Diferencia os protocolos solucionados. */
.badge.solved { background:#e5f3eb; color:#28734c; }
/* Apresenta estados vazios sem deixar o painel em branco. */
.empty { text-align:center; padding:45px 20px; background:white; border:1px dashed var(--line); border-radius:10px; color:var(--muted); }
/* Define as janelas acessíveis dos formulários. */
dialog { border:0; border-radius:16px; padding:30px; width:min(660px,94vw); max-height:90vh; color:var(--ink); box-shadow:0 20px 90px #032c4960; }
/* Escurece o fundo enquanto uma janela está aberta. */
dialog::backdrop { background:#052c46a6; }
/* Alinha o cabeçalho da janela e o botão de fechamento. */
.dialog-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
/* Mantém assuntos compridos dentro da janela. */
.dialog-header h2 { overflow-wrap:anywhere; font-size:25px; }
/* Destaca o botão de fechar sem competir com as ações. */
.close { border:0; background:#eef3f6; border-radius:50%; width:38px; min-height:38px; flex-shrink:0; font-size:24px; color:var(--blue); }
/* Distribui campos relacionados em duas colunas. */
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
/* Explica a opção anônima junto à caixa de seleção. */
.anonymous-option { display:flex; gap:12px; align-items:flex-start; padding:16px; border:1px solid var(--line); border-radius:8px; background:var(--paper); }
/* Dimensiona o controle de anonimato. */
.anonymous-option input { margin-top:3px; width:18px; height:18px; accent-color:var(--blue); flex-shrink:0; }
/* Apresenta os limites do anonimato em texto normal. */
.anonymous-option small { display:block; color:var(--muted); font-weight:400; margin-top:5px; font-size:11px; line-height:1.6; }
/* Padroniza notas dos formulários. */
.form-note { font-size:11px; color:var(--muted); }
/* Separa a descrição original do histórico. */
.detail-body { white-space:pre-wrap; overflow-wrap:anywhere; background:var(--paper); border-radius:10px; padding:18px; font-size:13px; }
/* Garante que mensagens não ultrapassem a tela. */
.message { border-left:3px solid var(--line); padding:9px 14px; margin:15px 0; font-size:13px; overflow-wrap:anywhere; }
/* Preserva quebras de linha nas respostas. */
.message p { white-space:pre-wrap; margin:7px 0; }
/* Destaca as respostas institucionais. */
.message.staff { border-color:var(--blue); background:#f2f7fa; }
/* Organiza as ações de acompanhamento. */
.detail-actions { display:flex; flex-wrap:wrap; gap:8px; padding:16px 0; border-top:1px solid var(--line); margin-top:20px; }
/* Mostra notificações com contraste e largura limitada. */
.toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%); background:var(--navy); color:white; padding:15px 22px; border-radius:9px; box-shadow:0 5px 22px #0002; max-width:min(580px,92vw); font-size:13px; z-index:50; }
/* Diferencia erros sem depender apenas de cor. */
.toast.error { background:#873c32; }
/* Mantém rótulos acessíveis sem ocupar espaço visual. */
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
/* Ajusta o layout para tablets. */
@media(max-width:950px) { .welcome{padding:0 24px}.intro{padding:40px 28px}.login-card{padding:36px 28px}h1{font-size:39px}.how{padding:0 28px;gap:18px}.header{padding:14px 24px;gap:20px}.brand img{width:170px}.header-label{padding-left:20px}.toolbar{align-items:flex-start;flex-direction:column}.filters{width:100%}.filters input{max-width:none} }
/* Empilha os elementos para celulares. */
@media(max-width:650px) { .header{min-height:95px;flex-wrap:wrap;gap:12px}.brand img{width:145px;height:65px}.header-label{padding-left:15px}.header-label strong{font-size:20px}.eyebrow{font-size:9px}.account{width:100%;text-align:left;border-top:1px solid var(--line);padding-top:8px}.account strong{display:inline;margin-right:10px}.welcome{grid-template-columns:1fr;margin-top:22px;padding:0 16px}.intro{border-radius:14px 14px 0 0;padding:32px 26px}.intro h1{font-size:38px}.intro-points{margin-bottom:22px}.intro-bottom{padding-top:18px}.login-card{border-left:1px solid var(--line);border-top:0;border-radius:0 0 14px 14px;padding:30px 26px}.how{grid-template-columns:1fr;padding:0 22px;margin-top:30px}.how-step{padding:0 0 0 18px}.how-step h3{margin-top:10px}.workspace{padding:0 16px;margin-top:24px}.workspace-heading{align-items:flex-start;flex-direction:column}.workspace h1{font-size:29px}.stats{grid-template-columns:1fr 1fr;gap:10px}.stat{padding:16px}.filters{flex-direction:column}.ticket-card{padding:17px;gap:8px;align-items:flex-start}.ticket-card h3{font-size:14px}.ticket-card>.badge{font-size:9px}.form-row{grid-template-columns:1fr;gap:0}dialog{padding:22px}.detail-actions .button{flex:1}footer{padding:16px 22px;gap:12px;font-size:10px} }

/* Alinha a versão branca da marca no rodapé azul. */
.footer-brand { display:flex; align-items:center; gap:22px; }
/* Mantém a proporção da segunda versão da marca. */
.footer-brand img { object-fit:contain; }

/* Facilita encontrar os atalhos da conta abaixo do botão principal. */
#toggleRegister,#forgotPassword { display:block; text-align:left; margin-top:8px; }

/* Permite alternar as abas e combinar três filtros em telas menores. */
.tabs { display:flex; flex-wrap:wrap; gap:14px; }
/* Marca somente a aba selecionada com a cor de detalhe. */
.tab { border-bottom-color:transparent; }
/* Mantém um indicador visível de seleção. */
.tab.active { border-bottom-color:var(--yellow); }
/* Evita que a área aumente a barra além da tela. */
.filters { flex-wrap:wrap; }
/* Mantém o seletor de área legível entre os demais filtros. */
#sectorFilterField { min-width:170px; flex:1; }
/* Permite que os indicadores de arquivamento se ajustem no celular. */
.ticket-card { flex-wrap:wrap; }
/* Evita esticar campos para fora do painel em telas pequenas. */
@media(max-width:650px) { #sectorFilterField { width:100%; } }

</style> <!-- Carrega as cores e o layout. -->
 <!-- Executa as interações depois de carregar o HTML. -->
</head>
<body> <!-- Inicia a parte visível. -->
<div id="demoBanner" class="demo-banner" hidden>Demonstração local • Dados fictícios • Não envie informações pessoais.</div> <!-- Distingue a prévia do sistema real. -->
<header class="header"> <!-- Identifica a instituição. -->
<a class="brand" href="#inicio" aria-label="Campo Real, início"><img src="data:image/svg+xml;base64,PCEtLSBSZXByb2R1w6fDo28gdmV0b3JpYWwgZGUgcmVmZXLDqm5jaWEgYmFzZWFkYSBuYSBtYXJjYSBhbmV4YWRhOyBzdWJzdGl0dWlyIHBlbG8gYXJxdWl2byBvZmljaWFsIHBhcmEgcHVibGljYcOnw6NvLiAtLT4KPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2ODAgMzM1IiByb2xlPSJpbWciIGFyaWEtbGFiZWw9IkNlbnRybyBVbml2ZXJzaXTDoXJpbyBDYW1wbyBSZWFsLCBleGNlbMOqbmNpYSBubyBlbnNpbm8gc3VwZXJpb3IiPgo8IS0tIEVzdHJlbGEgYW1hcmVsYSBkYSBpZGVudGlkYWRlIHZpc3VhbC4gLS0+Cjxwb2x5Z29uIGZpbGw9IiNmZmRkMDAiIHBvaW50cz0iNTc1LDAgNjA2LDY2IDY3OCw3NCA2MjUsMTIzIDYzOSwxOTcgNTc1LDE2MCA1MDksMTk3IDUyMywxMjMgNDcwLDc0IDU0NCw2NiIvPgo8IS0tIE5vbWUgc3VwZXJpb3IgZSBub21lIHByaW5jaXBhbCBlbSBmb250ZSBzZXJpZmFkYS4gLS0+CjxnIGZpbGw9IiMwMDRjNzAiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZvbnQtZmFtaWx5PSJHZW9yZ2lhLFRpbWVzIE5ldyBSb21hbixzZXJpZiIgZm9udC13ZWlnaHQ9ImJvbGQiPgo8dGV4dCB4PSIzMzUiIHk9IjE0MSIgZm9udC1zaXplPSI0MCI+Q0VOVFJPPC90ZXh0Pgo8dGV4dCB4PSIzMzUiIHk9IjE4NyIgZm9udC1zaXplPSI0MCI+VU5JVkVSU0lUw4FSSU88L3RleHQ+Cjx0ZXh0IHg9IjM0MCIgeT0iMjgyIiBmb250LXNpemU9Ijk4IiB0ZXh0TGVuZ3RoPSI2NzUiIGxlbmd0aEFkanVzdD0ic3BhY2luZ0FuZEdseXBocyI+Q0FNUE8gUkVBTDwvdGV4dD4KPHRleHQgeD0iMzQwIiB5PSIzMzAiIGZvbnQtc2l6ZT0iMzciIHRleHRMZW5ndGg9IjY3NSIgbGVuZ3RoQWRqdXN0PSJzcGFjaW5nQW5kR2x5cGhzIj5FWENFTMOKTkNJQSBOTyBFTlNJTk8gU1VQRVJJT1I8L3RleHQ+CjwvZz4KPC9zdmc+" alt="Centro Universitário Campo Real" width="220" height="108"></a> <!-- Exibe a marca. -->
<div class="header-label"><span class="eyebrow">CENTRO UNIVERSITÁRIO</span><strong>Ouvidoria</strong></div> <!-- Nomeia o serviço. -->
<div id="account" class="account"></div> <!-- Recebe o perfil conectado e o botão de saída. -->
</header>
<main id="inicio"> <!-- Agrupa o conteúdo principal. -->
<section id="welcome" class="welcome"> <!-- Apresenta o canal de escuta. -->
<div class="intro"><span class="eyebrow light">OUVIDORIA CAMPO REAL</span><h1>Sua voz faz<br>parte da mudança<span>.</span></h1><p>Um espaço para ouvir você, acolher suas ideias e construir uma faculdade cada vez melhor.</p><div class="intro-points"><span>✓ Escuta com respeito</span><span>✓ Acompanhamento por protocolo</span></div><div class="intro-bottom"><span class="small-star" aria-hidden="true">✦</span><p>Reclamações, críticas, sugestões e elogios.<br><strong>Toda manifestação importa.</strong></p></div></div> <!-- Explica a proposta do atendimento. -->
<div class="login-card"><span class="step-label">SEU ESPAÇO DE ESCUTA</span><h2>Vamos conversar?</h2><p>Entre com seu e-mail institucional e senha. No primeiro acesso, crie sua conta de aluno.</p>
<form id="loginForm"> <!-- Acesso direto com e-mail e senha, sem serviço de envio. -->
<label for="email">E-mail institucional</label><input id="email" type="email" required maxlength="254" autocomplete="username"> <!-- Mantém o campo vazio e exige endereço institucional. -->
<label for="password">Senha</label><input id="password" type="password" required minlength="8" maxlength="128" autocomplete="current-password"> <!-- Não exibe a senha digitada. -->
<div id="confirmField" hidden><label for="confirmPassword">Confirmar senha</label><input id="confirmPassword" type="password" minlength="8" maxlength="128" autocomplete="new-password"></div> <!-- Confere a senha antes de cadastrar. -->
<button id="loginButton" class="button primary" type="submit">Entrar →</button> <!-- Envia o acesso ao servidor Python. -->
<button id="toggleRegister" type="button" class="text-button">Primeiro acesso? Criar conta de aluno</button> <!-- Permite cadastro sem escolher permissões administrativas. -->
<button id="forgotPassword" type="button" class="text-button">Esqueci minha senha</button> <!-- Orienta recuperação pelo responsável, sem SMTP. -->
<p id="authHint" class="form-note">Use seu e-mail @camporeal.edu.br. O cadastro verifica o domínio, mas não comprova a titularidade do e-mail.</p> <!-- Explica o limite do modelo escolhido. -->
</form>
<div id="demoAccounts" class="demo-accounts" hidden><p>Explore os perfis fictícios:</p><button type="button" data-demo="aluno">Aluno</button><button type="button" data-demo="supervisor">Supervisor</button><button type="button" data-demo="diretor">Diretor</button></div> <!-- Oferece perfis apenas no arquivo de demonstração. -->
<div class="privacy-note"><span aria-hidden="true">◈</span><p><strong>Você escolhe como se identificar.</strong><br>Na opção anônima, sua identidade fica oculta para a equipe de atendimento e pode ser consultada somente pelo diretor. O login continua obrigatório.</p></div> <!-- Explica o limite do anonimato antes do acesso. -->
</div>
</section>
<section id="workspace" class="workspace" hidden> <!-- Mostra o painel após o login. -->
<div class="workspace-heading"><div><span id="panelLabel" class="eyebrow">ÁREA DO ALUNO</span><h1 id="panelTitle">Minhas manifestações</h1><p id="panelDescription">Acompanhe cada conversa, do primeiro contato à solução.</p></div><button id="newTicket" class="button primary" type="button">＋ Nova manifestação</button></div> <!-- Apresenta o painel apropriado ao perfil. -->
<div id="stats" class="stats"></div> <!-- Resume os protocolos por situação. -->
<div class="toolbar"><div class="tabs" role="group" aria-label="Listas de manifestações"><button id="allTab" class="tab active" type="button" aria-pressed="true">Todas as manifestações</button><button id="archivedTab" class="tab" type="button" aria-pressed="false" hidden>Arquivadas</button></div><div class="filters"><div id="sectorFilterField" hidden><label class="sr-only" for="sectorFilter">Filtrar área da manifestação</label><select id="sectorFilter"><option value="">Todas as áreas</option></select></div><label class="sr-only" for="search">Buscar manifestações</label><input id="search" type="search" placeholder="Buscar assunto ou protocolo"><label class="sr-only" for="statusFilter">Filtrar situação</label><select id="statusFilter"><option value="">Todas as situações</option><option>Recebida</option><option>Em análise</option><option>Respondida</option><option>Resolvida</option></select></div></div> <!-- Permite localizar manifestações. -->
<div id="ticketList" class="ticket-list"></div> <!-- Recebe a lista filtrada. -->
</section>
<section id="how" class="how"><div><span class="eyebrow">SIMPLES, DO COMEÇO AO FIM</span><h2>Da sua voz à nossa ação.</h2></div><div class="how-step"><span>01</span><h3>Conte o que aconteceu</h3><p>Escolha o tipo de manifestação e compartilhe seu relato.</p></div><div class="how-step"><span>02</span><h3>Acompanhe a resposta</h3><p>Consulte o protocolo e converse com a ouvidoria.</p></div><div class="how-step"><span>03</span><h3>Ajude a concluir</h3><p>Informe se foi resolvido ou peça uma nova análise.</p></div></section> <!-- Explica o fluxo de atendimento. -->
</main>
<footer><div class="footer-brand"><img src="data:image/svg+xml;base64,PCEtLSBSZXByb2R1w6fDo28gdmV0b3JpYWwgZGUgcmVmZXLDqm5jaWEgYmFzZWFkYSBuYSBtYXJjYSBhbmV4YWRhOyBzdWJzdGl0dWlyIHBlbG8gYXJxdWl2byBvZmljaWFsIHBhcmEgcHVibGljYcOnw6NvLiAtLT4KPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2ODAgMzM1IiByb2xlPSJpbWciIGFyaWEtbGFiZWw9IkNlbnRybyBVbml2ZXJzaXTDoXJpbyBDYW1wbyBSZWFsLCBleGNlbMOqbmNpYSBubyBlbnNpbm8gc3VwZXJpb3IiPgo8IS0tIEVzdHJlbGEgYW1hcmVsYSBkYSBpZGVudGlkYWRlIHZpc3VhbC4gLS0+Cjxwb2x5Z29uIGZpbGw9IiNmZmRkMDAiIHBvaW50cz0iNTc1LDAgNjA2LDY2IDY3OCw3NCA2MjUsMTIzIDYzOSwxOTcgNTc1LDE2MCA1MDksMTk3IDUyMywxMjMgNDcwLDc0IDU0NCw2NiIvPgo8IS0tIE5vbWUgc3VwZXJpb3IgZSBub21lIHByaW5jaXBhbCBlbSBmb250ZSBzZXJpZmFkYS4gLS0+CjxnIGZpbGw9IiNmZmZmZmYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZvbnQtZmFtaWx5PSJHZW9yZ2lhLFRpbWVzIE5ldyBSb21hbixzZXJpZiIgZm9udC13ZWlnaHQ9ImJvbGQiPgo8dGV4dCB4PSIzMzUiIHk9IjE0MSIgZm9udC1zaXplPSI0MCI+Q0VOVFJPPC90ZXh0Pgo8dGV4dCB4PSIzMzUiIHk9IjE4NyIgZm9udC1zaXplPSI0MCI+VU5JVkVSU0lUw4FSSU88L3RleHQ+Cjx0ZXh0IHg9IjM0MCIgeT0iMjgyIiBmb250LXNpemU9Ijk4IiB0ZXh0TGVuZ3RoPSI2NzUiIGxlbmd0aEFkanVzdD0ic3BhY2luZ0FuZEdseXBocyI+Q0FNUE8gUkVBTDwvdGV4dD4KPHRleHQgeD0iMzQwIiB5PSIzMzAiIGZvbnQtc2l6ZT0iMzciIHRleHRMZW5ndGg9IjY3NSIgbGVuZ3RoQWRqdXN0PSJzcGFjaW5nQW5kR2x5cGhzIj5FWENFTMOKTkNJQSBOTyBFTlNJTk8gU1VQRVJJT1I8L3RleHQ+CjwvZz4KPC9zdmc+" alt="Campo Real" width="100" height="50"><p>Ouvidoria</p></div><p>Escutar. Acolher. Transformar.</p></footer> <!-- Fecha a página com a identidade institucional. -->
<dialog id="composeDialog"> <!-- Contém o formulário de nova manifestação. -->
<div class="dialog-header"><div><span class="eyebrow">ESTAMOS AQUI PARA OUVIR</span><h2>Nova manifestação</h2></div><button class="close" data-close="composeDialog" type="button" aria-label="Fechar formulário">×</button></div> <!-- Oferece título e fechamento acessível. -->
<form id="ticketForm"><div class="form-row"><div><label for="kind">Tipo de manifestação</label><select id="kind" name="kind"><option>Reclamação</option><option>Crítica</option><option>Sugestão</option><option>Elogio</option><option>Solicitação</option></select></div><div><label for="sector">Área relacionada</label><select id="sector" name="sector"><option>Geral</option><option>Coordenação de curso</option><option>Atendimento / Secretaria</option><option>Infraestrutura</option><option>Financeiro</option><option>Ensino e aprendizagem</option><option>Outros</option></select></div></div> <!-- Classifica o relato. -->
<label for="subject">Assunto</label><input id="subject" name="subject" minlength="5" maxlength="120" placeholder="Resuma sua manifestação" required> <!-- Resume o assunto em até 120 caracteres. -->
<label for="body">Seu relato</label><textarea id="body" name="body" minlength="20" maxlength="5000" rows="5" placeholder="Conte o que aconteceu e como podemos ajudar. Mínimo de 20 caracteres." required></textarea> <!-- Recebe o relato completo. -->
<label class="anonymous-option"><input id="anonymous" name="anonymous" type="checkbox"><span><strong>Enviar de forma anônima para o atendimento</strong><small>Supervisores não verão seu e-mail. Somente o diretor poderá consultar sua identidade; a consulta ficará registrada. Evite escrever seu nome no relato.</small></span></label> <!-- Solicita a escolha informada sobre a identificação. -->
<p class="form-note">Você poderá consultar o protocolo e receber respostas mesmo na opção anônima.</p><button class="button primary" type="submit">Enviar manifestação →</button> <!-- Registra a manifestação. -->
</form>
</dialog>
<dialog id="detailDialog"> <!-- Exibe o protocolo e sua conversa. -->
<div class="dialog-header"><div><span id="detailProtocol" class="eyebrow"></span><h2 id="detailSubject"></h2></div><button class="close" data-close="detailDialog" type="button" aria-label="Fechar manifestação">×</button></div> <!-- Mostra a identificação do protocolo. -->
<div id="detailContent"></div><div id="detailActions" class="detail-actions"></div> <!-- Recebe dados, respostas e controles autorizados. -->
<form id="replyForm"><label for="replyBody">Escrever uma mensagem</label><textarea id="replyBody" rows="3" minlength="3" maxlength="5000" required placeholder="Continue a conversa por aqui..."></textarea><button class="button primary" type="submit">Enviar mensagem →</button></form> <!-- Permite responder e complementar. -->
</dialog>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div> <!-- Anuncia sucessos e erros sem usar alertas invasivos. -->
<script>
'use strict'; // Evita variáveis criadas por engano.
const $ = id => document.getElementById(id); // Facilita localizar elementos pelo identificador.
const DEMO = location.protocol === 'file:'; // Ativa o demonstrador somente quando o arquivo é aberto diretamente.
const statuses = ['Recebida', 'Em análise', 'Respondida', 'Resolvida']; // Define a ordem das situações.
const demoEmails = {aluno:'aluno.exemplo@camporeal.edu.br',supervisor:'supervisor.exemplo@camporeal.edu.br',diretor:'diretor.exemplo@camporeal.edu.br'}; // Contas fictícias, sem validade no servidor.
let user = null, tickets = [], activeId = null, registerMode = false, archiveView = false, toastTimer; // Guarda o estado da tela, sem armazenar a sessão real.
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])); // Impede que relatos sejam interpretados como HTML.
const date = value => new Date(value * 1000).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo',dateStyle:'short',timeStyle:'short'}); // Mostra datas no horário de Brasília.
const badge = status => `<span class="badge ${['','analysis','answered','solved'][statuses.indexOf(status)] || ''}">${escapeHTML(status)}</span>`; // Gera o marcador de situação.
function notify(message, error = false) { // Exibe um retorno acessível sobre uma ação.
  $('toast').textContent = (error ? 'Atenção: ' : '') + message; // Usa texto simples para evitar injeção de HTML.
  $('toast').className = 'toast' + (error ? ' error' : ''); // Diferencia erros visualmente.
  $('toast').hidden = false; // Mostra a notificação.
  clearTimeout(toastTimer); // Reinicia o tempo quando chega outra mensagem.
  toastTimer = setTimeout(() => $('toast').hidden = true, 6500); // Oculta depois de permitir a leitura.
}
async function busy(button, task) { // Evita envio repetido e apresenta erros.
  button.disabled = true; // Bloqueia o controle enquanto aguarda a resposta.
  try { await task(); } catch (error) { notify(error.message || 'Não foi possível concluir.', true); } // Exibe a falha com clareza.
  finally { button.disabled = false; } // Restaura o botão mesmo após erros.
}
function demoData() { // Carrega apenas registros fictícios do navegador.
  try { return JSON.parse(localStorage.getItem('camporeal-demo-v1')) || seedDemo(); } // Recupera o exemplo salvo.
  catch { return seedDemo(); } // Recria os exemplos se o armazenamento estiver indisponível.
}
function saveDemo(data) { // Salva o estado da demonstração sem simular segurança real.
  try { localStorage.setItem('camporeal-demo-v1', JSON.stringify(data)); } // Persiste somente no navegador local.
  catch { throw new Error('O navegador bloqueou o armazenamento local. Abra o arquivo em outro navegador.'); } // Informa restrições do navegador.
}
function seedDemo() { // Cria manifestações fictícias para explorar as telas.
  const now = Date.now() / 1000; // Usa o horário da abertura do demonstrador.
  return [ // Define exemplos de atendimento.
    {id:'CR-DEMO-001',email:demoEmails.aluno,anonymous:true,kind:'Reclamação',subject:'Iluminação no estacionamento',sector:'Infraestrutura',body:'A iluminação perto da saída do estacionamento precisa de manutenção. Seria possível verificar as lâmpadas desse trecho?',status:'Respondida',created:now-172800,messages:[{author:'Ouvidoria Campo Real',body:'Exemplo de resposta: encaminhamos o pedido à manutenção. Você pode acompanhar e nos informar se o problema foi resolvido.',created:now-86400}]}, // Exemplo anônimo com resposta.
    {id:'CR-DEMO-002',email:demoEmails.aluno,anonymous:false,kind:'Sugestão',subject:'Mais horários para grupos de estudo',sector:'Ensino e aprendizagem',body:'Gostaria de sugerir mais horários para utilização das salas por grupos de estudo durante o período de provas.',status:'Em análise',created:now-86400,messages:[]}, // Exemplo identificado em análise.
    {id:'CR-DEMO-003',email:'outro.aluno@camporeal.edu.br',anonymous:true,kind:'Elogio',subject:'Atendimento da biblioteca',sector:'Geral',body:'Quero registrar um elogio pelo apoio da equipe da biblioteca na pesquisa dos materiais para as atividades.',status:'Recebida',created:now-3600,messages:[]} // Exemplo que aparece somente para a equipe.
  ];
}
async function demoAPI(path, data) { // Reproduz o fluxo com dados locais; não substitui a API protegida.
  if (path === '/api/me') { if (!user) throw new Error('Entre para continuar.'); return user; } // Retorna o perfil fictício atual.
  if (path === '/api/logout') { user = null; return {ok:true}; } // Encerra a demonstração da sessão.
  const list = demoData().map(t => ({...t, archived: t.archived ?? (t.status === 'Resolvida')})); // Recupera os protocolos locais.
  if (path === '/api/tickets' && !data) return list.filter(t => user.role !== 'aluno' || t.email === user.email).map(t => ({...t,identity:!t.anonymous || user.role === 'aluno' ? t.email : null,email:undefined})); // Oculta dados no fluxo de demonstração.
  if (path === '/api/tickets') { // Registra um exemplo de manifestação.
    const item = {...data,id:'CR-DEMO-' + Math.random().toString(16).slice(2,10).toUpperCase(),email:user.email,created:Date.now()/1000,status:'Recebida',archived:false,messages:[]}; // Associa a conta fictícia.
    list.unshift(item); saveDemo(list); return {id:item.id}; // Persiste o exemplo.
  }
  const item = list.find(t => t.id === data.id); // Localiza o protocolo selecionado.
  if (!item) throw new Error('Protocolo não encontrado.'); // Trata exemplos removidos.
  if (path === '/api/identity') { if(user.role !== 'diretor') throw new Error('Somente o diretor pode consultar.'); return {email:item.email}; } // Demonstra a consulta restrita.
  if (path === '/api/reply') { item.archived = false; item.messages.push({author:user.role === 'aluno' ? 'Aluno' : 'Ouvidoria Campo Real',body:data.body,created:Date.now()/1000}); item.status = user.role === 'aluno' ? 'Em análise' : 'Respondida'; } // Acrescenta uma mensagem fictícia.
  if (path === '/api/status') { item.archived = data.status === 'Resolvida'; item.status = data.status; item.messages.push({author:'Sistema',body:'Situação alterada para ' + data.status.toLowerCase() + '.',created:Date.now()/1000}); } // Registra o andamento do exemplo.
  if (path === '/api/archive') { if (user.role === 'aluno') throw new Error('Somente a equipe pode arquivar.'); item.archived = data.archived; item.status = data.archived ? 'Resolvida' : 'Em análise'; item.messages.push({author:'Sistema',body:data.archived ? 'Manifestação resolvida e arquivada pelo atendimento.' : 'Manifestação desarquivada para nova análise.',created:Date.now()/1000}); } // Demonstra o arquivo compartilhado da equipe.
  saveDemo(list); return {ok:true}; // Confirma a alteração local.
}
async function api(path, data) { // Centraliza a comunicação com o servidor real ou a prévia.
  if (DEMO) return demoAPI(path, data); // Mantém a simulação separada da aplicação real.
  const response = await fetch(path, {method:data ? 'POST' : 'GET',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':user?.csrf || ''},body:data ? JSON.stringify(data) : undefined}); // Envia sessão por cookie e token CSRF.
  const result = await response.json(); // Interpreta a resposta.
  if (!response.ok) { // Trata os erros antes de atualizar a interface.
    if (response.status === 401) loggedOut(); // Volta ao acesso quando a sessão vence.
    throw new Error(result.error || 'Não foi possível concluir a solicitação.'); // Exibe o erro retornado pelo servidor.
  }
  return result; // Entrega os dados autorizados.
}
function loggedOut() { // Restaura a apresentação pública.
  user = null; tickets = []; activeId = null; archiveView = false; resetLogin(); $('sectorFilter').value = ''; $('search').value = ''; $('statusFilter').value = ''; // Descarta dados privados da memória da tela.
  $('workspace').hidden = true; $('welcome').hidden = false; $('how').hidden = false; // Mostra a entrada.
  $('account').replaceChildren(); $('ticketList').replaceChildren(); $('detailContent').replaceChildren(); // Limpa os dados exibidos.
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()); // Fecha janelas privadas.
}
async function loggedIn() { // Monta a área do perfil autenticado.
  $('welcome').hidden = true; $('how').hidden = true; $('workspace').hidden = false; // Alterna para o painel.
  const student = user.role === 'aluno'; // Identifica a experiência do aluno.
  $('panelLabel').textContent = student ? 'ÁREA DO ALUNO' : 'GESTÃO DA OUVIDORIA'; // Nomeia a área atual.
  $('panelTitle').textContent = student ? 'Minhas manifestações' : 'Central de manifestações'; // Adapta o título ao perfil.
  $('panelDescription').textContent = student ? 'Acompanhe cada conversa, do primeiro contato à solução.' : 'Acolha os relatos, acompanhe os protocolos e responda aos alunos.'; // Explica a tarefa principal.
  archiveView = false; $('archivedTab').hidden = student; $('sectorFilterField').hidden = student; $('sectorFilter').value = ''; $('search').value = ''; $('statusFilter').value = ''; // Limpa filtros ao trocar de perfil e mostra os controles somente à equipe.
  $('newTicket').hidden = !student; // Restringe a criação ao perfil de aluno na interface.
  $('account').innerHTML = `<strong>${escapeHTML(user.role)}</strong><span>${escapeHTML(user.email)}</span> <button class="text-button" id="logout" type="button">Sair</button>`; // Mostra os dados da própria sessão.
  $('logout').onclick = event => busy(event.currentTarget, async () => {await api('/api/logout', {}); loggedOut();}); // Invalida a sessão no servidor.
  await refresh(); // Busca as manifestações autorizadas.
}
async function refresh() { // Atualiza os protocolos e os indicadores.
  tickets = await api('/api/tickets'); // Recebe apenas registros permitidos pelo servidor.
  $('stats').innerHTML = [['Total de manifestações',tickets.length],['Em atendimento',tickets.filter(t => ['Recebida','Em análise'].includes(t.status)).length],['Respondidas',tickets.filter(t => t.status === 'Respondida').length],['Resolvidas',tickets.filter(t => t.status === 'Resolvida').length]].map(([label,count]) => `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`).join(''); // Resume os registros recebidos.
  const selectedSector = $('sectorFilter').value; // Mantém o filtro ativo após responder ou arquivar.
  const sectors = [...new Set([...Array.from($('sector').options, option => option.value), ...tickets.map(t => t.sector)])].sort((a,b) => a.localeCompare(b, 'pt-BR')); // Inclui as áreas do formulário e áreas antigas do banco.
  $('sectorFilter').innerHTML = '<option value="">Todas as áreas</option>' + sectors.map(sector => `<option value="${escapeHTML(sector)}">${escapeHTML(sector)}</option>`).join(''); // Escapa os textos antes de montar as opções.
  $('sectorFilter').value = selectedSector; // Preserva a área escolhida nas duas abas.
  renderList(); // Reaplica os filtros atuais.
}
function renderList() { // Exibe resultados de busca e situação.
  const search = $('search').value.trim().toLocaleLowerCase('pt-BR'); // Normaliza a consulta digitada.
  const staff = user?.role !== 'aluno'; // O aluno continua consultando todos os próprios protocolos, inclusive resolvidos.
  $('allTab').classList.toggle('active', !archiveView); $('archivedTab').classList.toggle('active', archiveView); // Destaca a aba atual.
  $('allTab').setAttribute('aria-pressed', String(!archiveView)); $('archivedTab').setAttribute('aria-pressed', String(archiveView)); // Anuncia a escolha a leitores de tela.
  const filtered = tickets.filter(t => (!staff || Boolean(t.archived) === archiveView) && (!staff || !$('sectorFilter').value || t.sector === $('sectorFilter').value) && (!$('statusFilter').value || t.status === $('statusFilter').value) && (t.subject + ' ' + t.id).toLocaleLowerCase('pt-BR').includes(search)); // Combina aba, área, situação e busca sem alterar permissões de acesso.
  $('ticketList').innerHTML = filtered.length ? filtered.map(t => `<button type="button" class="ticket-card" data-ticket="${escapeHTML(t.id)}"><div><span class="protocol">${escapeHTML(t.id)}</span><h3>${escapeHTML(t.subject)}</h3><span class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${t.anonymous ? 'Identidade restrita ao diretor' : 'Manifestação identificada'}</span></div>${badge(t.status)}${t.archived ? '<span class="badge">Arquivada</span>' : ''}</button>`).join('') : `<div class="empty"><h3>${archiveView ? 'Nenhuma manifestação arquivada nesta busca.' : 'Nenhuma manifestação por aqui.'}</h3><p>Ajuste os filtros${staff ? ' ou consulte a outra aba' : ' ou crie uma nova manifestação'}.</p></div>`; // Exibe cartões ou um estado vazio.
}
function showDetail(id) { // Abre o histórico do protocolo selecionado.
  activeId = id; // Guarda o alvo das próximas ações.
  const t = tickets.find(item => item.id === id); // Busca somente na lista autorizada recebida.
  if (!t) return; // Evita abrir um protocolo ausente.
  $('detailProtocol').textContent = t.id; $('detailSubject').textContent = t.subject; // Usa texto simples para protocolo e título.
  const identity = t.anonymous ? 'Identidade restrita ao diretor' : `Identificado: ${t.identity || ''}`; // Não tenta deduzir o autor anônimo.
  $('detailContent').innerHTML = `${badge(t.status)}${t.archived ? ' <span class="badge">Arquivada</span>' : ''}<p class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${escapeHTML(identity)}</p><p class="detail-body">${escapeHTML(t.body)}</p><h3>Histórico de atendimento</h3>${t.messages.length ? t.messages.map(m => `<div class="message ${m.author === 'Ouvidoria Campo Real' ? 'staff' : ''}"><strong>${escapeHTML(m.author)}</strong><span class="meta"> · ${date(m.created)}</span><p>${escapeHTML(m.body)}</p></div>`).join('') : '<p class="form-note">Aguardando atendimento. As respostas aparecerão aqui.</p>'}`; // Exibe relatos como texto escapado.
  $('detailActions').replaceChildren(); // Limpa ações e identidades reveladas em aberturas anteriores.
  if (user.role === 'aluno') { // Mostra as ações de confirmação do aluno.
    action(t.status === 'Resolvida' ? 'Pedir nova análise' : '✓ Foi resolvido', () => updateStatus(t.status === 'Resolvida' ? 'Em análise' : 'Resolvida')); // Permite encerrar ou reabrir o atendimento.
    if (t.status === 'Respondida') action('Ainda não foi resolvido', () => updateStatus('Em análise')); // Permite contestar a solução proposta.
  } else { // Mostra as ações de atendimento.
    if (t.archived) action('Desarquivar e retomar atendimento', () => updateArchive(false)); // Retoma sem perder nenhuma mensagem.
    else { action('Marcar em análise', () => updateStatus('Em análise')); action('Resolver e arquivar', () => updateArchive(true)); } // A conclusão pela equipe arquiva automaticamente. // Atualiza o andamento institucional.
    if (user.role === 'diretor' && t.anonymous) action('Consultar autoria restrita', async () => { // Exige consulta explícita do diretor.
      const result = await api('/api/identity', {id:activeId}); // O servidor autoriza e registra a consulta.
      const note = document.createElement('p'); note.className = 'form-note'; note.textContent = `Autoria: ${result.email}. Consulta registrada${DEMO ? ' apenas ilustrativa na demonstração' : ' na auditoria do servidor'}.`; // Mostra a identidade sem inserir HTML.
      $('detailActions').append(note); // Mantém a informação dentro da janela atual.
    });
  }
  $('replyForm').hidden = user.role !== 'aluno' && Boolean(t.archived); // A equipe retoma antes de enviar outra resposta; o aluno ainda pode complementar.
  $('replyForm').reset(); // Remove rascunhos de outros protocolos.
  if (!$('detailDialog').open) $('detailDialog').showModal(); // Usa uma janela com foco controlado pelo navegador.
}
function action(label, handler) { // Cria um botão de ação sem eventos HTML embutidos.
  const button = document.createElement('button'); button.type = 'button'; button.className = 'button'; button.textContent = label; // Define aparência e rótulo.
  button.onclick = () => busy(button, handler); $('detailActions').append(button); // Trata erros e cliques repetidos.
}
async function updateStatus(status) { // Solicita a alteração autorizada de situação.
  await api('/api/status', {id:activeId,status}); await refresh(); showDetail(activeId); notify('Situação atualizada.'); // Recarrega o estado confirmado pelo servidor.
}
async function updateArchive(archived) { // Resolve e arquiva ou retoma uma manifestação na fila compartilhada da equipe.
  await api('/api/archive', {id:activeId,archived}); await refresh(); $('detailDialog').close(); // A mudança só aparece depois da confirmação do servidor.
  notify(archived ? 'Manifestação resolvida e movida para Arquivadas.' : 'Manifestação desarquivada e devolvida ao atendimento.'); // Indica em qual aba encontrar o protocolo.
}
function setRegisterMode(enabled) { // Alterna entre entrar e criar conta, sem segunda etapa por e-mail.
  registerMode = enabled; $('confirmField').hidden = !enabled; $('confirmPassword').required = enabled; // Solicita confirmação somente no cadastro.
  $('password').autocomplete = enabled ? 'new-password' : 'current-password'; // Ajuda o gerenciador de senhas do navegador.
  $('loginButton').textContent = enabled ? 'Criar minha conta →' : 'Entrar →'; // Explica exatamente o que o botão fará.
  $('toggleRegister').textContent = enabled ? 'Já tenho conta. Entrar' : 'Primeiro acesso? Criar conta de aluno'; // Oferece retorno à tela de entrada.
  $('forgotPassword').hidden = enabled; $('password').value = ''; $('confirmPassword').value = ''; // Limpa senhas ao trocar a operação.
}
$('loginForm').onsubmit = event => { // Faz cadastro ou acesso com e-mail e senha.
  event.preventDefault(); // Evita recarregar a página.
  busy($('loginButton'), async () => { // Impede cliques repetidos durante a autenticação.
    const email = $('email').value.trim().toLowerCase(); const password = $('password').value; // Preserva os caracteres da senha, inclusive espaços.
    if (!/^[^\s@]+@camporeal\.edu\.br$/.test(email)) throw new Error('Use seu e-mail @camporeal.edu.br.'); // Oferece validação imediata do domínio.
    if (registerMode && password !== $('confirmPassword').value) throw new Error('As senhas precisam ser iguais.'); // Evita cadastrar uma senha digitada incorretamente.
    if (DEMO) { user = {email,role:'aluno'}; await loggedIn(); resetLogin(); return; } // No demonstrador, toda conta digitada continua fictícia.
    await api(registerMode ? '/api/register' : '/api/login', {email,password}); // O servidor define o perfil e verifica a senha.
    user = await api('/api/me'); await loggedIn(); resetLogin(); // Entra direto após o cadastro ou a senha correta.
  });
};
function resetLogin() { // Remove as credenciais da tela depois do acesso.
  $('loginForm').reset(); setRegisterMode(false); // Volta ao modo padrão de entrada.
}
$('toggleRegister').onclick = () => setRegisterMode(!registerMode); // Permite criar somente contas de aluno pelo site.
$('forgotPassword').onclick = () => notify('Peça ao responsável pela instalação para redefinir sua senha pelo menu python ouvidoria.py --contas.'); // Não usa links ou códigos de recuperação por e-mail.
$('newTicket').onclick = () => { $('ticketForm').reset(); $('composeDialog').showModal(); }; // Abre um formulário limpo.
$('ticketForm').onsubmit = event => { // Envia uma manifestação.
  event.preventDefault(); // Preserva a navegação atual.
  busy(event.submitter, async () => { // Impede protocolos duplicados por clique repetido.
    const payload = Object.fromEntries(new FormData(event.currentTarget)); payload.anonymous = $('anonymous').checked; // Converte os campos e a escolha de anonimato.
    const result = await api('/api/tickets', payload); $('composeDialog').close(); await refresh(); showDetail(result.id); notify('Manifestação registrada. Guarde seu protocolo: ' + result.id); // Exibe confirmação e acompanhamento.
  });
};
$('replyForm').onsubmit = event => { // Envia uma resposta ou complemento.
  event.preventDefault(); // Mantém o protocolo aberto.
  busy(event.submitter, async () => { await api('/api/reply', {id:activeId,body:$('replyBody').value.trim()}); await refresh(); showDetail(activeId); notify('Mensagem enviada.'); }); // Atualiza o histórico após confirmação.
};
$('ticketList').onclick = event => { const card = event.target.closest('[data-ticket]'); if (card) showDetail(card.dataset.ticket); }; // Abre o cartão clicado.
$('search').oninput = renderList; $('statusFilter').onchange = renderList; $('sectorFilter').onchange = renderList; // Reaplica filtros ao editar os controles.
$('allTab').onclick = () => { archiveView = false; renderList(); }; // Volta à lista principal preservando os filtros.
$('archivedTab').onclick = () => { if (user?.role === 'aluno') return; archiveView = true; renderList(); }; // Permite consultar o arquivo somente na interface da equipe.
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close()); // Liga os botões de fechar às janelas.
if (DEMO) { // Configura somente o arquivo de demonstração.
  $('demoBanner').hidden = false; $('demoAccounts').hidden = false; $('loginButton').textContent = 'Explorar como aluno →'; $('password').required = false; // Identifica claramente a simulação.
  document.querySelectorAll('[data-demo]').forEach(button => button.onclick = () => busy(button, async () => {user = {email:demoEmails[button.dataset.demo],role:button.dataset.demo}; await loggedIn();})); // Permite explorar os três perfis fictícios.
} else { // Ao abrir pelo servidor, tenta recuperar uma sessão já validada.
  api('/api/me').then(async result => {user = result; await loggedIn();}).catch(error => { if (error.message && !error.message.includes('Entre com') && !error.message.includes('expirou')) notify(error.message, true); }); // Mostra a entrada se não houver sessão.
}

</script>
</body>
</html>
''',
    # Conteúdo comentado de configuracao.env.example.
    'configuracao.env.example': r'''# Configuração opcional: o site funciona sem SMTP e sem arquivo .env.
# Para testes locais, basta executar python ouvidoria.py.
APP_URL=http://localhost:8000
HOST=127.0.0.1
PORT=8000
# As contas de aluno, supervisor e diretor ficam no banco SQLite.
# Crie ou redefina contas pelo comando: python ouvidoria.py --contas
''',
    # Conteúdo comentado de LEIA-ME.md.
    'LEIA-ME.md': r'''# Ouvidoria Campo Real — login simples

Projeto em **Python 3.10 ou superior**, com código comentado e banco SQLite. Não precisa instalar bibliotecas, configurar Gmail, SMTP ou receber códigos por e-mail.

## Baixar e abrir

No GitHub, clique em **Code → Download ZIP** e extraia a pasta. Abra o terminal nessa pasta e execute:

```sh
python ouvidoria.py
```

No Windows, se necessário, use `py -3 ouvidoria.py`. Depois, abra **http://localhost:8000** no navegador. Para parar o programa, use **Ctrl+C**.

O arquivo `ouvidoria.py` já contém o servidor e os conteúdos das telas. A cópia `ouvidoria-python.txt` tem o mesmo conteúdo; pode ser renomeada para `.py` caso o download dessa extensão seja bloqueado.

## Alunos: criar conta e entrar

1. Na tela de acesso, clique em **Primeiro acesso? Criar conta de aluno**.
2. Digite um e-mail `@camporeal.edu.br`.
3. Escolha uma senha de **8 a 128 caracteres** e repita para confirmar.
4. Clique em **Criar minha conta**. O acesso acontece imediatamente.
5. Nas próximas visitas, use apenas e-mail e senha e clique em **Entrar**.

O campo de e-mail começa vazio, sem texto de exemplo. O cadastro público é sempre de **aluno**; não existe escolha de perfil administrativo no site.

**O domínio institucional é conferido, mas o sistema não comprova que a pessoa é dona do e-mail.** Esse é o limite da opção sem verificação por mensagem. Não use a informação como identidade institucional verificada.

## Criar supervisor e diretor

No computador em que o programa está instalado, pare o servidor com **Ctrl+C** e execute:

```sh
python ouvidoria.py --contas
```

O menu oferece:

- **1 — Criar conta:** informe e-mail institucional, escolha aluno, supervisor ou diretor e defina a senha duas vezes. A senha não aparece enquanto é digitada; isso é normal.
- **2 — Redefinir senha:** informe uma conta existente e uma nova senha. As sessões anteriores dessa conta serão encerradas.
- **3 — Listar contas:** mostra apenas os e-mails e os perfis, nunca senhas.
- **0 — Sair:** fecha o menu.

Depois, inicie novamente com `python ouvidoria.py`.

Crie as contas de equipe por esse menu, antes de tentar cadastrá-las no site. Existe somente **um diretor** no banco. O perfil é atribuído localmente; conhecer o e-mail da direção não permite receber privilégios por cadastro público. Não há senha padrão ou código mestre.

## Esqueci a senha

O aluno deve pedir ao responsável pela instalação para usar a opção **Redefinir senha** no menu `--contas`. Não há recuperação automática por e-mail e não é possível consultar a senha antiga, pois ela não é armazenada em texto simples.

## Atualizar uma instalação anterior

1. Pare o programa.
2. Faça uma cópia privada da pasta `data` com o serviço parado.
3. Substitua `ouvidoria.py` pela versão nova, **na mesma pasta**, mantendo `data`.
4. Execute `python ouvidoria.py --contas` e crie as contas necessárias, com os mesmos e-mails de quem já tem relatos.
5. Inicie o servidor novamente.

A primeira execução cria as tabelas de contas e encerra sessões/códigos antigos. **Os relatos, as respostas e a auditoria são preservados.** E-mails que já têm histórico da versão antiga não podem ser tomados pelo cadastro público: o responsável precisa criar a conta no menu local. A migração não repete o encerramento de sessões a cada reinício.

O `.env` antigo pode continuar na pasta, mas as opções SMTP não são usadas. `DIRECTOR_EMAIL` e `SUPERVISOR_EMAILS`, quando existentes, apenas reservam os antigos endereços contra cadastro público; não concedem perfis automaticamente. Crie as contas no menu local.

## Permissões e atendimento

- **Aluno:** cria reclamação, crítica, sugestão, elogio ou solicitação; consulta somente os próprios protocolos; lê respostas; envia complementos; confirma solução ou pede nova análise.
- **Supervisor:** atende e responde à fila, sem receber a autoria dos relatos anônimos.
- **Diretor:** atende como a equipe e pode consultar explicitamente a autoria anônima. Cada consulta fica registrada na tabela `audit`.

As situações são **Recebida**, **Em análise**, **Respondida** e **Resolvida**. O aluno pode confirmar a solução, e a equipe também pode concluir pelo botão **Resolver e arquivar**. O aluno mantém a opção de pedir nova análise. Respostas e mudanças de situação ficam no histórico. O aluno acompanha pelo painel, sem notificações automáticas por e-mail.

**Anonimato significa identidade oculta para o atendimento, com consulta pelo diretor na aplicação.** O cadastro e o login continuam obrigatórios. Se a pessoa escrever nome ou e-mail no relato, esse texto ficará visível. Quem administra o computador ou o banco também pode acessar os arquivos; restrinja o acesso à infraestrutura.

## Filtro por área e manifestações arquivadas

Supervisor e diretor têm um seletor **Todas as áreas**, no qual podem escolher Infraestrutura, Financeiro, Secretaria e as demais áreas do formulário. O filtro combina com a busca por assunto/protocolo e com a situação, tanto na lista principal quanto na aba **Arquivadas**. Trocar de aba mantém os filtros escolhidos. É um filtro de consulta da fila autorizada, não uma restrição de acesso por departamento.

Na aba **Todas as manifestações**, a equipe vê os protocolos que ainda não foram arquivados. Para concluir um atendimento, abra o protocolo e clique em **Resolver e arquivar**. Essa ação muda a situação para **Resolvida**, tira o registro da lista principal e o coloca em **Arquivadas**. A confirmação de solução pelo aluno também arquiva o protocolo para a equipe.

Na aba **Arquivadas**, supervisor e diretor podem consultar o histórico e usar **Desarquivar e retomar atendimento**. A situação volta para **Em análise** e o registro reaparece na lista principal. A equipe precisa retomar o atendimento antes de enviar outra resposta pela interface. O aluno continua vendo os próprios protocolos, inclusive os arquivados; se pedir nova análise ou escrever outra mensagem, o protocolo volta ao atendimento automaticamente.

Arquivar não exclui dados e não altera a proteção da autoria anônima. A autoria permanece indisponível para o supervisor; o diretor precisa usar a consulta restrita. Ações de resolver/arquivar e desarquivar pelo atendimento ficam no histórico e na auditoria, com conta responsável e data.

A tabela `tickets` recebeu o campo `archived`, inteiro restrito a 0 ou 1. A migração acrescenta esse campo aos bancos existentes sem apagar relatos ou respostas, e coloca os protocolos anteriormente resolvidos no arquivo. A situação e a marca de arquivamento são atualizadas na mesma transação. Faça backup com o serviço parado antes de substituir o programa, mantenha a pasta `data` e reinicie. Não é necessário cadastrar novamente as contas da versão que já usava senha.

## Demonstração sem contas reais

Abra `DEMONSTRACAO.html` com dois cliques ou execute:

```sh
python ouvidoria.py --demo
```

Os botões de aluno, supervisor e diretor usam dados fictícios armazenados no navegador. Não coloque informações pessoais na demonstração. O demonstrador não representa a segurança da API real.

## Configuração opcional

O programa funciona localmente sem `.env`. Se precisar mudar endereço ou porta, gere o modelo com `python ouvidoria.py --configurar`, copie `.env.example` para `.env` e ajuste os valores. Não é necessário preencher parâmetros de e-mail.

O banco fica em `data/ouvidoria.sqlite3`. Não publique `.env` nem `data` no GitHub; ambos estão no `.gitignore`. Não mude `DATABASE_PATH` se quiser continuar usando o banco atual.

As senhas usam PBKDF2-HMAC-SHA256, com sal aleatório e 600 mil iterações. Os cookies de sessão são HttpOnly, SameSite e Secure quando o endereço usa HTTPS. Alterações exigem token CSRF e origem compatível com `APP_URL`. Há limites de tentativas por conta e IP. O menu de contas é local, não uma rota pública do site.

Para uso na faculdade, a TI precisa instalar o programa em servidor persistente e colocar um proxy reverso HTTPS à frente dele. O servidor HTTP da biblioteca padrão foi escolhido para simplificar a instalação e deve ficar atrás desse proxy. Ajuste limites por IP para redes compartilhadas e proxy, pois o programa considera a conexão direta e não confia em `X-Forwarded-For`. Defina privacidade, retenção e backups antes de coletar relatos reais.

## Telas e marcas

HTML, CSS e JavaScript são os conteúdos recebidos pelo navegador e estão embutidos no dicionário `ASSETS`, dentro do Python. O servidor, a autenticação, as permissões e o banco são implementados em Python.

As marcas são reproduções vetoriais de referência das imagens fornecidas, não os arquivos originais. Antes da publicação oficial, substitua os SVGs azul e branco em `ASSETS`. O demonstrador contém cópias próprias que também precisam ser atualizadas.

## Testes

```sh
python -m unittest discover -s tests -v
```

Os testes usam banco temporário e verificam cadastro/login sem SMTP, domínio institucional, senha incorreta, bloqueio de tentativas, hashes, perfis, diretor único, recuperação local, migração, isolamento dos protocolos, autoria restrita, auditoria, respostas, solução/reabertura, CSRF, logout, migração de arquivamento, conclusão pela equipe, histórico arquivado e retomada pelo aluno. Os filtros de área, aba, busca e situação também foram verificados em conjunto. As telas precisam de conferência visual em computador e celular antes da publicação.
''',
}

ROOT = Path(__file__).parent  # Localiza a pasta do projeto.
config = ROOT / '.env'  # Localiza as configurações privadas ao lado deste arquivo.
if config.exists():  # Carrega parâmetros somente se o arquivo foi criado pelo responsável.
    for line in config.read_text(encoding='utf-8-sig').splitlines():  # Percorre as configurações.
        line = line.strip()  # Remove espaços externos.
        if not line or line.startswith('#'):  # Ignora linhas vazias e comentários.
            continue
        key, separator, value = line.partition('=')  # Separa o nome e o valor da configuração.
        if separator:  # Aceita linhas no formato NOME=valor.
            value = value.strip()  # Remove espaços externos sem alterar a senha internamente.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):  # Aceita valores entre aspas no .env.
                value = value[1:-1]  # Retira somente as aspas que envolvem o valor inteiro.
            os.environ.setdefault(key.strip(), value)  # Respeita as variáveis já definidas no sistema.
DB = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'ouvidoria.sqlite3')))  # Banco fora da pasta pública.
APP_URL = os.getenv('APP_URL', 'http://localhost:8000').rstrip('/')  # Origem permitida.
DIRECTOR = os.getenv('DIRECTOR_EMAIL', '').strip().lower()  # Somente uma conta recebe o perfil diretor.
SUPERVISORS = {x.strip().lower() for x in os.getenv('SUPERVISOR_EMAILS', '').split(',') if x.strip()}  # Equipe autorizada.
INSTITUTIONAL = re.compile(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@camporeal\.edu\.br', re.ASCII)  # Exige o domínio exato.
TYPES = {'Reclamação', 'Crítica', 'Sugestão', 'Elogio', 'Solicitação'}  # Tipos aceitos.
STATUSES = {'Recebida', 'Em análise', 'Respondida', 'Resolvida'}  # Situações aceitas.


@contextmanager  # Permite abrir, confirmar e fechar uma conexão com a instrução with.
def database():
    connection = sqlite3.connect(DB, timeout=15)  # Abre uma conexão por requisição.
    connection.row_factory = sqlite3.Row  # Permite acessar as colunas pelo nome.
    connection.execute('PRAGMA foreign_keys=ON')  # Mantém os relacionamentos válidos.
    try:
        with connection:  # Confirma ao terminar ou desfaz se houver erro.
            yield connection  # Disponibiliza a conexão para esta operação.
    finally:
        connection.close()  # Libera o arquivo e os recursos em todos os caminhos.


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)  # Cria a pasta de dados.
    os.chmod(DB.parent, 0o700)  # Restringe a pasta ao usuário do servidor.
    with database() as db:  # Confirma todas as alterações de estrutura juntas.
        db.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(email TEXT PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('aluno','supervisor','diretor')), created REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_director ON accounts(role) WHERE role='diretor';
        CREATE TABLE IF NOT EXISTS auth_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires REAL NOT NULL, csrf TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, email TEXT NOT NULL, anonymous INTEGER NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL, sector TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)));
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ticket TEXT NOT NULL REFERENCES tickets(id), author TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, ticket TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, hits INTEGER NOT NULL, reset REAL NOT NULL);
        ''')  # Cria autenticação, manifestações, histórico e auditoria.
        if not db.execute("SELECT 1 FROM auth_meta WHERE key='password_auth_v1'").fetchone():
            db.execute('DELETE FROM sessions')  # Encerra os acessos antigos por código somente na primeira migração.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='codes'").fetchone():
                db.execute('DELETE FROM codes')  # Invalida códigos de e-mail antigos sem remover relatos ou auditorias.
            db.execute("INSERT INTO auth_meta VALUES ('password_auth_v1','1')")  # Evita repetir a migração a cada reinício.
        columns = {row['name'] for row in db.execute('PRAGMA table_info(tickets)')}  # Detecta bancos criados antes da aba de arquivo.
        if 'archived' not in columns:
            db.execute('ALTER TABLE tickets ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))')  # Acrescenta o campo sem apagar relatos, mensagens ou autoria.
        if not db.execute("SELECT 1 FROM auth_meta WHERE key='archive_v1'").fetchone():
            db.execute("UPDATE tickets SET archived=1 WHERE status='Resolvida'")  # Coloca solicitações já resolvidas no arquivo da equipe.
            db.execute("INSERT INTO auth_meta VALUES ('archive_v1','1')")  # Executa essa organização somente uma vez.
    os.chmod(DB, 0o600)  # Restringe a leitura do arquivo de banco.


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()  # Não guarda códigos nem cookies em texto simples.


PASSWORD_ITERATIONS = 600000  # Aumenta o custo de adivinhar senhas a partir do banco.


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PASSWORD_ITERATIONS).hex()  # Nunca guarda a senha em texto simples.


def check_password(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
        raise ValueError('A senha precisa ter entre 8 e 128 caracteres e não pode conter apenas espaços.')  # Usa a mesma regra no site e no menu local.


def insert_account(db, email, password, profile):
    if not INSTITUTIONAL.fullmatch(email) or profile not in ('aluno', 'supervisor', 'diretor'):
        raise ValueError('Use um e-mail @camporeal.edu.br e um perfil válido.')  # Valida as contas criadas pelo responsável.
    check_password(password)  # Rejeita senhas curtas ou vazias.
    salt = secrets.token_hex(16)  # Gera um sal diferente para cada conta.
    db.execute('INSERT INTO accounts VALUES (?,?,?,?,?)', (email, salt, password_hash(password, salt), profile, time.time()))  # O perfil é determinado pelo servidor ou pelo operador local.


def role(email):
    with database() as db:
        account = db.execute('SELECT role FROM accounts WHERE email=?', (email,)).fetchone()  # Consulta o perfil atribuído pelo responsável.
        if not account:
            raise Error(401, 'Entre com seu e-mail e senha para continuar.')  # Não aceita sessões sem conta cadastrada.
        return account['role']  # O usuário não pode escolher outro perfil pela API.


def manage_accounts():
    initialize()  # Prepara as tabelas antes de abrir o menu local.
    while True:
        print('\nCONTAS DA OUVIDORIA\n1 - Criar conta\n2 - Redefinir senha\n3 - Listar contas\n0 - Sair')  # Oferece gerenciamento sem SMTP ou painel extra.
        option = input('Escolha: ').strip()  # Lê uma opção no terminal da instalação.
        if option == '0':
            return  # Volta ao terminal sem iniciar o servidor.
        try:
            if option == '3':
                with database() as db:
                    for row in db.execute('SELECT email,role FROM accounts ORDER BY role,email'):
                        print(row['role'] + ': ' + row['email'])  # Lista contas sem mostrar senhas ou hashes.
                continue
            if option not in ('1', '2'):
                print('Escolha uma das opções do menu.')
                continue
            email = input('E-mail @camporeal.edu.br: ').strip().lower()  # Identifica a conta a criar ou recuperar.
            profile = {'1': 'aluno', '2': 'supervisor', '3': 'diretor'}.get(input('Perfil: 1-aluno, 2-supervisor, 3-diretor: ').strip()) if option == '1' else None  # Perfil só é escolhido no terminal local.
            password = getpass.getpass('Nova senha (mínimo 8 caracteres): ')  # Oculta a senha durante a digitação.
            if password != getpass.getpass('Repita a senha: '):
                raise ValueError('As senhas não são iguais.')
            check_password(password)  # Valida antes de gravar qualquer alteração.
            with database() as db:
                if option == '1':
                    insert_account(db, email, password, profile)  # Permite ao operador provisionar as contas com segurança.
                else:
                    salt = secrets.token_hex(16)  # Gera um novo sal para a senha redefinida.
                    changed = db.execute('UPDATE accounts SET salt=?,hash=? WHERE email=?', (salt, password_hash(password, salt), email)).rowcount  # Mantém o perfil e o histórico existentes.
                    if not changed:
                        raise ValueError('Conta não encontrada. Use a opção criar conta, caso ainda não exista.')
                    db.execute('DELETE FROM sessions WHERE email=?', (email,))  # Invalida todas as sessões anteriores após a recuperação.
            print('Conta criada.' if option == '1' else 'Senha redefinida; os acessos anteriores foram encerrados.')
        except sqlite3.IntegrityError:
            print('Essa conta já existe ou já há um diretor cadastrado. É permitido somente um diretor.')  # Não exibe detalhes internos do banco.
        except ValueError as error:
            print(str(error))  # Exibe somente validações locais, sem mostrar senhas.


class Error(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message  # Guarda uma falha que pode ser exibida ao usuário.


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Não registra URLs, e-mails, códigos ou conteúdo das manifestações.

    def send(self, status, payload, cookie=None):
        data = json.dumps(payload, ensure_ascii=False).encode()  # Codifica o resultado em UTF-8.
        self.send_response(status)  # Define o status HTTP.
        self.send_header('Content-Type', 'application/json; charset=utf-8')  # Declara o formato JSON.
        self.send_header('Content-Length', str(len(data)))  # Informa o tamanho da resposta.
        self.send_header('Cache-Control', 'no-store')  # Evita guardar dados privados em cache.
        self.send_header('X-Content-Type-Options', 'nosniff')  # Impede interpretação de outro formato.
        if cookie:  # Atualiza o cookie somente no login e no logout.
            self.send_header('Set-Cookie', cookie)
        self.end_headers()  # Finaliza os cabeçalhos.
        self.wfile.write(data)  # Envia a resposta ao navegador.

    def success(self, db, status, payload, cookie=None):
        db.commit()  # Confirma a gravação antes de informar sucesso ou revelar a autoria ao navegador.
        return self.send(status, payload, cookie)  # Só responde depois da persistência, inclusive da auditoria.

    def cookie(self, value, age):
        secure = '; Secure' if APP_URL.startswith('https://') else ''  # Exige HTTPS no ambiente publicado.
        return f'cr_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}'  # Impede leitura via JavaScript.

    def session(self, db):
        cookies = SimpleCookie()  # Prepara o interpretador de cookies.
        try:
            cookies.load(self.headers.get('Cookie', ''))  # Lê a sessão enviada pelo navegador.
            token = cookies['cr_session'].value  # Extrai o identificador secreto.
        except (KeyError, ValueError):
            raise Error(401, 'Entre com seu e-mail institucional para continuar.')  # Bloqueia visitantes.
        row = db.execute('SELECT sessions.* FROM sessions JOIN accounts ON accounts.email=sessions.email WHERE sessions.hash=? AND sessions.expires>?', (digest(token), time.time())).fetchone()  # Busca uma sessão válida.
        if not row:  # Rejeita sessões inexistentes ou expiradas.
            raise Error(401, 'Sua sessão expirou. Entre novamente.')
        return dict(row)  # Retorna a identidade validada no servidor.

    def limit(self, db, key, maximum, window):
        now = time.time()  # Obtém o horário atual.
        db.execute('DELETE FROM limits WHERE reset<?', (now,))  # Remove contadores expirados.
        db.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET hits=hits+1', (key, now + window))  # Conta tentativas.
        count = db.execute('SELECT hits FROM limits WHERE key=?', (key,)).fetchone()[0]  # Consulta o total.
        db.commit()  # Persiste o limite mesmo se a requisição for rejeitada.
        if count > maximum:  # Protege contra excesso de solicitações.
            raise Error(429, 'Muitas tentativas. Aguarde alguns minutos e tente novamente.')

    def text(self, data, key, minimum=1, maximum=5000):
        value = data.get(key, '')  # Lê o campo solicitado.
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:  # Valida tipo e tamanho.
            raise Error(400, f'Preencha corretamente o campo {key} ({minimum} a {maximum} caracteres).')
        return value.strip()  # Remove espaços externos.

    def do_GET(self):
        path = urlparse(self.path).path  # Desconsidera parâmetros de consulta.
        try:
            if path.startswith('/api/'):  # Encaminha chamadas privadas para a API.
                with database() as db:
                    session = self.session(db)  # Todas as consultas exigem autenticação.
                    email = session['email']  # Usa a identidade do cookie validado.
                    profile = role(email)  # Calcula o perfil no servidor.
                    if path == '/api/me':
                        return self.send(200, {'email': email, 'role': profile, 'csrf': session['csrf']})  # Devolve dados da própria sessão.
                    if path == '/api/tickets':
                        query = 'SELECT * FROM tickets' + (' WHERE email=?' if profile == 'aluno' else '') + ' ORDER BY created DESC'  # Aluno vê apenas seus protocolos.
                        rows = db.execute(query, (email,) if profile == 'aluno' else ()).fetchall()  # Consulta parametrizada.
                        tickets = []  # Prepara uma lista sem identidades restritas.
                        for row in rows:
                            ticket = dict(row)  # Copia os dados da manifestação.
                            owner = ticket.pop('email')  # Remove o campo privado em todos os perfis antes de montar a resposta.
                            ticket['identity'] = owner if not ticket['anonymous'] or profile == 'aluno' else None  # Nunca envia a autoria anônima à equipe.
                            ticket['messages'] = [dict(m) for m in db.execute('SELECT author,body,created FROM messages WHERE ticket=? ORDER BY id', (ticket['id'],))]  # Inclui histórico público da conversa.
                            tickets.append(ticket)  # Adiciona o protocolo já filtrado.
                        return self.send(200, tickets)  # Envia somente dados autorizados.
                    raise Error(404, 'Recurso não encontrado.')  # Rejeita outras rotas de API.
            paths = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/assets/logo-azul.svg': 'assets/logo-azul.svg', '/assets/logo-branca.svg': 'assets/logo-branca.svg'}  # Lista fechada impede acesso ao banco e ao código do servidor.
            if path not in paths:
                raise Error(404, 'Página não encontrada.')  # Não permite navegar pelo sistema de arquivos.
            filename = paths[path]  # Localiza somente um dos conteúdos públicos autorizados.
            mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml'}[Path(filename).suffix]  # Define o tipo correto pela extensão.
            data = ASSETS[filename].encode('utf-8')  # Entrega o conteúdo embutido sem depender de pastas externas.
            self.send_response(200)  # Informa que o arquivo existe.
            self.send_header('Content-Type', mime + '; charset=utf-8')  # Usa UTF-8.
            self.send_header('Content-Length', str(len(data)))  # Informa o tamanho.
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")  # Restringe scripts e incorporação em outros sites.
            self.send_header('X-Content-Type-Options', 'nosniff')  # Impede interpretação incorreta.
            self.send_header('Referrer-Policy', 'no-referrer')  # Não envia origem de navegação a terceiros.
            self.end_headers()  # Conclui os cabeçalhos.
            self.wfile.write(data)  # Entrega o arquivo.
        except Error as error:
            self.send(error.status, {'error': error.message})  # Responde a falhas previstas.
        except Exception:
            self.send(500, {'error': 'Não foi possível carregar os dados.'})  # Não expõe detalhes internos.

    def do_POST(self):
        try:
            if self.headers.get('Origin') != APP_URL:  # Exige a origem configurada, inclusive atrás do proxy.
                raise Error(403, 'Origem da solicitação não autorizada.')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':  # Recusa formulários externos.
                raise Error(415, 'Envie dados no formato JSON.')
            length = int(self.headers.get('Content-Length', '0'))  # Lê o tamanho declarado.
            if not 0 < length <= 24000:  # Limita a carga enviada.
                raise Error(413, 'Solicitação muito grande ou vazia.')
            data = json.loads(self.rfile.read(length))  # Interpreta o JSON.
            if not isinstance(data, dict):
                raise Error(400, 'Dados inválidos.')  # Exige um objeto de campos.
            path = urlparse(self.path).path  # Identifica a operação.
            now = time.time()  # Usa o mesmo horário na operação.
            with database() as db:
                if path in ('/api/login', '/api/register'):
                    self.limit(db, 'auth-ip:' + self.client_address[0], 60, 600)  # Limita cadastros e tentativas antes de calcular o hash.
                    email = self.text(data, 'email', 1, 254).lower()  # Normaliza o endereço institucional.
                    if not INSTITUTIONAL.fullmatch(email):
                        raise Error(400, 'Use seu e-mail @camporeal.edu.br.')  # Exige o domínio completo, sem sufixos parecidos.
                    self.limit(db, 'auth-email:' + email, 15, 600)  # Limita tentativas para a mesma conta.
                    password = data.get('password')  # Não remove espaços de senhas escolhidas pelo usuário.
                    try:
                        check_password(password)  # Aplica o mesmo tamanho permitido em cadastro e acesso.
                    except ValueError as error:
                        raise Error(400, str(error)) from None
                    if path == '/api/register':
                        db.execute('BEGIN IMMEDIATE')  # Serializa a verificação e o cadastro da conta.
                        exists = db.execute('SELECT 1 FROM accounts WHERE email=?', (email,)).fetchone()  # Impede sobrescrever contas existentes.
                        legacy = db.execute('SELECT 1 FROM tickets WHERE email=? LIMIT 1', (email,)).fetchone()  # Protege relatos de usuários da versão anterior.
                        if exists or legacy or email == DIRECTOR or email in SUPERVISORS:
                            raise Error(409, 'Conta existente ou reservada. Entre com sua senha ou peça ao responsável para criar ou recuperar a conta.')
                        insert_account(db, email, password, 'aluno')  # Ignora qualquer perfil enviado pelo navegador; cadastro público é sempre aluno.
                    else:
                        account = db.execute('SELECT * FROM accounts WHERE email=?', (email,)).fetchone()  # Busca o hash da conta solicitada.
                        salt = account['salt'] if account else '0' * 32  # Usa um cálculo equivalente para endereços não cadastrados.
                        candidate = password_hash(password, salt)  # Confere a senha sem armazená-la.
                        if not account or not hmac.compare_digest(account['hash'], candidate):
                            raise Error(401, 'E-mail ou senha incorretos. No primeiro acesso, crie sua conta de aluno.')  # Não distingue senha errada de conta inexistente.
                    db.execute('DELETE FROM sessions WHERE expires<?', (now,))  # Remove sessões antigas.
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)  # Gera segredos novos após cada autenticação.
                    db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), email, now + 28800, csrf))  # Mantém o acesso por oito horas.
                    return self.success(db, 201 if path == '/api/register' else 200, {'ok': True}, self.cookie(token, 28800))  # Confirma a transação antes de autenticar o navegador.
                session = self.session(db)  # Exige login para as operações seguintes.
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                    raise Error(403, 'Atualize a página e tente novamente.')  # Impede uso de sessão sem token CSRF.
                email, profile = session['email'], role(session['email'])  # Recupera a identidade real.
                if path == '/api/logout':
                    db.execute('DELETE FROM sessions WHERE hash=?', (session['hash'],))  # Invalida a sessão no banco.
                    return self.success(db, 200, {'ok': True}, self.cookie('', 0))  # Remove o cookie do navegador.
                self.limit(db, 'write:' + email, 60, 600)  # Limita operações autenticadas.
                if path == '/api/tickets':
                    if profile != 'aluno':
                        raise Error(403, 'Use uma conta de aluno para registrar uma manifestação.')
                    subject, body = self.text(data, 'subject', 5, 120), self.text(data, 'body', 20, 5000)  # Valida o relato.
                    kind, sector = self.text(data, 'kind', 1, 30), self.text(data, 'sector', 1, 80)  # Valida os campos auxiliares.
                    if kind not in TYPES or type(data.get('anonymous')) is not bool:
                        raise Error(400, 'Tipo ou identificação inválidos.')
                    ticket_id = 'CR-' + time.strftime('%Y') + '-' + secrets.token_hex(4).upper()  # Cria protocolo não sequencial.
                    db.execute('INSERT INTO tickets(id,email,anonymous,kind,subject,sector,body,status,created) VALUES (?,?,?,?,?,?,?,?,?)', (ticket_id, email, int(data['anonymous']), kind, subject, sector, body, 'Recebida', now))  # Associa a autoria somente no servidor.
                    return self.success(db, 201, {'id': ticket_id})  # Informa o protocolo gerado.
                ticket_id = self.text(data, 'id', 1, 40)  # Identifica o protocolo solicitado.
                ticket = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()  # Busca a manifestação.
                if not ticket or (profile == 'aluno' and ticket['email'] != email):
                    raise Error(404, 'Manifestação não encontrada.')  # Não revela existência de registros alheios.
                if path == '/api/archive':
                    if profile not in ('supervisor', 'diretor'):
                        raise Error(403, 'Somente supervisor e diretor podem resolver e arquivar pelo atendimento.')  # O aluno não controla o arquivo da equipe por esta rota.
                    archived = data.get('archived')  # Lê uma escolha booleana, sem aceitar textos como verdadeiro.
                    if type(archived) is not bool:
                        raise Error(400, 'Informe se deseja arquivar ou desarquivar.')
                    if bool(ticket['archived']) == archived:
                        return self.success(db, 200, {'ok': True})  # Repetir o mesmo pedido não duplica o histórico.
                    status = 'Resolvida' if archived else 'Em análise'  # Toda conclusão pelo atendimento arquiva; toda retomada volta à fila.
                    db.execute('UPDATE tickets SET archived=?,status=? WHERE id=?', (int(archived), status, ticket_id))  # Grava situação e arquivo na mesma transação.
                    message = 'Manifestação resolvida e arquivada pelo atendimento.' if archived else 'Manifestação desarquivada e devolvida para análise pelo atendimento.'
                    db.execute('INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)', (ticket_id, 'Sistema', message, now))  # O aluno vê o andamento sem dados internos da equipe.
                    db.execute('INSERT INTO audit(actor,action,ticket,created) VALUES (?,?,?,?)', (email, 'Resolver e arquivar' if archived else 'Desarquivar', ticket_id, now))  # Registra qual conta realizou a ação.
                    return self.success(db, 200, {'ok': True})
                if path == '/api/identity':
                    if profile != 'diretor':
                        raise Error(403, 'Somente o diretor pode consultar a autoria restrita.')
                    db.execute('INSERT INTO audit(actor,action,ticket,created) VALUES (?,?,?,?)', (email, 'Consulta de autoria restrita', ticket_id, now))  # Registra cada acesso do diretor.
                    return self.success(db, 200, {'email': ticket['email']})  # Revela somente na consulta explícita e autorizada.
                if path == '/api/reply':
                    body = self.text(data, 'body', 3, 5000)  # Valida o texto da resposta.
                    db.execute('INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)', (ticket_id, 'Aluno' if profile == 'aluno' else 'Ouvidoria Campo Real', body, now))  # Preserva o anonimato do autor nas mensagens.
                    if ticket['archived']:
                        db.execute('INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)', (ticket_id, 'Sistema', 'Manifestação desarquivada após nova mensagem.', now))  # Evita deixar uma nova solicitação escondida no arquivo.
                    if profile != 'aluno':
                        db.execute('UPDATE tickets SET status=?,archived=0 WHERE id=?', ('Respondida', ticket_id))  # Sinaliza a nova resposta institucional.
                    elif ticket['status'] in ('Respondida', 'Resolvida'):
                        db.execute('UPDATE tickets SET status=?,archived=0 WHERE id=?', ('Em análise', ticket_id))  # Reabre a análise quando o aluno volta a se manifestar.
                    return self.success(db, 200, {'ok': True})
                if path == '/api/status':
                    status = self.text(data, 'status', 1, 30)  # Lê a nova situação.
                    allowed = {'Resolvida', 'Em análise'} if profile == 'aluno' else {'Em análise', 'Respondida'}  # A equipe conclui pelo botão específico de resolver e arquivar.
                    if status not in allowed or (status == 'Respondida' and not db.execute("SELECT 1 FROM messages WHERE ticket=? AND author='Ouvidoria Campo Real'", (ticket_id,)).fetchone()):
                        raise Error(400, 'Alteração de situação não permitida.')
                    db.execute('UPDATE tickets SET status=?,archived=? WHERE id=?', (status, int(status == 'Resolvida'), ticket_id))  # Atualiza o andamento.
                    db.execute('INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)', (ticket_id, 'Sistema', f'Situação alterada para {status.lower()} pelo ' + ('aluno.' if profile == 'aluno' else 'atendimento.'), now))  # Mantém o histórico.
                    return self.success(db, 200, {'ok': True})
                raise Error(404, 'Operação não encontrada.')
        except Error as error:
            self.send(error.status, {'error': error.message})  # Exibe erros esperados de forma simples.
        except (ValueError, TypeError):
            self.send(400, {'error': 'Confira os dados enviados.'})  # Rejeita JSON e tipos inválidos.
        except Exception:
            self.send(500, {'error': 'Não foi possível concluir. Tente novamente.'})  # Oculta detalhes do banco e do servidor.


if __name__ == '__main__':
    import sys  # Lê a opção escolhida no terminal.
    if len(sys.argv) > 1:  # Processa os atalhos sem iniciar o servidor real.
        option = sys.argv[1]  # Identifica a opção solicitada.
        if option in ('--ajuda', '--help', '-h'):  # Disponibiliza instruções sem conexão externa.
            print(__doc__)  # Mostra a ajuda incluída no início do programa.
            raise SystemExit(0)  # Finaliza normalmente.
        if option == '--contas':  # Permite criar equipe ou redefinir senhas apenas no computador responsável pela instalação.
            try:
                manage_accounts()  # Abre o menu local sem exigir credenciais SMTP.
            except (EOFError, KeyboardInterrupt):
                print('\nMenu encerrado.')  # Sai sem expor rastreamentos ao interromper a digitação.
            raise SystemExit(0)
        if option == '--configurar':  # Cria o modelo de configuração sem sobrescrever credenciais existentes.
            target = ROOT / '.env.example'  # Define o nome do modelo.
            if not target.exists():  # Preserva modelos que já tenham sido editados.
                target.write_text(ASSETS['configuracao.env.example'], encoding='utf-8')  # Grava os parâmetros necessários.
            print('Modelo disponível em:', target)  # Explica onde encontrar as opções.
            print('Configuração opcional de endereço e porta. Não é necessário configurar SMTP.')  # Orienta a instalação.
            raise SystemExit(0)  # Não inicia o servidor antes da configuração.
        if option == '--demo':  # Mostra somente uma prévia com contas e relatos fictícios.
            import webbrowser  # Abre o navegador padrão do computador.
            target = ROOT / 'DEMONSTRACAO.html'  # Define o arquivo local da demonstração.
            target.write_text(ASSETS['DEMONSTRACAO.html'], encoding='utf-8')  # Gera uma página independente de servidor.
            print('Demonstração fictícia salva em:', target)  # Informa a localização caso o navegador não abra.
            webbrowser.open(target.resolve().as_uri())  # Abre a página local para explorar os perfis.
            raise SystemExit(0)  # Não cria sessão, banco ou acesso de produção.
        raise SystemExit('Opção desconhecida. Use --ajuda, --demo, --configurar ou --contas.')  # Rejeita argumentos digitados por engano.
    initialize()  # Prepara o banco na primeira execução.
    host, port = os.getenv('HOST', '127.0.0.1'), int(os.getenv('PORT', '8000'))  # Escuta apenas no computador local por padrão.
    print('Para criar supervisor/diretor ou redefinir senha: python ouvidoria.py --contas')  # Orienta o responsável pela instalação.
    print(f'Ouvidoria disponível em {APP_URL}. Use Ctrl+C para parar.')  # Não imprime segredos.
    ThreadingHTTPServer((host, port), Handler).serve_forever()  # Mantém o servidor ativo.
