'use strict';
const $ = (id) => document.getElementById(id);
const labels = {PENDING:'입금 대기',MATCHED_UNVERIFIED:'입금 정보 수신 · 관리자 검증 대기',PAID_VERIFIED:'입금 승인 · 이메일 발송 대기',SENT:'다운로드 이메일 발송 완료',EMAIL_FAILED:'이메일 발송 지연 · 재시도 또는 관리자 확인 필요',REVIEW_REQUIRED:'중복 정보 · 관리자 확인 필요',EXPIRED:'주문 만료',CANCELLED:'주문 취소',REFUNDED:'환불 완료'};
let currentOrder = null;
async function api(path, options={}) {
  const response = await fetch(path, {cache:'no-store', ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다.');
  return data;
}
function text(tag, value) { const el=document.createElement(tag); el.textContent=value; return el; }
function message(value) { $('message').textContent=value; }
function showOrder(o) {
  const result=$('order-result'); result.replaceChildren(); result.hidden=false;
  result.append(text('strong','주문이 저장되었습니다.'),text('p','주문번호'),text('code',o.id),text('p','비밀 조회 토큰 (분실 시 자동 복구할 수 없습니다)'),text('code',o.status_token),text('p',`입금 금액: ${o.amount.toLocaleString()}원`),text('p',`입금 안내: ${o.bank_account}`),text('p',`예금주: ${o.bank_holder}`),text('p',`주문 만료: ${new Date(o.expires_at*1000).toLocaleString('ko-KR')}`));
  const save=text('button','주문 조회 정보 저장'); save.type='button'; save.className='button secondary';
  save.onclick=()=>{const content=JSON.stringify({id:o.id,status_token:o.status_token},null,2);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type:'application/json'}));a.download=`analog-order-${o.id.slice(0,8)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
  result.append(save); $('lookup-id').value=o.id; $('lookup-token').value=o.status_token;
}
async function refresh() {
  if (!currentOrder) return;
  try {const s=await api(`/api/orders/${encodeURIComponent(currentOrder.id)}/status`,{headers:{Authorization:`Bearer ${currentOrder.status_token}`}});message(labels[s.status]||s.status);}catch(e){message(e.message);}
}
$('order-form').addEventListener('submit',async(e)=>{
  e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;message('주문 저장 중…');
  try {const o=await api('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('email').value.trim(),depositor_name:$('depositor').value.trim(),privacy_consent:$('consent').checked})});currentOrder=o;$('order-form').hidden=true;showOrder(o);await refresh();}catch(err){message(err.message);}finally{button.disabled=false;}
});
$('lookup').onclick=()=>{currentOrder={id:$('lookup-id').value.trim(),status_token:$('lookup-token').value.trim()};refresh();};
api('/api/config').then(c=>{$('price').textContent=c.price.toLocaleString();$('version').textContent=c.version;$('release').textContent=c.version;$('supported').textContent=c.supported_keyboards;$('mode').textContent=c.mode==='mock'?'모의 운영 중입니다. 실제 송금하지 마세요.':'입금 후 관리자 확인까지 시간이 걸릴 수 있습니다.';if(!c.support_email.endsWith('@example.com')){$('support').textContent=c.support_email;$('support').href=`mailto:${c.support_email}`;}}).catch(()=>{message('서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.');$('order-form').querySelector('button').disabled=true;});
setInterval(()=>{if(!document.hidden)refresh();},15000);
