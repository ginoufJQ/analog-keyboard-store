'use strict';
const $=id=>document.getElementById(id);
let key='',offset=0,total=0,depOffset=0,depTotal=0;
const pageSize=50;
function el(tag,value,cls){const e=document.createElement(tag);if(value!==undefined)e.textContent=value;if(cls)e.className=cls;return e;}
function msg(t){$('admin-message').textContent=t;}
async function api(path,options={}){const r=await fetch(path,{cache:'no-store',...options,headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json',...options.headers}});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'요청 실패');return d;}
function post(path,body){return api(path,{method:'POST',body:JSON.stringify(body)});}
function date(t){return t?new Date(t*1000).toLocaleString('ko-KR'):'—';}
function cells(row,values){for(const value of values)row.append(el('td',value));}
async function action(id,kind){const label={resend:'기존 링크를 폐기하고 새 다운로드 메일을 발송',cancel:'주문 취소',refund:'실제 환불 완료 기록'}[kind];const note=prompt(`${label}\n사유를 3자 이상 입력하세요. 환불 송금은 이 시스템이 실행하지 않습니다.`);if(!note||note.trim().length<3)return;try{await post(`/api/admin/orders/${id}/${kind}`,{note:note.trim()});msg('처리했습니다.');await refresh();}catch(e){msg(e.message);}}
function button(text,fn,danger=false){const b=el('button',text,'small-button'+(danger?' danger':''));b.type='button';b.onclick=fn;return b;}
async function refresh(){
 const filter=$('status-filter').value;
 const [os,ds,jobs,config,pending,matched,failed]=await Promise.all([
  api(`/api/admin/orders?limit=${pageSize}&offset=${offset}&status=${encodeURIComponent(filter)}`),api(`/api/admin/deposits?limit=${pageSize}&offset=${depOffset}`),api('/api/admin/email-jobs?limit=100'),api('/api/config'),api('/api/admin/orders?limit=1&status=PENDING'),api('/api/admin/orders?limit=1&status=MATCHED_UNVERIFIED'),api('/api/admin/orders?limit=1&status=EMAIL_FAILED')]);
 total=os.total;depTotal=ds.total;$('orders').replaceChildren();$('deposits').replaceChildren();$('email-jobs').replaceChildren();
 $('stat-pending').textContent=pending.total;$('stat-matched').textContent=matched.total;$('stat-failed').textContent=failed.total;
 $('stat-total').textContent=filter?(await api('/api/admin/orders?limit=1')).total:total;
 $('admin-mode').textContent=config.mode==='mock'?'MOCK · 실제 송금 금지':'LIVE · 은행 확인 필수';$('price-input').value=config.price;
 for(const o of os.items){const row=el('tr');cells(row,[o.id,o.email,`${o.depositor_name} / ${o.amount.toLocaleString()}원`,o.status,date(o.created_at)]);const td=el('td');if(['PENDING','MATCHED_UNVERIFIED','REVIEW_REQUIRED'].includes(o.status))td.append(button('승인 선택',()=>{$('approve-order').value=o.id;const d=ds.items.find(x=>x.matched_order_id===o.id);$('approve-deposit').value=d?d.id:'';$('approve-form').scrollIntoView({behavior:'smooth',block:'center'});}));if(['PENDING','MATCHED_UNVERIFIED','REVIEW_REQUIRED','EXPIRED'].includes(o.status))td.append(button('취소',()=>action(o.id,'cancel'),true));if(o.paid_at&&!['REFUNDED','CANCELLED'].includes(o.status)){td.append(button('메일·링크 재발급',()=>action(o.id,'resend')),button('환불 기록',()=>action(o.id,'refund'),true));}row.append(td);$('orders').append(row);}
 for(const d of ds.items){const row=el('tr');cells(row,[d.id,`${d.depositor_name} / ${d.amount.toLocaleString()}원`,date(d.received_at),d.source,d.verification_status,d.matched_order_id||'—']);const td=el('td');td.append(button('입금 선택',()=>{$('approve-deposit').value=d.id;}));row.append(td);$('deposits').append(row);}
 for(const j of jobs.items){const row=el('tr');cells(row,[j.id,j.order_id,j.status,j.attempts,j.last_error||'—']);$('email-jobs').append(row);}
 $('page-info').textContent=`${total?offset+1:0}–${Math.min(offset+pageSize,total)} / ${total}`;$('prev').disabled=offset===0;$('next').disabled=offset+pageSize>=total;
 $('dep-page-info').textContent=`${depTotal?depOffset+1:0}–${Math.min(depOffset+pageSize,depTotal)} / ${depTotal}`;$('dep-prev').disabled=depOffset===0;$('dep-next').disabled=depOffset+pageSize>=depTotal;
 $('mock-mail-section').hidden=config.mode!=='mock';if(config.mode==='mock'){const mail=await api('/api/admin/mock-mail');$('mock-mail').replaceChildren();for(const m of mail.items){const box=el('details');box.append(el('summary',`${m.to.join(', ')} — ${m.subject}`),el('pre',m.text,'mail-preview'));const found=m.text.match(/https?:\/\/\S+\/api\/download\/[A-Za-z0-9_-]+/);if(found){const url=new URL(found[0]);if(url.origin===location.origin){const a=el('a','테스트 다운로드','button secondary');a.href=url.href;box.append(a);}}$('mock-mail').append(box);}}
}
async function safeRefresh(){try{await refresh();}catch(e){msg(e.message);}}
$('login-form').onsubmit=async e=>{e.preventDefault();key=$('admin-key').value;try{await refresh();$('admin-key').value='';$('login-panel').hidden=true;$('dashboard').hidden=false;msg('인증되었습니다.');}catch(err){key='';msg(err.message);}};
$('logout').onclick=()=>{key='';location.reload();};$('refresh').onclick=safeRefresh;
$('status-filter').onchange=()=>{offset=0;safeRefresh();};$('prev').onclick=()=>{offset=Math.max(0,offset-pageSize);safeRefresh();};$('next').onclick=()=>{offset+=pageSize;safeRefresh();};$('dep-prev').onclick=()=>{depOffset=Math.max(0,depOffset-pageSize);safeRefresh();};$('dep-next').onclick=()=>{depOffset+=pageSize;safeRefresh();};
$('deposit-form').onsubmit=async e=>{e.preventDefault();try{const d=await post('/api/admin/deposits',{depositor_name:$('dep-name').value,amount:Number($('dep-amount').value),received_at:new Date($('dep-time').value).toISOString(),source:'manual',raw_notification:$('dep-raw').value});$('approve-deposit').value=d.id;msg(`미검증 입금 저장: ${d.id}`);await refresh();}catch(err){msg(err.message);}};
$('approve-form').onsubmit=async e=>{e.preventDefault();try{await post(`/api/admin/orders/${encodeURIComponent($('approve-order').value.trim())}/approve`,{deposit_id:$('approve-deposit').value.trim(),bank_checked:$('bank-checked').checked,note:$('approve-note').value});$('bank-checked').checked=false;msg('승인 완료. 이메일 큐에 등록되었습니다.');await refresh();}catch(err){msg(err.message);}};
$('process').onclick=async()=>{try{const r=await post('/api/admin/email-jobs/process',{});msg(`이번에 발송 처리한 이메일: ${r.sent}개`);await refresh();}catch(e){msg(e.message);}};
$('price-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/admin/settings',{method:'PATCH',body:JSON.stringify({price:Number($('price-input').value)})});msg('새 주문 금액을 변경했습니다.');await refresh();}catch(err){msg(err.message);}};
$('export').onclick=async()=>{try{const r=await fetch('/api/admin/export.csv',{headers:{Authorization:`Bearer ${key}`}});if(!r.ok)throw Error('CSV 내보내기 실패');const a=el('a');a.href=URL.createObjectURL(await r.blob());a.download='analog-orders.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}catch(e){msg(e.message);}};
const local=new Date(Date.now()-new Date().getTimezoneOffset()*60000);$('dep-time').value=local.toISOString().slice(0,19);
