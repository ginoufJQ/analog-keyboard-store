'use strict';
let step=-1;
const states=[
 {code:'PENDING',title:'가상 주문이 생성되었습니다.',description:'예시 주문번호 DEMO-0001. 실제 이메일이나 이름을 입력하지 않고 주문 생성 단계를 표현했습니다.',button:'모의 입금 정보 수신 ↗'},
 {code:'MATCHED_UNVERIFIED',title:'정보는 일치해도, 아직 미검증.',description:'이름과 금액이 일치하는 알림을 받았습니다. 알림만으로 실제 입금을 확정하지 않으며, 관리자 확인을 기다립니다.',button:'가상 관리자 승인 ↗'},
 {code:'PAID_VERIFIED',title:'확인 후에 다음 단계로.',description:'실제 운영에서는 관리자가 은행 거래내역과 중복 사용 여부를 확인합니다. 이 데모에서는 가상 승인만 진행합니다.',button:'가상 이메일 전달 ↗'},
 {code:'SENT',title:'전달까지, 하나의 흐름으로.',description:'실제 운영에서는 만료되는 전용 다운로드 링크를 이메일로 보냅니다. 이 페이지는 이메일이나 파일을 전송하지 않습니다.',button:'다시 체험하기 ↗'}
];
const $=id=>document.getElementById(id);
function render(){const s=states[step];$('demo-state').textContent=s?s.code:'READY';$('demo-title').textContent=s?s.title:'흐름을 시작해 보세요.';$('demo-description').textContent=s?s.description:'실제 정보를 입력할 필요 없이 가상의 주문부터 이메일 전달까지 살펴볼 수 있습니다.';$('demo-next').textContent=s?s.button:'가상 주문 생성 ↗';document.querySelectorAll('[data-step]').forEach((e,i)=>e.classList.toggle('active',i===(step<0?0:step)));}
$('demo-next').onclick=()=>{step=step===3?-1:step+1;render();};$('demo-reset').onclick=()=>{step=-1;render();};
