'use strict';
const $ = (id) => document.getElementById(id);
const labels = {PENDING:'입금 대기',MATCHED_UNVERIFIED:'입금 정보 수신 · 관리자 검증 대기',PAID_VERIFIED:'입금 승인 · 이메일 발송 대기',SENT:'다운로드 이메일 발송 완료',EMAIL_FAILED:'이메일 발송 지연 · 재시도 또는 관리자 확인 필요',REVIEW_REQUIRED:'중복 정보 · 관리자 확인 필요',EXPIRED:'주문 만료',CANCELLED:'주문 취소',REFUNDED:'환불 완료'};
let currentOrder = null;
let configReady = false, submitting = false, currentPrice = 1900, qrObjectUrl = null;
function updatePurchaseButton() {
  const email = $('email');
  $('purchase-button').disabled = !configReady || submitting || !email.value.trim() || !email.validity.valid;
  $('purchase-button').textContent = `${currentPrice.toLocaleString()}원 입금 안내 ↗`;
  $('email-payment-hint').textContent = `이메일을 먼저 입력하면 ${currentPrice.toLocaleString()}원 입금 안내 버튼이 활성화됩니다.`;
}
$('email').addEventListener('input', updatePurchaseButton);
async function showPayment(o) {
  const panel = $('payment-panel'), pay = $('toss-pay'), qr = $('payment-qr');
  panel.hidden = false; pay.hidden = true; pay.removeAttribute('href'); qr.hidden = true; qr.removeAttribute('src');
  if (qrObjectUrl) { URL.revokeObjectURL(qrObjectUrl); qrObjectUrl = null; }
  $('payment-help').textContent = '모의 운영 중입니다. 실제 송금 링크와 QR은 실판매 설정 완료 후 표시됩니다.';
  if (o.payment_url && new URL(o.payment_url).protocol === 'supertoss:') {
    pay.href = o.payment_url; pay.textContent = `${o.amount.toLocaleString()}원 토스에서 입금하기 ↗`; pay.hidden = false;
    $('payment-help').textContent = '앱이 열리지 않으면 토스 앱에서 계좌로 직접 송금하세요. QR에 표시된 금액도 확인해 주세요.';
  }
  if (o.payment_qr_url) {
    try {
      const response = await fetch(o.payment_qr_url, {cache:'no-store', headers:{Authorization:`Bearer ${currentOrder.status_token}`}});
      if (!response.ok) throw Error('QR을 불러오지 못했습니다. 토스 링크 또는 계좌 안내를 이용하세요.');
      qrObjectUrl = URL.createObjectURL(await response.blob()); qr.src = qrObjectUrl; qr.hidden = false;
    } catch (err) { $('payment-help').textContent = err.message; }
  }
  if (o.status && !['PENDING','MATCHED_UNVERIFIED','REVIEW_REQUIRED'].includes(o.status)) panel.hidden = true;
}
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
  try {const s=await api(`/api/orders/${encodeURIComponent(currentOrder.id)}/status`,{headers:{Authorization:`Bearer ${currentOrder.status_token}`}});message(labels[s.status]||s.status);await showPayment(s);}catch(e){message(e.message);$('payment-panel').hidden=true;}
}
$('order-form').addEventListener('submit',async(e)=>{
  e.preventDefault();if (submitting || !configReady || !$('email').validity.valid || !e.target.reportValidity()) return;
  submitting=true;updatePurchaseButton();message('주문 저장 중…');
  try {const o=await api('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('email').value.trim(),depositor_name:$('depositor').value.trim(),privacy_consent:$('consent').checked})});currentOrder=o;$('order-form').hidden=true;showOrder(o);await refresh();}catch(err){message(err.message);}finally{submitting=false;updatePurchaseButton();}
});
$('lookup').onclick=()=>{currentOrder={id:$('lookup-id').value.trim(),status_token:$('lookup-token').value.trim()};refresh();};
api('/api/config').then(c=>{currentPrice=c.price;configReady=true;$('price').textContent=c.price.toLocaleString();$('version').textContent=c.version;$('release').textContent=c.version;$('supported').textContent=c.supported_keyboards;$('mode').textContent=c.mode==='mock'?'모의 운영 중입니다. 실제 송금하지 마세요.':'입금 후 관리자 확인까지 시간이 걸릴 수 있습니다.';if(!c.support_email.endsWith('@example.com')){$('support').textContent=c.support_email;$('support').href=`mailto:${c.support_email}`;}updatePurchaseButton();}).catch(()=>{configReady=false;message('서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.');updatePurchaseButton();});
updatePurchaseButton();
setInterval(()=>{if(!document.hidden)refresh();},15000);
