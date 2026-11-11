import asyncio
from contextlib import asynccontextmanager
import csv
import hmac
import io
import json
import logging
from pathlib import Path
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .mailer import Mailer
from .models import ApprovalInput, DepositInput, NoteInput, OrderInput, ParseInput, PriceInput, parse_notification
from .service import Store, digest


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.validate()
    store = Store(settings, Mailer(settings))

    async def worker():
        while True:
            try:
                await asyncio.to_thread(store.process_email_jobs)
            except Exception:
                # Avoid logging request data, tokens, or provider response bodies.
                logging.getLogger('store').error('Email worker iteration failed; inspect DB and configuration')
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker()) if settings.worker_enabled else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title='Analog Keyboard Store', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=['GET', 'POST', 'PATCH', 'OPTIONS'],
                       allow_headers=['Authorization', 'Content-Type', 'X-API-Key'], max_age=600)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Pydantic's default errors echo input; deliberately omit it (PII).
        return JSONResponse({'detail': '입력 형식과 필수 항목을 확인하세요.'}, status_code=422)

    @app.middleware('http')
    async def safety(request: Request, call_next):
        if request.method in ('POST', 'PATCH'):
            try:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 16384:
                        return JSONResponse({'detail': '요청 본문이 너무 큽니다'}, status_code=413)
                request._body = bytes(body)
            except Exception:
                return JSONResponse({'detail': '요청 본문 오류'}, status_code=400)
        if request.url.path.startswith('/api/'):
            ip = request.client.host if request.client else 'unknown'
            # Trust CF-Connecting-IP only after cloudflared strips spoofed headers and
            # loopback service is not reachable externally. Local requests may spoof it
            # but already have local machine access. No x-forwarded-for is trusted.
            if ip in ('127.0.0.1', '::1') and request.headers.get('cf-connecting-ip'):
                ip = request.headers['cf-connecting-ip'][:64]
            bucket = digest(ip)
            try:
                await asyncio.to_thread(store.rate_limit, 'api:' + bucket, 180, 60)
                if request.method == 'POST' and request.url.path == '/api/orders':
                    await asyncio.to_thread(store.rate_limit, 'order:' + bucket, settings.order_limit)
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    def admin(authorization: str = Header(default='')):
        if not hmac.compare_digest(authorization.encode(), ('Bearer ' + settings.admin_key).encode()):
            raise HTTPException(401, '관리자 인증이 필요합니다')

    def deposit_auth(x_api_key: str = Header(default='')):
        if not hmac.compare_digest(x_api_key.encode(), settings.deposit_key.encode()):
            raise HTTPException(401, '입금 수신 인증이 필요합니다')

    @app.get('/health')
    def health():
        with store.db.connect() as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ok', 'mode': 'live' if settings.live_sales else 'mock'}

    @app.get('/api/config')
    def config():
        return store.config()

    @app.post('/api/orders', status_code=201)
    def orders(data: OrderInput):
        return store.create_order(data)

    @app.get('/api/orders/{order_id}/status')
    def status(order_id: str, authorization: str = Header(default='')):
        if not authorization.startswith('Bearer ') or len(authorization) > 200:
            raise HTTPException(401, '주문 조회 토큰이 필요합니다')
        return store.order_status(order_id, authorization[7:])

    @app.post('/api/deposits', dependencies=[Depends(deposit_auth)])
    def deposits(data: DepositInput):
        row, created = store.receive_deposit(data)
        return JSONResponse(row, status_code=201 if created else 200)

    @app.post('/api/deposits/parse', dependencies=[Depends(deposit_auth)])
    def parse(data: ParseInput):
        try:
            return parse_notification(data.text)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/admin/orders', dependencies=[Depends(admin)])
    def admin_orders(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), status: str | None = None):
        return store.list_rows('orders', limit, offset, status)

    @app.get('/api/admin/deposits', dependencies=[Depends(admin)])
    def admin_deposits(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return store.list_rows('deposits', limit, offset)

    @app.get('/api/admin/email-jobs', dependencies=[Depends(admin)])
    def email_jobs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return store.list_rows('email_jobs', limit, offset)

    @app.get('/api/admin/audit', dependencies=[Depends(admin)])
    def audit(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return store.list_rows('audit_log', limit, offset)

    @app.post('/api/admin/deposits', dependencies=[Depends(admin)], status_code=201)
    def manual_deposit(data: DepositInput):
        row, created = store.receive_deposit(data)
        return JSONResponse(row, status_code=201 if created else 200)

    @app.post('/api/admin/orders/{order_id}/approve', dependencies=[Depends(admin)])
    def approve(order_id: str, data: ApprovalInput):
        return store.approve(order_id, data)

    @app.post('/api/admin/orders/{order_id}/resend', dependencies=[Depends(admin)])
    @app.post('/api/admin/orders/{order_id}/reissue', dependencies=[Depends(admin)])
    def resend(order_id: str, data: NoteInput):
        return store.resend(order_id, data.note)

    @app.post('/api/admin/orders/{order_id}/cancel', dependencies=[Depends(admin)])
    def cancel(order_id: str, data: NoteInput):
        return store.close_order(order_id, 'CANCELLED', data.note)

    @app.post('/api/admin/orders/{order_id}/refund', dependencies=[Depends(admin)])
    def refund(order_id: str, data: NoteInput):
        return store.close_order(order_id, 'REFUNDED', data.note)

    @app.patch('/api/admin/settings', dependencies=[Depends(admin)])
    def price(data: PriceInput):
        return store.set_price(data.price)

    @app.post('/api/admin/email-jobs/process', dependencies=[Depends(admin)])
    def process_jobs():
        return {'sent': store.process_email_jobs()}

    @app.get('/api/admin/export.csv', dependencies=[Depends(admin)])
    def export():
        # Stream a consistent snapshot, with formula injection neutralized.
        with store.db.connect() as db:
            rows = db.execute('SELECT id,email,depositor_name,amount,status,created_at,paid_at,sent_at FROM orders ORDER BY created_at').fetchall()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['id','email','depositor_name','amount','status','created_at','paid_at','sent_at'])
        for row in rows:
            writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in row])
        return Response('\ufeff' + out.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="orders.csv"'})

    @app.get('/api/admin/mock-mail', dependencies=[Depends(admin)])
    def mock_mail():
        if settings.mail_mode != 'mock':
            raise HTTPException(404)
        files = sorted(settings.outbox_dir.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        return {'items': [{'id': p.stem, **json.loads(p.read_text())} for p in files]}

    @app.get('/api/download/{token}')
    def download(token: str):
        if len(token) > 100:
            raise HTTPException(404)
        path = store.download(token)
        return FileResponse(path, filename=path.name, media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})

    @app.get('/admin')
    def admin_page():
        return FileResponse(ROOT / 'web/admin.html')

    @app.get('/')
    def storefront():
        return FileResponse(ROOT / 'web/index.html')

    (ROOT / 'web').mkdir(exist_ok=True)
    app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')
    app.mount('/demo', StaticFiles(directory=ROOT / 'dist', html=True, check_dir=False), name='demo')
    return app
