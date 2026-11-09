"""OUVIDORIA CAMPO REAL — PROJETO EM UM ÚNICO ARQUIVO PYTHON

Requer Python 3.10 ou superior. Não requer instalar bibliotecas.

Executar o sistema:          python ouvidoria.py
Ver a demonstração:          python ouvidoria.py --demo
Gerar arquivo de parâmetros: python ouvidoria.py --configurar
Testar configuração SMTP:    python ouvidoria.py --testar-smtp
Ver estas instruções:        python ouvidoria.py --ajuda

Depois de executar, abra http://localhost:8000 no navegador.
Para login real, configure o envio SMTP e as contas autorizadas no .env.
O servidor, o banco, o login e as permissões são implementados em Python.
HTML, CSS e JavaScript são os conteúdos entregues por Python ao navegador.
Todo o conteúdo está embutido neste arquivo, de forma legível e comentada.

Anonimato: supervisores não recebem a identidade; somente o diretor pode
consultá-la, com auditoria. O login institucional continua obrigatório.
As logos são reproduções vetoriais de referência, conforme o guia anterior.
A demonstração é fictícia e não deve receber dados reais.
"""
import hashlib  # Calcula hashes dos códigos e das sessões.
import hmac  # Compara hashes sem revelar diferenças de tempo.
import json  # Converte dados entre JSON e objetos Python.
import os  # Lê configurações do ambiente.
import re  # Valida o endereço institucional completo.
import secrets  # Gera códigos, protocolos e sessões imprevisíveis.
import smtplib  # Envia os códigos de acesso por e-mail.
import sqlite3  # Persiste os registros em banco de dados local.
import ssl  # Protege a conexão com o servidor de e-mail.
import time  # Controla expiração e limites de acesso.
from contextlib import contextmanager  # Garante fechamento das conexões ao banco.
from email.message import EmailMessage  # Monta o e-mail de autenticação.
from http.cookies import SimpleCookie  # Interpreta o cookie de sessão.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # Atende HTTP.
from pathlib import Path  # Trabalha com caminhos de arquivos.
from urllib.parse import urlparse  # Separa o caminho da URL.


# Os arquivos abaixo ficam dentro do próprio programa Python.
ASSETS = {
    # Conteúdo de app.js; mantém os comentários para facilitar o estudo.
    'app.js': r''''use strict'; // Evita variáveis criadas por engano.
const $ = id => document.getElementById(id); // Facilita localizar elementos pelo identificador.
const DEMO = location.protocol === 'file:'; // Ativa o demonstrador somente quando o arquivo é aberto diretamente.
const statuses = ['Recebida', 'Em análise', 'Respondida', 'Resolvida']; // Define a ordem das situações.
const demoEmails = {aluno:'aluno.exemplo@camporeal.edu.br',supervisor:'supervisor.exemplo@camporeal.edu.br',diretor:'diretor.exemplo@camporeal.edu.br'}; // Contas fictícias, sem validade no servidor.
let user = null, tickets = [], activeId = null, codeSent = false, toastTimer; // Guarda o estado da tela, sem armazenar a sessão real.
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
  const list = demoData(); // Recupera os protocolos locais.
  if (path === '/api/tickets' && !data) return list.filter(t => user.role !== 'aluno' || t.email === user.email).map(t => ({...t,identity:!t.anonymous || user.role === 'aluno' ? t.email : null,email:undefined})); // Oculta dados no fluxo de demonstração.
  if (path === '/api/tickets') { // Registra um exemplo de manifestação.
    const item = {...data,id:'CR-DEMO-' + Math.random().toString(16).slice(2,10).toUpperCase(),email:user.email,created:Date.now()/1000,status:'Recebida',messages:[]}; // Associa a conta fictícia.
    list.unshift(item); saveDemo(list); return {id:item.id}; // Persiste o exemplo.
  }
  const item = list.find(t => t.id === data.id); // Localiza o protocolo selecionado.
  if (!item) throw new Error('Protocolo não encontrado.'); // Trata exemplos removidos.
  if (path === '/api/identity') { if(user.role !== 'diretor') throw new Error('Somente o diretor pode consultar.'); return {email:item.email}; } // Demonstra a consulta restrita.
  if (path === '/api/reply') { item.messages.push({author:user.role === 'aluno' ? 'Aluno' : 'Ouvidoria Campo Real',body:data.body,created:Date.now()/1000}); item.status = user.role === 'aluno' ? 'Em análise' : 'Respondida'; } // Acrescenta uma mensagem fictícia.
  if (path === '/api/status') { item.status = data.status; item.messages.push({author:'Sistema',body:'Situação alterada para ' + data.status.toLowerCase() + '.',created:Date.now()/1000}); } // Registra o andamento do exemplo.
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
  user = null; tickets = []; activeId = null; // Descarta dados privados da memória da tela.
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
  $('newTicket').hidden = !student; // Restringe a criação ao perfil de aluno na interface.
  $('account').innerHTML = `<strong>${escapeHTML(user.role)}</strong><span>${escapeHTML(user.email)}</span> <button class="text-button" id="logout" type="button">Sair</button>`; // Mostra os dados da própria sessão.
  $('logout').onclick = event => busy(event.currentTarget, async () => {await api('/api/logout', {}); loggedOut();}); // Invalida a sessão no servidor.
  await refresh(); // Busca as manifestações autorizadas.
}
async function refresh() { // Atualiza os protocolos e os indicadores.
  tickets = await api('/api/tickets'); // Recebe apenas registros permitidos pelo servidor.
  $('stats').innerHTML = [['Total de manifestações',tickets.length],['Em atendimento',tickets.filter(t => ['Recebida','Em análise'].includes(t.status)).length],['Respondidas',tickets.filter(t => t.status === 'Respondida').length],['Resolvidas',tickets.filter(t => t.status === 'Resolvida').length]].map(([label,count]) => `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`).join(''); // Resume os registros recebidos.
  renderList(); // Reaplica os filtros atuais.
}
function renderList() { // Exibe resultados de busca e situação.
  const search = $('search').value.trim().toLocaleLowerCase('pt-BR'); // Normaliza a consulta digitada.
  const filtered = tickets.filter(t => (! $('statusFilter').value || t.status === $('statusFilter').value) && (t.subject + ' ' + t.id).toLocaleLowerCase('pt-BR').includes(search)); // Combina os filtros.
  $('ticketList').innerHTML = filtered.length ? filtered.map(t => `<button type="button" class="ticket-card" data-ticket="${escapeHTML(t.id)}"><div><span class="protocol">${escapeHTML(t.id)}</span><h3>${escapeHTML(t.subject)}</h3><span class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${t.anonymous ? 'Identidade restrita ao diretor' : 'Manifestação identificada'}</span></div>${badge(t.status)}</button>`).join('') : '<div class="empty"><h3>Nenhuma manifestação por aqui.</h3><p>Crie uma nova manifestação ou ajuste os filtros.</p></div>'; // Exibe cartões ou um estado vazio.
}
function showDetail(id) { // Abre o histórico do protocolo selecionado.
  activeId = id; // Guarda o alvo das próximas ações.
  const t = tickets.find(item => item.id === id); // Busca somente na lista autorizada recebida.
  if (!t) return; // Evita abrir um protocolo ausente.
  $('detailProtocol').textContent = t.id; $('detailSubject').textContent = t.subject; // Usa texto simples para protocolo e título.
  const identity = t.anonymous ? 'Identidade restrita ao diretor' : `Identificado: ${t.identity || ''}`; // Não tenta deduzir o autor anônimo.
  $('detailContent').innerHTML = `${badge(t.status)}<p class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${escapeHTML(identity)}</p><p class="detail-body">${escapeHTML(t.body)}</p><h3>Histórico de atendimento</h3>${t.messages.length ? t.messages.map(m => `<div class="message ${m.author === 'Ouvidoria Campo Real' ? 'staff' : ''}"><strong>${escapeHTML(m.author)}</strong><span class="meta"> · ${date(m.created)}</span><p>${escapeHTML(m.body)}</p></div>`).join('') : '<p class="form-note">Aguardando atendimento. As respostas aparecerão aqui.</p>'}`; // Exibe relatos como texto escapado.
  $('detailActions').replaceChildren(); // Limpa ações e identidades reveladas em aberturas anteriores.
  if (user.role === 'aluno') { // Mostra as ações de confirmação do aluno.
    action(t.status === 'Resolvida' ? 'Pedir nova análise' : '✓ Foi resolvido', () => updateStatus(t.status === 'Resolvida' ? 'Em análise' : 'Resolvida')); // Permite encerrar ou reabrir o atendimento.
    if (t.status === 'Respondida') action('Ainda não foi resolvido', () => updateStatus('Em análise')); // Permite contestar a solução proposta.
  } else { // Mostra as ações de atendimento.
    action('Marcar em análise', () => updateStatus('Em análise')); // Atualiza o andamento institucional.
    if (user.role === 'diretor' && t.anonymous) action('Consultar autoria restrita', async () => { // Exige consulta explícita do diretor.
      const result = await api('/api/identity', {id:activeId}); // O servidor autoriza e registra a consulta.
      const note = document.createElement('p'); note.className = 'form-note'; note.textContent = `Autoria: ${result.email}. Consulta registrada${DEMO ? ' apenas ilustrativa na demonstração' : ' na auditoria do servidor'}.`; // Mostra a identidade sem inserir HTML.
      $('detailActions').append(note); // Mantém a informação dentro da janela atual.
    });
  }
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
$('loginForm').onsubmit = event => { // Trata envio do e-mail ou do código.
  event.preventDefault(); // Evita recarregar a página.
  busy($('loginButton'), async () => { // Mostra o estado de espera.
    const email = $('email').value.trim().toLowerCase(); // Normaliza o endereço.
    if (!/^[^\s@]+@camporeal\.edu\.br$/.test(email)) throw new Error('Use seu e-mail @camporeal.edu.br.'); // Ajuda o usuário antes da validação definitiva no servidor.
    if (DEMO) { user = {email,role:'aluno'}; await loggedIn(); return; } // No arquivo local, todo e-mail digitado é apenas um aluno fictício.
    if (!codeSent) { // Solicita o código na primeira etapa.
      await api('/api/login', {email}); codeSent = true; $('codeField').hidden = false; $('code').required = true; $('email').readOnly = true; $('loginButton').textContent = 'Entrar na ouvidoria →'; $('changeEmail').hidden = false; $('code').focus(); // Prepara a confirmação do e-mail.
      notify('Código enviado ao e-mail institucional. Ele vale por 10 minutos.'); // Informa o próximo passo.
    } else { // Confirma o código recebido.
      await api('/api/verify', {email,code:$('code').value.trim()}); user = await api('/api/me'); await loggedIn(); // Inicia a sessão real somente após validação.
      resetLogin(); // Limpa os campos usados no acesso.
    }
  });
};
function resetLogin() { // Restaura a primeira etapa da autenticação.
  codeSent = false; $('codeField').hidden = true; $('code').required = false; $('email').readOnly = false; $('changeEmail').hidden = true; $('loginButton').textContent = 'Receber código de acesso →'; $('loginForm').reset(); // Descarta código e e-mail da tela.
}
$('changeEmail').onclick = resetLogin; // Permite voltar à etapa inicial e reenviar após o intervalo.
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
$('search').oninput = renderList; $('statusFilter').onchange = renderList; // Reaplica filtros ao editar os controles.
$('allTab').onclick = () => { $('search').value = ''; $('statusFilter').value = ''; renderList(); }; // Restaura todos os protocolos.
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close()); // Liga os botões de fechar às janelas.
if (DEMO) { // Configura somente o arquivo de demonstração.
  $('demoBanner').hidden = false; $('demoAccounts').hidden = false; $('loginButton').textContent = 'Explorar como aluno →'; // Identifica claramente a simulação.
  document.querySelectorAll('[data-demo]').forEach(button => button.onclick = () => busy(button, async () => {user = {email:demoEmails[button.dataset.demo],role:button.dataset.demo}; await loggedIn();})); // Permite explorar os três perfis fictícios.
} else { // Ao abrir pelo servidor, tenta recuperar uma sessão já validada.
  api('/api/me').then(async result => {user = result; await loggedIn();}).catch(error => { if (error.message && !error.message.includes('Entre com') && !error.message.includes('expirou')) notify(error.message, true); }); // Mostra a entrada se não houver sessão.
}
''',
    # Conteúdo de assets/logo-azul.svg; mantém os comentários para facilitar o estudo.
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
    # Conteúdo de assets/logo-branca.svg; mantém os comentários para facilitar o estudo.
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
    # Conteúdo de index.html; mantém os comentários para facilitar o estudo.
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
<div class="login-card"><span class="step-label">SEU ESPAÇO DE ESCUTA</span><h2>Vamos conversar?</h2><p>Entre com seu e-mail institucional para enviar ou acompanhar uma manifestação.</p>
<form id="loginForm"> <!-- Solicita e confirma a identidade institucional. -->
<label for="email">E-mail institucional</label><input id="email" type="email" required maxlength="254" autocomplete="email"> <!-- Recebe o endereço do aluno ou da equipe. -->
<div id="codeField" hidden><label for="code">Código recebido por e-mail</label><input id="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6 dígitos"></div> <!-- Exibe a verificação após o envio. -->
<button id="loginButton" class="button primary" type="submit">Receber código de acesso <span aria-hidden="true">→</span></button> <!-- Inicia a autenticação. -->
<button id="changeEmail" type="button" class="text-button" hidden>Trocar e-mail / solicitar novo código</button> <!-- Permite corrigir o endereço. -->
</form>
<div id="demoAccounts" class="demo-accounts" hidden><p>Explore os perfis fictícios:</p><button type="button" data-demo="aluno">Aluno</button><button type="button" data-demo="supervisor">Supervisor</button><button type="button" data-demo="diretor">Diretor</button></div> <!-- Oferece perfis apenas no arquivo de demonstração. -->
<div class="privacy-note"><span aria-hidden="true">◈</span><p><strong>Você escolhe como se identificar.</strong><br>Na opção anônima, sua identidade fica oculta para a equipe de atendimento e pode ser consultada somente pelo diretor. O login continua obrigatório.</p></div> <!-- Explica o limite do anonimato antes do acesso. -->
</div>
</section>
<section id="workspace" class="workspace" hidden> <!-- Mostra o painel após o login. -->
<div class="workspace-heading"><div><span id="panelLabel" class="eyebrow">ÁREA DO ALUNO</span><h1 id="panelTitle">Minhas manifestações</h1><p id="panelDescription">Acompanhe cada conversa, do primeiro contato à solução.</p></div><button id="newTicket" class="button primary" type="button">＋ Nova manifestação</button></div> <!-- Apresenta o painel apropriado ao perfil. -->
<div id="stats" class="stats"></div> <!-- Resume os protocolos por situação. -->
<div class="toolbar"><div class="tabs"><button id="allTab" class="tab active" type="button">Todas as manifestações</button></div><div class="filters"><label class="sr-only" for="search">Buscar manifestações</label><input id="search" type="search" placeholder="Buscar assunto ou protocolo"><label class="sr-only" for="statusFilter">Filtrar situação</label><select id="statusFilter"><option value="">Todas as situações</option><option>Recebida</option><option>Em análise</option><option>Respondida</option><option>Resolvida</option></select></div></div> <!-- Permite localizar manifestações. -->
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
    # Conteúdo de style.css; mantém os comentários para facilitar o estudo.
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
''',
    # Conteúdo de DEMONSTRACAO.html; mantém os comentários para facilitar o estudo.
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
<div class="login-card"><span class="step-label">SEU ESPAÇO DE ESCUTA</span><h2>Vamos conversar?</h2><p>Entre com seu e-mail institucional para enviar ou acompanhar uma manifestação.</p>
<form id="loginForm"> <!-- Solicita e confirma a identidade institucional. -->
<label for="email">E-mail institucional</label><input id="email" type="email" required maxlength="254" autocomplete="email"> <!-- Recebe o endereço do aluno ou da equipe. -->
<div id="codeField" hidden><label for="code">Código recebido por e-mail</label><input id="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6 dígitos"></div> <!-- Exibe a verificação após o envio. -->
<button id="loginButton" class="button primary" type="submit">Receber código de acesso <span aria-hidden="true">→</span></button> <!-- Inicia a autenticação. -->
<button id="changeEmail" type="button" class="text-button" hidden>Trocar e-mail / solicitar novo código</button> <!-- Permite corrigir o endereço. -->
</form>
<div id="demoAccounts" class="demo-accounts" hidden><p>Explore os perfis fictícios:</p><button type="button" data-demo="aluno">Aluno</button><button type="button" data-demo="supervisor">Supervisor</button><button type="button" data-demo="diretor">Diretor</button></div> <!-- Oferece perfis apenas no arquivo de demonstração. -->
<div class="privacy-note"><span aria-hidden="true">◈</span><p><strong>Você escolhe como se identificar.</strong><br>Na opção anônima, sua identidade fica oculta para a equipe de atendimento e pode ser consultada somente pelo diretor. O login continua obrigatório.</p></div> <!-- Explica o limite do anonimato antes do acesso. -->
</div>
</section>
<section id="workspace" class="workspace" hidden> <!-- Mostra o painel após o login. -->
<div class="workspace-heading"><div><span id="panelLabel" class="eyebrow">ÁREA DO ALUNO</span><h1 id="panelTitle">Minhas manifestações</h1><p id="panelDescription">Acompanhe cada conversa, do primeiro contato à solução.</p></div><button id="newTicket" class="button primary" type="button">＋ Nova manifestação</button></div> <!-- Apresenta o painel apropriado ao perfil. -->
<div id="stats" class="stats"></div> <!-- Resume os protocolos por situação. -->
<div class="toolbar"><div class="tabs"><button id="allTab" class="tab active" type="button">Todas as manifestações</button></div><div class="filters"><label class="sr-only" for="search">Buscar manifestações</label><input id="search" type="search" placeholder="Buscar assunto ou protocolo"><label class="sr-only" for="statusFilter">Filtrar situação</label><select id="statusFilter"><option value="">Todas as situações</option><option>Recebida</option><option>Em análise</option><option>Respondida</option><option>Resolvida</option></select></div></div> <!-- Permite localizar manifestações. -->
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
let user = null, tickets = [], activeId = null, codeSent = false, toastTimer; // Guarda o estado da tela, sem armazenar a sessão real.
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
  const list = demoData(); // Recupera os protocolos locais.
  if (path === '/api/tickets' && !data) return list.filter(t => user.role !== 'aluno' || t.email === user.email).map(t => ({...t,identity:!t.anonymous || user.role === 'aluno' ? t.email : null,email:undefined})); // Oculta dados no fluxo de demonstração.
  if (path === '/api/tickets') { // Registra um exemplo de manifestação.
    const item = {...data,id:'CR-DEMO-' + Math.random().toString(16).slice(2,10).toUpperCase(),email:user.email,created:Date.now()/1000,status:'Recebida',messages:[]}; // Associa a conta fictícia.
    list.unshift(item); saveDemo(list); return {id:item.id}; // Persiste o exemplo.
  }
  const item = list.find(t => t.id === data.id); // Localiza o protocolo selecionado.
  if (!item) throw new Error('Protocolo não encontrado.'); // Trata exemplos removidos.
  if (path === '/api/identity') { if(user.role !== 'diretor') throw new Error('Somente o diretor pode consultar.'); return {email:item.email}; } // Demonstra a consulta restrita.
  if (path === '/api/reply') { item.messages.push({author:user.role === 'aluno' ? 'Aluno' : 'Ouvidoria Campo Real',body:data.body,created:Date.now()/1000}); item.status = user.role === 'aluno' ? 'Em análise' : 'Respondida'; } // Acrescenta uma mensagem fictícia.
  if (path === '/api/status') { item.status = data.status; item.messages.push({author:'Sistema',body:'Situação alterada para ' + data.status.toLowerCase() + '.',created:Date.now()/1000}); } // Registra o andamento do exemplo.
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
  user = null; tickets = []; activeId = null; // Descarta dados privados da memória da tela.
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
  $('newTicket').hidden = !student; // Restringe a criação ao perfil de aluno na interface.
  $('account').innerHTML = `<strong>${escapeHTML(user.role)}</strong><span>${escapeHTML(user.email)}</span> <button class="text-button" id="logout" type="button">Sair</button>`; // Mostra os dados da própria sessão.
  $('logout').onclick = event => busy(event.currentTarget, async () => {await api('/api/logout', {}); loggedOut();}); // Invalida a sessão no servidor.
  await refresh(); // Busca as manifestações autorizadas.
}
async function refresh() { // Atualiza os protocolos e os indicadores.
  tickets = await api('/api/tickets'); // Recebe apenas registros permitidos pelo servidor.
  $('stats').innerHTML = [['Total de manifestações',tickets.length],['Em atendimento',tickets.filter(t => ['Recebida','Em análise'].includes(t.status)).length],['Respondidas',tickets.filter(t => t.status === 'Respondida').length],['Resolvidas',tickets.filter(t => t.status === 'Resolvida').length]].map(([label,count]) => `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`).join(''); // Resume os registros recebidos.
  renderList(); // Reaplica os filtros atuais.
}
function renderList() { // Exibe resultados de busca e situação.
  const search = $('search').value.trim().toLocaleLowerCase('pt-BR'); // Normaliza a consulta digitada.
  const filtered = tickets.filter(t => (! $('statusFilter').value || t.status === $('statusFilter').value) && (t.subject + ' ' + t.id).toLocaleLowerCase('pt-BR').includes(search)); // Combina os filtros.
  $('ticketList').innerHTML = filtered.length ? filtered.map(t => `<button type="button" class="ticket-card" data-ticket="${escapeHTML(t.id)}"><div><span class="protocol">${escapeHTML(t.id)}</span><h3>${escapeHTML(t.subject)}</h3><span class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${t.anonymous ? 'Identidade restrita ao diretor' : 'Manifestação identificada'}</span></div>${badge(t.status)}</button>`).join('') : '<div class="empty"><h3>Nenhuma manifestação por aqui.</h3><p>Crie uma nova manifestação ou ajuste os filtros.</p></div>'; // Exibe cartões ou um estado vazio.
}
function showDetail(id) { // Abre o histórico do protocolo selecionado.
  activeId = id; // Guarda o alvo das próximas ações.
  const t = tickets.find(item => item.id === id); // Busca somente na lista autorizada recebida.
  if (!t) return; // Evita abrir um protocolo ausente.
  $('detailProtocol').textContent = t.id; $('detailSubject').textContent = t.subject; // Usa texto simples para protocolo e título.
  const identity = t.anonymous ? 'Identidade restrita ao diretor' : `Identificado: ${t.identity || ''}`; // Não tenta deduzir o autor anônimo.
  $('detailContent').innerHTML = `${badge(t.status)}<p class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${escapeHTML(identity)}</p><p class="detail-body">${escapeHTML(t.body)}</p><h3>Histórico de atendimento</h3>${t.messages.length ? t.messages.map(m => `<div class="message ${m.author === 'Ouvidoria Campo Real' ? 'staff' : ''}"><strong>${escapeHTML(m.author)}</strong><span class="meta"> · ${date(m.created)}</span><p>${escapeHTML(m.body)}</p></div>`).join('') : '<p class="form-note">Aguardando atendimento. As respostas aparecerão aqui.</p>'}`; // Exibe relatos como texto escapado.
  $('detailActions').replaceChildren(); // Limpa ações e identidades reveladas em aberturas anteriores.
  if (user.role === 'aluno') { // Mostra as ações de confirmação do aluno.
    action(t.status === 'Resolvida' ? 'Pedir nova análise' : '✓ Foi resolvido', () => updateStatus(t.status === 'Resolvida' ? 'Em análise' : 'Resolvida')); // Permite encerrar ou reabrir o atendimento.
    if (t.status === 'Respondida') action('Ainda não foi resolvido', () => updateStatus('Em análise')); // Permite contestar a solução proposta.
  } else { // Mostra as ações de atendimento.
    action('Marcar em análise', () => updateStatus('Em análise')); // Atualiza o andamento institucional.
    if (user.role === 'diretor' && t.anonymous) action('Consultar autoria restrita', async () => { // Exige consulta explícita do diretor.
      const result = await api('/api/identity', {id:activeId}); // O servidor autoriza e registra a consulta.
      const note = document.createElement('p'); note.className = 'form-note'; note.textContent = `Autoria: ${result.email}. Consulta registrada${DEMO ? ' apenas ilustrativa na demonstração' : ' na auditoria do servidor'}.`; // Mostra a identidade sem inserir HTML.
      $('detailActions').append(note); // Mantém a informação dentro da janela atual.
    });
  }
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
$('loginForm').onsubmit = event => { // Trata envio do e-mail ou do código.
  event.preventDefault(); // Evita recarregar a página.
  busy($('loginButton'), async () => { // Mostra o estado de espera.
    const email = $('email').value.trim().toLowerCase(); // Normaliza o endereço.
    if (!/^[^\s@]+@camporeal\.edu\.br$/.test(email)) throw new Error('Use seu e-mail @camporeal.edu.br.'); // Ajuda o usuário antes da validação definitiva no servidor.
    if (DEMO) { user = {email,role:'aluno'}; await loggedIn(); return; } // No arquivo local, todo e-mail digitado é apenas um aluno fictício.
    if (!codeSent) { // Solicita o código na primeira etapa.
      await api('/api/login', {email}); codeSent = true; $('codeField').hidden = false; $('code').required = true; $('email').readOnly = true; $('loginButton').textContent = 'Entrar na ouvidoria →'; $('changeEmail').hidden = false; $('code').focus(); // Prepara a confirmação do e-mail.
      notify('Código enviado ao e-mail institucional. Ele vale por 10 minutos.'); // Informa o próximo passo.
    } else { // Confirma o código recebido.
      await api('/api/verify', {email,code:$('code').value.trim()}); user = await api('/api/me'); await loggedIn(); // Inicia a sessão real somente após validação.
      resetLogin(); // Limpa os campos usados no acesso.
    }
  });
};
function resetLogin() { // Restaura a primeira etapa da autenticação.
  codeSent = false; $('codeField').hidden = true; $('code').required = false; $('email').readOnly = false; $('changeEmail').hidden = true; $('loginButton').textContent = 'Receber código de acesso →'; $('loginForm').reset(); // Descarta código e e-mail da tela.
}
$('changeEmail').onclick = resetLogin; // Permite voltar à etapa inicial e reenviar após o intervalo.
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
$('search').oninput = renderList; $('statusFilter').onchange = renderList; // Reaplica filtros ao editar os controles.
$('allTab').onclick = () => { $('search').value = ''; $('statusFilter').value = ''; renderList(); }; // Restaura todos os protocolos.
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close()); // Liga os botões de fechar às janelas.
if (DEMO) { // Configura somente o arquivo de demonstração.
  $('demoBanner').hidden = false; $('demoAccounts').hidden = false; $('loginButton').textContent = 'Explorar como aluno →'; // Identifica claramente a simulação.
  document.querySelectorAll('[data-demo]').forEach(button => button.onclick = () => busy(button, async () => {user = {email:demoEmails[button.dataset.demo],role:button.dataset.demo}; await loggedIn();})); // Permite explorar os três perfis fictícios.
} else { // Ao abrir pelo servidor, tenta recuperar uma sessão já validada.
  api('/api/me').then(async result => {user = result; await loggedIn();}).catch(error => { if (error.message && !error.message.includes('Entre com') && !error.message.includes('expirou')) notify(error.message, true); }); // Mostra a entrada se não houver sessão.
}

</script>
</body>
</html>
''',
    # Conteúdo de configuracao.env.example; mantém os comentários para facilitar o estudo.
    'configuracao.env.example': r'''# Copie este arquivo para .env. Não compartilhe o arquivo preenchido.
# Endereço exato usado no navegador (sem barra no final).
APP_URL=http://localhost:8000
# Mantém o acesso restrito ao computador local durante a instalação.
HOST=127.0.0.1
# Porta em que o servidor atende.
PORT=8000
# Única conta que pode consultar a autoria das manifestações anônimas.
DIRECTOR_EMAIL=
# Contas da equipe que responde, separadas por vírgula.
SUPERVISOR_EMAILS=
# Servidor SMTP da faculdade, com STARTTLS obrigatório.
SMTP_HOST=
# Porta padrão de SMTP com STARTTLS; use o valor fornecido pela TI.
SMTP_PORT=587
# Endereço de remetente autorizado pelo servidor SMTP.
SMTP_FROM=
# Usuário de envio; deixe vazio se o servidor não exigir autenticação.
SMTP_USER=
# Senha de aplicativo ou credencial SMTP, obtida com a TI.
SMTP_PASSWORD=
''',
    # Conteúdo de LEIA-ME.md; mantém os comentários para facilitar o estudo.
    'LEIA-ME.md': r'''# Ouvidoria Campo Real

Site em português, com azul e branco como cores principais e amarelo nos detalhes. Código comentado em HTML, CSS, JavaScript e Python, sem dependências externas. Requer Python 3.10 ou superior para o sistema real.

## 1. Veja primeiro a demonstração

Abra `DEMONSTRACAO.html` com dois cliques no navegador. Esse arquivo é independente, funciona sem internet e já contém estilos, scripts e as duas versões da marca. Os botões **Aluno**, **Supervisor** e **Diretor** permitem explorar os perfis com dados fictícios.

A demonstração NÃO autentica pessoas e NÃO protege dados: tudo fica no navegador. Não coloque relatos nem e-mails reais nela. A auditoria mostrada na demonstração é ilustrativa. Ela serve para apresentação e avaliação das telas.

Para restaurar os exemplos, exclua a chave `camporeal-demo-v1` no armazenamento local do navegador. Os três protocolos iniciais são fictícios.

## 2. Inicie o sistema com servidor e banco de dados

1. Extraia o ZIP para uma pasta no seu computador.
2. Instale Python 3.10 ou superior, caso ainda não esteja instalado.
3. Copie `.env.example` para um arquivo chamado `.env`, na mesma pasta de `start.py`.
4. Preencha os parâmetros de envio de e-mail fornecidos pela TI da faculdade.
5. Preencha `DIRECTOR_EMAIL` com UMA conta institucional do diretor. Não coloque vírgulas nesse campo.
6. Preencha `SUPERVISOR_EMAILS` com as contas dos supervisores/administradores autorizados, separadas por vírgula.
7. No terminal, entre na pasta do projeto e execute `python start.py` (no Windows, também pode usar `py -3 start.py` ou abrir `INICIAR.bat`).
8. Abra **http://localhost:8000**. Use exatamente esse endereço, porque `APP_URL` controla a origem permitida.

O banco é criado automaticamente em `data/ouvidoria.sqlite3`, fora da pasta pública. Não é necessário instalar bibliotecas nem executar migrações manualmente. O servidor permanece ativo enquanto a janela do terminal estiver aberta.

O arquivo `.env` é lido pelo `start.py`. Se preferir iniciar `server.py` diretamente, configure as variáveis no ambiente do sistema operacional.

### Configuração de e-mail

O acesso real exige um código de seis dígitos enviado ao e-mail `@camporeal.edu.br`. O código dura dez minutos e admite cinco tentativas incorretas. Cada reenvio exige intervalo mínimo de 60 segundos. A sessão dura oito horas.

- `SMTP_HOST`: servidor SMTP autorizado pela faculdade.
- `SMTP_PORT`: normalmente 587, com STARTTLS obrigatório.
- `SMTP_FROM`: remetente permitido pelo servidor.
- `SMTP_USER` e `SMTP_PASSWORD`: credenciais de SMTP. Se o servidor não exigir autenticação, deixe o usuário vazio.

Não envie senhas pelo chat e não coloque credenciais no código. O `.env` é privado e deve ficar apenas no servidor. Provedores que exigem OAuth para envio SMTP precisam de uma integração própria de envio ou de um relay autorizado pela TI; este projeto usa SMTP com STARTTLS e autenticação por usuário/senha quando configurada.

**Google:** não foi incluído um botão de login do Google sem integração. A alternativa solicitada foi implementada com verificação real do e-mail institucional por código, em vez de apenas validar o texto do domínio.

Sem SMTP configurado, a aplicação real informa que o envio está indisponível. Não existe código mestre, senha padrão ou desvio de login para a produção.

## 3. Perfis e privacidade

| Perfil | Permissões |
| --- | --- |
| Aluno | Criar reclamação, crítica, sugestão, elogio ou solicitação; escolher identificação; consultar somente os próprios protocolos; ler respostas; complementar o relato; confirmar solução; pedir nova análise. |
| Supervisor / administrador de atendimento | Consultar a fila; responder manifestações; marcar em análise; ver e-mail somente em manifestações identificadas. Não pode consultar autoria de manifestações anônimas. |
| Diretor | Atender como a equipe e, adicionalmente, consultar a autoria de manifestações anônimas. Cada consulta exige ação explícita e fica na auditoria do servidor. |

Os perfis são definidos no servidor, a partir das contas verificadas. O aluno não escolhe virar supervisor ou diretor. Se uma conta estiver nas duas configurações, o perfil diretor prevalece.

**“Anônima” significa identidade oculta para a equipe de atendimento, com acesso restrito ao diretor. Não significa anonimato absoluto.** O site explica isso antes do login e antes do envio. A autenticação é obrigatória em ambos os modos. Um nome ou e-mail escrito pelo próprio aluno no relato continuará visível; o formulário orienta a não se identificar no texto.

O diretor também recebe a fila sem a autoria anônima; para vê-la, precisa clicar em **Consultar autoria restrita**. O acesso cria um registro em `audit`, com conta do diretor, protocolo, ação e data. Não há tela pública de auditoria; a TI pode consultar essa tabela no banco com ferramentas administrativas.

O controle exclusivo do diretor é aplicado pela API. Pessoas com acesso administrativo ao servidor ou ao arquivo de banco podem acessar os dados armazenados; restrinja essas permissões na infraestrutura da faculdade.

## 4. Como funciona o atendimento

1. O aluno recebe um protocolo ao enviar o relato.
2. A manifestação começa como **Recebida**.
3. A equipe pode marcar **Em análise**.
4. Quando a equipe responde, a situação passa para **Respondida**.
5. O aluno consulta a resposta na própria área e pode marcar **Foi resolvido**, mudando para **Resolvida**.
6. Se ainda houver problema, o aluno pede nova análise ou escreve outra mensagem. O protocolo volta a **Em análise**.

A equipe não marca uma manifestação como resolvida em nome do aluno. As mensagens e mudanças de situação permanecem no histórico. A aplicação não envia avisos automáticos de novas respostas: o aluno acompanha pelo painel.

## 5. Marca e arquivos

As imagens anexadas ficaram visíveis na conversa, mas não foram disponibilizadas como arquivos binários ao ambiente de execução. Por isso, as duas versões incluídas são **reproduções vetoriais de referência**, baseadas nas imagens recebidas, com estrela amarela e textos azul ou branco. Elas não são os arquivos originais e podem ter diferenças tipográficas.

Antes de publicar oficialmente, substitua:

- `public/assets/logo-azul.svg`: marca usada no cabeçalho branco.
- `public/assets/logo-branca.svg`: marca usada no rodapé azul.

Você pode manter esses nomes se receber os originais em SVG. Se os originais forem PNG, ajuste também os caminhos em `public/index.html` e a lista de arquivos públicos em `server.py`. O demonstrador independente contém cópias embutidas e precisa ser atualizado separadamente caso queira trocar as marcas nele.

### Organização

- `public/index.html`: estrutura das páginas, formulários e janelas.
- `public/style.css`: cores, espaçamentos e adaptação a celulares.
- `public/app.js`: interação com a API e modo demonstrativo local.
- `public/assets/`: versões azul e branca da marca.
- `server.py`: autenticação, autorização, dados, histórico e auditoria.
- `start.py`: carregamento da configuração e inicialização.
- `.env.example`: parâmetros que a TI precisa preencher.
- `tests/test_server.py`: testes de integração e permissões.
- `DEMONSTRACAO.html`: prévia independente para abrir com dois cliques.

Os comentários explicam as instruções e os blocos do código; linhas de fechamento de blocos e delimitadores não repetem comentários sem conteúdo útil.

## 6. Instalação na faculdade

O pacote é uma base funcional, sem hospedagem contratada ou publicação automática. Para disponibilizá-lo aos alunos, a TI precisa configurar um servidor Python persistente, SMTP e um proxy HTTPS, com `APP_URL` igual ao endereço institucional definitivo. O servidor HTTP da biblioteca padrão foi escolhido pela simplicidade e deve ficar atrás de um proxy reverso adequado (por exemplo, Nginx), com limites de conexão e tempo. Não exponha a pasta do projeto inteira por um servidor de arquivos estáticos.

Mantenha `HOST=127.0.0.1` quando o proxy estiver no mesmo computador. A aplicação não confia em cabeçalhos `X-Forwarded-For`; o limite por IP considera a conexão direta, portanto a TI deve ajustar essa política ao colocar o servidor atrás de proxy ou em uma rede compartilhada. Os limites por e-mail continuam independentes.

Mantenha backups privados do banco com o serviço parado, proteja a conta do diretor, defina retenção dos relatos e a política institucional de privacidade antes da coleta real. Mudanças de perfis no `.env` passam a valer após reiniciar o servidor. Não compartilhe `.env` nem a pasta `data` com os alunos.

## 7. Verificação

Execute na pasta do projeto:

```sh
python -m unittest discover -s tests -v
```

A suíte usa banco temporário e substitui somente o envio de e-mail. As chamadas HTTP passam pelo servidor real. Verifica domínio exato, autenticação obrigatória, tentativas e validade de código, uso único, isolamento entre alunos, ausência de autoria anônima na fila institucional, bloqueio de consulta pelo supervisor, acesso e auditoria do diretor, respostas, solução/reabertura, CSRF, origem HTTP, proteção dos arquivos privados e logout.

Foram aprovados os testes automatizados do servidor e a verificação de sintaxe do Python e do JavaScript. O envio SMTP real depende das credenciais da faculdade e não foi exercitado. Não houve validação visual em navegador neste ambiente; confira o demonstrador em computador e celular antes de publicar.
''',
}  # Finaliza os conteúdos embutidos.

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
        CREATE TABLE IF NOT EXISTS codes(email TEXT PRIMARY KEY, hash TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL, sent REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires REAL NOT NULL, csrf TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, email TEXT NOT NULL, anonymous INTEGER NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL, sector TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ticket TEXT NOT NULL REFERENCES tickets(id), author TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, ticket TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, hits INTEGER NOT NULL, reset REAL NOT NULL);
        ''')  # Cria autenticação, manifestações, histórico e auditoria.
    os.chmod(DB, 0o600)  # Restringe a leitura do arquivo de banco.


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()  # Não guarda códigos nem cookies em texto simples.


def role(email):
    if email == DIRECTOR:  # Confere a conta definida no servidor.
        return 'diretor'  # Concede acesso à identidade somente ao diretor.
    return 'supervisor' if email in SUPERVISORS else 'aluno'  # Os demais são alunos por padrão.


class SMTPConfigurationError(ValueError):
    pass  # Identifica erros locais de configuração sem incluir senhas na mensagem.


def smtp_settings():
    required = ['SMTP_HOST', 'SMTP_FROM']  # Define os campos obrigatórios para qualquer envio.
    if os.getenv('SMTP_USER', '').strip():  # A senha só é necessária quando existe usuário de autenticação.
        required.append('SMTP_PASSWORD')
    missing = [name for name in required if not os.getenv(name, '').strip()]  # Verifica nomes, sem imprimir valores.
    if missing:
        location = 'Confira o .env na mesma pasta de ouvidoria.py e reinicie o programa.' if config.exists() else 'Não encontrei o arquivo .env ao lado de ouvidoria.py. Confira se ele não ficou como .env.txt.'  # Orienta onde corrigir.
        raise SMTPConfigurationError('Configuração SMTP incompleta: ' + ', '.join(missing) + '. ' + location)  # Mostra apenas nomes de campos.
    try:
        port = int(os.getenv('SMTP_PORT', '587'))  # Valida a porta antes de tentar conexão.
        if not 1 <= port <= 65535:
            raise ValueError  # Recusa números fora da faixa de portas.
    except ValueError:
        raise SMTPConfigurationError('SMTP_PORT precisa ser uma porta válida. No Gmail, use 587 com STARTTLS ou 465 com TLS.') from None
    host = os.environ['SMTP_HOST'].strip()  # Remove espaços no nome do servidor.
    if '://' in host or '/' in host or ':' in host or any(c.isspace() for c in host):
        raise SMTPConfigurationError('SMTP_HOST deve conter somente o servidor. No Gmail, use smtp.gmail.com, sem https:// e sem porta.')
    return host, port  # Retorna somente os parâmetros necessários à conexão.


def smtp_error_message(error):
    if isinstance(error, SMTPConfigurationError):
        return str(error)  # Os textos dessa classe são criados pelo próprio programa e nunca incluem valores privados.
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return 'O servidor recusou o usuário ou a senha SMTP. No Gmail, use uma senha de app do Google, não a senha normal. Confira SMTP_USER e reinicie após editar o .env.'
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return 'O servidor recusou o destinatário. Confira o e-mail institucional e as regras de envio da conta.'
    if isinstance(error, smtplib.SMTPSenderRefused):
        return 'O servidor recusou o remetente. No Gmail, SMTP_FROM deve ser o mesmo Gmail de SMTP_USER ou um endereço autorizado na conta.'
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return 'O servidor não oferece a conexão segura exigida. Confira SMTP_HOST e SMTP_PORT; no Gmail, use smtp.gmail.com e porta 587 ou 465.'
    if isinstance(error, ssl.SSLError):
        return 'Não foi possível validar a conexão TLS do SMTP. Confira a porta, a data do computador e os certificados; não desative a validação de segurança.'
    if isinstance(error, smtplib.SMTPException):
        return 'O provedor de e-mail recusou ou interrompeu o envio. Execute python ouvidoria.py --testar-smtp para verificar a conexão e a autenticação.'
    if isinstance(error, OSError):
        return 'Não foi possível conectar ao servidor SMTP. Confira internet, firewall, SMTP_HOST e SMTP_PORT. No Gmail, tente a porta 587 ou 465.'
    return 'Não foi possível enviar o código. Execute python ouvidoria.py --testar-smtp no terminal para verificar a configuração.'  # Não repassa respostas brutas que possam conter dados privados.


@contextmanager  # Fecha a conexão mesmo quando autenticação ou envio falhar.
def smtp_connection():
    host, port = smtp_settings()  # Valida os parâmetros sem revelar credenciais.
    context = ssl.create_default_context()  # Exige certificados confiáveis.
    client = smtplib.SMTP_SSL(host, port, timeout=15, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=15)  # Suporta TLS direto ou STARTTLS.
    try:
        if port != 465:
            client.starttls(context=context)  # Exige criptografia antes de transmitir credenciais.
        username = os.getenv('SMTP_USER', '').strip()  # Normaliza o usuário da conta de envio.
        if username:
            password = os.environ['SMTP_PASSWORD']  # Mantém a senha apenas na memória do processo.
            if host.lower() == 'smtp.gmail.com':
                password = password.replace(' ', '')  # Aceita a senha de app do Google copiada com espaços entre os grupos.
            client.login(username, password)  # Autentica sem registrar a senha nem habilitar logs de protocolo.
        yield client  # Disponibiliza a conexão autenticada para envio ou diagnóstico.
    finally:
        try:
            client.quit()  # Encerra a conexão educadamente.
        except (smtplib.SMTPException, OSError):
            client.close()  # Garante liberação caso o servidor já tenha desconectado.


def deliver(email, code):
    smtp_settings()  # Valida a presença do remetente antes de montar o e-mail.
    message = EmailMessage()  # Cria uma mensagem de texto.
    message['Subject'] = 'Seu código de acesso — Ouvidoria Campo Real'  # Define o assunto.
    message['From'] = os.environ['SMTP_FROM'].strip()  # Usa o remetente configurado, sem espaços externos.
    message['To'] = email  # Envia somente ao e-mail institucional validado.
    message.set_content(f'Seu código de acesso é {code}. Ele expira em 10 minutos. Não compartilhe este código. Se não solicitou, ignore esta mensagem.')  # Informa validade.
    with smtp_connection() as smtp:  # Usa a mesma conexão segura validada pelo diagnóstico.
        smtp.send_message(message)  # Entrega o código sem registrá-lo em logs.


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
        row = db.execute('SELECT * FROM sessions WHERE hash=? AND expires>?', (digest(token), time.time())).fetchone()  # Busca uma sessão válida.
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
                if path in ('/api/login', '/api/verify'):
                    self.limit(db, 'ip:' + self.client_address[0], 50, 600)  # Limita tentativas por IP direto.
                    email = self.text(data, 'email', 1, 254).lower()  # Normaliza o e-mail.
                    if not INSTITUTIONAL.fullmatch(email):  # Não aceita domínios parecidos ou subdomínios.
                        raise Error(400, 'Use seu e-mail @camporeal.edu.br.')
                    if path == '/api/login':
                        self.limit(db, 'email:' + email, 5, 600)  # Limita envios para cada conta.
                        previous = db.execute('SELECT sent FROM codes WHERE email=?', (email,)).fetchone()  # Consulta o último envio.
                        if previous and now - previous['sent'] < 60:
                            raise Error(429, 'Aguarde 60 segundos antes de pedir outro código.')  # Evita disparos repetidos.
                        code = f'{secrets.randbelow(1000000):06d}'  # Gera seis números aleatórios.
                        try:
                            deliver(email, code)  # Só permite autenticação por e-mail realmente recebido.
                        except Exception as error:
                            raise Error(503, smtp_error_message(error)) from None  # Informa a categoria da falha sem expor credenciais ou respostas brutas do SMTP.
                        db.execute('INSERT OR REPLACE INTO codes VALUES (?,?,?,0,?)', (email, digest(email + code), now + 600, now))  # Guarda código com validade de dez minutos.
                        return self.success(db, 200, {'ok': True})  # Não devolve o código no HTTP.
                    supplied = self.text(data, 'code', 6, 6)  # Lê o código digitado.
                    db.execute('BEGIN IMMEDIATE')  # Serializa verificações para impedir reutilização concorrente.
                    row = db.execute('SELECT * FROM codes WHERE email=?', (email,)).fetchone()  # Procura o código da conta.
                    if not row or row['expires'] < now or row['attempts'] >= 5:
                        raise Error(400, 'Código expirado ou inválido. Solicite outro.')
                    if not hmac.compare_digest(row['hash'], digest(email + supplied)):
                        db.execute('UPDATE codes SET attempts=attempts+1 WHERE email=?', (email,))  # Conta cada código incorreto na mesma transação.
                        db.commit()  # Mantém o contador mesmo retornando erro ao usuário.
                        raise Error(400, 'Código incorreto. Confira o e-mail recebido.')
                    db.execute('DELETE FROM codes WHERE email=?', (email,))  # Consome o código de uso único.
                    db.execute('DELETE FROM sessions WHERE expires<?', (now,))  # Limpa sessões antigas.
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)  # Gera segredos independentes.
                    db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), email, now + 28800, csrf))  # Sessão dura oito horas.
                    return self.success(db, 200, {'ok': True}, self.cookie(token, 28800))  # Cria cookie protegido.
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
                    db.execute('INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)', (ticket_id, email, int(data['anonymous']), kind, subject, sector, body, 'Recebida', now))  # Associa a autoria somente no servidor.
                    return self.success(db, 201, {'id': ticket_id})  # Informa o protocolo gerado.
                ticket_id = self.text(data, 'id', 1, 40)  # Identifica o protocolo solicitado.
                ticket = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()  # Busca a manifestação.
                if not ticket or (profile == 'aluno' and ticket['email'] != email):
                    raise Error(404, 'Manifestação não encontrada.')  # Não revela existência de registros alheios.
                if path == '/api/identity':
                    if profile != 'diretor':
                        raise Error(403, 'Somente o diretor pode consultar a autoria restrita.')
                    db.execute('INSERT INTO audit(actor,action,ticket,created) VALUES (?,?,?,?)', (email, 'Consulta de autoria restrita', ticket_id, now))  # Registra cada acesso do diretor.
                    return self.success(db, 200, {'email': ticket['email']})  # Revela somente na consulta explícita e autorizada.
                if path == '/api/reply':
                    body = self.text(data, 'body', 3, 5000)  # Valida o texto da resposta.
                    db.execute('INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)', (ticket_id, 'Aluno' if profile == 'aluno' else 'Ouvidoria Campo Real', body, now))  # Preserva o anonimato do autor nas mensagens.
                    if profile != 'aluno':
                        db.execute('UPDATE tickets SET status=? WHERE id=?', ('Respondida', ticket_id))  # Sinaliza a nova resposta institucional.
                    elif ticket['status'] in ('Respondida', 'Resolvida'):
                        db.execute('UPDATE tickets SET status=? WHERE id=?', ('Em análise', ticket_id))  # Reabre a análise quando o aluno volta a se manifestar.
                    return self.success(db, 200, {'ok': True})
                if path == '/api/status':
                    status = self.text(data, 'status', 1, 30)  # Lê a nova situação.
                    allowed = {'Resolvida', 'Em análise'} if profile == 'aluno' else {'Em análise', 'Respondida'}  # O aluno confirma a solução; equipe não encerra por ele.
                    if status not in allowed or (status == 'Respondida' and not db.execute("SELECT 1 FROM messages WHERE ticket=? AND author='Ouvidoria Campo Real'", (ticket_id,)).fetchone()):
                        raise Error(400, 'Alteração de situação não permitida.')
                    db.execute('UPDATE tickets SET status=? WHERE id=?', (status, ticket_id))  # Atualiza o andamento.
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
        if option == '--testar-smtp':  # Testa a configuração sem enviar e-mails nem criar códigos de acesso.
            try:
                with smtp_connection() as smtp:  # Verifica conexão, TLS e autenticação quando configurada.
                    status, _ = smtp.noop()  # Consulta se a sessão SMTP está ativa, sem remeter uma mensagem.
                    if status != 250:
                        raise smtplib.SMTPResponseException(status, b'Falha na verificacao SMTP')  # Não imprime a resposta bruta do provedor.
            except Exception as error:
                print('Falha no teste SMTP:', smtp_error_message(error))  # Mostra somente uma orientação segura para compartilhar.
                raise SystemExit(1) from None  # Sinaliza falha sem despejar rastreamento nem credenciais.
            print('Conexão SMTP segura concluída' + (' e autenticação aceita.' if os.getenv('SMTP_USER', '').strip() else '; autenticação não configurada.'))  # Distingue conexão de autenticação efetiva.
            print('Nenhum e-mail foi enviado. Este teste não confirma entrega ao destinatário nem permissão do remetente.')  # Explica o alcance exato do diagnóstico.
            raise SystemExit(0)  # Finaliza o teste sem iniciar o servidor.
        if option == '--configurar':  # Cria o modelo de configuração sem sobrescrever credenciais existentes.
            target = ROOT / '.env.example'  # Define o nome do modelo.
            if not target.exists():  # Preserva modelos que já tenham sido editados.
                target.write_text(ASSETS['configuracao.env.example'], encoding='utf-8')  # Grava os parâmetros necessários.
            print('Modelo disponível em:', target)  # Explica onde encontrar as opções.
            print('Copie para .env, preencha SMTP e contas autorizadas e execute novamente sem opções.')  # Orienta a instalação.
            raise SystemExit(0)  # Não inicia o servidor antes da configuração.
        if option == '--demo':  # Mostra somente uma prévia com contas e relatos fictícios.
            import webbrowser  # Abre o navegador padrão do computador.
            target = ROOT / 'DEMONSTRACAO.html'  # Define o arquivo local da demonstração.
            target.write_text(ASSETS['DEMONSTRACAO.html'], encoding='utf-8')  # Gera uma página independente de servidor.
            print('Demonstração fictícia salva em:', target)  # Informa a localização caso o navegador não abra.
            webbrowser.open(target.resolve().as_uri())  # Abre a página local para explorar os perfis.
            raise SystemExit(0)  # Não cria sessão, banco ou acesso de produção.
        raise SystemExit('Opção desconhecida. Use --ajuda, --demo, --configurar ou --testar-smtp.')  # Rejeita argumentos digitados por engano.
    if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'):  # Informa a configuração pendente antes do primeiro acesso.
        print('Para login real, configure SMTP: python ouvidoria.py --configurar')  # Explica por que um código não seria enviado.
        print('Para explorar com dados fictícios: python ouvidoria.py --demo')  # Oferece um modo de apresentação separado.
    if DIRECTOR and not INSTITUTIONAL.fullmatch(DIRECTOR):
        raise SystemExit('DIRECTOR_EMAIL deve ser uma única conta @camporeal.edu.br.')  # Impede configuração de diretor externo.
    if any(not INSTITUTIONAL.fullmatch(email) for email in SUPERVISORS):
        raise SystemExit('Todos os supervisores devem usar @camporeal.edu.br.')  # Valida a equipe.
    initialize()  # Prepara o banco na primeira execução.
    host, port = os.getenv('HOST', '127.0.0.1'), int(os.getenv('PORT', '8000'))  # Escuta apenas no computador local por padrão.
    print(f'Ouvidoria disponível em {APP_URL}. Use Ctrl+C para parar.')  # Não imprime segredos.
    ThreadingHTTPServer((host, port), Handler).serve_forever()  # Mantém o servidor ativo.
